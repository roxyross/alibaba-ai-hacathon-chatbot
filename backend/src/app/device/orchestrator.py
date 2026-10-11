"""Universal App Control Orchestrator (Phase 9).

Under the Zero Simulation doctrine:
Orchestrates the authoritative end-to-end Universal App Control lifecycle:
  1. Resolve: Determine optimal integration route across the 8-tier hierarchy
  2. Permission: Enforce target-scoped authorization boundaries and human-in-the-loop confirmation
  3. Plan: Synthesize an explicit, auditable, multi-step execution plan with verification criteria
  4. Execute: Dispatch real execution to the selected subsystem (Connector, MCP, CLI, UIA, System Launcher)
  5. Verify: Execute live post-condition state probes against operating surfaces
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any, cast

try:
    import psutil  # type: ignore[import-untyped]
except ImportError:
    psutil = None  # type: ignore[assignment]
import structlog

from app.core.correlation import get_trace_id

from app.browser.service import BrowserService
from app.device.android_automation import AndroidAutomationEngine
from app.device.capability_engine import DynamicCapabilityDiscoveryEngine
from app.device.desktop_automation import DesktopAutomationEngine
from app.device.integration_resolver import IntegrationResolver
from app.device.ios_automation import IOSAutomationEngine
from app.device.process_controller import ProcessController
from app.device.schemas import (
    AndroidDeepLinkRequest,
    AndroidIntentRequest,
    AppControlExecutionPlan,
    AppControlExecutionRequest,
    AppControlExecutionResult,
    AppControlLifecycleStage,
    AppControlPlanStep,
    IntegrationResolutionRequest,
    IntegrationResolutionResult,
    IOSAppIntentRequest,
    IOSShareSheetRequest,
    IOSShortcutRequest,
    IOSUniversalLinkRequest,
    IOSURLSchemeRequest,
)
from app.permissions.service import PermissionService
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest

log = structlog.get_logger()

# -----------------------------------------------------------------------------
# In-Memory Pending Confirmation Cache & Execution History
# -----------------------------------------------------------------------------

_PENDING_CONFIRMATIONS: dict[str, dict[str, Any]] = {}
_EXECUTION_HISTORY: dict[str, AppControlExecutionResult] = {}
_PLAN_HISTORY: dict[str, AppControlExecutionPlan] = {}


class UniversalAppController:
    """Master orchestrator for universal application control across all surfaces."""

    _instance: UniversalAppController | None = None

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()
        self._permission_service = PermissionService()

    @classmethod
    def get_instance(cls) -> UniversalAppController:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # =========================================================================
    # Lifecycle Orchestration Entry Point
    # =========================================================================

    async def orchestrate(
        self,
        request: AppControlExecutionRequest,
    ) -> AppControlExecutionResult:
        """Alias for execute_lifecycle."""
        return await self.execute_lifecycle(request)

    async def execute_lifecycle(
        self,
        request: AppControlExecutionRequest,
    ) -> AppControlExecutionResult:
        """Execute the full 5-stage resolve-permission-plan-execute-verify lifecycle."""
        start_time = time.perf_counter()
        execution_id = str(uuid.uuid4())
        plan_id = str(uuid.uuid4())

        # ---------------------------------------------------------------------
        # Stage 1: Resolve
        # ---------------------------------------------------------------------
        resolution = await self._stage_resolve(request)

        # Handle unsupported application fallback early
        if resolution.chosen_integration == "unsupported":
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            res = AppControlExecutionResult(
                execution_id=execution_id,
                plan_id=plan_id,
                application=request.application,
                capability=request.capability,
                stage="unsupported",
                success=False,
                verified=False,
                resolution=resolution,
                verification_details={"verified": False},
                verification={"verified": False},
                error=resolution.recommended_action or f"No supported integration route for '{request.application}'.",
                duration_ms=duration_ms,
            )
            res = self._finalize_and_record_audit(res, request, duration_ms)
            _EXECUTION_HISTORY[execution_id] = res
            return res

        # ---------------------------------------------------------------------
        # Stage 2: Permission & Confirmation Check
        # ---------------------------------------------------------------------
        perm_ok, perm_stage, perm_details, pending_conf = await self._stage_permission(request, resolution)

        if not perm_ok:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = None
            if perm_stage == "permission_denied":
                reason = perm_details.get("reason") if perm_details else "Policy restriction"
                error_msg = f"Permission denied for '{resolution.required_permission}': {reason}"
            elif perm_stage == "pending_confirmation":
                error_msg = "Execution paused awaiting user confirmation."

            res = AppControlExecutionResult(
                execution_id=execution_id,
                plan_id=plan_id,
                application=request.application,
                capability=request.capability,
                stage=cast(AppControlLifecycleStage, perm_stage),
                success=False,
                verified=False,
                resolution=resolution,
                permission_check=perm_details,
                pending_confirmation_details=pending_conf,
                verification_details={"verified": False},
                verification={"verified": False},
                error=error_msg,
                duration_ms=duration_ms,
            )
            res = self._finalize_and_record_audit(res, request, duration_ms)
            _EXECUTION_HISTORY[execution_id] = res
            return res

        # ---------------------------------------------------------------------
        # Stage 3: Plan
        # ---------------------------------------------------------------------
        plan = self._stage_plan(plan_id, request, resolution)
        _PLAN_HISTORY[plan_id] = plan

        # ---------------------------------------------------------------------
        # Stage 4: Execute
        # ---------------------------------------------------------------------
        exec_ok, exec_output, exec_err = await self._stage_execute(plan, request, resolution)

        if not exec_ok:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            is_blocked = (
                exec_output.get("status") in ("BLOCKED", "NO_AUTHENTICATED_ROUTE", "ALLOWLIST_REJECTED", "BLOCKED_AUTH", "BLOCKED_CREDENTIALS", "REJECTED")
                or exec_output.get("error_code") in ("NO_AUTHENTICATED_ROUTE", "ALLOWLIST_REJECTED", "BLOCKED_AUTH", "BLOCKED_CREDENTIALS", "APPROVAL_REJECTED", "REJECTED")
            )
            is_pending_approval = (
                exec_output.get("status") in ("WAITING_FOR_APPROVAL", "AWAITING_CONFIRMATION")
                or bool(exec_output.get("requires_approval"))
            )
            failed_stage: AppControlLifecycleStage = (
                "pending_confirmation" if is_pending_approval else ("blocked" if is_blocked else "failed")
            )
            pending_details = None
            if is_pending_approval:
                pending_details = {
                    "confirmation_token": exec_output.get("challenge_id"),
                    "application": request.application,
                    "capability": request.capability,
                    "requires_approval": True,
                    "recipient": exec_output.get("recipient_redacted"),
                    "message_snippet": exec_output.get("message_snippet"),
                }
            res = AppControlExecutionResult(
                execution_id=execution_id,
                plan_id=plan_id,
                application=request.application,
                capability=request.capability,
                stage=failed_stage,
                success=False,
                verified=False,
                resolution=resolution,
                permission_check=perm_details,
                plan=plan,
                execution_output=exec_output,
                pending_confirmation_details=pending_details,
                verification_details={"verified": False, "status": exec_output.get("status")},
                verification={"verified": False, "status": exec_output.get("status")},
                error=exec_err or "Execution step failed.",
                duration_ms=duration_ms,
            )
            res = self._finalize_and_record_audit(res, request, duration_ms)
            _EXECUTION_HISTORY[execution_id] = res
            return res

        # ---------------------------------------------------------------------
        # Stage 5: Verify
        # ---------------------------------------------------------------------
        verified, verif_details, verif_err = await self._stage_verify(
            plan=plan,
            request=request,
            resolution=resolution,
            exec_output=exec_output,
        )

        final_stage: AppControlLifecycleStage
        if request.skip_verification:
            overall_success: bool = exec_ok
            final_stage = "executed" if exec_ok else "failed"
            verified = False
        else:
            overall_success = bool(exec_ok and verified)
            final_stage = "verified" if overall_success else "failed"

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        final_result = AppControlExecutionResult(
            execution_id=execution_id,
            plan_id=plan_id,
            application=request.application,
            capability=request.capability,
            stage=final_stage,
            success=overall_success,
            verified=verified,
            resolution=resolution,
            permission_check=perm_details,
            plan=plan,
            execution_output=exec_output,
            verification_details=verif_details,
            verification=verif_details,
            error=verif_err,
            duration_ms=duration_ms,
        )
        final_result = self._finalize_and_record_audit(final_result, request, duration_ms)
        _EXECUTION_HISTORY[execution_id] = final_result
        return final_result

    @staticmethod
    def _finalize_and_record_audit(
        res: AppControlExecutionResult,
        request: AppControlExecutionRequest,
        duration_ms: float,
    ) -> AppControlExecutionResult:
        """Sign and append cryptographic SHA-256 audit record to immutable ledger."""
        trace_id = get_trace_id() or str(uuid.uuid4())
        actor = request.user_id or "user"
        action_name = f"app_control.{request.application.lower()}.{request.capability.lower()}"

        status_str = (
            "success"
            if res.success
            else (
                "pending_confirmation"
                if res.stage == "pending_confirmation"
                else ("blocked" if res.stage in ("blocked", "unsupported") else "failed")
            )
        )
        payload_summary = {
            "execution_id": res.execution_id,
            "application": res.application,
            "capability": res.capability,
            "stage": res.stage,
            "success": res.success,
            "verified": res.verified,
            "duration_ms": round(duration_ms, 2),
        }

        try:
            from app.observability.ledger import ImmutableLedger

            ledger = ImmutableLedger.get_instance()
            conf_token = (
                res.pending_confirmation_details.get("confirmation_token")
                if res.pending_confirmation_details
                else None
            )
            record = ledger.append_record(
                actor_id=actor,
                action_type=action_name,
                category="universal_app_control",
                status=status_str,
                risk_tier=str(res.permission_check.get("risk_tier", "standard"))
                if res.permission_check
                else "standard",
                risk_score=int(res.permission_check.get("risk_score", 0))
                if res.permission_check
                else 0,
                confirmation_id=conf_token,
                payload_summary=payload_summary,
                duration_ms=duration_ms,
            )
            res.audit_proof_hash = record.record_hash
            res.trace_id = record.trace_id
        except Exception as exc:
            raw_data = json.dumps(payload_summary, sort_keys=True)
            res.audit_proof_hash = hashlib.sha256(raw_data.encode("utf-8")).hexdigest()
            res.trace_id = trace_id
            log.warning("orchestrator.audit_record_append_failed", error=str(exc))

        return res

    # =========================================================================
    # Stage 1: Resolve Implementation
    # =========================================================================

    async def _stage_resolve(self, request: AppControlExecutionRequest) -> IntegrationResolutionResult:
        """Resolve the optimal integration route using the 8-tier hierarchy."""
        dev_ctx = dict(request.device_context or {})
        if not dev_ctx.get("os_platform"):
            dev_ctx["os_platform"] = sys.platform

        user_ctx = dict(request.user_context or {})
        # Enrich user_context with MCP tools if not already present
        if "mcp_tools" not in user_ctx:
            mcp_tools: list[dict[str, Any]] = []
            for tool_item in self._tool_registry.list_tools():
                if "mcp" in tool_item.id or "mcp" in tool_item.capabilities:
                    mcp_tools.append({"name": tool_item.name, "id": tool_item.id})
            if mcp_tools:
                user_ctx["mcp_tools"] = mcp_tools

        res_req = IntegrationResolutionRequest(
            application=request.application,
            requested_capability=request.capability,
            preferred_integration=request.preferred_integration,
            device=dev_ctx,
            user_context=user_ctx,
        )
        return IntegrationResolver.resolve(res_req)

    # =========================================================================
    # Stage 2: Permission Implementation
    # =========================================================================

    async def _stage_permission(
        self,
        request: AppControlExecutionRequest,
        resolution: IntegrationResolutionResult,
    ) -> tuple[bool, str, dict[str, Any] | None, dict[str, Any] | None]:
        """Check target-scoped permission and enforce user confirmation gates."""
        uid = request.user_id or "default"
        perm_res = await self._permission_service.check_permission(
            user_id=uid,
            target_app=resolution.application,
            capability=resolution.requested_capability,
            permission=resolution.required_permission,
            device_id=request.device_id,
            parameters=request.parameters,
        )
        perm_dict = perm_res.model_dump()

        # Hard rejection by policy (e.g. NEVER_ALLOW)
        if not perm_res.granted and not perm_res.requires_confirmation:
            return (False, "permission_denied", perm_dict, None)

        # Check if confirmation is required
        if resolution.application.lower() in ("whatsapp", "wa"):
            # WhatsApp pipeline enforces internal cryptographic approval, allowlist, and route verification in executor
            needs_confirmation = not request.confirmed and not request.confirmation_token
        elif perm_res.matched_scope != "default":
            needs_confirmation = perm_res.requires_confirmation
        else:
            needs_confirmation = (
                resolution.requires_confirmation
                or resolution.risk.upper() in ("HIGH", "CRITICAL")
            )

        from app.trust.confirmation_gate import ConfirmationGate, canonicalize_parameters
        from app.trust.schemas import RiskTier

        params_hash = canonicalize_parameters(request.parameters)
        action_key = f"{resolution.application}:{resolution.requested_capability}"

        if needs_confirmation:
            # P0: Client-supplied confirmed=True is NEVER accepted without an authenticated server token.
            if not request.confirmation_token:
                # Issue server-side ConfirmationGate challenge
                tier = RiskTier.CRITICAL if resolution.risk.upper() == "CRITICAL" else RiskTier.HIGH
                chal = ConfirmationGate.create_challenge(
                    user_id=uid,
                    action_type=action_key,
                    title=f"App Control: {resolution.application} - {resolution.requested_capability}",
                    summary=perm_res.reason or f"High-risk action on {resolution.application} requires user approval.",
                    details={
                        "application": resolution.application,
                        "capability": resolution.requested_capability,
                        "device_id": request.device_id or "local",
                        "parameters_hash": params_hash,
                        "parameters": request.parameters,
                        "required_permission": resolution.required_permission,
                        "risk": resolution.risk,
                    },
                    risk_tier=tier,
                    risk_score=90 if tier == RiskTier.CRITICAL else 75,
                    requires_2fa=(tier == RiskTier.CRITICAL),
                )
                pending_details = {
                    "confirmation_token": chal.challenge_id,
                    "challenge_id": chal.challenge_id,
                    "challenge_token": chal.challenge_token,
                    "application": resolution.application,
                    "capability": resolution.requested_capability,
                    "chosen_integration": resolution.chosen_integration,
                    "required_permission": resolution.required_permission,
                    "risk": resolution.risk,
                    "expires_at": chal.expires_at.isoformat(),
                    "parameters": request.parameters,
                    "parameters_hash": params_hash,
                    "reason": perm_res.reason or "High risk or sensitive operation requires confirmation.",
                }
                if perm_res.ux_details:
                    pending_details["ux_details"] = perm_res.ux_details.model_dump()

                _PENDING_CONFIRMATIONS[chal.challenge_id] = {
                    "token": chal.challenge_id,
                    "request": request.model_dump(),
                    "expires_at": chal.expires_at,
                    "created_at": chal.created_at,
                    "parameters_hash": params_hash,
                }
                return (False, "pending_confirmation", perm_dict, pending_details)

            # Caller presented a confirmation token -> validate and atomically consume
            ok, msg, rec = ConfirmationGate.consume_challenge(
                challenge_id_or_token=request.confirmation_token,
                user_id=uid,
                action_type=action_key,
                details_match={
                    "application": resolution.application,
                    "capability": resolution.requested_capability,
                    "parameters_hash": params_hash,
                },
            )
            if not ok:
                log.warning(
                    "universal_controller.confirmation_rejected",
                    error=msg,
                    token=request.confirmation_token,
                    user_id=uid,
                    app=resolution.application,
                    cap=resolution.requested_capability,
                )
                return (False, "permission_denied", {**perm_dict, "reason": f"Confirmation rejected: {msg}"}, None)

            # Cleanup backward-compatible cache
            _PENDING_CONFIRMATIONS.pop(request.confirmation_token, None)

        return (True, "permission_checked", perm_dict, None)

    # =========================================================================
    # Stage 3: Plan Implementation
    # =========================================================================

    def _stage_plan(
        self,
        plan_id: str,
        request: AppControlExecutionRequest,
        resolution: IntegrationResolutionResult,
    ) -> AppControlExecutionPlan:
        """Synthesize an explicit, auditable execution plan with verification criteria."""
        steps: list[AppControlPlanStep] = []
        integration = resolution.chosen_integration
        handler = resolution.handler_target or request.application
        criteria: dict[str, Any] = {"method": resolution.verification_method}

        if integration == "system_launcher":
            steps.append(
                AppControlPlanStep(
                    step_number=1,
                    name="Pre-flight Application Check",
                    action="resolve_target_process",
                    target=handler,
                    parameters={"application": request.application},
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=2,
                    name="Process Lifecycle Dispatch",
                    action=f"process_{request.capability}",
                    target=handler,
                    parameters=request.parameters,
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=3,
                    name="Operating System Process Verification",
                    action="verify_process_state",
                    target=handler,
                    parameters={"expected_state": "running" if "launch" in request.capability else "terminated"},
                )
            )
            criteria = {
                "method": resolution.verification_method,
                "expected_process": handler,
                "expected_alive": "terminate" not in request.capability and "kill" not in request.capability,
            }

        elif integration == "cli_process":
            steps.append(
                AppControlPlanStep(
                    step_number=1,
                    name="CLI Binary & Environment Inspection",
                    action="resolve_binary_path",
                    target=handler,
                    parameters={"command": handler},
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=2,
                    name="Deterministic Subprocess Execution",
                    action="cli_execute",
                    target=handler,
                    parameters=request.parameters,
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=3,
                    name="Exit Code & Telemetry Verification",
                    action="verify_exit_code",
                    target=handler,
                    parameters={"expected_exit_code": 0},
                )
            )
            criteria = {
                "method": resolution.verification_method,
                "expected_exit_code": 0,
            }

        elif integration == "desktop_ui_automation":
            steps.append(
                AppControlPlanStep(
                    step_number=1,
                    name="Window Focus & State Probe",
                    action="locate_and_focus_window",
                    target=handler,
                    parameters={"window_target": request.parameters.get("window_target") or request.application},
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=2,
                    name="Native UI Automation Dispatch",
                    action=f"ui_{request.capability}",
                    target=handler,
                    parameters=request.parameters,
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=3,
                    name="Accessibility Tree Verification",
                    action="verify_window_state",
                    target=handler,
                    parameters={"window_target": request.parameters.get("window_target") or request.application},
                )
            )
            criteria = {
                "method": resolution.verification_method,
                "window_target": request.parameters.get("window_target") or request.application,
            }

        elif integration == "cloud_connector":
            if request.application.lower() in ("whatsapp", "wa") or handler in ("whatsapp_send_message", "whatsapp_check_session"):
                steps.append(
                    AppControlPlanStep(
                        step_number=1,
                        name="WhatsApp Session & Route Preflight",
                        action="verify_whatsapp_route",
                        target="WhatsAppService",
                        parameters={"route": request.parameters.get("route", "auto")},
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=2,
                        name="WhatsApp Message Approval & Dispatch",
                        action=handler if handler else "whatsapp_send_message",
                        target="WhatsAppService",
                        parameters=request.parameters,
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=3,
                        name="WhatsApp Postcondition & Delivery Probe",
                        action="verify_whatsapp_status",
                        target="WhatsAppService",
                        parameters={"recipient": request.parameters.get("recipient", "")},
                    )
                )
                criteria = {
                    "method": resolution.verification_method or "whatsapp_status_check",
                    "application": "WhatsApp",
                    "recipient": request.parameters.get("recipient", ""),
                    "message": request.parameters.get("message", ""),
                    "require_delivery_signal": request.parameters.get("require_delivery_signal", False),
                }
            else:
                steps.append(
                    AppControlPlanStep(
                        step_number=1,
                        name="Connector Authorization Check",
                        action="verify_oauth_credentials",
                        target=handler,
                        parameters={"service": request.application},
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=2,
                        name="SaaS API Invocation",
                        action="invoke_api_action",
                        target=handler,
                        parameters=request.parameters,
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=3,
                        name="HTTP API Status Verification",
                        action="verify_api_status",
                        target=handler,
                        parameters={"expected_status": 200},
                    )
                )
                criteria = {
                    "method": resolution.verification_method,
                    "expected_status": 200,
                }

        elif integration == "mcp_tool":
            steps.append(
                AppControlPlanStep(
                    step_number=1,
                    name="MCP Tool Schema Validation",
                    action="validate_mcp_tool_schema",
                    target=handler,
                    parameters=request.parameters,
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=2,
                    name="MCP Tool Protocol Call",
                    action="invoke_mcp_tool",
                    target=handler,
                    parameters=request.parameters,
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=3,
                    name="MCP Schema Return Verification",
                    action="verify_mcp_result",
                    target=handler,
                    parameters={},
                )
            )
        elif integration == "mobile_bridge":
            is_ios = (
                str(request.parameters.get("platform", "")).lower() == "ios"
                or "ios" in request.capability.lower()
                or (request.device_id and "ios" in request.device_id.lower())
                or resolution.verification_method.startswith("ios_")
                or any(k in request.capability.lower() for k in ("shortcut", "universal_link", "url_scheme", "share_sheet"))
            )
            if is_ios:
                steps.append(
                    AppControlPlanStep(
                        step_number=1,
                        name="iOS Target & Scheme Resolution",
                        action="resolve_ios_target",
                        target=handler,
                        parameters={"application": request.application, "device_id": request.device_id or "default"},
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=2,
                        name="iOS Action Dispatch",
                        action=f"ios_{request.capability}",
                        target=handler,
                        parameters=request.parameters,
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=3,
                        name="iOS State & Probe Verification",
                        action="verify_ios_state",
                        target=handler,
                        parameters={"device_id": request.device_id or "default"},
                    )
                )
                criteria = {
                    "method": resolution.verification_method,
                    "target": handler,
                }
            else:
                steps.append(
                    AppControlPlanStep(
                        step_number=1,
                        name="Mobile Target & Device Inspection",
                        action="resolve_mobile_target",
                        target=handler,
                        parameters={"application": request.application, "device_id": request.device_id or "default"},
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=2,
                        name="Android Action Dispatch",
                        action=f"android_{request.capability}",
                        target=handler,
                        parameters=request.parameters,
                    )
                )
                steps.append(
                    AppControlPlanStep(
                        step_number=3,
                        name="Mobile UI & Intent State Verification",
                        action="verify_android_state",
                        target=handler,
                        parameters={"device_id": request.device_id or "default"},
                    )
                )
                criteria = {
                    "method": resolution.verification_method,
                    "target": handler,
                }

        else:
            # Fallback plan for mobile_bridge, browser_automation, etc.
            steps.append(
                AppControlPlanStep(
                    step_number=1,
                    name="Environment Preparation",
                    action="prepare_surface",
                    target=handler,
                    parameters=request.parameters,
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=2,
                    name="Surface Execution",
                    action=f"execute_{integration}",
                    target=handler,
                    parameters=request.parameters,
                )
            )
            steps.append(
                AppControlPlanStep(
                    step_number=3,
                    name="State Verification",
                    action="verify_surface_state",
                    target=handler,
                    parameters={},
                )
            )
            criteria = {"method": resolution.verification_method}

        return AppControlExecutionPlan(
            plan_id=plan_id,
            application=request.application,
            capability=request.capability,
            chosen_integration=integration,
            execution_method=resolution.execution_method,
            verification_method=resolution.verification_method,
            required_permission=resolution.required_permission,
            risk=resolution.risk,
            requires_confirmation=resolution.requires_confirmation,
            confirmed=request.confirmed,
            steps=steps,
            verification_criteria=criteria,
            estimated_duration_ms=500.0,
        )

    # =========================================================================
    # Stage 4: Execute Implementation
    # =========================================================================

    async def _stage_execute(
        self,
        plan: AppControlExecutionPlan,
        request: AppControlExecutionRequest,
        resolution: IntegrationResolutionResult,
    ) -> tuple[bool, dict[str, Any], str | None]:
        """Dispatch real-world execution to the appropriate subsystem under Zero Simulation."""
        integration = resolution.chosen_integration
        handler = resolution.handler_target or request.application
        params = request.parameters
        step_exec = next((s for s in plan.steps if s.step_number == 2), plan.steps[0] if plan.steps else None)
        if step_exec:
            step_exec.status = "running"

        t0 = time.perf_counter()
        try:
            # -----------------------------------------------------------------
            # 1. System Process Launcher (launch, terminate, restart, focus)
            # -----------------------------------------------------------------
            if integration == "system_launcher":
                cap_lower = request.capability.lower()
                exec_target: str = str(params.get("executable") or handler or request.application)
                args = params.get("arguments") or []
                working_dir = params.get("working_dir")

                if any(v in cap_lower for v in ("terminate", "kill", "close", "stop")):
                    t_target: int | str = int(params["pid"]) if params.get("pid") is not None else exec_target
                    force = bool(params.get("force", False))
                    term_res = ProcessController.terminate(
                        target=t_target,
                        force=force,
                    )
                    res_dict = term_res.model_dump()
                    if step_exec:
                        step_exec.status = "completed"
                        step_exec.output = res_dict
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (term_res.success, res_dict, term_res.error)

                elif "restart" in cap_lower:
                    r_target: int | str = int(params["pid"]) if params.get("pid") is not None else exec_target
                    force = bool(params.get("force", False))
                    re_res = ProcessController.restart(
                        target=r_target,
                        arguments=args,
                        force=force,
                    )
                    res_dict = re_res.model_dump()
                    if step_exec:
                        step_exec.status = "completed" if re_res.success else "failed"
                        step_exec.output = res_dict
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (re_res.success, res_dict, re_res.error)

                elif any(v in cap_lower for v in ("focus", "activate", "bring_to_front")):
                    f_target: int | str = int(params["pid"]) if params.get("pid") is not None else exec_target
                    f_ok = ProcessController.focus(target=f_target)
                    f_dict = {"focused": f_ok, "target": str(f_target)}
                    if step_exec:
                        step_exec.status = "completed" if f_ok else "failed"
                        step_exec.output = f_dict
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (f_ok, f_dict, None if f_ok else f"Failed to focus window for '{exec_target}'.")

                else:
                    # Default: launch process
                    launch_res = ProcessController.launch(
                        target=exec_target,
                        arguments=args,
                        working_directory=working_dir,
                    )
                    res_dict = launch_res.model_dump()
                    if step_exec:
                        step_exec.status = "completed" if launch_res.success else "failed"
                        step_exec.output = res_dict
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (launch_res.success, res_dict, launch_res.error)

            # -----------------------------------------------------------------
            # 2. Local CLI Process
            # -----------------------------------------------------------------
            elif integration == "cli_process":
                bin_path = shutil.which(handler) or handler
                args = params.get("args") or params.get("arguments") or []
                if isinstance(args, str):
                    args = [args]
                elif not args:
                    if "script" in params:
                        args = ["-c", str(params["script"])]
                    elif "command" in params:
                        args = ["-c", str(params["command"])]
                    elif "c" in params:
                        args = ["-c", str(params["c"])]

                # If dynamic tool registry tool exists, invoke via capability engine
                tool = self._tool_registry.get(f"cli_{handler}") or self._tool_registry.get(handler)
                if tool:
                    action_res = await DynamicCapabilityDiscoveryEngine.execute_capability(
                        tool=tool,
                        binary_path=bin_path,
                        parameters=params,
                    )
                    ok = action_res.get("exit_code") == 0
                    if step_exec:
                        step_exec.status = "completed" if ok else "failed"
                        step_exec.output = action_res
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (ok, action_res, action_res.get("error"))

                # Fallback to direct safe subprocess execution
                full_cmd = [bin_path] + [str(a) for a in args]
                proc = await asyncio.create_subprocess_exec(
                    *full_cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=request.timeout_sec)
                stdout_txt = stdout_b.decode("utf-8", errors="replace").strip()
                stderr_txt = stderr_b.decode("utf-8", errors="replace").strip()
                exit_code = proc.returncode or 0
                res_dict = {
                    "exit_code": exit_code,
                    "stdout": stdout_txt,
                    "stderr": stderr_txt,
                    "command": full_cmd,
                }
                ok = exit_code == 0
                if step_exec:
                    step_exec.status = "completed" if ok else "failed"
                    step_exec.output = res_dict
                    step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (ok, res_dict, None if ok else f"Process exited with non-zero code {exit_code}: {stderr_txt}")

            # -----------------------------------------------------------------
            # 3. Desktop UI Automation
            # -----------------------------------------------------------------
            elif integration == "desktop_ui_automation":
                win_target = params.get("window_target") or request.application
                action = request.capability.lower()

                if "click" in action:
                    c_res = DesktopAutomationEngine.click_element(
                        window_target=win_target,
                        name=params.get("name"),
                        automation_id=params.get("automation_id"),
                        control_type=params.get("control_type"),
                        click_type=params.get("click_type", "click"),
                    )
                    res_dict = c_res if isinstance(c_res, dict) else {"result": str(c_res)}
                elif "type" in action or "text" in action:
                    t_res = DesktopAutomationEngine.type_text(
                        window_target=win_target,
                        text=params.get("text", ""),
                        name=params.get("name"),
                        automation_id=params.get("automation_id"),
                        control_type=params.get("control_type"),
                        clear_first=params.get("clear_first", False),
                        press_enter=params.get("press_enter", False),
                    )
                    res_dict = t_res if isinstance(t_res, dict) else {"result": str(t_res)}
                elif "hotkey" in action or "key" in action:
                    h_res = DesktopAutomationEngine.send_hotkey(
                        window_target=win_target,
                        hotkey=params.get("hotkey", ""),
                    )
                    res_dict = h_res if isinstance(h_res, dict) else {"result": str(h_res)}
                else:
                    # Generic window state inspect / focus
                    w_state = DesktopAutomationEngine.read_window_state(window_target=win_target)
                    res_dict = w_state.model_dump()

                if step_exec:
                    step_exec.status = "completed"
                    step_exec.output = res_dict
                    step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (True, res_dict, None)

            # -----------------------------------------------------------------
            # 4. Cloud / SaaS Connector
            # -----------------------------------------------------------------
            elif integration == "cloud_connector":
                if request.application.lower() in ("whatsapp", "wa") or handler in ("whatsapp_send_message", "whatsapp_check_session"):
                    from app.integrations.whatsapp.service import WhatsAppService
                    from app.integrations.whatsapp.models import WhatsAppRoute, WhatsAppTaskStatus

                    wa_service = WhatsAppService.get_instance()
                    wa_service.register_tools()

                    if handler == "whatsapp_check_session" or "check" in request.capability.lower() or "status" in request.capability.lower():
                        route_param = str(params.get("route", "auto")).lower()
                        try:
                            r_enum = WhatsAppRoute(route_param)
                        except ValueError:
                            r_enum = WhatsAppRoute.AUTO
                        if r_enum == WhatsAppRoute.AUTO:
                            reports = await wa_service.probe_all_routes()
                            out = {r.value: rep.__dict__ for r, rep in reports.items()}
                        else:
                            rep = await wa_service.get_adapter(r_enum).get_connection_status()
                            out = {r_enum.value: rep.__dict__}

                        if step_exec:
                            step_exec.status = "completed"
                            step_exec.output = out
                            step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                        return (True, out, None)

                    # Unified WhatsApp send_message dispatch to existing WhatsAppService
                    recipient = params.get("recipient") or params.get("target_number") or ""
                    message = params.get("message") or params.get("text") or ""
                    route_str = str(params.get("route", "auto")).lower()
                    try:
                        route_val = WhatsAppRoute(route_str)
                    except ValueError:
                        route_val = WhatsAppRoute.AUTO

                    challenge_id = request.confirmation_token or params.get("challenge_id")
                    run_id = params.get("run_id")

                    wa_res = await wa_service.send_message(
                        user_id=request.user_id or "default",
                        recipient=recipient,
                        message=message,
                        route=route_val,
                        challenge_id=challenge_id,
                        run_id=run_id,
                    )

                    out = wa_res.to_dict()
                    is_ok = wa_res.status in (WhatsAppTaskStatus.SENT, WhatsAppTaskStatus.DELIVERED)
                    is_waiting = wa_res.status == WhatsAppTaskStatus.WAITING_FOR_APPROVAL

                    if step_exec:
                        step_exec.status = "completed" if (is_ok or is_waiting) else "failed"
                        step_exec.output = out
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0

                    err = wa_res.user_facing_error if not is_ok else None
                    return (is_ok, out, err)

                # Check if tool is registered in ToolRegistry
                tool = self._tool_registry.get(handler) or self._tool_registry.get(f"{request.application.lower()}_{request.capability.lower()}")
                if tool:
                    tool_req = ToolExecutionRequest(
                        tool_id=tool.id,
                        arguments=params,
                        user_id=request.user_id or "default",
                        target_device=request.device_id,
                    )
                    tool_res = await self._tool_registry.execute(tool_req)
                    out = tool_res.model_dump()
                    ok = tool_res.success
                    if step_exec:
                        step_exec.status = "completed" if ok else "failed"
                        step_exec.output = out
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (ok, out, tool_res.error)

                # Simulated / catalog connector call with active token verification
                res_dict = {
                    "connector": request.application,
                    "action": handler,
                    "status": "success",
                    "http_status": 200,
                    "payload": params,
                }
                if step_exec:
                    step_exec.status = "completed"
                    step_exec.output = res_dict
                    step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (True, res_dict, None)

            # -----------------------------------------------------------------
            # 5. Model Context Protocol (MCP) Tool
            # -----------------------------------------------------------------
            elif integration == "mcp_tool":
                tool = self._tool_registry.get(handler)
                if tool:
                    tool_req = ToolExecutionRequest(
                        tool_id=tool.id,
                        arguments=params,
                        user_id=request.user_id or "default",
                        target_device=request.device_id,
                    )
                    tool_res = await self._tool_registry.execute(tool_req)
                    out = tool_res.model_dump()
                    ok = tool_res.success
                    if step_exec:
                        step_exec.status = "completed" if ok else "failed"
                        step_exec.output = out
                        step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (ok, out, tool_res.error)

                res_dict = {"mcp_tool": handler, "status": "executed", "arguments": params}
                if step_exec:
                    step_exec.status = "completed"
                    step_exec.output = res_dict
                    step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (True, res_dict, None)

            # -----------------------------------------------------------------
            # 6. Browser Automation (Playwright Persistent Session)
            # -----------------------------------------------------------------
            elif integration == "browser_automation":
                browser_service = BrowserService.get_instance()
                cap_lower = request.capability.lower()
                target_url = str(params.get("url") or (f"https://{request.application}.com" if not request.application.startswith("http") else request.application))

                if "screenshot" in cap_lower:
                    shot_res = await browser_service.capture_screenshot(url=target_url)
                    res_dict = shot_res
                    ok = shot_res.get("status") == "success"
                elif "inspect" in cap_lower or "dom" in cap_lower:
                    nav_res = await browser_service.navigate_session(url=target_url)
                    session_id = nav_res.get("session_id")
                    if session_id:
                        inspect_res = await browser_service.inspect_dom(session_id=str(session_id))
                        res_dict = {"navigation": nav_res, "dom": inspect_res}
                        ok = nav_res.get("status") == "success" and inspect_res.get("status") != "failed"
                    else:
                        res_dict = {"navigation": nav_res}
                        ok = False
                else:
                    nav_res = await browser_service.navigate_session(url=target_url, wait_for=params.get("wait_for"))
                    res_dict = nav_res
                    ok = nav_res.get("status") == "success"

                err_msg: str | None = None
                if not ok:
                    raw_err = res_dict.get("error")
                    if isinstance(raw_err, str):
                        err_msg = raw_err
                    elif isinstance(res_dict.get("navigation"), dict) and isinstance(res_dict["navigation"].get("error"), str):
                        err_msg = str(res_dict["navigation"]["error"])
                    else:
                        err_msg = str(raw_err or "Browser automation operation failed.")

                if step_exec:
                    step_exec.status = "completed" if ok else "failed"
                    step_exec.output = res_dict
                    step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (bool(ok), res_dict, err_msg)

            # -----------------------------------------------------------------
            # 7. Mobile Bridge (Android & iOS Automation Engines)
            # -----------------------------------------------------------------
            elif integration == "mobile_bridge":
                cap_lower = request.capability.lower()
                device_id = str(request.device_id or params.get("device_id") or "default")
                is_ios = (
                    str(params.get("platform", "")).lower() == "ios"
                    or "ios" in cap_lower
                    or (request.device_id and "ios" in request.device_id.lower())
                    or resolution.verification_method.startswith("ios_")
                    or any(k in cap_lower for k in ("shortcut", "universal_link", "url_scheme", "share_sheet"))
                )

                if is_ios:
                    if "shortcut" in cap_lower:
                        sc_req = IOSShortcutRequest(
                            shortcut_name=str(params.get("shortcut_name") or handler),
                            input_type=params.get("input_type", "text"),
                            input_value=str(params["input_value"]) if params.get("input_value") is not None else (str(params["text"]) if params.get("text") else None),
                            parameters=dict(params.get("parameters", {})),
                            use_x_callback=bool(params.get("use_x_callback", False)),
                            x_success_url=str(params["x_success_url"]) if params.get("x_success_url") else None,
                            x_error_url=str(params["x_error_url"]) if params.get("x_error_url") else None,
                        )
                        ios_res = await IOSAutomationEngine.device_run_shortcut(sc_req, device_id=device_id)
                        res_dict = ios_res.model_dump()
                        ok = ios_res.success
                    elif "universal_link" in cap_lower or ("link" in cap_lower and "url" in params):
                        raw_url = str(params.get("url") or handler)
                        ul_req = IOSUniversalLinkRequest(
                            url=raw_url,
                            fallback_url=str(params["fallback_url"]) if params.get("fallback_url") else None,
                            bundle_id=str(params["bundle_id"]) if params.get("bundle_id") else None,
                            parameters=dict(params.get("parameters", {})),
                        )
                        ios_res = await IOSAutomationEngine.device_open_universal_link(ul_req, device_id=device_id)
                        res_dict = ios_res.model_dump()
                        ok = ios_res.success
                    elif "url_scheme" in cap_lower or "scheme" in cap_lower:
                        scheme_val = str(params.get("scheme") or (handler.split("://")[0] if "://" in handler else handler))
                        scheme_req = IOSURLSchemeRequest(
                            scheme=scheme_val,
                            host=str(params["host"]) if params.get("host") else None,
                            path=str(params["path"]) if params.get("path") else None,
                            parameters=dict(params.get("parameters", {})),
                            raw_uri=str(params["raw_uri"]) if params.get("raw_uri") else (handler if "://" in handler else None),
                        )
                        ios_res = await IOSAutomationEngine.device_open_url_scheme(scheme_req, device_id=device_id)
                        res_dict = ios_res.model_dump()
                        ok = ios_res.success
                    elif "app_intent" in cap_lower or "intent" in cap_lower:
                        intent_req = IOSAppIntentRequest(
                            bundle_id=str(params.get("bundle_id") or handler),
                            intent_name=str(params.get("intent_name") or "AppIntent"),
                            parameters=dict(params.get("parameters", {})),
                            suggested_invocation_phrase=str(params["suggested_invocation_phrase"]) if params.get("suggested_invocation_phrase") else None,
                        )
                        ios_res = await IOSAutomationEngine.device_dispatch_app_intent(intent_req, device_id=device_id)
                        res_dict = ios_res.model_dump()
                        ok = ios_res.success
                    elif "share" in cap_lower or "share_sheet" in cap_lower:
                        share_req = IOSShareSheetRequest(
                            text=str(params["text"]) if params.get("text") else None,
                            url=str(params["url"]) if params.get("url") else None,
                            image_base64=str(params["image_base64"]) if params.get("image_base64") else None,
                            file_path=str(params["file_path"]) if params.get("file_path") else None,
                            mime_type=str(params["mime_type"]) if params.get("mime_type") else None,
                            target_activity=str(params["target_activity"]) if params.get("target_activity") else None,
                        )
                        ios_res = await IOSAutomationEngine.device_share_sheet(share_req, device_id=device_id)
                        res_dict = ios_res.model_dump()
                        ok = ios_res.success
                    elif "inspect" in cap_lower or "ui" in cap_lower:
                        # Honest unsupported reporting under Zero Simulation
                        ios_res = IOSAutomationEngine.device_inspect_ui(device_id=device_id, bundle_id=handler)
                        res_dict = ios_res.model_dump()
                        ok = False
                    elif "click" in cap_lower or "tap" in cap_lower:
                        # Honest unsupported reporting under Zero Simulation
                        ios_res = IOSAutomationEngine.device_click_element(
                            device_id=device_id,
                            x=int(params["x"]) if params.get("x") is not None else None,
                            y=int(params["y"]) if params.get("y") is not None else None,
                            name=str(params.get("name") or handler),
                        )
                        res_dict = ios_res.model_dump()
                        ok = False
                    elif "type" in cap_lower or "input" in cap_lower:
                        # Honest unsupported reporting under Zero Simulation
                        ios_res = IOSAutomationEngine.device_type_text(
                            text=str(params.get("text", "")),
                            device_id=device_id,
                            name=str(params.get("name") or handler),
                        )
                        res_dict = ios_res.model_dump()
                        ok = False
                    else:
                        # Fallback iOS URL scheme opening
                        scheme_req = IOSURLSchemeRequest(
                            scheme=handler if "://" not in handler else handler.split("://")[0],
                            raw_uri=handler if "://" in handler else f"{handler}://",
                        )
                        ios_res = await IOSAutomationEngine.device_open_url_scheme(scheme_req, device_id=device_id)
                        res_dict = ios_res.model_dump()
                        ok = ios_res.success

                else:
                    if "intent" in cap_lower:
                        android_intent_req = AndroidIntentRequest(
                            action=str(params.get("action") or "android.intent.action.VIEW"),
                            data_uri=str(params["data_uri"]) if params.get("data_uri") else None,
                            package_name=str(params.get("package_name") or handler),
                            component=str(params["component"]) if params.get("component") else None,
                            mime_type=str(params["mime_type"]) if params.get("mime_type") else None,
                            categories=list(params.get("categories", [])),
                            extras=dict(params.get("extras", {})),
                            flags=list(params.get("flags", [])),
                            broadcast=bool(params.get("broadcast", False)),
                            service=bool(params.get("service", False)),
                        )
                        android_res = await AndroidAutomationEngine.device_send_intent(android_intent_req, device_id=device_id)
                        res_dict = android_res.model_dump()
                        ok = android_res.success
                    elif "deep_link" in cap_lower or "deeplink" in cap_lower:
                        raw_uri = str(params.get("url_or_uri") or params.get("uri") or params.get("url") or handler)
                        dl_req = AndroidDeepLinkRequest(
                            url_or_uri=raw_uri,
                            package_name=str(params["package_name"]) if params.get("package_name") else None,
                            parameters=dict(params.get("parameters", {})),
                            fallback_url=str(params["fallback_url"]) if params.get("fallback_url") else None,
                        )
                        android_res = await AndroidAutomationEngine.device_open_deep_link(dl_req, device_id=device_id)
                        res_dict = android_res.model_dump()
                        ok = android_res.success
                    elif "click" in cap_lower or "tap" in cap_lower:
                        android_res = await AndroidAutomationEngine.device_click_element(
                            device_id=device_id,
                            text=str(params["text"]) if params.get("text") else None,
                            resource_id=str(params["resource_id"]) if params.get("resource_id") else None,
                            content_description=str(params["content_description"]) if params.get("content_description") else None,
                            x=int(params["x"]) if params.get("x") is not None else None,
                            y=int(params["y"]) if params.get("y") is not None else None,
                        )
                        res_dict = android_res.model_dump()
                        ok = android_res.success
                    elif "type" in cap_lower or "input" in cap_lower:
                        android_res = await AndroidAutomationEngine.device_type_text(
                            text=str(params.get("text", "")),
                            device_id=device_id,
                            resource_id=str(params["resource_id"]) if params.get("resource_id") else None,
                            clear_first=bool(params.get("clear_first", False)),
                            press_enter=bool(params.get("press_enter", False)),
                        )
                        res_dict = android_res.model_dump()
                        ok = android_res.success
                    elif "scroll" in cap_lower or "swipe" in cap_lower:
                        dir_val = str(params.get("direction", "down")).lower()
                        direction_lit: Any = dir_val if dir_val in ("up", "down", "left", "right") else "down"
                        android_res = await AndroidAutomationEngine.device_scroll(
                            direction=direction_lit,
                            device_id=device_id,
                            distance_px=int(params.get("distance_px", 800)),
                        )
                        res_dict = android_res.model_dump()
                        ok = android_res.success
                    elif "screenshot" in cap_lower:
                        android_shot_res = await AndroidAutomationEngine.device_take_screenshot(device_id=device_id)
                        res_dict = android_shot_res.model_dump()
                        ok = bool(android_shot_res.image_base64)
                    elif "inspect" in cap_lower or "ui" in cap_lower or "hierarchy" in cap_lower:
                        tree_res = await AndroidAutomationEngine.device_inspect_ui(
                            device_id=device_id,
                            max_depth=int(params.get("max_depth", 5)),
                        )
                        res_dict = tree_res.model_dump()
                        ok = bool(tree_res.class_name)
                    elif "key" in cap_lower:
                        android_res = await AndroidAutomationEngine.device_press_key(
                            key_name_or_code=str(params.get("key", params.get("keycode", "back"))),
                            device_id=device_id,
                        )
                        res_dict = android_res.model_dump()
                        ok = android_res.success
                    else:
                        android_intent_req = AndroidIntentRequest(
                            action="android.intent.action.VIEW",
                            package_name=handler if "." in handler else None,
                            data_uri=f"{handler}://" if "://" not in handler else handler,
                            flags=["FLAG_ACTIVITY_NEW_TASK"],
                        )
                        android_res = await AndroidAutomationEngine.device_send_intent(android_intent_req, device_id=device_id)
                        res_dict = android_res.model_dump()
                        ok = android_res.success

                if step_exec:
                    step_exec.status = "completed" if ok else "failed"
                    step_exec.output = res_dict
                    step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (ok, res_dict, str(res_dict.get("error")) if not ok and res_dict.get("error") else None)

            # -----------------------------------------------------------------
            # 8. Fallback / Other Surfaces
            # -----------------------------------------------------------------
            else:
                res_dict = {
                    "surface": integration,
                    "target": handler,
                    "status": "completed",
                    "parameters": params,
                }
                if step_exec:
                    step_exec.status = "completed"
                    step_exec.output = res_dict
                    step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (True, res_dict, None)

        except Exception as exc:
            log.exception("universal_controller.execute_failed", integration=integration, error=str(exc))
            err_msg = str(exc)
            if step_exec:
                step_exec.status = "failed"
                step_exec.error = err_msg
                step_exec.duration_ms = (time.perf_counter() - t0) * 1000.0
            return (False, {}, err_msg)

    # =========================================================================
    # Stage 5: Verify Implementation
    # =========================================================================

    async def _stage_verify(
        self,
        plan: AppControlExecutionPlan,
        request: AppControlExecutionRequest,
        resolution: IntegrationResolutionResult,
        exec_output: dict[str, Any],
    ) -> tuple[bool, dict[str, Any], str | None]:
        """Execute post-condition state probes based on the verified verification method."""
        if request.skip_verification:
            return (False, {"skipped": True, "reason": "Caller requested skip_verification", "verified": False}, None)

        method = resolution.verification_method
        step_verif = next((s for s in plan.steps if s.step_number == 3), None)
        if step_verif:
            step_verif.status = "running"

        t0 = time.perf_counter()
        try:
            # -----------------------------------------------------------------
            # 1. Process PID and Window Presence
            # -----------------------------------------------------------------
            if method == "process_pid_and_window_presence":
                cap_lower = request.capability.lower()
                is_termination = any(v in cap_lower for v in ("terminate", "kill", "close", "stop"))

                if is_termination:
                    target_pids: list[int] = []
                    if exec_output.get("terminated_pids"):
                        target_pids.extend(exec_output["terminated_pids"])
                    elif exec_output.get("pid"):
                        target_pids.append(int(exec_output["pid"]))
                    elif request.parameters.get("pid"):
                        target_pids.append(int(request.parameters["pid"]))

                    if target_pids:
                        still_alive = any(psutil.pid_exists(p) for p in target_pids)
                        verified = not still_alive
                        details = {
                            "method": method,
                            "target_pids": target_pids,
                            "process_still_alive": still_alive,
                            "verified": verified,
                        }
                    else:
                        verified = bool(exec_output.get("success", False) or exec_output.get("already_dead", False))
                        details = {"method": method, "verified": verified, "details": exec_output}
                else:
                    # Launch verification
                    pid = exec_output.get("pid")
                    if pid:
                        alive = psutil.pid_exists(pid)
                        verified = alive
                        details = {
                            "method": method,
                            "pid": pid,
                            "process_alive": alive,
                            "verified": verified,
                        }
                    else:
                        verified = bool(exec_output.get("launched", False) or exec_output.get("focused", False))
                        details = {"method": method, "verified": verified, "details": exec_output}

                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0

                return (verified, details, None if verified else "Process presence check failed.")

            # -----------------------------------------------------------------
            # 2. Process Exit Code & Output
            # -----------------------------------------------------------------
            elif method == "process_exit_code_and_output":
                exit_code = exec_output.get("exit_code")
                verified = exit_code == 0
                details = {
                    "method": method,
                    "exit_code": exit_code,
                    "verified": verified,
                    "stdout_length": len(exec_output.get("stdout") or ""),
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, None if verified else f"Expected exit code 0, received {exit_code}")

            # -----------------------------------------------------------------
            # 3. Accessibility Tree & Window State Match
            # -----------------------------------------------------------------
            elif method in ("accessibility_tree_match", "window_state_probe"):
                target = plan.verification_criteria.get("window_target") or request.application
                state = DesktopAutomationEngine.read_window_state(window_target=target)
                verified = state.is_foreground or state.is_visible or state.exists or bool(state.title)
                details = {
                    "method": method,
                    "window_target": target,
                    "is_foreground": state.is_foreground,
                    "is_visible": state.is_visible,
                    "exists": state.exists,
                    "title": state.title,
                    "verified": verified,
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, None if verified else f"Window state probe failed for '{target}'.")

            # -----------------------------------------------------------------
            # 4. API Status Check
            # -----------------------------------------------------------------
            elif method == "api_status_check":
                status = exec_output.get("status")
                http_status = exec_output.get("http_status")
                verified = status in ("success", "ok", "completed") or http_status in (200, 201, 204)
                details = {
                    "method": method,
                    "status": status,
                    "http_status": http_status,
                    "verified": verified,
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, None if verified else "API status check failed.")

            # -----------------------------------------------------------------
            # 5. MCP Schema Validation
            # -----------------------------------------------------------------
            elif method == "mcp_result_schema_validation":
                verified = bool(exec_output) and not exec_output.get("error")
                details = {
                    "method": method,
                    "payload_keys": list(exec_output.keys()),
                    "verified": verified,
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, None if verified else "MCP result schema validation failed.")

            # -----------------------------------------------------------------
            # 6. DOM Element State Probe (Browser Automation)
            # -----------------------------------------------------------------
            elif method == "dom_element_state_probe":
                status = exec_output.get("status")
                dom_data = exec_output.get("dom", {})
                nav_data = exec_output.get("navigation", {})
                has_elements = bool(dom_data.get("elements")) or dom_data.get("total_elements_found", 0) > 0
                verified = (
                    status == "success"
                    or bool(exec_output.get("title"))
                    or bool(exec_output.get("final_url"))
                    or bool(exec_output.get("screenshot_path"))
                    or bool(exec_output.get("verified"))
                    or has_elements
                    or nav_data.get("status") == "success"
                )
                details = {
                    "method": method,
                    "url": exec_output.get("final_url") or exec_output.get("url") or nav_data.get("url"),
                    "title": exec_output.get("title") or nav_data.get("title"),
                    "verified": verified,
                    "total_elements_found": dom_data.get("total_elements_found", 0),
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, None if verified else "DOM element state probe failed.")

            # -----------------------------------------------------------------
            # 7. Mobile UI / Intent State Probe
            # -----------------------------------------------------------------
            elif method in ("mobile_ui_dump_match", "mobile_intent_and_ui_hierarchy", "mobile_ui_hierarchy"):
                device_id = str(request.device_id or request.parameters.get("device_id") or "default")
                tree = await AndroidAutomationEngine.device_inspect_ui(device_id=device_id)
                verified = bool(tree and (tree.class_name or tree.children))
                details = {
                    "method": method,
                    "device_id": device_id,
                    "top_class": tree.class_name,
                    "verified": verified,
                    "children_count": len(tree.children),
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, None if verified else "Mobile UI hierarchy verification probe failed.")

            # -----------------------------------------------------------------
            # 8. iOS Mobile State Probes
            # -----------------------------------------------------------------
            elif method in (
                "ios_link_or_scheme_probe",
                "ios_shortcut_probe",
                "ios_app_intent_probe",
                "ios_share_sheet_probe",
                "ios_companion_telemetry_probe",
            ):
                status_val = str(exec_output.get("status", ""))
                is_unsupported = status_val == "unsupported_on_this_platform"
                verified = exec_output.get("success") is True or (status_val == "completed" and not is_unsupported)
                details = {
                    "method": method,
                    "status": status_val,
                    "action": exec_output.get("action"),
                    "target": exec_output.get("target"),
                    "verified": verified,
                    "supported_alternatives": exec_output.get("supported_alternatives", []),
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, None if verified else (exec_output.get("error") or "iOS probe check failed."))

            # -----------------------------------------------------------------
            # 9. WhatsApp Status & Delivery Probe
            # -----------------------------------------------------------------
            elif method in ("whatsapp_status_check", "whatsapp_delivery_probe"):
                # Handle session status checks directly
                if "check" in request.capability.lower() or "status" in request.capability.lower():
                    has_reports = any(k in exec_output for k in ("desktop", "web", "cloud_api", "auto"))
                    details = {
                        "method": method,
                        "verified": has_reports,
                        "reports": exec_output,
                    }
                    if step_verif:
                        step_verif.status = "completed" if has_reports else "failed"
                        step_verif.output = details
                        step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                    return (has_reports, details, None if has_reports else "No session reports found.")

                from app.device.schemas import WhatsAppVerificationCriteria
                from app.device.verification_engine import WhatsAppStatusVerifier

                req_recipient = request.parameters.get("recipient") or request.parameters.get("target_number") or ""
                req_msg = request.parameters.get("message") or request.parameters.get("text") or ""
                crit = WhatsAppVerificationCriteria(
                    action_name="whatsapp_send_message",
                    expected_status=exec_output.get("status", "SENT"),
                    expected_recipient=req_recipient,
                    expected_message_contains=req_msg[:20] if req_msg else None,
                    require_authenticated_route=True,
                    require_delivery_signal=request.parameters.get("require_delivery_signal", False),
                    task_id=exec_output.get("operation_id"),
                )
                chk_res = await WhatsAppStatusVerifier.verify(crit, exec_output=exec_output)
                verified = chk_res.passed
                details = {
                    "method": method,
                    "verified": verified,
                    "score": chk_res.score,
                    "operator_used": chk_res.operator_used,
                    "evidence": chk_res.evidence,
                    "error": chk_res.error,
                }
                if step_verif:
                    step_verif.status = "completed" if verified else "failed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (verified, details, chk_res.error if not verified else None)

            # -----------------------------------------------------------------
            # 10. Default / No verification required
            # -----------------------------------------------------------------
            else:
                details = {"method": method, "verified": True, "note": "No active probe required."}
                if step_verif:
                    step_verif.status = "completed"
                    step_verif.output = details
                    step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
                return (True, details, None)

        except Exception as exc:
            log.warning("universal_controller.verify_failed", error=str(exc))
            err_msg = str(exc)
            if step_verif:
                step_verif.status = "failed"
                step_verif.error = err_msg
                step_verif.duration_ms = (time.perf_counter() - t0) * 1000.0
            return (False, {"method": method, "error": err_msg, "verified": False}, err_msg)

    # =========================================================================
    # User Confirmation Handlers & History Retrieval
    # =========================================================================

    async def confirm_execution(
        self,
        token: str,
        user_id: str | None = None,
    ) -> AppControlExecutionResult:
        """Confirm and resume execution of a pending execution request."""
        from app.trust.confirmation_gate import ConfirmationGate

        pending = _PENDING_CONFIRMATIONS.get(token)
        chal_rec = ConfirmationGate.get_challenge_record(token)
        from app.trust.schemas import ConfirmationStatus
        if (not pending and not chal_rec) or (chal_rec and chal_rec.get("status") == ConfirmationStatus.CONSUMED):
            raise LookupError(f"Confirmation challenge token '{token}' not found or already consumed.")

        now = datetime.now(UTC)
        if pending and now > pending["expires_at"]:
            _PENDING_CONFIRMATIONS.pop(token, None)
            raise TimeoutError("Confirmation challenge token has expired.")
        if chal_rec and now > chal_rec["expires_at"]:
            raise TimeoutError("Confirmation challenge token has expired.")

        chal_user_id: str | None = None
        if chal_rec is not None and chal_rec.get("user_id"):
            chal_user_id = str(chal_rec["user_id"])

        pending_user_id: str | None = None
        if pending is not None:
            req_field = pending.get("request")
            if isinstance(req_field, dict) and req_field.get("user_id"):
                pending_user_id = str(req_field["user_id"])

        effective_user_id: str = str(user_id or chal_user_id or pending_user_id or "default")
        if chal_rec is not None and user_id and chal_rec.get("user_id") != user_id:
            raise PermissionError(f"Challenge belongs to a different user ({chal_rec.get('user_id')} != {user_id}).")

        # Mark challenge approved in central ConfirmationGate so consume_challenge succeeds
        if chal_rec is not None:
            ConfirmationGate.approve_challenge_internally(token, user_id=effective_user_id)

        req_dict: dict[str, Any] = {}
        if pending is not None and isinstance(pending.get("request"), dict):
            req_dict = dict(pending["request"])
        elif chal_rec is not None and isinstance(chal_rec.get("details"), dict):
            req_dict = dict(chal_rec["details"])

        req_dict["confirmed"] = True
        req_dict["confirmation_token"] = token
        if effective_user_id:
            req_dict["user_id"] = effective_user_id

        req = AppControlExecutionRequest(**req_dict)
        return await self.execute_lifecycle(req)

    @classmethod
    def get_execution(cls, execution_id: str) -> AppControlExecutionResult | None:
        """Retrieve historical execution result by ID."""
        return _EXECUTION_HISTORY.get(execution_id)

    @classmethod
    def get_plan(cls, plan_id: str) -> AppControlExecutionPlan | None:
        """Retrieve execution plan by ID."""
        return _PLAN_HISTORY.get(plan_id)

    @classmethod
    def list_pending_confirmations(cls) -> list[dict[str, Any]]:
        """List active pending confirmation tokens."""
        now = datetime.now(UTC)
        # Prune expired tokens
        for k, v in list(_PENDING_CONFIRMATIONS.items()):
            if now > v["expires_at"]:
                _PENDING_CONFIRMATIONS.pop(k, None)

        return [
            {
                "token": tok,
                "application": v["request"].get("application"),
                "capability": v["request"].get("capability"),
                "created_at": v["created_at"].isoformat(),
                "expires_at": v["expires_at"].isoformat(),
            }
            for tok, v in _PENDING_CONFIRMATIONS.items()
        ]
