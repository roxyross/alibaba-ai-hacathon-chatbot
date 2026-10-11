"""Phase 7: Dynamic Capability Discovery Engine for ROXY-AI Universal App Control.

Discovers, introspects, generates schemas, and verifies dynamic application capabilities:
1. CLI/Executable Introspection:
   - Automated --help, -h, help, --version interrogation
   - Subcommand, flag, argument, and option parser
   - Syntax and parameter extraction
2. Protocol Probing:
   - Local REST / HTTP API detection (Ollama, Docker, dev servers, Jupyter)
   - CLI execution in system PATH
   - Native UI Automation window availability (via DesktopAutomationEngine)
   - Model Context Protocol (MCP) configuration discovery
3. Dynamic Schema Generation:
   - Production JSONSchema input schemas for each capability
   - Semantic RiskLevel assignment (LOW, MEDIUM, HIGH, CRITICAL)
   - Scope-based permission generation (app:<app>:<action>, app:execute)
   - Safe confirmation gating for mutating or destructive actions
4. Live Action Verification:
   - Non-destructive probe execution (--version, dry-run, ping, healthcheck)
   - Latency tracking and evidence capture under Zero Simulation
5. Central ToolRegistry Dynamic Registration:
   - On-the-fly synthesis and registration of executable AgentTool definitions
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

import httpx
import structlog

from app.device.desktop_automation import DesktopAutomationEngine
from app.tools.schemas import (
    AgentTool,
    RiskLevel,
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolSource,
)

log = structlog.get_logger()


# -----------------------------------------------------------------------------
# Enums and Models
# -----------------------------------------------------------------------------

class CapabilityType(StrEnum):
    CLI_SUBCOMMAND = "cli_subcommand"
    CLI_FLAG = "cli_flag"
    REST_ENDPOINT = "rest_endpoint"
    UI_ACTION = "ui_action"
    MCP_TOOL = "mcp_tool"


# Known risk categorization verbs
CRITICAL_VERBS = {"delete", "remove", "drop", "purge", "rm", "kill", "destroy", "wipe", "format", "reset"}
HIGH_VERBS = {"write", "update", "set", "commit", "push", "create", "start", "stop", "restart", "deploy", "build", "publish", "terminate", "close", "execute"}
MEDIUM_VERBS = {"install", "download", "fetch", "pull", "exec", "run", "launch", "import", "export"}
LOW_VERBS = {"get", "list", "status", "info", "version", "show", "inspect", "help", "view", "read", "log", "diff", "check"}


def assess_action_risk(action_name: str, description: str = "") -> RiskLevel:
    """Classify action risk level based on semantic verbs and description."""
    tokens = set(re.findall(r"[a-zA-Z]+", f"{action_name} {description}".lower()))

    if tokens & CRITICAL_VERBS:
        return RiskLevel.CRITICAL
    if tokens & HIGH_VERBS:
        return RiskLevel.HIGH
    if tokens & MEDIUM_VERBS:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


# -----------------------------------------------------------------------------
# 1. CLI / Executable Introspector
# -----------------------------------------------------------------------------

class CLIIntrospector:
    """Introspects CLI applications and binaries via runtime help and version interrogation."""

    @classmethod
    def resolve_binary(cls, app_name_or_path: str) -> str | None:
        """Find executable in PATH or verify direct file path."""
        s = app_name_or_path.strip().strip('"').strip("'")
        if os.path.isabs(s) and os.path.isfile(s):
            return s
        found = shutil.which(s)
        if found:
            return found
        # Common suffixes on Windows
        if sys.platform == "win32" and not s.lower().endswith((".exe", ".cmd", ".bat")):
            for ext in (".exe", ".cmd", ".bat"):
                candidate = shutil.which(f"{s}{ext}")
                if candidate:
                    return candidate
        return None

    @classmethod
    def execute_help_query(cls, binary_path: str, args: list[str], timeout_sec: float = 3.0) -> str:
        """Safely execute a help or version query against an executable without shell invocation."""
        cmd = [binary_path] + args
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                errors="replace",
            )
            # Combine stdout and stderr as many CLI tools output help to stderr
            return (res.stdout or "") + "\n" + (res.stderr or "")
        except (subprocess.TimeoutExpired, OSError) as exc:
            log.debug("cli_introspector.query_failed", cmd=cmd, error=str(exc))
            return ""

    @classmethod
    def parse_help_text(cls, help_text: str) -> dict[str, Any]:
        """Extract subcommands, options, and usage descriptions from raw CLI help text."""
        subcommands: list[dict[str, str]] = []
        options: list[dict[str, Any]] = []
        lines = help_text.splitlines()

        in_commands_section = False
        in_options_section = False

        # Regex patterns for common CLI help formats
        cmd_header_re = re.compile(r"^(commands|available commands|subcommands):", re.IGNORECASE)
        opt_header_re = re.compile(r"^(options|flags|arguments):", re.IGNORECASE)

        # Standard option pattern: -f, --flag <arg>  Description
        opt_pattern = re.compile(r"^\s*(?:(-\w),\s*)?(--[a-zA-Z0-9\-_]+)(?:[=\s]<([a-zA-Z0-9\-_]+)>)?\s{2,}(.*)$")
        # Standard subcommand pattern:   command_name   Description
        subcmd_pattern = re.compile(r"^\s*([a-zA-Z0-9\-_]+)\s{2,}(.*)$")

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            if cmd_header_re.match(trimmed):
                in_commands_section = True
                in_options_section = False
                continue

            if opt_header_re.match(trimmed):
                in_options_section = True
                in_commands_section = False
                continue

            if in_commands_section:
                m = subcmd_pattern.match(line)
                if m:
                    c_name = m.group(1).strip()
                    c_desc = m.group(2).strip()
                    # Filter out non-command words
                    if c_name.lower() not in ("use", "see", "flags", "options", "for"):
                        subcommands.append({"name": c_name, "description": c_desc})
                elif not line.startswith(" "):
                    in_commands_section = False

            elif in_options_section or "--" in line:
                m = opt_pattern.match(line)
                if m:
                    short_flag = m.group(1) or ""
                    long_flag = m.group(2) or ""
                    arg_name = m.group(3) or ""
                    desc = m.group(4) or ""
                    clean_name = long_flag.lstrip("-").replace("-", "_")
                    options.append({
                        "name": clean_name,
                        "flag": long_flag,
                        "short_flag": short_flag,
                        "type": "string" if arg_name else "boolean",
                        "description": desc.strip(),
                    })

        return {"subcommands": subcommands, "options": options}

    @classmethod
    def introspect(cls, app_name_or_path: str) -> dict[str, Any]:
        """Perform full CLI introspection for an application or binary."""
        binary = cls.resolve_binary(app_name_or_path)
        if not binary:
            return {"available": False, "error": f"Executable for '{app_name_or_path}' not found in PATH."}

        # Query version
        version_raw = cls.execute_help_query(binary, ["--version"])
        if not version_raw.strip():
            version_raw = cls.execute_help_query(binary, ["-v"])
        version_line = (version_raw.strip().splitlines() or [""])[0]

        # Query primary help
        help_raw = cls.execute_help_query(binary, ["--help"])
        if not help_raw.strip():
            help_raw = cls.execute_help_query(binary, ["-h"])
        if not help_raw.strip():
            help_raw = cls.execute_help_query(binary, ["help"])

        parsed = cls.parse_help_text(help_raw)

        # For well-known subcommands, introspect top subcommands if available
        detailed_subcommands: list[dict[str, Any]] = []
        for subcmd in parsed["subcommands"][:8]:  # Limit top 8 subcommands
            c_name = subcmd["name"]
            sub_help = cls.execute_help_query(binary, [c_name, "--help"])
            sub_parsed = cls.parse_help_text(sub_help)
            detailed_subcommands.append({
                "name": c_name,
                "description": subcmd["description"],
                "options": sub_parsed["options"],
            })

        return {
            "available": True,
            "binary_path": binary,
            "version": version_line,
            "options": parsed["options"],
            "subcommands": detailed_subcommands or parsed["subcommands"],
            "raw_help_snippet": help_raw[:400],
        }


# -----------------------------------------------------------------------------
# 2. Protocol Prober (HTTP/REST, Sockets, MCP, UI)
# -----------------------------------------------------------------------------

class ProtocolProber:
    """Probes communication and automation protocols exposed by applications."""

    COMMON_PORT_MAP: dict[str, list[int]] = {
        "ollama": [11434],
        "docker": [2375, 2376],
        "jupyter": [8888, 8889],
        "postgres": [5432],
        "mysql": [3306],
        "redis": [6379],
        "mongodb": [27017],
        "node": [3000, 5000, 8000, 8080],
        "python": [5000, 8000, 8080],
        "fastapi": [8000],
    }

    @classmethod
    async def probe_http_service(cls, host: str = "127.0.0.1", port: int = 8000, timeout_sec: float = 1.0) -> dict[str, Any] | None:
        """Probe local port for active HTTP/REST service with OpenAPI / health detection."""
        base_url = f"http://{host}:{port}"
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            # 1. Try OpenAPI schema
            for path in ("/openapi.json", "/api/v1/openapi.json", "/swagger.json"):
                try:
                    resp = await client.get(f"{base_url}{path}")
                    if resp.status_code == 200:
                        try:
                            schema = resp.json()
                            endpoints = list(schema.get("paths", {}).keys())
                            return {
                                "protocol": "rest",
                                "base_url": base_url,
                                "port": port,
                                "has_openapi": True,
                                "endpoints": endpoints[:15],
                                "title": schema.get("info", {}).get("title", ""),
                                "version": schema.get("info", {}).get("version", ""),
                            }
                        except Exception:
                            pass
                except Exception:
                    pass

            # 2. Try generic health check
            for path in ("/health", "/api/health", "/status", "/api/version", "/"):
                try:
                    resp = await client.get(f"{base_url}{path}")
                    if resp.status_code in (200, 204, 301, 302, 401, 403):
                        return {
                            "protocol": "http",
                            "base_url": base_url,
                            "port": port,
                            "has_openapi": False,
                            "probe_path": path,
                            "status_code": resp.status_code,
                        }
                except Exception:
                    pass

        return None

    @classmethod
    def probe_mcp_config(cls, app_name: str) -> list[dict[str, Any]]:
        """Inspect common local MCP server configurations."""
        mcp_configs: list[dict[str, Any]] = []
        home = Path.home()

        candidates = [
            home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
            home / ".config" / "Claude" / "claude_desktop_config.json",
            home / ".cursor" / "mcp.json",
            home / ".vscode" / "mcp.json",
        ]

        for cfg_file in candidates:
            if cfg_file.exists():
                try:
                    data = json.loads(cfg_file.read_text(encoding="utf-8"))
                    servers = data.get("mcpServers", {})
                    for s_name, s_def in servers.items():
                        if app_name.lower() in s_name.lower() or app_name.lower() in str(s_def.get("command", "")).lower():
                            mcp_configs.append({
                                "server_name": s_name,
                                "command": s_def.get("command"),
                                "args": s_def.get("args", []),
                                "config_source": str(cfg_file),
                            })
                except Exception:
                    pass

        return mcp_configs

    @classmethod
    def probe_ui_automation(cls, app_name: str) -> dict[str, Any]:
        """Verify if target application has a native interactive UI window."""
        try:
            state = DesktopAutomationEngine.read_window_state(app_name)
            return {
                "has_native_window": state.exists,
                "window_title": state.title if state.exists else None,
                "pid": state.pid if state.exists else None,
                "is_foreground": state.is_foreground if state.exists else False,
            }
        except Exception:
            return {"has_native_window": False}

    @classmethod
    async def probe_all(cls, app_name: str, executable_path: str | None = None) -> dict[str, Any]:
        """Coordinate full protocol probing across CLI, REST, UI, and MCP."""
        cli_info = CLIIntrospector.introspect(executable_path or app_name)
        ui_info = cls.probe_ui_automation(app_name)
        mcp_info = cls.probe_mcp_config(app_name)

        # HTTP probing
        http_service: dict[str, Any] | None = None
        ports_to_check = cls.COMMON_PORT_MAP.get(app_name.lower(), [])
        for p in ports_to_check:
            http_service = await cls.probe_http_service(port=p, timeout_sec=0.5)
            if http_service:
                break

        return {
            "app_name": app_name,
            "cli": cli_info,
            "http": http_service,
            "ui": ui_info,
            "mcp": mcp_info,
        }


# -----------------------------------------------------------------------------
# 3. Dynamic Schema Generator
# -----------------------------------------------------------------------------

class DynamicSchemaGenerator:
    """Generates authoritative JSONSchema and AgentTool definitions for discovered capabilities."""

    @classmethod
    def sanitize_identifier(cls, text: str) -> str:
        """Convert arbitrary strings into valid, safe Python / JSON identifiers."""
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", text.strip().lower())
        clean = re.sub(r"_+", "_", clean).strip("_")
        return clean or "action"

    @classmethod
    def build_cli_subcommand_tool(
        cls,
        app_name: str,
        binary_path: str,
        subcmd: dict[str, Any],
    ) -> AgentTool:
        """Construct AgentTool definition from an introspected CLI subcommand."""
        app_slug = cls.sanitize_identifier(app_name)
        cmd_name = subcmd["name"]
        cmd_slug = cls.sanitize_identifier(cmd_name)
        desc = subcmd.get("description") or f"Execute '{cmd_name}' via {app_name}."

        properties: dict[str, Any] = {
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional positional arguments",
                "default": [],
            },
            "working_directory": {
                "type": "string",
                "description": "Directory in which to execute the command",
            },
        }

        # Add flags from options if discovered
        for opt in subcmd.get("options", []):
            o_name = opt["name"]
            o_type = opt.get("type", "string")
            o_desc = opt.get("description") or f"Flag {opt.get('flag')}"
            properties[o_name] = {
                "type": o_type,
                "description": o_desc,
            }

        risk = assess_action_risk(cmd_name, desc)
        requires_conf = risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

        return AgentTool(
            id=f"app_{app_slug}_{cmd_slug}",
            name=f"{app_slug}_{cmd_slug}",
            description=desc,
            source=ToolSource.DEVICE,
            capabilities=["app", "cli", app_slug, cmd_slug],
            permissions=[f"app:{app_slug}:{cmd_slug}", "app:execute"],
            risk_level=risk,
            requires_confirmation=requires_conf,
            input_schema={
                "type": "object",
                "properties": properties,
            },
        )

    @classmethod
    def build_rest_endpoint_tool(
        cls,
        app_name: str,
        base_url: str,
        endpoint_path: str,
        method: str = "GET",
    ) -> AgentTool:
        """Construct AgentTool definition from a discovered local REST endpoint."""
        app_slug = cls.sanitize_identifier(app_name)
        ep_slug = cls.sanitize_identifier(endpoint_path)
        desc = f"Call {method} {endpoint_path} on local {app_name} service at {base_url}."

        risk = assess_action_risk(endpoint_path, method)
        return AgentTool(
            id=f"app_{app_slug}_rest_{ep_slug}",
            name=f"{app_slug}_{ep_slug}",
            description=desc,
            source=ToolSource.CONNECTOR,
            capabilities=["app", "rest", "api", app_slug],
            permissions=[f"app:{app_slug}:api", "system:network"],
            risk_level=risk,
            requires_confirmation=risk in (RiskLevel.HIGH, RiskLevel.CRITICAL),
            input_schema={
                "type": "object",
                "properties": {
                    "payload": {"type": "object", "description": "JSON request body or query parameters"},
                    "timeout_sec": {"type": "number", "default": 10.0, "description": "HTTP request timeout"},
                },
            },
        )


# -----------------------------------------------------------------------------
# 4. Live Action Verifier (Zero Simulation)
# -----------------------------------------------------------------------------

class LiveActionVerifier:
    """Verifies discovered capabilities via non-destructive probes before offering to planner."""

    @classmethod
    def verify_cli_capability(
        cls,
        binary_path: str,
        subcmd_name: str | None = None,
        timeout_sec: float = 3.0,
    ) -> dict[str, Any]:
        """Perform non-destructive dry-run or version verification of CLI action."""
        start_time = time.perf_counter()
        args = [subcmd_name, "--help"] if subcmd_name else ["--version"]
        cmd = [binary_path] + [a for a in args if a]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                errors="replace",
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            # Most CLI tools return exit code 0 on --help/--version
            is_valid = res.returncode == 0 or bool(res.stdout.strip())
            return {
                "verified": is_valid,
                "latency_ms": elapsed_ms,
                "exit_code": res.returncode,
                "evidence": {
                    "cmd": cmd,
                    "output_preview": (res.stdout or res.stderr)[:200].strip(),
                },
                "error": None if is_valid else f"Exited with code {res.returncode}",
            }
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "verified": False,
                "latency_ms": elapsed_ms,
                "exit_code": -1,
                "evidence": {"cmd": cmd},
                "error": str(exc),
            }

    @classmethod
    async def verify_rest_capability(cls, base_url: str, endpoint: str, timeout_sec: float = 2.0) -> dict[str, Any]:
        """Verify REST endpoint responsiveness."""
        start_time = time.perf_counter()
        url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                res = await client.get(url)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "verified": res.status_code < 500,
                    "latency_ms": elapsed_ms,
                    "status_code": res.status_code,
                    "evidence": {"url": url},
                    "error": None if res.status_code < 500 else f"HTTP {res.status_code}",
                }
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "verified": False,
                "latency_ms": elapsed_ms,
                "status_code": 0,
                "evidence": {"url": url},
                "error": str(exc),
            }


# -----------------------------------------------------------------------------
# 5. Master Dynamic Capability Discovery Engine
# -----------------------------------------------------------------------------

class DynamicCapabilityDiscoveryEngine:
    """Master coordinator for Phase 7 Dynamic Capability Discovery."""

    @classmethod
    async def discover_app_capabilities(
        cls,
        app_name: str,
        executable_path: str | None = None,
        probe_live: bool = True,
    ) -> dict[str, Any]:
        """End-to-end capability discovery pipeline for an application."""
        # Step 1: Probe protocols
        probes = await ProtocolProber.probe_all(app_name=app_name, executable_path=executable_path)

        generated_tools: list[AgentTool] = []
        capabilities_meta: list[dict[str, Any]] = []

        cli_info = probes.get("cli", {})
        binary_path = cli_info.get("binary_path")

        # Step 2: Build CLI tools and verify
        if binary_path and cli_info.get("available"):
            subcommands = cli_info.get("subcommands", [])
            for sub in subcommands:
                tool = DynamicSchemaGenerator.build_cli_subcommand_tool(
                    app_name=app_name,
                    binary_path=binary_path,
                    subcmd=sub,
                )
                verification: dict[str, Any] = {"verified": False}
                if probe_live:
                    verification = LiveActionVerifier.verify_cli_capability(
                        binary_path=binary_path,
                        subcmd_name=sub["name"],
                    )

                generated_tools.append(tool)
                capabilities_meta.append({
                    "id": tool.id,
                    "name": sub["name"],
                    "description": tool.description,
                    "capability_type": CapabilityType.CLI_SUBCOMMAND.value,
                    "risk_level": tool.risk_level.value,
                    "requires_confirmation": tool.requires_confirmation,
                    "verified": verification.get("verified", False),
                    "verification": verification,
                    "input_schema": tool.input_schema,
                })

        # Step 3: Build REST endpoint tools if discovered
        http_info = probes.get("http")
        if http_info and http_info.get("endpoints"):
            base_url = http_info["base_url"]
            for ep in http_info["endpoints"][:10]:
                tool = DynamicSchemaGenerator.build_rest_endpoint_tool(
                    app_name=app_name,
                    base_url=base_url,
                    endpoint_path=ep,
                )
                verification = {"verified": False}
                if probe_live:
                    verification = await LiveActionVerifier.verify_rest_capability(base_url, ep)

                generated_tools.append(tool)
                capabilities_meta.append({
                    "id": tool.id,
                    "name": ep,
                    "description": tool.description,
                    "capability_type": CapabilityType.REST_ENDPOINT.value,
                    "risk_level": tool.risk_level.value,
                    "requires_confirmation": tool.requires_confirmation,
                    "verified": verification.get("verified", False),
                    "verification": verification,
                    "input_schema": tool.input_schema,
                })

        # Step 4: Include UI Automation capability if desktop window is present
        ui_info = probes.get("ui", {})
        if ui_info.get("has_native_window"):
            ui_tool = AgentTool(
                id=f"app_{DynamicSchemaGenerator.sanitize_identifier(app_name)}_ui_control",
                name=f"{DynamicSchemaGenerator.sanitize_identifier(app_name)}_ui_control",
                description=f"Interact with active desktop window of {app_name}.",
                source=ToolSource.DEVICE,
                capabilities=["ui", "automation", "window", app_name.lower()],
                permissions=[f"app:{DynamicSchemaGenerator.sanitize_identifier(app_name)}:ui"],
                risk_level=RiskLevel.MEDIUM,
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["inspect", "click", "type", "screenshot"]},
                        "element_name": {"type": "string"},
                        "text": {"type": "string"},
                    },
                },
            )
            generated_tools.append(ui_tool)
            capabilities_meta.append({
                "id": ui_tool.id,
                "name": "ui_control",
                "description": ui_tool.description,
                "capability_type": CapabilityType.UI_ACTION.value,
                "risk_level": ui_tool.risk_level.value,
                "requires_confirmation": False,
                "verified": True,
                "input_schema": ui_tool.input_schema,
            })

        verified_count = sum(1 for c in capabilities_meta if c.get("verified"))

        return {
            "app_name": app_name,
            "executable_path": binary_path or executable_path,
            "probes": probes,
            "capabilities": capabilities_meta,
            "total_discovered": len(capabilities_meta),
            "total_verified": verified_count,
            "generated_tools": generated_tools,
        }

    @classmethod
    def register_in_tool_registry(
        cls,
        tools: list[AgentTool],
        binary_path: str | None = None,
        registry: Any = None,
    ) -> int:
        """Register synthesized tools into Roxy ToolRegistry with live execution handler."""
        if not registry:
            from app.device.service import DeviceService
            registry = DeviceService.get_instance()._tool_registry

        registered = 0
        for tool in tools:
            bound_tool = tool
            bound_bin = binary_path

            # Create a bound closure execution handler supporting both arguments dict and kwargs
            async def _action_handler(
                arguments: dict[str, Any] | None = None,
                t: AgentTool = bound_tool,
                b: str | None = bound_bin,
                **kwargs: Any,
            ) -> dict[str, Any]:
                merged_params = dict(arguments or {})
                merged_params.update(kwargs)
                return await cls.execute_capability(tool=t, binary_path=b, parameters=merged_params)

            try:
                registry.register(tool, _action_handler)
                registered += 1
            except Exception as exc:
                log.warning("capability_engine.register_tool_failed", tool_id=tool.id, error=str(exc))

        return registered

    @classmethod
    async def execute_capability(
        cls,
        tool: AgentTool,
        binary_path: str | None,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a dynamic capability safely with parameter binding and stdout/stderr capture."""
        subcmd_name = ""
        parts = tool.id.split("_")
        if len(parts) >= 3:
            subcmd_name = parts[-1]

        real_bin: str | None = None
        if binary_path:
            if os.path.exists(binary_path):
                real_bin = binary_path
            else:
                real_bin = CLIIntrospector.resolve_binary(binary_path) or shutil.which(binary_path)

        # Handle CLI execution
        if real_bin and os.path.exists(real_bin):
            is_version_action = (
                subcmd_name == "version"
                or parameters.get("version") is True
                or "version" in tool.id.lower().split("_")
                or "version" in tool.name.lower().split("_")
            )
            is_help_action = (
                subcmd_name == "help"
                or parameters.get("help") is True
                or "help" in tool.id.lower().split("_")
                or "help" in tool.name.lower().split("_")
            )

            cmd = [real_bin]
            if subcmd_name and subcmd_name not in ("ui", "rest", "control", "test", "cli", "run", "action", "version", "help"):
                cmd.append(subcmd_name)

            # Bind kwargs to flags
            has_version_flag = False
            has_help_flag = False
            for k, v in parameters.items():
                if k in ("args", "working_directory", "user_id"):
                    continue
                flag = f"--{k.replace('_', '-')}"
                if k == "version":
                    has_version_flag = True
                elif k == "help":
                    has_help_flag = True

                if isinstance(v, bool):
                    if v:
                        cmd.append(flag)
                elif v is not None:
                    cmd.extend([flag, str(v)])

            if is_version_action and not has_version_flag:
                cmd.append("--version")
            elif is_help_action and not has_help_flag:
                cmd.append("--help")

            # Additional positional arguments
            extra_args = parameters.get("args") or []
            if isinstance(extra_args, list):
                cmd.extend([str(a) for a in extra_args])

            cwd = parameters.get("working_directory") or None

            start_t = time.perf_counter()
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=30.0,
                    check=False,
                    errors="replace",
                )
                dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
                return {
                    "success": proc.returncode == 0,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                    "duration_ms": dur_ms,
                    "command": cmd,
                }
            except Exception as exc:
                dur_ms = round((time.perf_counter() - start_t) * 1000, 2)
                return {
                    "success": False,
                    "exit_code": -1,
                    "error": str(exc),
                    "duration_ms": dur_ms,
                    "command": cmd,
                }

        return {"success": False, "error": f"Binary path '{binary_path}' not executable."}
