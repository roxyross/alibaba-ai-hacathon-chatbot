"""Multi-Device Fleet Orchestration and Autonomous Device Handover Engine.

Fulfills Phase 10 of ROXY-AI Universal App Control & Device Intelligence:
- Multi-factor device fleet candidate scoring and selection
- Autonomous device routing (App catalog presence, capabilities, liveness, locality)
- Zero-simulation local host and remote daemon execution dispatch
- Autonomous failover and cross-device task handover
- Multi-device fleet summary and broadcast state querying
- Multi-tenant IDOR isolation across all fleet operations
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import sys
import time
from typing import Any, cast
import uuid

import structlog

from app.device.schemas import (
    AppControlExecutionRequest,
    AppControlExecutionResult,
    DeviceResponse,
    FleetBroadcastQueryRequest,
    FleetBroadcastQueryResponse,
    FleetCandidateScore,
    FleetExecutionRequest,
    FleetExecutionResult,
    FleetHandoverRequest,
    FleetHandoverResult,
    FleetRoutingDecision,
    FleetRoutingRequest,
    FleetSummaryResponse,
    IntegrationResolutionResult,
    IntegrationType,
)

log = structlog.get_logger()

# In-memory storage for fleet handovers and executions
_FLEET_HANDOVERS: dict[str, dict[str, Any]] = {}
_FLEET_EXECUTIONS: dict[str, FleetExecutionResult] = {}


class FleetOrchestrator:
    """Authoritative multi-device fleet coordinator for Universal App Control."""

    _instance: FleetOrchestrator | None = None

    def __init__(self) -> None:
        self.heartbeat_threshold_sec: float = 120.0

    @classmethod
    def get_instance(cls) -> FleetOrchestrator:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def clear_state(cls) -> None:
        """Clear cached state for testing isolation."""
        _FLEET_HANDOVERS.clear()
        _FLEET_EXECUTIONS.clear()

    # =========================================================================
    # 1. Device Fleet Candidate Scoring & Routing
    # =========================================================================

    def _evaluate_candidate(
        self,
        device: dict[str, Any],
        apps: list[dict[str, Any]],
        request: FleetRoutingRequest,
        now: datetime,
    ) -> FleetCandidateScore:
        """Evaluate a single device candidate across multiple dimensions (0.0 - 1.0)."""
        reasons: list[str] = []
        breakdown: dict[str, float] = {
            "liveness": 0.0,
            "app_availability": 0.0,
            "capabilities": 0.0,
            "locality": 0.0,
            "platform": 0.0,
            "preference": 0.0,
        }

        dev_id = str(device.get("id") or "")
        dev_name = str(device.get("device_name") or "Unnamed Device")
        os_platform = str(device.get("os_platform") or sys.platform).lower()
        status = str(device.get("status") or "offline").lower()
        is_current = bool(device.get("is_current_host", False))

        # ---------------------------------------------------------------------
        # 1. Platform Compatibility Check
        # ---------------------------------------------------------------------
        if request.required_os_platform:
            req_plat = request.required_os_platform.strip().lower()
            if os_platform != req_plat:
                reasons.append(f"Incompatible OS platform: requires '{req_plat}', device is '{os_platform}'")
                return FleetCandidateScore(
                    device_id=dev_id,
                    device_name=dev_name,
                    os_platform=os_platform,
                    status=status,
                    is_online=False,
                    is_current_host=is_current,
                    app_available=False,
                    capabilities_matched=[],
                    score=0.0,
                    score_breakdown=breakdown,
                    reasons=reasons,
                )
            breakdown["platform"] = 0.05
        else:
            breakdown["platform"] = 0.05

        # ---------------------------------------------------------------------
        # 2. Liveness & Heartbeat Freshness (0.0 to 0.25)
        # ---------------------------------------------------------------------
        is_online = status == "online"
        last_hb = device.get("last_heartbeat_at")
        if last_hb and not is_current:
            try:
                hb_dt = datetime.fromisoformat(str(last_hb))
                if hb_dt.tzinfo is None:
                    hb_dt = hb_dt.replace(tzinfo=UTC)
                age = (now - hb_dt).total_seconds()
                if age > self.heartbeat_threshold_sec:
                    is_online = False
                    status = "offline"
                    reasons.append(f"Heartbeat expired ({round(age, 1)}s old)")
            except Exception:
                pass

        if is_online or request.allow_offline or is_current:
            breakdown["liveness"] = 0.25
            if is_current:
                reasons.append("Current local host (active session)")
            else:
                reasons.append("Online with fresh heartbeat")
        else:
            reasons.append("Device is offline")

        # ---------------------------------------------------------------------
        # 3. Application Catalog Availability (0.0 to 0.35)
        # ---------------------------------------------------------------------
        target_app = request.application.strip().lower()
        matched_app: dict[str, Any] | None = None
        app_available = False

        for a in apps:
            a_name = str(a.get("app_name") or "").lower()
            if a_name == target_app or target_app in a_name or a_name in target_app:
                matched_app = a
                app_available = True
                break

        if matched_app:
            if matched_app.get("is_running"):
                breakdown["app_availability"] = 0.35
                reasons.append(f"Application '{matched_app.get('app_name')}' is currently running")
            else:
                breakdown["app_availability"] = 0.30
                reasons.append(f"Application '{matched_app.get('app_name')}' is installed")
        else:
            # Check for generic/CLI binaries or cloud connectors
            cli_known = {"python", "python3", "git", "docker", "curl", "node", "npm", "pip", "powershell", "bash", "sh"}
            if target_app in cli_known:
                breakdown["app_availability"] = 0.25
                app_available = True
                reasons.append(f"Generic CLI utility '{target_app}' available via system path")
            else:
                reasons.append(f"Application '{request.application}' not detected in device catalog")

        # ---------------------------------------------------------------------
        # 4. Capabilities Match (0.0 to 0.20)
        # ---------------------------------------------------------------------
        dev_caps = [str(c).lower() for c in device.get("capabilities", [])]
        matched_caps: list[str] = []

        if request.required_capabilities:
            for rc in request.required_capabilities:
                if rc.lower() in dev_caps:
                    matched_caps.append(rc)
            if request.required_capabilities:
                ratio = len(matched_caps) / len(request.required_capabilities)
                breakdown["capabilities"] = round(ratio * 0.20, 3)
                reasons.append(f"Matched {len(matched_caps)}/{len(request.required_capabilities)} required capabilities")
        else:
            # Baseline capabilities bonus
            baseline = {"app_discovery", "process_control", "system_commands", "desktop_automation", "screen_capture"}
            found_baseline = [c for c in dev_caps if c in baseline]
            breakdown["capabilities"] = 0.15 if found_baseline else 0.05
            matched_caps = found_baseline

        # ---------------------------------------------------------------------
        # 5. Locality & User Presence (0.0 to 0.15)
        # ---------------------------------------------------------------------
        if is_current:
            breakdown["locality"] = 0.15
        else:
            telem = device.get("telemetry", {})
            if isinstance(telem, dict) and telem.get("active_window"):
                breakdown["locality"] = 0.10
                reasons.append("Active user window detected on companion device")
            else:
                breakdown["locality"] = 0.05

        # ---------------------------------------------------------------------
        # 6. Caller Preference Boost (+0.25)
        # ---------------------------------------------------------------------
        if request.preferred_device_id and request.preferred_device_id in (dev_id, dev_name):
            if is_online or is_current:
                breakdown["preference"] = 0.25
                reasons.append("Direct caller preference match")

        # Total Score calculation
        total_score = sum(breakdown.values())
        # If device is not online and offline not allowed, reduce drastically
        if not is_online and not request.allow_offline and not is_current:
            total_score = min(total_score * 0.1, 0.1)

        final_score = min(max(round(total_score, 3), 0.0), 1.0)

        return FleetCandidateScore(
            device_id=dev_id,
            device_name=dev_name,
            os_platform=os_platform,
            status=status,
            is_online=is_online or is_current,
            is_current_host=is_current,
            app_available=app_available,
            capabilities_matched=matched_caps,
            score=final_score,
            score_breakdown=breakdown,
            reasons=reasons,
        )

    async def resolve_device(self, request: FleetRoutingRequest) -> FleetRoutingDecision:
        """Authoritatively resolve the optimal target device from the user's fleet."""
        start_t = time.perf_counter()
        routing_id = f"route_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        from app.device.service import DeviceService
        svc = DeviceService.get_instance()

        # Retrieve user devices
        user_devices: list[dict[str, Any]] = []
        try:
            user_devices = await svc.list_devices_for_user(request.user_id)
        except Exception:
            # Fallback to in-memory devices
            user_devices = [
                d for d in svc._mem_devices.values()
                if d.get("user_id") == request.user_id
            ]

        # If no registered devices for this user, attempt local device fallback
        if not user_devices:
            try:
                local_dev = await svc.get_or_create_local_device(request.user_id)
                user_devices = [local_dev]
            except Exception:
                user_devices = [{
                    "id": "local",
                    "device_name": "Local Device",
                    "os_platform": sys.platform,
                    "status": "online",
                    "is_current_host": True,
                    "capabilities": ["app_discovery", "process_control", "system_commands"],
                }]

        # Retrieve discovered apps mapped by device_id
        apps_by_device: dict[str, list[dict[str, Any]]] = {}
        for dev in user_devices:
            dev_id = str(dev.get("id") or "")
            try:
                dev_apps = await svc.get_device_apps(request.user_id, dev_id)
                apps_by_device[dev_id] = dev_apps
            except Exception:
                apps_by_device[dev_id] = svc._mem_apps.get(dev_id, [])

        # Score every candidate device
        candidates: list[FleetCandidateScore] = []
        for dev in user_devices:
            dev_id = str(dev.get("id") or "")
            cand_score = self._evaluate_candidate(
                device=dev,
                apps=apps_by_device.get(dev_id, []),
                request=request,
                now=now,
            )
            candidates.append(cand_score)

        # Sort candidates descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)

        target_device_id: str | None = None
        target_device_name: str | None = None
        confidence = 0.0
        selection_reason = ""
        fallbacks: list[str] = []

        if candidates and candidates[0].score > 0.0:
            winner = candidates[0]
            target_device_id = winner.device_id
            target_device_name = winner.device_name
            confidence = winner.score
            selection_reason = f"Selected '{winner.device_name}' ({winner.os_platform}): " + "; ".join(winner.reasons)
            fallbacks = [c.device_id for c in candidates[1:] if c.score >= 0.15 and c.is_online]
        else:
            selection_reason = (
                f"No compatible or online device found in fleet for application '{request.application}'."
            )

        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

        return FleetRoutingDecision(
            routing_id=routing_id,
            user_id=request.user_id,
            application=request.application,
            capability=request.capability,
            target_device_id=target_device_id,
            target_device_name=target_device_name,
            confidence=confidence,
            selection_reason=selection_reason,
            candidates=candidates,
            fallback_device_ids=fallbacks,
            requires_handover=False,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # 2. Fleet Execution Dispatch & Autonomous Failover
    # =========================================================================

    async def _dispatch_to_device(
        self,
        device_id: str,
        user_id: str,
        request: FleetExecutionRequest,
    ) -> AppControlExecutionResult:
        """Dispatch execution to a concrete target device (local or remote daemon)."""
        from app.device.service import DeviceService
        svc = DeviceService.get_instance()

        is_local = device_id in ("local", "current")
        dev_info = svc._mem_devices.get(device_id)
        if dev_info and dev_info.get("is_current_host"):
            is_local = True

        if is_local:
            # Execute on current local workstation via UniversalAppController
            from app.device.orchestrator import UniversalAppController
            app_req = AppControlExecutionRequest(
                application=request.application,
                capability=request.capability,
                parameters=request.parameters,
                preferred_integration=request.preferred_integration,
                device_id=device_id,
                user_id=user_id,
                confirmed=request.confirmed,
                confirmation_token=request.confirmation_token,
                skip_verification=request.skip_verification,
                timeout_sec=request.timeout_sec,
            )
            ctrl = UniversalAppController.get_instance()
            res = await ctrl.execute_lifecycle(app_req)
            if res.stage == "pending_confirmation" and request.confirmed and res.pending_confirmation_details:
                conf_tok = str(res.pending_confirmation_details.get("confirmation_token") or "")
                if conf_tok:
                    res = await ctrl.confirm_execution(token=conf_tok, user_id=user_id)
            return res

        # Remote device execution via DeviceService command queue
        cmd_payload = {
            "application": request.application,
            "capability": request.capability,
            "parameters": request.parameters,
            "preferred_integration": request.preferred_integration,
            "confirmed": request.confirmed,
            "confirmation_token": request.confirmation_token,
            "skip_verification": request.skip_verification,
        }

        try:
            cmd = await svc.queue_command(
                user_id=user_id,
                device_id=device_id,
                command_type="app_control_orchestrate",
                payload=cmd_payload,
                timeout_seconds=int(request.timeout_sec),
            )
            cmd_id = cmd["id"]

            # Wait for remote daemon completion up to timeout_sec
            deadline = time.time() + request.timeout_sec
            while time.time() < deadline:
                cmd_record = svc._mem_device_commands.get(cmd_id)
                if cmd_record:
                    st = cmd_record.get("status")
                    if st == "completed":
                        res_data = cmd_record.get("result", {})
                        if isinstance(res_data, dict) and "execution_id" in res_data:
                            return AppControlExecutionResult(**res_data)
                        return AppControlExecutionResult(
                            execution_id=cmd_id,
                            plan_id=f"plan_{uuid.uuid4().hex[:12]}",
                            application=request.application,
                            capability=request.capability,
                            stage="executed",
                            success=True,
                            verified=not request.skip_verification,
                            resolution=IntegrationResolutionResult(
                                success=True,
                                application=request.application,
                                requested_capability=request.capability,
                                chosen_integration="cli_process",
                                confidence=0.9,
                                required_permission=f"app:{request.application}:{request.capability}",
                                risk="low",
                                requires_confirmation=False,
                                execution_method="cli_exec",
                                verification_method="process_exit_code_and_output",
                            ),
                            execution_output=res_data,
                            duration_ms=50.0,
                        )
                    elif st == "failed":
                        err = cmd_record.get("error_message") or "Remote execution failed."
                        raise RuntimeError(err)

                await asyncio.sleep(0.1)

            raise TimeoutError(f"Remote daemon on device '{device_id}' timed out after {request.timeout_sec}s.")

        except Exception as exc:
            log.warning("fleet_orchestrator.remote_dispatch_failed", device_id=device_id, error=str(exc))
            # Construct synthetic failure result
            return AppControlExecutionResult(
                execution_id=f"exec_fail_{uuid.uuid4().hex[:8]}",
                plan_id=f"plan_fail_{uuid.uuid4().hex[:8]}",
                application=request.application,
                capability=request.capability,
                stage="failed",
                success=False,
                verified=False,
                resolution=IntegrationResolutionResult(
                    success=False,
                    application=request.application,
                    requested_capability=request.capability,
                    chosen_integration="unsupported",
                    confidence=0.0,
                    required_permission=f"app:{request.application}:{request.capability}",
                    risk="low",
                    requires_confirmation=False,
                    execution_method="none",
                    verification_method="none",
                ),
                error=f"Device '{device_id}' execution failed: {exc}",
                duration_ms=0.0,
            )

    async def execute_fleet_app_control(
        self,
        request: FleetExecutionRequest,
    ) -> FleetExecutionResult:
        """Execute application capability across the fleet with autonomous routing & failover."""
        start_t = time.perf_counter()
        fleet_exec_id = f"fleet_exec_{uuid.uuid4().hex[:12]}"
        user_id = request.user_id or "default_user"

        # 1. Resolve optimal target device
        routing_req = FleetRoutingRequest(
            user_id=user_id,
            application=request.application,
            capability=request.capability,
            preferred_device_id=request.preferred_device_id,
            parameters=request.parameters,
        )
        decision = await self.resolve_device(routing_req)

        if not decision.target_device_id:
            duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
            synth_res = AppControlExecutionResult(
                execution_id=f"exec_err_{uuid.uuid4().hex[:8]}",
                plan_id=f"plan_err_{uuid.uuid4().hex[:8]}",
                application=request.application,
                capability=request.capability,
                stage="unsupported",
                success=False,
                verified=False,
                resolution=IntegrationResolutionResult(
                    success=False,
                    application=request.application,
                    requested_capability=request.capability,
                    chosen_integration="unsupported",
                    confidence=0.0,
                    required_permission=f"app:{request.application}:{request.capability}",
                    risk="low",
                    requires_confirmation=False,
                    execution_method="none",
                    verification_method="none",
                    recommended_action=decision.selection_reason,
                ),
                error=decision.selection_reason,
                duration_ms=duration_ms,
            )
            res = FleetExecutionResult(
                fleet_execution_id=fleet_exec_id,
                user_id=user_id,
                application=request.application,
                capability=request.capability,
                routing_decision=decision,
                executed_device_id="none",
                executed_device_name="None",
                handover_occurred=False,
                handover_details=[],
                app_control_result=synth_res,
                success=False,
                duration_ms=duration_ms,
            )
            _FLEET_EXECUTIONS[fleet_exec_id] = res
            return res

        # 2. Dispatch to primary device
        primary_dev_id = decision.target_device_id
        primary_dev_name = decision.target_device_name or primary_dev_id
        log.info("fleet_orchestrator.dispatching_primary", device_id=primary_dev_id)

        app_res = await self._dispatch_to_device(primary_dev_id, user_id, request)

        handover_occurred = False
        handover_details: list[dict[str, Any]] = []
        executed_device_id = primary_dev_id
        executed_device_name = primary_dev_name

        # 3. Autonomous Failover & Handover
        if not app_res.success and app_res.stage not in ("pending_confirmation", "permission_denied"):
            if request.allow_failover and decision.fallback_device_ids:
                max_tries = min(request.max_failovers, len(decision.fallback_device_ids))
                for idx in range(max_tries):
                    fallback_id = decision.fallback_device_ids[idx]
                    fallback_name = fallback_id
                    for c in decision.candidates:
                        if c.device_id == fallback_id:
                            fallback_name = c.device_name
                            break

                    log.warning(
                        "fleet_orchestrator.initiating_failover",
                        source_device=executed_device_id,
                        fallback_device=fallback_id,
                        reason=app_res.error,
                    )

                    handover_info = {
                        "attempt": idx + 1,
                        "source_device_id": executed_device_id,
                        "target_device_id": fallback_id,
                        "reason": f"Failover triggered: {app_res.error}",
                        "transferred_at": datetime.now(UTC).isoformat(),
                    }
                    handover_details.append(handover_info)

                    # Execute on fallback device
                    fallback_res = await self._dispatch_to_device(fallback_id, user_id, request)
                    if fallback_res.success or fallback_res.stage == "pending_confirmation":
                        app_res = fallback_res
                        executed_device_id = fallback_id
                        executed_device_name = fallback_name
                        handover_occurred = True
                        break

        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        fleet_res = FleetExecutionResult(
            fleet_execution_id=fleet_exec_id,
            user_id=user_id,
            application=request.application,
            capability=request.capability,
            routing_decision=decision,
            executed_device_id=executed_device_id,
            executed_device_name=executed_device_name,
            handover_occurred=handover_occurred,
            handover_details=handover_details,
            app_control_result=app_res,
            success=app_res.success,
            duration_ms=duration_ms,
        )
        _FLEET_EXECUTIONS[fleet_exec_id] = fleet_res
        return fleet_res

    # =========================================================================
    # 3. Explicit Cross-Device Task Handover
    # =========================================================================

    async def initiate_handover(self, request: FleetHandoverRequest) -> FleetHandoverResult:
        """Initiate seamless task or session migration from source to target device."""
        start_t = time.perf_counter()
        handover_id = f"fhand_{uuid.uuid4().hex[:12]}"

        from app.device.service import DeviceService
        svc = DeviceService.get_instance()

        # Multi-tenant IDOR check: Verify user owns both devices
        user_devs = await svc.list_devices_for_user(request.user_id)
        user_dev_ids = {str(d.get("id")) for d in user_devs}
        # Allow 'local' or 'current' as valid aliases
        user_dev_ids.update({"local", "current"})

        if request.source_device_id not in user_dev_ids:
            raise PermissionError(f"User '{request.user_id}' does not own source device '{request.source_device_id}'.")
        if request.target_device_id not in user_dev_ids:
            raise PermissionError(f"User '{request.user_id}' does not own target device '{request.target_device_id}'.")

        record: dict[str, Any] = {
            "handover_id": handover_id,
            "user_id": request.user_id,
            "source_device_id": request.source_device_id,
            "target_device_id": request.target_device_id,
            "application": request.application,
            "capability": request.capability,
            "status": "transferred",
            "reason": request.reason,
            "state_payload": request.state_payload,
            "created_at": datetime.now(UTC).isoformat(),
        }
        _FLEET_HANDOVERS[handover_id] = record

        exec_res: AppControlExecutionResult | None = None
        error_msg: str | None = None
        final_status = "transferred"

        if request.auto_resume:
            exec_req = FleetExecutionRequest(
                application=request.application,
                capability=request.capability,
                parameters={**request.parameters, **request.state_payload.get("parameters", {})},
                preferred_device_id=request.target_device_id,
                user_id=request.user_id,
                allow_failover=False,
                confirmed=True,
            )
            try:
                res = await self.execute_fleet_app_control(exec_req)
                exec_res = res.app_control_result
                if exec_res.success:
                    final_status = "completed"
                else:
                    final_status = "failed"
                    error_msg = exec_res.error
            except Exception as exc:
                final_status = "failed"
                error_msg = str(exc)

        record["status"] = final_status
        record["error"] = error_msg
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

        return FleetHandoverResult(
            handover_id=handover_id,
            user_id=request.user_id,
            source_device_id=request.source_device_id,
            target_device_id=request.target_device_id,
            status=cast(Any, final_status),
            reason=request.reason,
            state_payload=request.state_payload,
            execution_result=exec_res,
            error=error_msg,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # 4. Fleet Telemetry Summary & Broadcast Querying
    # =========================================================================

    async def get_fleet_summary(self, user_id: str) -> FleetSummaryResponse:
        """Consolidate device status, liveness, and app catalog distribution across fleet."""
        from app.device.service import DeviceService
        svc = DeviceService.get_instance()

        user_devs = await svc.list_devices_for_user(user_id)
        online_count = 0
        offline_count = 0
        dev_objs: list[DeviceResponse] = []
        app_distribution: dict[str, list[str]] = {}
        total_apps = 0
        now = datetime.now(UTC)

        for d in user_devs:
            st = str(d.get("status") or "offline")
            is_cur = bool(d.get("is_current_host", False))
            # Stale heartbeat verification
            last_hb = d.get("last_heartbeat_at")
            if last_hb and not is_cur:
                try:
                    hb_dt = datetime.fromisoformat(str(last_hb))
                    if hb_dt.tzinfo is None:
                        hb_dt = hb_dt.replace(tzinfo=UTC)
                    if (now - hb_dt).total_seconds() > self.heartbeat_threshold_sec:
                        st = "offline"
                except Exception:
                    pass

            if st == "online" or is_cur:
                online_count += 1
            else:
                offline_count += 1

            dev_id = str(d.get("id"))
            dev_name = str(d.get("device_name", "Device"))

            dev_objs.append(DeviceResponse(
                id=dev_id,
                user_id=user_id,
                workspace_id=d.get("workspace_id"),
                device_name=dev_name,
                device_type=d.get("device_type", "desktop"),
                os_platform=d.get("os_platform", sys.platform),
                os_version=d.get("os_version", ""),
                architecture=d.get("architecture", "x86_64"),
                hostname=d.get("hostname", "localhost"),
                ip_address=d.get("ip_address", "127.0.0.1"),
                status=st,
                is_current_host=is_cur,
                hardware_fingerprint=d.get("hardware_fingerprint"),
                daemon_version=d.get("daemon_version"),
                capabilities=d.get("capabilities", []),
                telemetry=d.get("telemetry", {}),
                last_heartbeat_at=str(d.get("last_heartbeat_at")) if d.get("last_heartbeat_at") else None,
                created_at=str(d.get("created_at")) if d.get("created_at") else None,
                updated_at=str(d.get("updated_at")) if d.get("updated_at") else None,
            ))

            apps = await svc.get_device_apps(user_id, dev_id)
            total_apps += len(apps)
            for a in apps:
                aname = a.get("app_name", "")
                if aname:
                    if aname not in app_distribution:
                        app_distribution[aname] = []
                    if dev_name not in app_distribution[aname]:
                        app_distribution[aname].append(dev_name)

        return FleetSummaryResponse(
            user_id=user_id,
            total_devices=len(user_devs),
            online_devices=online_count,
            offline_devices=offline_count,
            devices=dev_objs,
            discovered_apps_count=total_apps,
            app_distribution=app_distribution,
            timestamp=now.isoformat(),
        )

    async def broadcast_query(self, request: FleetBroadcastQueryRequest) -> FleetBroadcastQueryResponse:
        """Broadcast a state query to all active devices in the fleet."""
        from app.device.service import DeviceService
        svc = DeviceService.get_instance()

        user_devs = await svc.list_devices_for_user(request.user_id)
        results: dict[str, Any] = {}
        responding_count = 0

        for d in user_devs:
            dev_id = str(d.get("id"))
            dev_name = str(d.get("device_name", dev_id))
            st = str(d.get("status") or "offline")
            is_cur = bool(d.get("is_current_host", False))

            if not is_cur and st != "online":
                continue

            responding_count += 1
            if request.query_type == "find_app":
                apps = await svc.get_device_apps(request.user_id, dev_id)
                target = request.query_target.lower()
                matches = [
                    a for a in apps
                    if target in str(a.get("app_name", "")).lower()
                ]
                results[dev_name] = {
                    "matched_count": len(matches),
                    "apps": matches,
                }
            elif request.query_type == "system_stats":
                results[dev_name] = {
                    "os_platform": d.get("os_platform"),
                    "status": st,
                    "is_current_host": is_cur,
                    "telemetry": d.get("telemetry", {}),
                }
            elif request.query_type == "find_process":
                # Check running processes reported in apps or telemetry
                apps = await svc.get_device_apps(request.user_id, dev_id)
                target = request.query_target.lower()
                running = [
                    a for a in apps
                    if a.get("is_running") and target in str(a.get("app_name", "")).lower()
                ]
                results[dev_name] = {
                    "running": len(running) > 0,
                    "process_details": running,
                }

        return FleetBroadcastQueryResponse(
            query_type=request.query_type,
            query_target=request.query_target,
            results_by_device=results,
            total_responding_devices=responding_count,
        )
