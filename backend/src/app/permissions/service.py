"""Permission Engine Service for ROXY-AI 2.0.

Evaluates permissions and policy grants (always_ask, ask_once, allow_automatically, never_allow).
Persists grants in PostgreSQL with resilient in-memory fallback.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select

from app.db import get_session_factory
from app.models.agent_runtime import PermissionGrant
from app.permissions.schemas import (
    PermissionCheckResult,
    PermissionGrantCreate,
    PermissionGrantResponse,
    PermissionPolicy,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel

log = structlog.get_logger()

# Thread-safe in-memory cache / fallback store keyed by (user_id, tool_id, permission)
_MEM_PERMISSION_GRANTS: dict[tuple[str, str, str], dict[str, Any]] = {}


def clear_in_memory_grants() -> None:
    """Clear in-memory permission grants (for test isolation)."""
    _MEM_PERMISSION_GRANTS.clear()


class PermissionService:
    """Evaluates and manages execution permissions for tools and capabilities."""

    def __init__(self) -> None:
        self._mem = _MEM_PERMISSION_GRANTS
        self._tool_registry = ToolRegistry.get_instance()

    async def check_permission(
        self,
        user_id: str,
        tool_id: str,
        permission: str | None = None,
        scope: str = "global",
    ) -> PermissionCheckResult:
        """Evaluate if user has permission to execute tool, or if user confirmation is required."""
        tool = self._tool_registry.get(tool_id)

        # 1. If tool is not registered
        if not tool:
            return PermissionCheckResult(
                granted=False,
                policy=PermissionPolicy.NEVER_ALLOW.value,
                requires_confirmation=False,
                reason=f"Tool '{tool_id}' is not registered in the system.",
            )

        # 2. Determine permission key
        target_perm = permission or (tool.permissions[0] if tool.permissions else "execute")

        # 3. Check existing database grant
        grant_dict: dict[str, Any] | None = None
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(PermissionGrant).where(
                        PermissionGrant.user_id == user_id,
                        PermissionGrant.tool_id == tool_id,
                        PermissionGrant.permission == target_perm,
                    )
                    res = await session.execute(stmt)
                    grant = res.scalars().first()
                    if grant:
                        grant_dict = grant.to_dict()
            except Exception as exc:
                log.warning("permission_service.db_check_failed", error=str(exc))

        # Check in-memory fallback if not in DB
        if not grant_dict:
            grant_dict = self._mem.get((user_id, tool_id, target_perm))

        # 4. Evaluate grant policy if found
        if grant_dict:
            policy = grant_dict.get("policy", PermissionPolicy.ALWAYS_ASK.value)
            if policy == PermissionPolicy.NEVER_ALLOW.value:
                return PermissionCheckResult(
                    granted=False,
                    policy=policy,
                    requires_confirmation=False,
                    reason=f"Execution blocked: User policy for tool '{tool_id}' is '{policy}'.",
                )
            elif policy == PermissionPolicy.ALLOW_AUTOMATICALLY.value:
                return PermissionCheckResult(
                    granted=True,
                    policy=policy,
                    requires_confirmation=False,
                    reason=f"Permission granted automatically per user policy for '{tool_id}'.",
                )
            elif policy == PermissionPolicy.ASK_ONCE.value:
                return PermissionCheckResult(
                    granted=True,
                    policy=policy,
                    requires_confirmation=False,
                    reason=f"Permission pre-authorized under '{policy}' policy for '{tool_id}'.",
                )
            elif policy == PermissionPolicy.ALWAYS_ASK.value:
                return PermissionCheckResult(
                    granted=False,
                    policy=policy,
                    requires_confirmation=True,
                    reason=f"Action requires explicit user confirmation per '{policy}' policy.",
                )

        # 5. Default policy based on tool risk level and specifications
        if tool.requires_confirmation or tool.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return PermissionCheckResult(
                granted=False,
                policy=PermissionPolicy.ALWAYS_ASK.value,
                requires_confirmation=True,
                reason=f"Tool '{tool.name}' has risk level '{tool.risk_level.value}' and requires confirmation before execution.",
            )

        # Medium or Low risk tools without explicit confirmation flag
        return PermissionCheckResult(
            granted=True,
            policy=PermissionPolicy.ALLOW_AUTOMATICALLY.value,
            requires_confirmation=False,
            reason=f"Tool '{tool.name}' has risk level '{tool.risk_level.value}' and does not require explicit confirmation.",
        )

    async def grant_permission(
        self,
        user_id: str,
        grant_in: PermissionGrantCreate,
    ) -> PermissionGrantResponse:
        """Create or update a user permission grant."""
        now = datetime.now(UTC)
        grant_id = str(uuid.uuid4())
        record_dict = {
            "id": grant_id,
            "user_id": user_id,
            "tool_id": grant_in.tool_id,
            "permission": grant_in.permission,
            "policy": grant_in.policy.value,
            "scope": grant_in.scope,
            "granted_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(PermissionGrant).where(
                        PermissionGrant.user_id == user_id,
                        PermissionGrant.tool_id == grant_in.tool_id,
                        PermissionGrant.permission == grant_in.permission,
                    )
                    res = await session.execute(stmt)
                    existing = res.scalars().first()
                    if existing:
                        existing.policy = grant_in.policy.value
                        existing.scope = grant_in.scope
                        existing.updated_at = now
                        await session.commit()
                        return PermissionGrantResponse(**existing.to_dict())
                    else:
                        new_grant = PermissionGrant(
                            id=grant_id,
                            user_id=user_id,
                            tool_id=grant_in.tool_id,
                            permission=grant_in.permission,
                            policy=grant_in.policy.value,
                            scope=grant_in.scope,
                            granted_at=now,
                            updated_at=now,
                        )
                        session.add(new_grant)
                        await session.commit()
                        return PermissionGrantResponse(**new_grant.to_dict())
            except Exception as exc:
                log.warning("permission_service.db_grant_failed", error=str(exc))

        # In-memory storage
        self._mem[(user_id, grant_in.tool_id, grant_in.permission)] = record_dict
        return PermissionGrantResponse(**record_dict)

    async def revoke_permission(
        self,
        user_id: str,
        tool_id: str,
        permission: str,
    ) -> bool:
        """Revoke a permission grant for user."""
        factory = get_session_factory()
        deleted = False
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = delete(PermissionGrant).where(
                        PermissionGrant.user_id == user_id,
                        PermissionGrant.tool_id == tool_id,
                        PermissionGrant.permission == permission,
                    )
                    res = await session.execute(stmt)
                    await session.commit()
                    if res.rowcount and res.rowcount > 0:
                        deleted = True
            except Exception as exc:
                log.warning("permission_service.db_revoke_failed", error=str(exc))

        mem_key = (user_id, tool_id, permission)
        if mem_key in self._mem:
            del self._mem[mem_key]
            deleted = True

        return deleted

    async def list_grants(self, user_id: str) -> list[PermissionGrantResponse]:
        """List all permission grants configured for user."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(PermissionGrant).where(PermissionGrant.user_id == user_id)
                    res = await session.execute(stmt)
                    rows = res.scalars().all()
                    if rows:
                        return [PermissionGrantResponse(**r.to_dict()) for r in rows]
            except Exception as exc:
                log.warning("permission_service.db_list_failed", error=str(exc))

        # In-memory return
        return [
            PermissionGrantResponse(**g)
            for (u_id, _, _), g in self._mem.items()
            if u_id == user_id
        ]
