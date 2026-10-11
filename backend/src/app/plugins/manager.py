"""Plugin Manager and Lifecycle Sandbox for ROXY 2.0.

Provides dynamic discovery, installation, verification, tool registration,
and revocation for community and internal plugins.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, ClassVar

import structlog

from app.plugins.schemas import (
    PluginManifest,
    PluginRecord,
    PluginStatus,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

log = structlog.get_logger()


class PluginSecurityError(Exception):
    """Raised when a plugin violates security or permission policies."""


class PluginManager:
    """Manages plugin discovery, lifecycle, sandboxed execution, and revocation."""

    _instance: ClassVar[PluginManager | None] = None

    _BANNED_IMPORTS: ClassVar[set[str]] = {
        "subprocess",
        "ctypes",
        "winreg",
        "pty",
        "shutil",
    }

    def __init__(self, plugins_dir: str | Path | None = None) -> None:
        self.plugins_dir = Path(plugins_dir) if plugins_dir else Path(__file__).resolve().parents[3] / "plugins"
        self._plugins: dict[str, PluginRecord] = {}

    @classmethod
    def get_instance(cls) -> PluginManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _validate_security(self, manifest: PluginManifest) -> None:
        """Inspect plugin tools for dangerous patterns before installation."""
        for tool in manifest.tools:
            if tool.handler_code:
                code_lower = tool.handler_code.lower()
                for banned in self._BANNED_IMPORTS:
                    if f"import {banned}" in code_lower or f"from {banned}" in code_lower:
                        raise PluginSecurityError(
                            f"Plugin '{manifest.plugin_id}' violates security policy: banned module '{banned}'."
                        )
                if "__subclasses__" in code_lower or "eval(" in code_lower or "exec(" in code_lower:
                    raise PluginSecurityError(
                        f"Plugin '{manifest.plugin_id}' uses forbidden dynamic evaluation or reflection."
                    )

    def install_plugin(self, manifest: PluginManifest, auto_enable: bool = True) -> PluginRecord:
        """Validate and install a plugin from manifest."""
        self._validate_security(manifest)

        record = PluginRecord(
            manifest=manifest,
            status=PluginStatus.INSTALLED,
        )
        self._plugins[manifest.plugin_id] = record
        log.info("plugins.installed", plugin_id=manifest.plugin_id, tools_count=len(manifest.tools))

        if auto_enable:
            self.enable_plugin(manifest.plugin_id)

        return record

    @staticmethod
    def _create_sandboxed_handler(
        code_str: str | None,
        desc: str,
        name: str,
        manifest_name: str,
        timeout_seconds: float = 4.0,
    ) -> Any:
        async def _handler(**kwargs: Any) -> Any:
            if not code_str:
                return {"output": f"Executed plugin {manifest_name}: {desc}", "params": kwargs}

            runner_code = (
                "import sys, json\n"
                "try:\n"
                "    raw = sys.stdin.read()\n"
                "    data = json.loads(raw) if raw else {}\n"
                "    inputs = data.get('inputs', {})\n"
                "    code = data.get('code', '')\n"
                "    safe_builtins = {\n"
                "        'dict': dict, 'list': list, 'str': str, 'int': int, 'float': float,\n"
                "        'len': len, 'range': range, 'bool': bool, 'min': min, 'max': max, 'sum': sum,\n"
                "        'round': round, 'abs': abs, 'isinstance': isinstance, 'print': lambda *a, **k: None\n"
                "    }\n"
                "    local_ns = {'inputs': inputs, 'result': None}\n"
                "    global_ns = {'__builtins__': safe_builtins}\n"
                "    exec(code, global_ns, local_ns)\n"
                "    res = local_ns.get('result')\n"
                "    if res is None:\n"
                "        res = {'output': 'Executed successfully'}\n"
                "    sys.stdout.write(json.dumps({'success': True, 'result': res}))\n"
                "except Exception as exc:\n"
                "    sys.stdout.write(json.dumps({'success': False, 'error': str(exc)}))\n"
            )

            # Scrub environment: strip database credentials, JWT secrets, and API keys
            safe_env = {
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
                "PATH": os.environ.get("PATH", ""),
                "TEMP": os.environ.get("TEMP", ""),
                "TMP": os.environ.get("TMP", ""),
                "PYTHONIOENCODING": "utf-8",
            }

            payload = json.dumps({"inputs": kwargs, "code": code_str})

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                runner_code,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(input=payload.encode("utf-8")),
                    timeout=timeout_seconds,
                )
            except (TimeoutError, asyncio.TimeoutError):
                with contextlib.suppress(Exception):
                    proc.kill()
                    await proc.wait()
                log.error("plugin.execution_timeout", tool=name, timeout=timeout_seconds)
                raise TimeoutError(f"Plugin tool '{name}' timed out after {timeout_seconds} seconds.")

            if proc.returncode != 0 and not stdout_data:
                err_msg = stderr_data.decode("utf-8", errors="replace").strip() or f"Process exited with code {proc.returncode}"
                raise RuntimeError(f"Plugin execution failed: {err_msg}")

            try:
                res_obj = json.loads(stdout_data.decode("utf-8", errors="replace"))
                if res_obj.get("success"):
                    return res_obj.get("result")
                raise RuntimeError(f"Plugin runtime error: {res_obj.get('error', 'Unknown error')}")
            except json.JSONDecodeError:
                return {"output": stdout_data.decode("utf-8", errors="replace")}

        return _handler

    def enable_plugin(self, plugin_id: str) -> PluginRecord:
        """Enable an installed plugin and register its tools in the ToolRegistry."""
        record = self._plugins.get(plugin_id)
        if not record:
            raise KeyError(f"Plugin '{plugin_id}' not found.")

        if record.status == PluginStatus.REVOKED:
            raise PermissionError(f"Plugin '{plugin_id}' has been revoked and cannot be enabled.")

        registry = ToolRegistry.get_instance()
        manifest = record.manifest

        for tool_def in manifest.tools:
            full_tool_id = f"plugin_{manifest.plugin_id}_{tool_def.name}"
            handler = self._create_sandboxed_handler(
                code_str=tool_def.handler_code,
                desc=tool_def.description,
                name=tool_def.name,
                manifest_name=manifest.name,
            )

            risk = RiskLevel.LOW
            if tool_def.risk_level.lower() == "medium":
                risk = RiskLevel.MEDIUM
            elif tool_def.risk_level.lower() in ("high", "critical"):
                risk = RiskLevel.HIGH

            registry.register(
                AgentTool(
                    id=full_tool_id,
                    name=f"[{manifest.name}] {tool_def.name}",
                    description=tool_def.description,
                    source=ToolSource.PLUGIN,
                    capabilities=tool_def.capabilities or [manifest.plugin_id, "plugin"],
                    input_schema=tool_def.input_schema or {"type": "object"},
                    permissions=manifest.permissions,
                    risk_level=risk,
                ),
                handler,
            )

        record.status = PluginStatus.ACTIVE
        record.updated_at = datetime.now(timezone.utc).isoformat()
        log.info("plugins.enabled", plugin_id=plugin_id)
        return record

    def disable_plugin(self, plugin_id: str) -> PluginRecord:
        """Disable a plugin and remove its tools from ToolRegistry."""
        record = self._plugins.get(plugin_id)
        if not record:
            raise KeyError(f"Plugin '{plugin_id}' not found.")

        registry = ToolRegistry.get_instance()
        for tool_def in record.manifest.tools:
            full_tool_id = f"plugin_{record.manifest.plugin_id}_{tool_def.name}"
            registry.unregister(full_tool_id)

        record.status = PluginStatus.DISABLED
        record.updated_at = datetime.now(timezone.utc).isoformat()
        log.info("plugins.disabled", plugin_id=plugin_id)
        return record

    def revoke_plugin(self, plugin_id: str, reason: str = "Admin revocation") -> PluginRecord:
        """Immediately revoke a plugin, unregister tools, and prevent re-activation."""
        record = self._plugins.get(plugin_id)
        if not record:
            raise KeyError(f"Plugin '{plugin_id}' not found.")

        self.disable_plugin(plugin_id)
        record.status = PluginStatus.REVOKED
        record.error = f"Revoked: {reason}"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        log.warning("plugins.revoked", plugin_id=plugin_id, reason=reason)
        return record

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """Remove plugin completely from system."""
        if plugin_id in self._plugins:
            try:
                self.disable_plugin(plugin_id)
            except Exception:
                pass
            del self._plugins[plugin_id]
            log.info("plugins.uninstalled", plugin_id=plugin_id)
            return True
        return False

    def get_plugin(self, plugin_id: str) -> PluginRecord | None:
        """Retrieve plugin record by ID."""
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[PluginRecord]:
        """List all registered plugins."""
        return list(self._plugins.values())
