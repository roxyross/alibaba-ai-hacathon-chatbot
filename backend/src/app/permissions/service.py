"""Target-Scoped Permission Engine Service for ROXY-AI 2.0.

Evaluates permissions and policy grants across:
- Application scopes (target_app)
- Capability scopes (capability)
- Resource scopes (resource)
- Device scopes (device_id)
- Parameter constraints (parameter_constraints)
- Expiration (TTL / allow_for_duration)
- Single-use consumption (allow_once)
- Revocation tracking (revoked_at)
- Human-readable UX details (PermissionUXDetails)

Persists grants in PostgreSQL with resilient in-memory fallback.
"""

from __future__ import annotations

import fnmatch
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from app.db import get_session_factory
from app.models.agent_runtime import PermissionGrant
from app.permissions.schemas import (
    PermissionCheckResult,
    PermissionGrantCreate,
    PermissionGrantResponse,
    PermissionPolicy,
    PermissionUXDetails,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel

log = structlog.get_logger()

# In-memory store keyed by grant_id: dict[str, dict[str, Any]]
_MEM_GRANTS_BY_ID: dict[str, dict[str, Any]] = {}
# Legacy secondary mapping (user_id, tool_id, permission) -> grant_id
_MEM_GRANTS_LOOKUP: dict[tuple[str, str, str], str] = {}


def clear_in_memory_grants() -> None:
    """Clear in-memory permission grants (for test isolation)."""
    _MEM_GRANTS_BY_ID.clear()
    _MEM_GRANTS_LOOKUP.clear()


def _evaluate_parameter_constraints(
    constraints: dict[str, Any], parameters: dict[str, Any]
) -> tuple[bool, str]:
    """Check if parameters conform to constraints defined on the grant."""
    if not constraints:
        return True, ""
    if not isinstance(constraints, dict):
        return False, "Malformed parameter constraints specification."

    for key, expected in constraints.items():
        actual = parameters.get(key)
        if actual is None:
            if expected is not None:
                return False, f"Missing required parameter '{key}' for constraint evaluation."
            continue

        if isinstance(expected, dict):
            for op, val in expected.items():
                if op == "eq" and actual != val:
                    return False, f"Parameter '{key}' ({actual}) != expected ({val})"
                elif op == "neq" and actual == val:
                    return False, f"Parameter '{key}' ({actual}) == forbidden ({val})"
                elif op == "lte":
                    try:
                        if not (float(actual) <= float(val)):
                            return False, f"Parameter '{key}' ({actual}) exceeds maximum ({val})"
                    except (ValueError, TypeError):
                        return False, f"Parameter '{key}' cannot be numerically compared to {val}"
                elif op == "gte":
                    try:
                        if not (float(actual) >= float(val)):
                            return False, f"Parameter '{key}' ({actual}) below minimum ({val})"
                    except (ValueError, TypeError):
                        return False, f"Parameter '{key}' cannot be numerically compared to {val}"
                elif op == "lt":
                    try:
                        if not (float(actual) < float(val)):
                            return False, f"Parameter '{key}' ({actual}) not less than ({val})"
                    except (ValueError, TypeError):
                        return False, f"Parameter '{key}' cannot be numerically compared to {val}"
                elif op == "gt":
                    try:
                        if not (float(actual) > float(val)):
                            return False, f"Parameter '{key}' ({actual}) not greater than ({val})"
                    except (ValueError, TypeError):
                        return False, f"Parameter '{key}' cannot be numerically compared to {val}"
                elif op == "in":
                    if isinstance(val, (list, tuple, set)) and actual not in val:
                        return False, f"Parameter '{key}' ({actual}) not in allowed set {val}"
                elif op == "not_in":
                    if isinstance(val, (list, tuple, set)) and actual in val:
                        return False, f"Parameter '{key}' ({actual}) in restricted set {val}"
                elif op == "prefix" and not str(actual).startswith(str(val)):
                    return False, f"Parameter '{key}' ({actual}) does not start with prefix '{val}'"
                elif op == "regex" and not re.search(str(val), str(actual)):
                    return False, f"Parameter '{key}' does not match pattern '{val}'"
        elif isinstance(expected, list):
            if actual not in expected:
                return False, f"Parameter '{key}' ({actual}) not in allowed list {expected}"
        else:
            if actual != expected:
                return False, f"Parameter '{key}' ({actual}) != expected ({expected})"

    return True, ""


def _match_resource_pattern(pattern: str | None, resource: str | None) -> bool:
    """Match resource against a grant pattern (exact, prefix, or wildcard)."""
    if not pattern:
        return True
    if not resource:
        return False
    if pattern == "*" or pattern == resource:
        return True
    if fnmatch.fnmatch(resource, pattern):
        return True
    if pattern.endswith("/*") and resource.startswith(pattern[:-2]):
        return True
    return bool(resource.startswith(pattern))


class PermissionService:
    """Target-scoped evaluation and policy management engine."""

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()

    async def _fetch_user_grants(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch all grants for user from DB or in-memory fallback."""
        factory = get_session_factory()
        db_grants: list[dict[str, Any]] = []
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(PermissionGrant).where(PermissionGrant.user_id == user_id)
                    res = await session.execute(stmt)
                    rows = res.scalars().all()
                    db_grants = [r.to_dict() for r in rows]
            except Exception as exc:
                log.warning("permission_service.db_fetch_failed", error=str(exc))

        # Merge with in-memory store
        mem_grants = [
            g for g in _MEM_GRANTS_BY_ID.values()
            if g.get("user_id") == user_id
        ]

        if db_grants:
            # Index by id so in-memory overrides take precedence if recently updated
            merged: dict[str, dict[str, Any]] = {g["id"]: g for g in db_grants}
            for mg in mem_grants:
                merged[mg["id"]] = mg
            res_list = list(merged.values())
        else:
            res_list = mem_grants

        res_list.sort(key=lambda x: str(x.get("updated_at") or x.get("granted_at") or ""), reverse=True)
        return res_list

    async def _mark_grant_consumed(self, user_id: str, grant_id: str) -> None:
        """Mark a single-use grant as consumed / revoked."""
        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(PermissionGrant).where(
                        PermissionGrant.id == grant_id,
                        PermissionGrant.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    grant = res.scalars().first()
                    if grant:
                        grant.revoked_at = now
                        grant.policy = PermissionPolicy.REVOKED.value
                        grant.updated_at = now
                        await session.commit()
            except Exception as exc:
                log.warning("permission_service.consume_grant_db_failed", error=str(exc))

        if grant_id in _MEM_GRANTS_BY_ID:
            _MEM_GRANTS_BY_ID[grant_id]["revoked_at"] = now.isoformat()
            _MEM_GRANTS_BY_ID[grant_id]["policy"] = PermissionPolicy.REVOKED.value
            _MEM_GRANTS_BY_ID[grant_id]["updated_at"] = now.isoformat()

    def _build_ux_details(
        self,
        tool: Any | None,
        target_app: str | None,
        capability: str | None,
        resource: str | None,
        device_id: str | None,
        parameters: dict[str, Any],
        risk_level: str | None,
        policy: str,
        expires_at: str | None = None,
    ) -> PermissionUXDetails:
        """Construct human-readable UX details for user confirmation."""
        # 1. Human-friendly App name
        app_name = "System"
        if target_app:
            app_name = target_app.replace("_", " ").title()
        elif tool and getattr(tool, "category", None):
            app_name = tool.category.replace("_", " ").title()
        elif tool and getattr(tool, "capabilities", None):
            app_name = tool.capabilities[0].replace("_", " ").title()
        elif tool:
            app_name = tool.name

        # 2. Human-friendly capability
        cap_name = "Execute Action"
        if capability:
            cap_name = capability.replace(":", " ").replace("_", " ").title()
        elif tool and tool.permissions:
            cap_name = tool.permissions[0].replace(":", " ").replace("_", " ").title()
        elif tool:
            cap_name = tool.name

        # 3. Target resource / recipient / path
        target = resource
        if not target and parameters:
            for k in ("to", "recipient", "url", "path", "file", "channel", "query", "command", "app_name"):
                if parameters.get(k):
                    target = str(parameters[k])
                    break
        if not target:
            target = device_id or "System Environment"

        # 4. Action summary
        action = f"Run {cap_name} on {app_name} ({target})"

        # 5. Data involved summary (sanitized, readable)
        data_parts: list[str] = []
        if parameters:
            for k, v in list(parameters.items())[:5]:
                # Mask potential secret keys
                if any(sec in k.lower() for sec in ("key", "token", "password", "secret", "auth")):
                    val_str = "***"
                else:
                    val_str = str(v)
                    if len(val_str) > 60:
                        val_str = val_str[:57] + "..."
                data_parts.append(f"{k}: {val_str}")
        data_summary = ", ".join(data_parts) if data_parts else "No additional payload"

        # 6. Risk string
        final_risk = risk_level or (tool.risk_level.value if tool else "medium")

        # 7. Duration string
        duration = "Until revoked"
        if policy == PermissionPolicy.ALLOW_ONCE.value:
            duration = "Single execution"
        elif expires_at:
            duration = f"Valid until {expires_at}"
        elif policy == PermissionPolicy.ALWAYS_ASK.value:
            duration = "Ask every time"

        # 8. Device string
        device = device_id or "Local Device"

        return PermissionUXDetails(
            application=app_name,
            capability=cap_name,
            target=target,
            action=action,
            data_involved=data_summary,
            risk=final_risk,
            duration=duration,
            device=device,
        )

    async def check_permission(
        self,
        user_id: str,
        tool_id: str | None = None,
        permission: str | None = None,
        target_app: str | None = None,
        capability: str | None = None,
        resource: str | None = None,
        device_id: str | None = None,
        scope: str = "global",
        parameters: dict[str, Any] | None = None,
    ) -> PermissionCheckResult:
        """Evaluate if user has permission to execute tool/action, or if user confirmation is required.

        Follows specific-to-general resolution hierarchy:
        1. Exact match (app + resource + capability + device)
        2. Resource match (app + resource)
        3. Capability match (app + capability)
        4. Device match (device + tool/app)
        5. Tool match (tool_id + permission)
        6. App match (app)
        7. Global default fallback
        """
        params = parameters or {}
        tool = self._tool_registry.get(tool_id) if tool_id else None
        if not tool and capability:
            tool = (
                self._tool_registry.get(capability)
                or self._tool_registry.get(f"browser_{capability}")
                or (self._tool_registry.get(f"{target_app}_{capability}") if target_app else None)
            )

        # If tool_id was specified but is not registered, and no app/capability given
        if tool_id and not tool and not target_app and not capability:
            return PermissionCheckResult(
                granted=False,
                policy=PermissionPolicy.NEVER_ALLOW.value,
                requires_confirmation=False,
                reason=f"Tool '{tool_id}' is not registered in the system.",
                ux_details=self._build_ux_details(
                    tool=None,
                    target_app=target_app,
                    capability=capability,
                    resource=resource,
                    device_id=device_id,
                    parameters=params,
                    risk_level="high",
                    policy=PermissionPolicy.NEVER_ALLOW.value,
                ),
            )

        target_perm = permission or (tool.permissions[0] if (tool and tool.permissions) else "execute")
        tool_cat = getattr(tool, "category", None) or (tool.capabilities[0] if (tool and getattr(tool, "capabilities", None)) else None)
        resolved_app = target_app or tool_cat
        resolved_cap = capability or target_perm

        # Fetch candidate grants for user
        all_grants = await self._fetch_user_grants(user_id)
        now = datetime.now(UTC)

        # Filter out revoked or expired grants
        active_grants: list[dict[str, Any]] = []
        for g in all_grants:
            if g.get("revoked_at") is not None or g.get("policy") == PermissionPolicy.REVOKED.value:
                continue
            exp_str = g.get("expires_at")
            if exp_str:
                try:
                    exp_dt = datetime.fromisoformat(exp_str)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=UTC)
                    if now > exp_dt:
                        continue  # Expired
                except Exception:
                    pass
            active_grants.append(g)

        # ---------------------------------------------------------------------
        # Resolution Hierarchy: Specific to General
        # ---------------------------------------------------------------------
        matched_grant: dict[str, Any] | None = None
        match_tier: str | None = None

        # Tier 1: Exact match (app, resource, capability, device)
        if resolved_app and resource and resolved_cap and device_id:
            for g in active_grants:
                if (
                    str(g.get("target_app") or "").lower() == str(resolved_app or "").lower()
                    and _match_resource_pattern(g.get("resource"), resource)
                    and g.get("capability") == resolved_cap
                    and g.get("device_id") == device_id
                ):
                    matched_grant = g
                    match_tier = "exact"
                    break

        # Tier 2: Resource match (app, resource)
        if not matched_grant and resolved_app and resource:
            for g in active_grants:
                if (
                    str(g.get("target_app") or "").lower() == str(resolved_app or "").lower()
                    and _match_resource_pattern(g.get("resource"), resource)
                ):
                    matched_grant = g
                    match_tier = "resource"
                    break

        # Tier 3: Capability match (app, capability)
        if not matched_grant and resolved_app and resolved_cap:
            for g in active_grants:
                if (
                    str(g.get("target_app") or "").lower() == str(resolved_app or "").lower()
                    and g.get("capability") in (resolved_cap, "*")
                    and not g.get("resource")
                    and not g.get("device_id")
                ):
                    matched_grant = g
                    match_tier = "capability"
                    break

        # Tier 4: Device match (device_id + matching tool or app)
        if not matched_grant and device_id:
            for g in active_grants:
                if (
                    g.get("device_id") == device_id
                    and (
                        (tool_id and g.get("tool_id") == tool_id)
                        or (resolved_app and str(g.get("target_app") or "").lower() == str(resolved_app or "").lower())
                        or (not g.get("tool_id") and not g.get("target_app"))
                    )
                    and not g.get("resource")
                    and not g.get("capability")
                ):
                    matched_grant = g
                    match_tier = "device"
                    break

        # Tier 5: Tool match (tool_id + permission)
        if not matched_grant and tool_id:
            for g in active_grants:
                if (
                    g.get("tool_id") == tool_id
                    and g.get("permission", "execute") in (target_perm, "*", None)
                    and not g.get("resource")
                    and not g.get("device_id")
                ):
                    matched_grant = g
                    match_tier = "tool"
                    break

        # Tier 6: App match (app only)
        if not matched_grant and resolved_app:
            for g in active_grants:
                if (
                    str(g.get("target_app") or "").lower() == str(resolved_app or "").lower()
                    and not g.get("resource")
                    and not g.get("capability")
                    and not g.get("device_id")
                    and not g.get("tool_id")
                ):
                    matched_grant = g
                    match_tier = "app"
                    break

        # ---------------------------------------------------------------------
        # Evaluation of Matched Grant
        # ---------------------------------------------------------------------
        if matched_grant:
            policy = matched_grant.get("policy", PermissionPolicy.ALWAYS_ASK.value)
            grant_id = matched_grant.get("id")

            # Check parameter constraints
            raw_constraints = matched_grant.get("parameter_constraints")
            constraints: dict[str, Any] = {}
            if isinstance(raw_constraints, str):
                try:
                    parsed = json.loads(raw_constraints)
                    if isinstance(parsed, dict):
                        constraints = parsed
                except Exception:
                    constraints = {}
            elif isinstance(raw_constraints, dict):
                constraints = raw_constraints

            params_valid, constraint_err = _evaluate_parameter_constraints(constraints, params)
            if not params_valid:
                # If constraints fail, authorization fails -> fallback to confirmation
                ux = self._build_ux_details(
                    tool=tool,
                    target_app=resolved_app,
                    capability=resolved_cap,
                    resource=resource,
                    device_id=device_id,
                    parameters=params,
                    risk_level=matched_grant.get("risk_level"),
                    policy=PermissionPolicy.ALWAYS_ASK.value,
                    expires_at=matched_grant.get("expires_at"),
                )
                return PermissionCheckResult(
                    granted=False,
                    policy=PermissionPolicy.ALWAYS_ASK.value,
                    requires_confirmation=True,
                    reason=f"Action requires confirmation: {constraint_err}",
                    grant_id=grant_id,
                    ux_details=ux,
                    matched_scope=match_tier,
                )

            ux = self._build_ux_details(
                tool=tool,
                target_app=resolved_app,
                capability=resolved_cap,
                resource=resource,
                device_id=device_id,
                parameters=params,
                risk_level=matched_grant.get("risk_level"),
                policy=policy,
                expires_at=matched_grant.get("expires_at"),
            )

            # Never allow policy
            if policy == PermissionPolicy.NEVER_ALLOW.value:
                return PermissionCheckResult(
                    granted=False,
                    policy=policy,
                    requires_confirmation=False,
                    reason=f"Execution blocked: User policy for target '{resolved_app or tool_id}' is '{policy}'.",
                    grant_id=grant_id,
                    ux_details=ux,
                    matched_scope=match_tier,
                )

            # Single-use consumption
            if policy == PermissionPolicy.ALLOW_ONCE.value:
                if grant_id:
                    await self._mark_grant_consumed(user_id=user_id, grant_id=grant_id)
                return PermissionCheckResult(
                    granted=True,
                    policy=policy,
                    requires_confirmation=False,
                    reason=f"Single-use permission consumed successfully for '{resolved_app or tool_id}'.",
                    grant_id=grant_id,
                    ux_details=ux,
                    matched_scope=match_tier,
                )

            # Automatic allow policies
            if policy in (
                PermissionPolicy.ALLOW_AUTOMATICALLY.value,
                PermissionPolicy.ALLOW_FOR_APP.value,
                PermissionPolicy.ALLOW_FOR_DEVICE.value,
                PermissionPolicy.ALLOW_FOR_RESOURCE.value,
                PermissionPolicy.ALLOW_FOR_DURATION.value,
            ):
                return PermissionCheckResult(
                    granted=True,
                    policy=policy,
                    requires_confirmation=False,
                    reason=f"Permission granted automatically per '{policy}' policy for '{resolved_app or tool_id}'.",
                    grant_id=grant_id,
                    ux_details=ux,
                    matched_scope=match_tier,
                )

            # Ask once (pre-authorized on subsequent checks)
            if policy == PermissionPolicy.ASK_ONCE.value:
                return PermissionCheckResult(
                    granted=True,
                    policy=policy,
                    requires_confirmation=False,
                    reason=f"Permission pre-authorized under '{policy}' policy for '{resolved_app or tool_id}'.",
                    grant_id=grant_id,
                    ux_details=ux,
                    matched_scope=match_tier,
                )

            # Always ask
            if policy == PermissionPolicy.ALWAYS_ASK.value:
                return PermissionCheckResult(
                    granted=False,
                    policy=policy,
                    requires_confirmation=True,
                    reason=f"Action requires explicit user confirmation per '{policy}' policy.",
                    grant_id=grant_id,
                    ux_details=ux,
                    matched_scope=match_tier,
                )

        # ---------------------------------------------------------------------
        # Fallback Default Policy
        # ---------------------------------------------------------------------
        if tool:
            risk = tool.risk_level.value
            is_low_risk_auto = bool(not tool.requires_confirmation and tool.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM))
        else:
            from app.device.capability_engine import assess_action_risk
            rl = assess_action_risk(resolved_cap or "", "")
            risk = rl.value
            is_low_risk_auto = False

        ux = self._build_ux_details(
            tool=tool,
            target_app=resolved_app,
            capability=resolved_cap,
            resource=resource,
            device_id=device_id,
            parameters=params,
            risk_level=risk,
            policy=PermissionPolicy.ALLOW_AUTOMATICALLY.value if is_low_risk_auto else PermissionPolicy.ALWAYS_ASK.value,
        )

        if is_low_risk_auto:
            name = tool.name if tool else (resolved_app or resolved_cap or "Action")
            return PermissionCheckResult(
                granted=True,
                policy=PermissionPolicy.ALLOW_AUTOMATICALLY.value,
                requires_confirmation=False,
                reason=f"Action '{name}' has risk level '{risk}' and does not require explicit confirmation.",
                ux_details=ux,
                matched_scope="default",
            )

        name = tool.name if tool else (resolved_app or resolved_cap or "Action")
        return PermissionCheckResult(
            granted=False,
            policy=PermissionPolicy.ALWAYS_ASK.value,
            requires_confirmation=True,
            reason=f"Action on '{name}' has risk level '{risk}' and requires confirmation before execution.",
            ux_details=ux,
            matched_scope="default",
        )

    async def grant_permission(
        self,
        user_id: str,
        grant_in: PermissionGrantCreate,
    ) -> PermissionGrantResponse:
        """Create or update a target-scoped user permission grant."""
        now = datetime.now(UTC)
        # Look for existing grant in memory to update
        existing_mem_id: str | None = None
        for gid, g in _MEM_GRANTS_BY_ID.items():
            if g.get("user_id") == user_id and (
                (
                    grant_in.tool_id
                    and g.get("tool_id") == grant_in.tool_id
                    and (g.get("permission") or "execute") == (grant_in.permission or "execute")
                )
                or (
                    grant_in.target_app
                    and g.get("target_app") == grant_in.target_app
                    and g.get("capability") == grant_in.capability
                    and g.get("resource") == grant_in.resource
                )
            ):
                existing_mem_id = gid
                break

        grant_id = existing_mem_id or str(uuid.uuid4())

        expires_at = grant_in.expires_at
        if expires_at is None and grant_in.duration_seconds is not None:
            expires_at = now + timedelta(seconds=grant_in.duration_seconds)

        record_dict: dict[str, Any] = {
            "id": grant_id,
            "user_id": user_id,
            "tool_id": grant_in.tool_id,
            "permission": grant_in.permission,
            "policy": grant_in.policy.value,
            "scope": grant_in.scope,
            "device_id": grant_in.device_id,
            "target_app": grant_in.target_app,
            "capability": grant_in.capability,
            "resource": grant_in.resource,
            "parameter_constraints": grant_in.parameter_constraints,
            "risk_level": grant_in.risk_level,
            "grant_source": grant_in.grant_source,
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
            "revoked_at": None,
            "granted_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "is_active": True,
        }

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    # Check existing match for update
                    conditions = [
                        PermissionGrant.user_id == user_id,
                    ]
                    if grant_in.tool_id:
                        conditions.append(PermissionGrant.tool_id == grant_in.tool_id)
                        conditions.append(PermissionGrant.permission == grant_in.permission)
                    if grant_in.target_app:
                        conditions.append(PermissionGrant.target_app == grant_in.target_app)
                    if grant_in.device_id:
                        conditions.append(PermissionGrant.device_id == grant_in.device_id)

                    stmt = select(PermissionGrant).where(*conditions)
                    res = await session.execute(stmt)
                    existing = res.scalars().first()

                    if existing:
                        existing.policy = grant_in.policy.value
                        existing.scope = grant_in.scope
                        existing.device_id = grant_in.device_id
                        existing.target_app = grant_in.target_app
                        existing.capability = grant_in.capability
                        existing.resource = grant_in.resource
                        existing.set_parameter_constraints(grant_in.parameter_constraints)
                        existing.risk_level = grant_in.risk_level
                        existing.grant_source = grant_in.grant_source
                        existing.expires_at = expires_at
                        existing.revoked_at = None
                        existing.updated_at = now
                        await session.commit()
                        record_dict = existing.to_dict()
                    else:
                        new_grant = PermissionGrant(
                            id=grant_id,
                            user_id=user_id,
                            tool_id=grant_in.tool_id,
                            permission=grant_in.permission,
                            policy=grant_in.policy.value,
                            scope=grant_in.scope,
                            device_id=grant_in.device_id,
                            target_app=grant_in.target_app,
                            capability=grant_in.capability,
                            resource=grant_in.resource,
                            parameter_constraints_json=json.dumps(grant_in.parameter_constraints),
                            risk_level=grant_in.risk_level,
                            grant_source=grant_in.grant_source,
                            expires_at=expires_at,
                            revoked_at=None,
                            granted_at=now,
                            updated_at=now,
                        )
                        session.add(new_grant)
                        await session.commit()
                        record_dict = new_grant.to_dict()
            except Exception as exc:
                log.warning("permission_service.db_grant_failed", error=str(exc))

        # Always update memory cache
        _MEM_GRANTS_BY_ID[record_dict["id"]] = record_dict
        if grant_in.tool_id:
            _MEM_GRANTS_LOOKUP[(user_id, grant_in.tool_id, grant_in.permission)] = record_dict["id"]

        return PermissionGrantResponse(**record_dict)

    async def revoke_grant(self, grant_id: str, user_id: str) -> bool:
        """Revoke a specific permission grant by ID."""
        return await self.revoke_permission(user_id=user_id, grant_id=grant_id)

    async def revoke_permission(
        self,
        user_id: str,
        tool_id: str | None = None,
        permission: str | None = None,
        grant_id: str | None = None,
        target_app: str | None = None,
        device_id: str | None = None,
    ) -> bool:
        """Revoke a permission grant by grant_id, tool_id+permission, or target_app."""
        now = datetime.now(UTC)
        revoked_count = 0
        factory = get_session_factory()

        if factory is not None:
            try:
                async with factory() as session:
                    conditions = [PermissionGrant.user_id == user_id]
                    if grant_id:
                        conditions.append(PermissionGrant.id == grant_id)
                    elif tool_id:
                        conditions.append(PermissionGrant.tool_id == tool_id)
                        if permission:
                            conditions.append(PermissionGrant.permission == permission)
                    elif target_app:
                        conditions.append(PermissionGrant.target_app == target_app)
                    elif device_id:
                        conditions.append(PermissionGrant.device_id == device_id)

                    stmt = select(PermissionGrant).where(*conditions)
                    res = await session.execute(stmt)
                    grants = res.scalars().all()
                    for g in grants:
                        g.revoked_at = now
                        g.policy = PermissionPolicy.REVOKED.value
                        g.updated_at = now
                        revoked_count += 1
                    if revoked_count > 0:
                        await session.commit()
            except Exception as exc:
                log.warning("permission_service.db_revoke_failed", error=str(exc))

        # Revoke in memory
        to_revoke_ids: list[str] = []
        for gid, mem_grant in _MEM_GRANTS_BY_ID.items():
            if mem_grant.get("user_id") != user_id:
                continue
            if grant_id and gid == grant_id:
                to_revoke_ids.append(gid)
            elif tool_id and mem_grant.get("tool_id") == tool_id:
                if not permission or mem_grant.get("permission") == permission:
                    to_revoke_ids.append(gid)
            elif (target_app and mem_grant.get("target_app") == target_app) or (
                device_id and mem_grant.get("device_id") == device_id
            ):
                to_revoke_ids.append(gid)

        for gid in to_revoke_ids:
            _MEM_GRANTS_BY_ID[gid]["revoked_at"] = now.isoformat()
            _MEM_GRANTS_BY_ID[gid]["policy"] = PermissionPolicy.REVOKED.value
            _MEM_GRANTS_BY_ID[gid]["is_active"] = False
            revoked_count += 1

        if tool_id and permission:
            mem_key = (user_id, tool_id, permission)
            if mem_key in _MEM_GRANTS_LOOKUP:
                del _MEM_GRANTS_LOOKUP[mem_key]

        return revoked_count > 0

    async def list_grants(
        self,
        user_id: str,
        target_app: str | None = None,
        device_id: str | None = None,
        active_only: bool = False,
    ) -> list[PermissionGrantResponse]:
        """List permission grants configured for user with optional filters."""
        all_grants = await self._fetch_user_grants(user_id)
        now = datetime.now(UTC)

        results: list[PermissionGrantResponse] = []
        for g in all_grants:
            if target_app and g.get("target_app") != target_app:
                continue
            if device_id and g.get("device_id") != device_id:
                continue

            is_rev = g.get("revoked_at") is not None or g.get("policy") == PermissionPolicy.REVOKED.value
            is_exp = False
            exp_str = g.get("expires_at")
            if exp_str:
                try:
                    exp_dt = datetime.fromisoformat(exp_str)
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=UTC)
                    if now > exp_dt:
                        is_exp = True
                except Exception:
                    pass

            is_active = not is_rev and not is_exp
            if active_only and not is_active:
                continue

            resp_dict = dict(g)
            resp_dict["is_active"] = is_active
            results.append(PermissionGrantResponse(**resp_dict))

        return results

    list_user_grants = list_grants
