"""Standalone Roxy Device Agent (Daemon Architecture).

Fulfills Phase 3 of ROXY-AI 2.0 Operating Layer:
- Cryptographic device identity and hardware fingerprinting
- Time-bounded enrollment pairing handshake
- Secure token-based daemon authentication
- Real-time periodic heartbeat with system telemetry
- Asynchronous bidirectional command queue polling and execution
- Safe local OS automation execution (apps, windows, screenshot, telemetry)
- Reconnect resilience with exponential backoff
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

DEFAULT_CONFIG_DIR = Path.home() / ".roxy"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "device_agent.json"


def get_hardware_fingerprint() -> str:
    """Generate a deterministic, spoof-resistant hardware fingerprint string.

    Combines OS-native machine GUID / product UUID, primary network MAC address,
    hostname, platform, and architecture.
    """
    raw_components: list[str] = [
        platform.system().lower(),
        platform.machine().lower(),
        socket.gethostname().lower(),
        str(uuid.getnode()),  # MAC address represented as integer
    ]

    # Query OS-specific machine identifier
    system = platform.system().lower()
    if system == "windows":
        # Check Windows Cryptography MachineGuid registry or wmic
        guid = ""
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        except Exception:
            pass

        if not guid:
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    guid = proc.stdout.strip()
            except Exception:
                pass

        if guid:
            raw_components.append(guid.lower())

    elif system == "linux":
        for mid_path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
            if mid_path.exists():
                try:
                    raw_components.append(mid_path.read_text().strip().lower())
                    break
                except Exception:
                    pass

    elif system == "darwin":
        try:
            proc = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in proc.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    parts = line.split("=")
                    if len(parts) >= 2:
                        raw_components.append(parts[1].strip().strip('"').lower())
                        break
        except Exception:
            pass

    joined = "|".join(raw_components)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"hwfp_{digest[:32]}"


def collect_system_telemetry() -> dict[str, Any]:
    """Collect real-time system performance metrics, hardware load, and active window."""
    cpu_percent = 0.0
    mem_percent = 0.0
    disk_free_gb = 0.0
    active_window: str | None = None

    try:
        import psutil  # type: ignore

        cpu_percent = float(psutil.cpu_percent(interval=None))
        mem = psutil.virtual_memory()
        mem_percent = float(mem.percent)
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        disk_free_gb = round(disk.free / (1024**3), 2)
    except Exception as exc:
        log.debug("daemon.psutil_metrics_fallback", error=str(exc))

    # Active window title detection
    system = platform.system().lower()
    if system == "windows":
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            active_window = buf.value or None
        except Exception:
            pass

    return {
        "hostname": socket.gethostname(),
        "os_platform": platform.system().lower(),
        "architecture": platform.machine(),
        "cpu_percent": cpu_percent,
        "memory_percent": mem_percent,
        "disk_free_gb": disk_free_gb,
        "active_window": active_window,
        "timestamp": datetime.now(UTC).isoformat(),
    }


class RoxyDeviceAgent:
    """Standalone background daemon managing device presence, telemetry, and command dispatch."""

    def __init__(
        self,
        backend_url: str = "http://localhost:8000",
        config_path: Path | str | None = None,
        device_id: str | None = None,
        device_token: str | None = None,
        daemon_version: str = "1.0.0",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.device_id = device_id
        self.device_token = device_token
        self.daemon_version = daemon_version
        self._external_client = client
        self._is_running = False
        self._stop_event = asyncio.Event()

    def _get_api_url(self, endpoint: str) -> str:
        """Resolve full API URL supporting both root-relative and api/v1 paths."""
        ep = endpoint.lstrip("/")
        if self.backend_url.endswith("/api/v1"):
            base = self.backend_url
        else:
            base = f"{self.backend_url}/api/v1"
        return f"{base}/{ep}"

    def load_config(self, path: Path | str | None = None) -> bool:
        """Load device ID and secret credentials from local JSON config."""
        cfg_file = Path(path) if path else self.config_path
        if not cfg_file.exists():
            return False
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            self.device_id = data.get("device_id")
            self.device_token = data.get("device_token")
            if data.get("backend_url"):
                self.backend_url = data["backend_url"].rstrip("/")
            return bool(self.device_id and self.device_token)
        except Exception as exc:
            log.warning("device_agent.load_config_failed", path=str(cfg_file), error=str(exc))
            return False

    def save_config(self, path: Path | str | None = None) -> Path:
        """Persist device identity and secret token to secure local config file."""
        cfg_file = Path(path) if path else self.config_path
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "device_id": self.device_id,
            "device_token": self.device_token,
            "backend_url": self.backend_url,
            "daemon_version": self.daemon_version,
            "hardware_fingerprint": get_hardware_fingerprint(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        cfg_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return cfg_file

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> httpx.Response:
        """Execute HTTP request using internal or external async client."""
        url = self._get_api_url(endpoint)
        req_headers = headers or {}
        if self.device_token and "X-Device-Token" not in req_headers:
            req_headers["X-Device-Token"] = self.device_token

        if self._external_client:
            return await self._external_client.request(
                method, url, json=json_data, headers=req_headers, timeout=timeout
            )

        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(
                method, url, json=json_data, headers=req_headers
            )

    async def enroll(
        self,
        enrollment_token: str,
        device_name: str | None = None,
        save_to_config: bool = True,
    ) -> dict[str, Any]:
        """Claim a pairing token, register hardware identity, and receive permanent device token."""
        hw_fp = get_hardware_fingerprint()
        hostname = socket.gethostname()
        dev_name = device_name or f"{hostname} ({platform.system()})"
        telemetry = collect_system_telemetry()

        payload = {
            "enrollment_token": enrollment_token.strip(),
            "device_name": dev_name,
            "device_type": "desktop",
            "os_platform": platform.system().lower(),
            "os_version": platform.release(),
            "architecture": platform.machine(),
            "hostname": hostname,
            "hardware_fingerprint": hw_fp,
            "daemon_version": self.daemon_version,
            "capabilities": [
                "app_discovery",
                "process_control",
                "screen_capture",
                "system_commands",
                "telemetry",
            ],
            "telemetry": telemetry,
        }

        resp = await self._make_request("POST", "devices/enrollment/claim", json_data=payload)
        if resp.status_code not in (200, 201):
            detail = resp.text
            with contextlib.suppress(Exception):
                detail = resp.json().get("detail", detail)
            raise RuntimeError(f"Enrollment claim failed ({resp.status_code}): {detail}")

        raw_data = resp.json()
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        if not data or "device_id" not in data or "device_token" not in data:
            raise RuntimeError(f"Enrollment claim response missing credentials: {resp.text}")

        self.device_id = str(data["device_id"])
        self.device_token = str(data["device_token"])

        if save_to_config:
            self.save_config()

        log.info(
            "device_agent.enrolled_successfully",
            device_id=self.device_id,
            device_name=data.get("device_name"),
        )
        return data

    async def send_heartbeat(self) -> dict[str, Any]:
        """Transmit telemetry heartbeat to the backend gateway."""
        if not self.device_id or not self.device_token:
            raise RuntimeError("Device agent is not enrolled. Cannot send heartbeat.")

        telemetry = collect_system_telemetry()
        payload = {
            "telemetry": telemetry,
            "daemon_version": self.daemon_version,
        }

        resp = await self._make_request(
            "POST",
            f"devices/{self.device_id}/heartbeat",
            json_data=payload,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Heartbeat failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        return dict(data) if isinstance(data, dict) else {"status": "ok", "raw": data}

    async def poll_commands(self, limit: int = 10) -> list[dict[str, Any]]:
        """Poll the backend for queued commands targeting this device."""
        if not self.device_id or not self.device_token:
            raise RuntimeError("Device agent is not enrolled. Cannot poll commands.")

        resp = await self._make_request(
            "GET",
            f"devices/{self.device_id}/commands/poll?limit={limit}",
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Command polling failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        if isinstance(data, list):
            return [dict(c) for c in data if isinstance(c, dict)]
        if isinstance(data, dict) and "commands" in data:
            return [dict(c) for c in data["commands"] if isinstance(c, dict)]
        return []

    async def submit_command_result(
        self,
        command_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Report execution outcome of a queued command back to the gateway."""
        if not self.device_id or not self.device_token:
            raise RuntimeError("Device agent is not enrolled. Cannot submit command result.")

        payload = {
            "status": status,
            "result": result,
            "error": error,
        }

        resp = await self._make_request(
            "POST",
            f"devices/{self.device_id}/commands/{command_id}/result",
            json_data=payload,
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Submit command result failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        return dict(data) if isinstance(data, dict) else {"status": status}

    async def sync_apps_to_backend(self, apps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Scan or use provided applications catalog and sync to gateway backend."""
        if not self.device_id or not self.device_token:
            raise RuntimeError("Device agent is not enrolled. Cannot sync applications.")

        if apps is None:
            from app.device.scanner import DeepAppScanner
            apps = DeepAppScanner.scan_system()

        apps_payload = [dict(a) for a in apps]
        resp = await self._make_request(
            "POST",
            f"devices/{self.device_id}/apps/sync",
            json_data={"apps": apps_payload},
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Sync apps failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        return dict(data) if isinstance(data, dict) else {"synced_count": len(apps_payload)}

    async def execute_command(self, command: dict[str, Any]) -> tuple[str, Any, str | None]:
        """Execute a dispatched command locally on this machine.

        Returns (status, result_dict, error_str).
        """
        cmd_type = command.get("command_type", "")
        payload = command.get("payload") or {}

        try:
            if cmd_type == "ping":
                return (
                    "completed",
                    {
                        "pong": True,
                        "device_id": self.device_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "echo": payload.get("message", "hello"),
                    },
                    None,
                )

            elif cmd_type == "system_telemetry":
                telemetry = collect_system_telemetry()
                return ("completed", telemetry, None)

            elif cmd_type == "app_scan":
                from app.device.scanner import DeepAppScanner
                include_sys = payload.get("include_system_apps", False)
                apps = DeepAppScanner.scan_system(include_system_apps=include_sys)
                return ("completed", {"discovered_apps": apps, "count": len(apps)}, None)

            elif cmd_type in ("launch_app", "app_launch"):
                from app.device.process_controller import ProcessLifecycleController
                target = payload.get("target") or payload.get("app_name_or_path") or payload.get("executable_path") or payload.get("app_name")
                if not target:
                    return ("failed", None, "Target executable path or app name not provided.")
                args = payload.get("arguments", [])
                cwd = payload.get("working_directory")
                env = payload.get("environment")
                wait_win = payload.get("wait_for_window", False)
                win_timeout = payload.get("window_timeout_sec", 5.0)

                launch_res = ProcessLifecycleController.launch(
                    target=target,
                    arguments=args,
                    working_directory=cwd,
                    environment=env,
                    wait_for_window=wait_win,
                    window_timeout_sec=win_timeout,
                )
                if launch_res.success:
                    return ("completed", launch_res.model_dump(), None)
                return ("failed", launch_res.model_dump(), launch_res.error or "Failed to launch application.")

            elif cmd_type in ("close_app", "app_terminate"):
                from app.device.process_controller import ProcessLifecycleController
                target = payload.get("target") or payload.get("app_name_or_pid") or payload.get("process_id") or payload.get("app_name")
                if target is None:
                    return ("failed", None, "Target process ID or name not provided.")
                force = payload.get("force", False)
                timeout_sec = payload.get("timeout_sec", 5.0)
                term_children = payload.get("terminate_children", True)

                term_res = ProcessLifecycleController.terminate(
                    target=target,
                    force=force,
                    timeout_sec=timeout_sec,
                    terminate_children=term_children,
                )
                if term_res.success:
                    return ("completed", term_res.model_dump(), None)
                return ("failed", term_res.model_dump(), term_res.error or f"Failed to terminate target '{target}'.")

            elif cmd_type in ("focus_app", "app_focus"):
                from app.device.process_controller import ProcessLifecycleController
                target = payload.get("target") or payload.get("app_name")
                if not target:
                    return ("failed", None, "Target application name or PID not provided.")
                focused = ProcessLifecycleController.focus(target)
                if focused:
                    return ("completed", {"target": target, "focused": True}, None)
                return ("failed", {"target": target, "focused": False}, f"Could not bring window for '{target}' to foreground.")

            elif cmd_type in ("restart_app", "app_restart"):
                from app.device.process_controller import ProcessLifecycleController
                target = payload.get("target") or payload.get("app_name_or_pid") or payload.get("app_name")
                if not target:
                    return ("failed", None, "Target application name or PID not provided.")
                force = payload.get("force", False)
                args = payload.get("arguments")
                wait_sec = payload.get("wait_timeout_sec", 5.0)
                res = ProcessLifecycleController.restart(
                    target=target,
                    force=force,
                    arguments=args,
                    wait_timeout_sec=wait_sec,
                )
                if res.success:
                    return ("completed", res.model_dump(), None)
                return ("failed", res.model_dump(), res.error or f"Failed to restart target '{target}'.")

            elif cmd_type == "process_list":
                from app.device.process_controller import ProcessLifecycleController
                filter_name = payload.get("filter_name")
                running_only = payload.get("running_only", True)
                limit = payload.get("limit", 100)
                procs = ProcessLifecycleController.list_processes(
                    filter_name=filter_name,
                    running_only=running_only,
                    limit=limit,
                )
                return ("completed", {"total": len(procs), "processes": [p.model_dump() for p in procs]}, None)

            elif cmd_type == "process_details":
                from app.device.process_controller import ProcessLifecycleController
                pid = payload.get("pid")
                if pid is None:
                    return ("failed", None, "PID not provided.")
                details = ProcessLifecycleController.get_process_details(int(pid))
                if details:
                    return ("completed", details.model_dump(), None)
                return ("failed", None, f"Process with PID {pid} not found.")

            elif cmd_type == "screen_capture":
                from app.device.service import DeviceService
                svc = DeviceService.get_instance()
                capture = await svc.capture_screen(user_id=command.get("user_id", "system"), device_id=self.device_id or "local")
                return ("completed", capture, None)

            # -----------------------------------------------------------------
            # UI Automation Commands (Phase 4: Windows UI Automation)
            # -----------------------------------------------------------------
            elif cmd_type == "ui_inspect":
                from app.device.desktop_automation import DesktopAutomationEngine
                target = payload.get("window_target")
                depth = payload.get("max_depth", 3)
                max_children = payload.get("max_children", 50)
                tree = DesktopAutomationEngine.inspect_ui(target, max_depth=depth, max_children=max_children)
                return ("completed", tree.model_dump(), None)

            elif cmd_type == "ui_find_element":
                from app.device.desktop_automation import DesktopAutomationEngine
                elem = DesktopAutomationEngine.find_element(
                    window_target=payload.get("window_target"),
                    name=payload.get("name"),
                    automation_id=payload.get("automation_id"),
                    control_type=payload.get("control_type"),
                    role=payload.get("role"),
                    timeout_sec=payload.get("timeout_sec", 5.0),
                )
                return ("completed", elem.model_dump(), None)

            elif cmd_type == "ui_click":
                from app.device.desktop_automation import DesktopAutomationEngine
                click_res = DesktopAutomationEngine.click_element(
                    window_target=payload.get("window_target"),
                    name=payload.get("name"),
                    automation_id=payload.get("automation_id"),
                    control_type=payload.get("control_type"),
                    click_type=payload.get("click_type", "click"),
                )
                return ("completed", click_res, None)

            elif cmd_type == "ui_type":
                from app.device.desktop_automation import DesktopAutomationEngine
                text = payload.get("text", "")
                type_res = DesktopAutomationEngine.type_text(
                    window_target=payload.get("window_target"),
                    text=text,
                    name=payload.get("name"),
                    automation_id=payload.get("automation_id"),
                    control_type=payload.get("control_type"),
                    clear_first=payload.get("clear_first", False),
                    press_enter=payload.get("press_enter", False),
                )
                return ("completed", type_res, None)

            elif cmd_type == "ui_hotkey":
                from app.device.desktop_automation import DesktopAutomationEngine
                hotkey = payload.get("hotkey", "")
                hotkey_res = DesktopAutomationEngine.send_hotkey(
                    window_target=payload.get("window_target"),
                    hotkey=hotkey,
                )
                return ("completed", hotkey_res, None)

            elif cmd_type == "ui_scroll":
                from app.device.desktop_automation import DesktopAutomationEngine
                scroll_res = DesktopAutomationEngine.scroll(
                    window_target=payload.get("window_target"),
                    name=payload.get("name"),
                    automation_id=payload.get("automation_id"),
                    direction=payload.get("direction", "down"),
                    amount=payload.get("amount", 1),
                )
                return ("completed", scroll_res, None)

            elif cmd_type == "ui_window_state":
                from app.device.desktop_automation import DesktopAutomationEngine
                state = DesktopAutomationEngine.read_window_state(
                    window_target=payload.get("window_target")
                )
                return ("completed", state.model_dump(), None)

            elif cmd_type == "ui_screenshot":
                from app.device.desktop_automation import DesktopAutomationEngine
                shot = DesktopAutomationEngine.take_screenshot(
                    window_target=payload.get("window_target")
                )
                return ("completed", shot, None)

            elif cmd_type == "ui_select":
                from app.device.desktop_automation import DesktopAutomationEngine
                select_res = DesktopAutomationEngine.select_element(
                    window_target=payload.get("window_target"),
                    name=payload.get("name"),
                    automation_id=payload.get("automation_id"),
                    item_name=payload.get("item_name"),
                )
                return ("completed", select_res, None)

            elif cmd_type == "ui_wait_element":
                from app.device.desktop_automation import DesktopAutomationEngine
                elem = DesktopAutomationEngine.wait_for_element(
                    window_target=payload.get("window_target"),
                    name=payload.get("name"),
                    automation_id=payload.get("automation_id"),
                    control_type=payload.get("control_type"),
                    timeout_sec=payload.get("timeout_sec", 10.0),
                )
                return ("completed", elem.model_dump(), None)

            # -----------------------------------------------------------------
            # Phase 7: Dynamic Capability Discovery Commands
            # -----------------------------------------------------------------
            elif cmd_type == "app_discover_capabilities":
                from app.device.capability_engine import DynamicCapabilityDiscoveryEngine
                app_name = payload.get("app_name", "")
                exec_path = payload.get("executable_path")
                probe_live = payload.get("probe_live", True)
                cap_res = await DynamicCapabilityDiscoveryEngine.discover_app_capabilities(
                    app_name=app_name,
                    executable_path=exec_path,
                    probe_live=probe_live,
                )
                clean_res = dict(cap_res)
                clean_res.pop("generated_tools", None)
                return ("completed", clean_res, None)

            elif cmd_type == "app_execute_action":
                from app.device.capability_engine import (
                    DynamicCapabilityDiscoveryEngine,
                    DynamicSchemaGenerator,
                )
                app_name = payload.get("app_name", "")
                action_name = payload.get("action_name", "")
                exec_path = payload.get("executable_path") or app_name
                params = payload.get("parameters") or {}

                subcmd_dict = {"name": action_name, "description": f"Execute '{action_name}' via {app_name}."}
                tool = DynamicSchemaGenerator.build_cli_subcommand_tool(
                    app_name=app_name,
                    binary_path=exec_path,
                    subcmd=subcmd_dict,
                )
                action_res = await DynamicCapabilityDiscoveryEngine.execute_capability(
                    tool=tool,
                    binary_path=exec_path,
                    parameters=params,
                )
                return ("completed", action_res, None)

            elif cmd_type in ("resolve_integration", "app_resolve_integration"):
                from app.device.integration_resolver import IntegrationResolver
                from app.device.schemas import IntegrationResolutionRequest

                app_name = payload.get("application") or payload.get("app_name") or ""
                cap_name = payload.get("requested_capability") or payload.get("capability") or ""
                preferred = payload.get("preferred_integration")
                dev_ctx = payload.get("device") or {"os_platform": sys.platform}
                user_ctx = payload.get("user_context") or {}

                req_obj = IntegrationResolutionRequest(
                    application=app_name,
                    requested_capability=cap_name,
                    preferred_integration=preferred,
                    device=dev_ctx,
                    user_context=user_ctx,
                )
                res = IntegrationResolver.resolve(req_obj)
                return ("completed", res.model_dump(), None)

            elif cmd_type in ("app_control_orchestrate", "orchestrate_app_control"):
                from app.device.orchestrator import UniversalAppController
                from app.device.schemas import AppControlExecutionRequest

                app_name = payload.get("application") or payload.get("app_name") or ""
                cap_name = payload.get("capability") or payload.get("requested_capability") or ""
                params = payload.get("parameters") or {}
                preferred = payload.get("preferred_integration")
                confirmed = bool(payload.get("confirmed", False))
                conf_tok = payload.get("confirmation_token")
                skip_v = bool(payload.get("skip_verification", False))
                dev_ctx = payload.get("device_context") or payload.get("device") or {"os_platform": sys.platform}
                user_ctx = payload.get("user_context") or {}

                req_obj = AppControlExecutionRequest(
                    application=app_name,
                    capability=cap_name,
                    parameters=params,
                    preferred_integration=preferred,
                    device_id=self.device_id,
                    confirmed=confirmed,
                    confirmation_token=conf_tok,
                    skip_verification=skip_v,
                    device_context=dev_ctx,
                    user_context=user_ctx,
                )
                ctrl = UniversalAppController.get_instance()
                exec_res = await ctrl.execute_lifecycle(req_obj)
                return ("completed" if exec_res.success or exec_res.stage == "pending_confirmation" else "failed", exec_res.model_dump(), exec_res.error)

            elif cmd_type in ("app_control_confirm", "confirm_app_control"):
                from app.device.orchestrator import UniversalAppController

                conf_tok = payload.get("confirmation_token") or ""
                ctrl = UniversalAppController.get_instance()
                exec_res = await ctrl.confirm_execution(token=conf_tok)
                return ("completed" if exec_res.success else "failed", exec_res.model_dump(), exec_res.error)

            # -----------------------------------------------------------------
            # Phase 10: Multi-Device Fleet Orchestration & Handover Commands
            # -----------------------------------------------------------------
            elif cmd_type in ("fleet_task_execute", "fleet_execute"):
                from app.device.orchestrator import UniversalAppController
                from app.device.schemas import AppControlExecutionRequest

                app_name = payload.get("application") or payload.get("app_name") or ""
                cap_name = payload.get("capability") or ""
                params = payload.get("parameters") or {}
                preferred = payload.get("preferred_integration")

                req_obj = AppControlExecutionRequest(
                    application=app_name,
                    capability=cap_name,
                    parameters=params,
                    preferred_integration=preferred,
                    device_id=self.device_id,
                    confirmed=bool(payload.get("confirmed", False)),
                    confirmation_token=payload.get("confirmation_token"),
                    skip_verification=bool(payload.get("skip_verification", False)),
                    device_context=payload.get("device_context") or {"os_platform": sys.platform},
                )
                ctrl = UniversalAppController.get_instance()
                exec_res = await ctrl.execute_lifecycle(req_obj)
                if exec_res.stage == "pending_confirmation" and bool(payload.get("confirmed", False)) and exec_res.pending_confirmation_details:
                    conf_tok = str(exec_res.pending_confirmation_details.get("confirmation_token") or "")
                    if conf_tok:
                        exec_res = await ctrl.confirm_execution(token=conf_tok)
                return ("completed" if exec_res.success else "failed", exec_res.model_dump(), exec_res.error)

            elif cmd_type in ("fleet_handover_receive", "fleet_receive_task"):
                from app.device.orchestrator import UniversalAppController
                from app.device.schemas import AppControlExecutionRequest

                app_name = payload.get("application") or ""
                cap_name = payload.get("capability") or ""
                state_pl = payload.get("state_payload") or {}
                merged_params = {**payload.get("parameters", {}), **state_pl.get("parameters", {})}

                req_obj = AppControlExecutionRequest(
                    application=app_name,
                    capability=cap_name,
                    parameters=merged_params,
                    device_id=self.device_id,
                    confirmed=True,  # Handed over tasks have already passed user authorization
                    device_context={"os_platform": sys.platform},
                )
                ctrl = UniversalAppController.get_instance()
                exec_res = await ctrl.execute_lifecycle(req_obj)
                if exec_res.stage == "pending_confirmation" and exec_res.pending_confirmation_details:
                    conf_tok = str(exec_res.pending_confirmation_details.get("confirmation_token") or "")
                    if conf_tok:
                        exec_res = await ctrl.confirm_execution(token=conf_tok)
                return ("completed" if exec_res.success else "failed", exec_res.model_dump(), exec_res.error)

            else:
                return ("failed", None, f"Unsupported command type: '{cmd_type}'.")

        except Exception as exc:
            log.exception("device_agent.execute_command_failed", command_type=cmd_type, error=str(exc))
            return ("failed", None, str(exc))

    async def process_pending_commands(self) -> int:
        """Poll and execute all currently queued commands for this device."""
        try:
            commands = await self.poll_commands(limit=10)
        except Exception as exc:
            log.warning("device_agent.poll_failed", error=str(exc))
            return 0

        executed = 0
        for cmd in commands:
            cmd_id = cmd["id"]
            cmd_type = cmd.get("command_type", "")
            log.info("device_agent.executing_command", command_id=cmd_id, command_type=cmd_type)

            status, result, error = await self.execute_command(cmd)

            try:
                await self.submit_command_result(
                    command_id=cmd_id,
                    status=status,
                    result=result,
                    error=error,
                )
                executed += 1
            except Exception as exc:
                log.error("device_agent.submit_result_failed", command_id=cmd_id, error=str(exc))

        return executed

    async def run_heartbeat_loop(self, interval: float = 15.0) -> None:
        """Continuous background task reporting device presence and telemetry."""
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                await self.send_heartbeat()
                backoff = 1.0  # Reset backoff on success
            except Exception as exc:
                log.warning("device_agent.heartbeat_loop_error", error=str(exc), retry_in=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)
                continue

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)

    async def run_command_loop(self, interval: float = 2.0) -> None:
        """Continuous background task polling and executing incoming commands."""
        backoff = 0.5
        while not self._stop_event.is_set():
            try:
                await self.process_pending_commands()
                backoff = 0.5
            except Exception as exc:
                log.warning("device_agent.command_loop_error", error=str(exc), retry_in=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 30.0)
                continue

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)

    async def start(
        self,
        heartbeat_interval: float = 15.0,
        poll_interval: float = 2.0,
        max_iterations: int | None = None,
    ) -> None:
        """Start the background heartbeat and command polling loops."""
        if (not self.device_id or not self.device_token) and not self.load_config():
            raise RuntimeError(
                "Device agent is not configured or enrolled. Run with --enroll <token> first."
            )

        self._is_running = True
        self._stop_event.clear()

        log.info(
            "device_agent.started",
            device_id=self.device_id,
            backend_url=self.backend_url,
            version=self.daemon_version,
        )

        if max_iterations is not None:
            # Controlled bounded run (for testing or one-shot executions)
            for _ in range(max_iterations):
                if self._stop_event.is_set():
                    break
                with contextlib.suppress(Exception):
                    await self.send_heartbeat()
                with contextlib.suppress(Exception):
                    await self.process_pending_commands()
                await asyncio.sleep(poll_interval)
            return

        hb_task = asyncio.create_task(self.run_heartbeat_loop(interval=heartbeat_interval))
        cmd_task = asyncio.create_task(self.run_command_loop(interval=poll_interval))

        try:
            await asyncio.gather(hb_task, cmd_task)
        except asyncio.CancelledError:
            pass
        finally:
            self._is_running = False

    def stop(self) -> None:
        """Signal all background daemon loops to terminate gracefully."""
        self._is_running = False
        self._stop_event.set()


# Canonical alias for daemon architecture
RoxyDeviceDaemon = RoxyDeviceAgent


def main() -> None:
    """CLI entrypoint for standalone Roxy Device Agent daemon."""
    parser = argparse.ArgumentParser(description="Roxy Device Agent Daemon")
    parser.add_argument("--url", default="http://localhost:8000", help="Roxy Gateway Backend API URL")
    parser.add_argument("--config", default=None, help="Custom path to device configuration JSON file")
    parser.add_argument("--enroll", default=None, help="15-minute enrollment token to pair this machine")
    parser.add_argument("--name", default=None, help="Custom human-readable name for this device")
    parser.add_argument("--fingerprint", action="store_true", help="Print local hardware fingerprint and exit")
    parser.add_argument("--run", action="store_true", help="Start the background agent daemon loops")

    args = parser.parse_args()

    if args.fingerprint:
        print(f"Hardware Fingerprint: {get_hardware_fingerprint()}")
        sys.exit(0)

    agent = RoxyDeviceAgent(
        backend_url=args.url,
        config_path=args.config,
    )

    if args.enroll:
        print(f"Pairing with Roxy Gateway at {args.url}...")
        try:
            res = asyncio.run(agent.enroll(enrollment_token=args.enroll, device_name=args.name))
            print(f"Enrolled successfully! Device ID: {res['device_id']}")
            print(f"Configuration saved to: {agent.config_path}")
        except Exception as exc:
            print(f"Enrollment failed: {exc}", file=sys.stderr)
            sys.exit(1)

    if args.run:
        print("Starting Roxy Device Agent daemon...")
        try:
            asyncio.run(agent.start())
        except KeyboardInterrupt:
            print("\nShutting down device agent daemon.")
            agent.stop()


if __name__ == "__main__":
    main()
