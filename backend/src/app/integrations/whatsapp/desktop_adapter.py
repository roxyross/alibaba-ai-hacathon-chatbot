"""WhatsApp Desktop Adapter for Windows 11 UWP Application Automation."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import time
import uuid
from typing import Any

import structlog

from app.device.windows_automation import IS_WINDOWS, WindowsUIAutomationEngine
from app.integrations.whatsapp.base import WhatsAppBaseAdapter
from app.integrations.whatsapp.models import (
    ConnectionState,
    WhatsAppCapability,
    WhatsAppConnectionReport,
    WhatsAppOperationResult,
    WhatsAppRoute,
    WhatsAppTaskStatus,
)

log = structlog.get_logger()

# Package & AppID identities on Windows 11
_WHATSAPP_UWP_PACKAGE = "5319275A.WhatsAppDesktop"
_WHATSAPP_UWP_APPID = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
_LIVE_GUI_ENV_FLAG = "ROXY_LIVE_WHATSAPP_GUI"


class WhatsAppDesktopAdapter(WhatsAppBaseAdapter):
    """Adapter for native Windows 11 WhatsApp Desktop application."""

    def __init__(self) -> None:
        self._cached_package_check: bool | None = None
        self._last_package_check_time: float = 0.0
        self._active_operations: dict[str, WhatsAppOperationResult] = {}

    @property
    def route(self) -> WhatsAppRoute:
        return WhatsAppRoute.DESKTOP

    def get_capabilities(self) -> list[WhatsAppCapability]:
        return [
            WhatsAppCapability.SESSION_DISCOVERY,
            WhatsAppCapability.RECIPIENT_RESOLUTION,
            WhatsAppCapability.MESSAGE_DRAFTING,
            WhatsAppCapability.SEND_TEXT,
            WhatsAppCapability.DELIVERY_VERIFICATION,
        ]

    def _is_package_installed(self) -> bool:
        """Check whether 5319275A.WhatsAppDesktop package is installed on the host OS."""
        if not IS_WINDOWS:
            return False

        now = time.monotonic()
        if self._cached_package_check is not None and (now - self._last_package_check_time < 30.0):
            return self._cached_package_check

        try:
            # Quick check via PowerShell Get-AppxPackage with timeout
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"Get-AppxPackage -Name '{_WHATSAPP_UWP_PACKAGE}' | Select-Object -ExpandProperty PackageFullName",
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            installed = _WHATSAPP_UWP_PACKAGE.lower() in proc.stdout.lower()
            self._cached_package_check = installed
            self._last_package_check_time = now
            return installed
        except Exception as exc:
            log.debug("whatsapp_desktop.package_check_failed", error=str(exc))
            return False

    @staticmethod
    def _extract_all_element_names(element: Any) -> list[str]:
        """Extract lowercase names from UI element tree (handles UIElementModel or list)."""
        names: list[str] = []
        if isinstance(element, list):
            for item in element:
                names.extend(WhatsAppDesktopAdapter._extract_all_element_names(item))
            return names
        name_val = getattr(element, "name", None)
        if name_val:
            names.append(str(name_val).lower())
        for child in getattr(element, "children", []):
            names.extend(WhatsAppDesktopAdapter._extract_all_element_names(child))
        return names

    def _find_running_process(self) -> Any | None:
        """Find active WhatsApp process if running."""
        try:
            import psutil  # type: ignore[import-untyped]
            for proc in psutil.process_iter(["pid", "name"]):
                name = (proc.info.get("name") or "").lower()
                if "whatsapp" in name:
                    return proc
        except Exception:
            pass
        return None

    async def get_connection_status(self) -> WhatsAppConnectionReport:
        """Probe Windows 11 environment for WhatsApp Desktop installation and session readiness."""
        if not IS_WINDOWS:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.NOT_INSTALLED,
                is_ready=False,
                details="WhatsApp Desktop is only supported on Windows host environments.",
                missing_prerequisites=["Windows OS environment"],
            )

        installed = self._is_package_installed()
        if not installed:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.NOT_INSTALLED,
                is_ready=False,
                details=f"WhatsApp Desktop UWP package '{_WHATSAPP_UWP_PACKAGE}' is not installed.",
                missing_prerequisites=["Install WhatsApp Desktop from the Microsoft Store"],
            )

        # Check if process is running
        proc = self._find_running_process()
        if not proc:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.NOT_RUNNING,
                is_ready=False,
                details="WhatsApp Desktop is installed but not currently running.",
                missing_prerequisites=["Launch WhatsApp Desktop and sign in"],
                metadata={"package": _WHATSAPP_UWP_PACKAGE, "appid": _WHATSAPP_UWP_APPID},
            )

        # Process is running, inspect window and UI tree
        pid = proc.info.get("pid", 0)
        try:
            target_win = WindowsUIAutomationEngine.resolve_target_window(window_target=pid, timeout_sec=2.0)
            if not target_win:
                target_win = WindowsUIAutomationEngine.resolve_target_window(window_target="WhatsApp", timeout_sec=2.0)

            if not target_win:
                return WhatsAppConnectionReport(
                    route=self.route,
                    state=ConnectionState.INACCESSIBLE,
                    is_ready=False,
                    details="WhatsApp process is active but main window could not be resolved in the interactive desktop.",
                    metadata={"pid": pid},
                )

            # Inspect elements to distinguish authenticated chat list from login / QR
            elements = WindowsUIAutomationEngine.device_inspect_ui(window_target="WhatsApp", max_depth=3)
            all_names = self._extract_all_element_names(elements)
            elem_names = " ".join(all_names)
            has_qr_login = any(k in elem_names for k in ("qr", "scan", "log in", "get started", "link a device"))

            if has_qr_login:
                return WhatsAppConnectionReport(
                    route=self.route,
                    state=ConnectionState.UNAUTHENTICATED,
                    is_ready=False,
                    details="WhatsApp Desktop is running but displays the sign-in / QR screen.",
                    missing_prerequisites=["Scan QR code in WhatsApp Desktop on your phone"],
                    metadata={"pid": pid, "ui_state": "QR_OR_LOGIN_PROMPT"},
                )

            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.AUTHENTICATED,
                is_ready=True,
                details="WhatsApp Desktop is running, interactive, and session appears authenticated.",
                metadata={"pid": pid, "package": _WHATSAPP_UWP_PACKAGE},
            )
        except Exception as exc:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.UNKNOWN,
                is_ready=False,
                details=f"Error inspecting WhatsApp Desktop window: {exc}",
                metadata={"pid": pid, "error": str(exc)},
            )

    async def send_message(
        self,
        user_id: str,
        recipient: str,
        message: str,
        challenge_id: str,
        run_id: str,
    ) -> WhatsAppOperationResult:
        """Send message via Windows UI Automation on WhatsApp Desktop."""
        active_op_id = run_id or f"op_desk_{uuid.uuid4().hex[:8]}"
        is_ok, norm_recipient, err = self.resolve_recipient(recipient)
        redacted = self.redact_phone_number(norm_recipient if is_ok else recipient)

        if not is_ok:
            return WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.FAILED,
                recipient_redacted=redacted,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code="INVALID_RECIPIENT",
                user_facing_error=err,
            )

        # Check session status
        status_report = await self.get_connection_status()
        if not status_report.is_ready:
            res = WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.BLOCKED,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code=f"SESSION_{status_report.state.value}",
                user_facing_error=(
                    f"BLOCKED: WhatsApp Desktop is not ready ({status_report.details}). "
                    + (f"Prerequisites: {', '.join(status_report.missing_prerequisites)}" if status_report.missing_prerequisites else "")
                ),
                verification_evidence={"connection_report": status_report.__dict__},
            )
            self._active_operations[active_op_id] = res
            return res

        # Safety check: Live UI automation opt-in
        live_opt_in = os.environ.get(_LIVE_GUI_ENV_FLAG, "").strip() == "1"
        if not live_opt_in:
            res = WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.BLOCKED,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code="LIVE_GUI_OPT_IN_REQUIRED",
                user_facing_error=(
                    f"BLOCKED: Live desktop GUI automation requires explicit opt-in via {_LIVE_GUI_ENV_FLAG}=1 "
                    "under the Zero Simulation Doctrine."
                ),
                verification_evidence={"live_opt_in": False},
            )
            self._active_operations[active_op_id] = res
            return res

        # Execute bounded UI Automation interaction
        try:
            # Protocol activation for whatsapp://send?phone=...&text=...
            phone_digits = norm_recipient.replace("+", "")
            import urllib.parse
            encoded_text = urllib.parse.quote(message)
            protocol_url = f"whatsapp://send?phone={phone_digits}&text={encoded_text}"

            # Activate protocol safely via Windows shell
            os.startfile(protocol_url)
            await asyncio.sleep(2.0)

            # Locate active WhatsApp window
            win = WindowsUIAutomationEngine.resolve_target_window("WhatsApp", timeout_sec=5.0)
            if not win:
                res = WhatsAppOperationResult(
                    operation_id=active_op_id,
                    route=self.route,
                    status=WhatsAppTaskStatus.UNKNOWN,
                    recipient_redacted=redacted,
                    message_snippet=message[:40],
                    challenge_id=challenge_id,
                    error_code="WINDOW_LOST_AFTER_PROTOCOL_ACTIVATION",
                    user_facing_error="WhatsApp window could not be brought to focus following protocol activation.",
                )
                self._active_operations[active_op_id] = res
                return res

            # Click send button or send keystroke
            send_clicked = False
            try:
                click_info = WindowsUIAutomationEngine.device_click_element(
                    window_target="WhatsApp",
                    name="Send",
                    control_type="ButtonControl",
                )
                send_clicked = bool(click_info.get("clicked"))
            except Exception:
                send_clicked = False

            if not send_clicked:
                with contextlib.suppress(Exception):
                    WindowsUIAutomationEngine.device_send_hotkey(window_target="WhatsApp", hotkey="Enter")

            await asyncio.sleep(1.5)

            # Inspect outgoing UI evidence
            elements = WindowsUIAutomationEngine.device_inspect_ui(window_target="WhatsApp", max_depth=4)
            all_names = self._extract_all_element_names(elements)
            found_bubble = any(message[:15].lower() in n or active_op_id.lower() in n for n in all_names)

            evidence = {
                "ui_bubble_detected": found_bubble,
                "protocol_url_dispatched": f"whatsapp://send?phone={phone_digits}&text=...",
                "send_method": "UIA_BUTTON" if send_clicked else "ENTER_KEY",
            }

            res = WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.SENT if found_bubble else WhatsAppTaskStatus.UNKNOWN,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                verification_evidence=evidence,
                user_facing_error=None if found_bubble else "Message send action was dispatched, but outgoing message bubble was not confirmed on screen.",
            )
            self._active_operations[active_op_id] = res
            return res

        except Exception as exc:
            log.error("whatsapp_desktop.send_failed", error=str(exc))
            res = WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.FAILED,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code="UI_AUTOMATION_EXCEPTION",
                user_facing_error=f"Desktop UI automation failed: {exc}",
            )
            self._active_operations[active_op_id] = res
            return res

    async def get_message_status(self, operation_id: str) -> WhatsAppOperationResult:
        if operation_id in self._active_operations:
            return self._active_operations[operation_id]
        return WhatsAppOperationResult(
            operation_id=operation_id,
            route=self.route,
            status=WhatsAppTaskStatus.UNKNOWN,
            error_code="OPERATION_NOT_FOUND",
            user_facing_error="Operation record not found.",
        )

    async def cancel_operation(self, operation_id: str) -> bool:
        if operation_id in self._active_operations:
            op = self._active_operations[operation_id]
            if op.status in (WhatsAppTaskStatus.DISCOVERING, WhatsAppTaskStatus.WAITING_FOR_APPROVAL, WhatsAppTaskStatus.READY_TO_SEND):
                op.status = WhatsAppTaskStatus.CANCELLED
                return True
        return False
