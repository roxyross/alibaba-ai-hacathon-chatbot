"""Conversational Grounding Engine for Device & Multi-Device Fleet Control.

Bridges natural language chat requests (via runtime_chat / runtime_chat_stream) directly into
FleetOrchestrator, UniversalAppController, and DeviceService under the Zero Simulation doctrine.
"""

from __future__ import annotations

import difflib
from typing import Any
import structlog

from app.device.intent_parser import DeviceIntentParser, DeviceIntentType, ParsedDeviceIntent
from app.device.schemas import (
    FleetBroadcastQueryResponse,
    FleetExecutionResult,
    FleetHandoverResult,
    FleetSummaryResponse,
)
from app.device.service import DeviceService

log = structlog.get_logger()


class DeviceConversationalGrounder:
    """Evaluates and executes conversational device and fleet actions directly for the chat agent."""

    # Active pending confirmation tokens per session/user for chat approval
    _PENDING_CHAT_CONFIRMATIONS: dict[str, str] = {}

    @classmethod
    def _match_device(cls, hint: str, devices: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Fuzzy match a natural language device hint against a list of enrolled devices."""
        if not devices:
            return None

        clean_hint = hint.strip().lower()

        # 1. Exact ID match
        for d in devices:
            if d.get("id") == hint or str(d.get("id", "")).lower() == clean_hint:
                return d

        # 2. Substring or keyword in device_name / hostname / device_type
        for d in devices:
            name = str(d.get("device_name", "")).lower()
            host = str(d.get("hostname", "")).lower()
            dtype = str(d.get("device_type", "")).lower()
            platform = str(d.get("os_platform", "")).lower()

            if clean_hint in name or clean_hint in host:
                return d
            if clean_hint in dtype or clean_hint in platform:
                return d

        # 3. Component word matching (e.g. "desktop", "laptop", "office", "living room")
        words = clean_hint.split()
        for w in words:
            if len(w) < 3:
                continue
            for d in devices:
                name = str(d.get("device_name", "")).lower()
                dtype = str(d.get("device_type", "")).lower()
                if w in name or w in dtype:
                    return d

        # 4. Difflib close match on device names
        names_map = {str(d.get("device_name", "")).lower(): d for d in devices}
        matches = difflib.get_close_matches(clean_hint, list(names_map.keys()), n=1, cutoff=0.5)
        if matches:
            return names_map[matches[0]]

        return None

    @classmethod
    async def handle_conversational_request(
        cls,
        user_id: str,
        message: str,
        session_id: str | None = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Evaluate user message for device/fleet intents and execute autonomously.

        Returns:
            (handled: bool, response_markdown: str, metadata: dict | None)
        """
        service = DeviceService.get_instance()
        trimmed = message.strip()
        lower = trimmed.lower()

        # ---------------------------------------------------------------------
        # 0. Check if user is approving a pending confirmation token in chat
        # ---------------------------------------------------------------------
        session_key = session_id or user_id
        if lower in ("confirm", "approve", "yes, confirm", "yes", "proceed"):
            pending_token = cls._PENDING_CHAT_CONFIRMATIONS.get(session_key)
            if pending_token:
                try:
                    conf_res = await service.confirm_app_control(confirmation_token=pending_token)
                    cls._PENDING_CHAT_CONFIRMATIONS.pop(session_key, None)
                    if conf_res.success:
                        exec_out = conf_res.execution_output or {}
                        stdout = exec_out.get("stdout") or exec_out.get("output") or ""
                        out_snippet = f"\n\n```text\n{stdout}\n```" if stdout else ""
                        msg = (
                            f"✅ **Action Confirmed & Executed Successfully**\n\n"
                            f"- **Application:** `{conf_res.application}`\n"
                            f"- **Capability:** `{conf_res.capability}`\n"
                            f"- **Verified:** {conf_res.verified}\n"
                            f"- **Duration:** {conf_res.duration_ms:.1f}ms{out_snippet}"
                        )
                        return (True, msg, conf_res.model_dump())
                    else:
                        msg = f"❌ **Execution Failed After Confirmation:** {conf_res.error}"
                        return (True, msg, conf_res.model_dump())
                except Exception as exc:
                    return (True, f"❌ Failed to confirm action: {exc}", None)

        if lower in ("cancel", "deny", "abort", "no"):
            if session_key in cls._PENDING_CHAT_CONFIRMATIONS:
                cls._PENDING_CHAT_CONFIRMATIONS.pop(session_key, None)
                return (True, "🛑 **Action Cancelled.** The pending operation was discarded.", None)

        # ---------------------------------------------------------------------
        # 1. Parse Natural Language Device Intent
        # ---------------------------------------------------------------------
        intent = DeviceIntentParser.parse(trimmed)
        if intent.intent_type == DeviceIntentType.UNKNOWN:
            return (False, "", None)

        log.info(
            "device_grounding.intent_detected",
            intent_type=intent.intent_type,
            application=intent.application,
            capability=intent.capability,
            target_device=intent.target_device_hint,
            user_id=user_id,
        )

        # ---------------------------------------------------------------------
        # 2. Handle Fleet Summary
        # ---------------------------------------------------------------------
        if intent.intent_type == DeviceIntentType.FLEET_SUMMARY:
            try:
                summary: FleetSummaryResponse = await service.get_fleet_summary(user_id=user_id)
                dev_rows = []
                for d in summary.devices:
                    status_emoji = "🟢" if d.status == "online" else "🔴"
                    host_badge = " *(Active Host)*" if d.is_current_host else ""
                    dev_rows.append(
                        f"| {status_emoji} **{d.device_name}**{host_badge} | `{d.os_platform}` | {d.device_type} | `{d.status}` | `{d.id[:8]}...` |"
                    )

                table_str = (
                    "| Device Name | Platform | Type | Status | Device ID |\n"
                    "| :--- | :--- | :--- | :--- | :--- |\n"
                    + "\n".join(dev_rows)
                ) if dev_rows else "*No devices enrolled yet.*"

                app_dist_lines = []
                for app_name, dev_list in summary.app_distribution.items():
                    app_dist_lines.append(f"- **{app_name}**: Available on {', '.join(dev_list)}")
                app_dist_str = "\n".join(app_dist_lines[:10]) if app_dist_lines else "*No applications indexed yet.*"

                markdown = (
                    f"### 🖥️ Roxy Multi-Device Fleet Status\n\n"
                    f"- **Total Enrolled Devices:** {summary.total_devices}\n"
                    f"- **Online & Connected:** {summary.online_devices} | **Offline:** {summary.offline_devices}\n"
                    f"- **Total Discovered Apps:** {summary.discovered_apps_count}\n\n"
                    f"#### Enrolled Devices\n\n{table_str}\n\n"
                    f"#### Application Distribution\n\n{app_dist_str}"
                )
                return (True, markdown, summary.model_dump())
            except Exception as exc:
                log.exception("device_grounding.fleet_summary_failed", error=str(exc))
                return (True, f"❌ Failed to query fleet status: {exc}", None)

        # ---------------------------------------------------------------------
        # 3. Handle Fleet Broadcast Query
        # ---------------------------------------------------------------------
        if intent.intent_type == DeviceIntentType.FLEET_BROADCAST:
            try:
                q_type = intent.parameters.get("query_type", "find_app")
                q_target = intent.parameters.get("query_target", "")
                b_res: FleetBroadcastQueryResponse = await service.broadcast_fleet_query(
                    user_id=user_id,
                    query_type=q_type,
                    query_target=q_target,
                )
                results_lines = []
                for dev_name, r in b_res.results_by_device.items():
                    results_lines.append(f"- **{dev_name}**: {r.get('status', 'responding')}")
                    if "matched_apps" in r:
                        for app in r["matched_apps"]:
                            results_lines.append(f"  * App: `{app.get('app_name')}` (Running: {app.get('is_running')})")

                md = (
                    f"### 📡 Fleet Broadcast Query Results\n\n"
                    f"- **Query:** `{q_type}` -> `{q_target}`\n"
                    f"- **Responding Devices:** {b_res.total_responding_devices}\n\n"
                    + "\n".join(results_lines)
                )
                return (True, md, b_res.model_dump())
            except Exception as exc:
                return (True, f"❌ Fleet broadcast failed: {exc}", None)

        # ---------------------------------------------------------------------
        # 4. Handle Cross-Device Handover
        # ---------------------------------------------------------------------
        if intent.intent_type == DeviceIntentType.HANDOVER:
            try:
                enrolled = await service.list_devices(user_id=user_id)
                if not enrolled:
                    return (True, "❌ No companion devices are enrolled in your fleet to hand over to.", None)

                target_device: dict[str, Any] | None = None
                if intent.target_device_hint:
                    target_device = cls._match_device(intent.target_device_hint, enrolled)

                if not target_device:
                    # Pick an alternative device that is not the current host
                    alternatives = [d for d in enrolled if not d.get("is_current_host") and d.get("status") == "online"]
                    if alternatives:
                        target_device = alternatives[0]
                    elif enrolled:
                        target_device = enrolled[0]

                if not target_device:
                    avail = ", ".join(f"'{d.get('device_name')}'" for d in enrolled)
                    return (True, f"❌ Target device '{intent.target_device_hint}' not recognized. Available devices: {avail}.", None)

                # Source device is local host or first available
                source_device = next((d for d in enrolled if d.get("is_current_host")), enrolled[0])

                handover_res: FleetHandoverResult = await service.initiate_fleet_handover(
                    user_id=user_id,
                    source_device_id=source_device["id"],
                    target_device_id=target_device["id"],
                    application=intent.application or "session",
                    capability=intent.capability or "resume_task",
                    reason=intent.reason or "Conversational user session handover",
                    auto_resume=True,
                )

                md = (
                    f"### 🔄 Autonomous Device Handover Completed\n\n"
                    f"Successfully transferred active session context to **{target_device.get('device_name')}**.\n\n"
                    f"- **Source Device:** `{source_device.get('device_name')}` ({source_device.get('os_platform')})\n"
                    f"- **Target Device:** `{target_device.get('device_name')}` ({target_device.get('os_platform')})\n"
                    f"- **Handover Status:** `{handover_res.status}`\n"
                    f"- **Reason:** {handover_res.reason}\n"
                    f"- **Auto-Resumed:** Yes\n\n"
                    f"*You can now seamlessly continue your work on {target_device.get('device_name')}.*"
                )
                return (True, md, handover_res.model_dump())
            except Exception as exc:
                log.exception("device_grounding.handover_failed", error=str(exc))
                return (True, f"❌ Handover failed: {exc}", None)

        # ---------------------------------------------------------------------
        # 5. Handle Application Control Execution
        # ---------------------------------------------------------------------
        if intent.intent_type == DeviceIntentType.APP_CONTROL:
            try:
                enrolled = await service.list_devices(user_id=user_id)
                preferred_device_id: str | None = None
                if intent.target_device_hint and enrolled:
                    matched = cls._match_device(intent.target_device_hint, enrolled)
                    if matched:
                        preferred_device_id = matched["id"]

                app_name = intent.application or "app"
                cap_name = intent.capability or "launch"

                fleet_res: FleetExecutionResult = await service.execute_fleet_app_control(
                    user_id=user_id,
                    application=app_name,
                    capability=cap_name,
                    parameters=intent.parameters,
                    preferred_device_id=preferred_device_id,
                    allow_failover=True,
                    skip_verification=False,
                )

                app_res = fleet_res.app_control_result
                routed_dev_id = fleet_res.executed_device_id
                matched_dev_name = routed_dev_id
                for d in enrolled:
                    if d.get("id") == routed_dev_id:
                        matched_dev_name = f"{d.get('device_name')} ({d.get('os_platform')})"
                        break

                # Case A: Pending human confirmation gate
                if app_res.stage == "pending_confirmation":
                    p_details = app_res.pending_confirmation_details or {}
                    token = p_details.get("confirmation_token") or ""
                    risk = p_details.get("risk") or "MEDIUM"
                    reason = p_details.get("reason") or "Action requires confirmation."
                    if token:
                        cls._PENDING_CHAT_CONFIRMATIONS[session_key] = token

                    md = (
                        f"### ⚠️ Action Requires Confirmation\n\n"
                        f"The requested action on **{app_name}** (`{cap_name}`) has a risk level of **{risk}**.\n\n"
                        f"- **Target Device:** `{matched_dev_name}`\n"
                        f"- **Action:** {reason}\n"
                        f"- **Confirmation Token:** `{token}`\n\n"
                        f"👉 **Reply 'confirm'** in this chat to execute, or cancel."
                    )
                    return (True, md, fleet_res.model_dump())

                # Case B: Execution Success
                if fleet_res.success:
                    exec_output = app_res.execution_output or {}
                    out_txt = exec_output.get("stdout") or exec_output.get("output") or ""
                    out_block = f"\n\n```text\n{out_txt}\n```" if out_txt else ""

                    chosen_int = app_res.resolution.chosen_integration if app_res.resolution else "fleet_route"
                    md = (
                        f"### ✅ Execution Complete & Verified\n\n"
                        f"Successfully executed **{cap_name}** for **{app_name}** on **{matched_dev_name}**.\n\n"
                        f"- **Integration Surface:** `{chosen_int}`\n"
                        f"- **Post-Condition Verified:** {'✅ Yes' if app_res.verified else '⚠️ Skipped'}\n"
                        f"- **Failover Occurred:** {'Yes' if fleet_res.handover_occurred else 'No'}\n"
                        f"- **Duration:** {fleet_res.duration_ms:.1f}ms{out_block}"
                    )
                    return (True, md, fleet_res.model_dump())

                # Case C: Execution Failed / Unsupported
                err_msg = app_res.error or "Unknown execution failure"
                md = (
                    f"### ❌ Action Failed on Fleet\n\n"
                    f"Could not execute **{cap_name}** for **{app_name}**.\n\n"
                    f"- **Stage:** `{app_res.stage}`\n"
                    f"- **Error:** {err_msg}\n"
                    f"- **Target Attempted:** `{matched_dev_name}`"
                )
                return (True, md, fleet_res.model_dump())

            except Exception as exc:
                log.exception("device_grounding.app_control_failed", error=str(exc))
                return (True, f"❌ Failed to execute application control: {exc}", None)

        return (False, "", None)

    @classmethod
    async def get_fleet_grounding_system_prompt(cls, user_id: str) -> str | None:
        """Construct live fleet telemetry system prompt for conversational background context."""
        try:
            service = DeviceService.get_instance()
            summary = await service.get_fleet_summary(user_id=user_id)
            if not summary.devices:
                return None

            lines = [
                f"[LIVE ROXY DEVICE FLEET CONTEXT — ENROLLED HARDWARE & APPS]:",
                f"Total Devices: {summary.total_devices} ({summary.online_devices} Online, {summary.offline_devices} Offline)",
                "Devices:",
            ]
            for d in summary.devices:
                host_str = " [CURRENT HOST]" if d.is_current_host else ""
                lines.append(f"- {d.device_name} (ID: {d.id}, Platform: {d.os_platform}, Status: {d.status}){host_str}")

            lines.append("Discovered Applications Across Fleet:")
            for app, devs in list(summary.app_distribution.items())[:15]:
                lines.append(f"- {app}: on {', '.join(devs)}")

            lines.append(
                "\nUse this verified device fleet context to answer questions about user devices, installed applications, and hardware status."
            )
            return "\n".join(lines)
        except Exception:
            return None
