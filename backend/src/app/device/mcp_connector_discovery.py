"""Dynamic Runtime MCP and Cloud Connector Discovery and Tool Binding Engine (Phase 15).

Operating under the Zero Simulation Doctrine:
- Discovers external MCP servers across filesystem configs, active SSE network ports,
  running system processes, environment variables, and authoritative open-source catalogs.
- Discovers Cloud Connectors, active user instances, localhost OpenAPI/Swagger specifications,
  and environment credentials.
- Dynamically converts discovered capabilities into typed AgentTool definitions and binds
  them into the central ToolRegistry with non-destructive verification probes.
- Ranks candidate integration pathways according to the Universal Integration Priority hierarchy
  (Tier 1: Cloud Connector / OpenAPI, Tier 2: MCP Tool / Server).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
import structlog

try:
    import psutil  # type: ignore[import-untyped]
except ImportError:
    psutil = None  # type: ignore[assignment]

from app.connectors.base import BaseConnector
from app.connectors.openapi import OpenAPIConnector
from app.connectors.service import ConnectorService
from app.device.integration_resolver import (
    KNOWN_CONNECTOR_CATALOG,
    IntegrationResolver,
)
from app.device.schemas import (
    ConnectorDiscoveredItem,
    ConnectorDiscoveryRequest,
    ConnectorDiscoveryResult,
    ConnectorDiscoverySource,
    ConnectorToolBindingRequest,
    ConnectorToolBindingResult,
    DiscoveredIntegrationPathway,
    MCPDiscoveredServer,
    MCPDiscoveryRequest,
    MCPDiscoveryResult,
    MCPDiscoverySource,
    MCPToolBindingRequest,
    MCPToolBindingResult,
    UnifiedDiscoveryRequest,
    UnifiedDiscoveryResult,
)
from app.mcp.client import MCPClient
from app.mcp.schemas import MCPToolDefinition
from app.tools.registry import ToolRegistry

log = structlog.get_logger()

# =============================================================================
# Authoritative Open-Source MCP Catalog
# =============================================================================

AUTHORITATIVE_MCP_CATALOG: dict[str, dict[str, Any]] = {
    "postgres": {
        "name": "PostgreSQL MCP Server",
        "transport": "stdio",
        "command": "npx",
        "arguments": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
        "description": "Read-only and read/write querying for PostgreSQL databases via Model Context Protocol.",
        "tools": ["query", "describe_table", "list_tables"],
    },
    "sqlite": {
        "name": "SQLite MCP Server",
        "transport": "stdio",
        "command": "uvx",
        "arguments": ["mcp-server-sqlite", "--db-path", "local.db"],
        "description": "Inspect, query, and manage local SQLite database files via Model Context Protocol.",
        "tools": ["read_query", "write_query", "create_table", "list_tables", "describe_table"],
    },
    "github": {
        "name": "GitHub MCP Server",
        "transport": "stdio",
        "command": "npx",
        "arguments": ["-y", "@modelcontextprotocol/server-github"],
        "description": "Search repos, create issues, review PRs, and inspect code on GitHub.",
        "tools": ["search_repositories", "create_issue", "get_file_contents", "create_pull_request"],
    },
    "slack": {
        "name": "Slack MCP Server",
        "transport": "stdio",
        "command": "npx",
        "arguments": ["-y", "@modelcontextprotocol/server-slack"],
        "description": "Post messages, list channels, and read thread history in Slack workspaces.",
        "tools": ["post_chat_message", "list_channels", "get_channel_history", "reply_to_thread"],
    },
    "filesystem": {
        "name": "Filesystem MCP Server",
        "transport": "stdio",
        "command": "npx",
        "arguments": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        "description": "Direct, secure filesystem read/write operations via Model Context Protocol.",
        "tools": ["read_file", "write_file", "list_directory", "move_file", "search_files"],
    },
    "puppeteer": {
        "name": "Puppeteer Web Automation MCP Server",
        "transport": "stdio",
        "command": "npx",
        "arguments": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "description": "Headless browser automation, page navigation, and web interaction via Puppeteer.",
        "tools": ["navigate", "screenshot", "click", "fill", "evaluate"],
    },
    "brave_search": {
        "name": "Brave Search MCP Server",
        "transport": "stdio",
        "command": "npx",
        "arguments": ["-y", "@modelcontextprotocol/server-brave-search"],
        "description": "Web search and local business search powered by the Brave Search API.",
        "tools": ["brave_web_search", "brave_local_search"],
    },
    "fetch": {
        "name": "Web Fetch MCP Server",
        "transport": "stdio",
        "command": "uvx",
        "arguments": ["mcp-server-fetch"],
        "description": "Fetch web pages and convert HTML to markdown for LLM consumption.",
        "tools": ["fetch"],
    },
    "git": {
        "name": "Git MCP Server",
        "transport": "stdio",
        "command": "uvx",
        "arguments": ["mcp-server-git"],
        "description": "Inspect git repositories, diffs, log histories, and status via Model Context Protocol.",
        "tools": ["git_status", "git_diff", "git_log", "git_show"],
    },
    "memory": {
        "name": "Knowledge Graph Memory MCP Server",
        "transport": "stdio",
        "command": "npx",
        "arguments": ["-y", "@modelcontextprotocol/server-memory"],
        "description": "Persistent graph-based memory and relation store for multi-turn reasoning.",
        "tools": ["create_entities", "create_relations", "read_graph", "search_nodes"],
    },
}


# =============================================================================
# Dynamic Tool Binding Registry
# =============================================================================


class DiscoveryBindingRegistry:
    """Thread-safe registry tracking all dynamically bound MCP and Connector tools."""

    _instance: DiscoveryBindingRegistry | None = None

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()
        self._bindings: dict[str, dict[str, Any]] = {}
        self._active_clients: dict[str, MCPClient] = {}
        self._active_connectors: dict[str, BaseConnector] = {}

    @classmethod
    def get_instance(cls) -> DiscoveryBindingRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_binding(
        self,
        binding_id: str,
        source_type: str,
        source_id: str,
        name: str,
        bound_tools: list[str],
        client: MCPClient | None = None,
        connector: BaseConnector | None = None,
    ) -> None:
        """Register a dynamic tool binding record."""
        self._bindings[binding_id] = {
            "binding_id": binding_id,
            "source_type": source_type,
            "source_id": source_id,
            "name": name,
            "bound_tools": bound_tools,
            "bound_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if client:
            self._active_clients[binding_id] = client
        if connector:
            self._active_connectors[binding_id] = connector

    def get_binding(self, binding_id: str) -> dict[str, Any] | None:
        """Retrieve binding details."""
        return self._bindings.get(binding_id)

    def list_bindings(self) -> list[dict[str, Any]]:
        """List all active dynamic tool bindings."""
        return list(self._bindings.values())

    def unbind(self, binding_id: str) -> bool:
        """Unbind and unregister all associated tools from ToolRegistry."""
        b = self._bindings.pop(binding_id, None)
        if not b:
            return False

        for tid in b.get("bound_tools", []):
            self._tool_registry.unregister(tid)

        self._active_clients.pop(binding_id, None)
        self._active_connectors.pop(binding_id, None)
        log.info("discovery_binding_registry.unbound", binding_id=binding_id, tools=b.get("bound_tools", []))
        return True

    def clear(self) -> None:
        """Clear all bindings and unregister all dynamically bound tools."""
        for bid in list(self._bindings.keys()):
            self.unbind(bid)
        self._bindings.clear()
        self._active_clients.clear()
        self._active_connectors.clear()


def get_discovery_binding_registry() -> DiscoveryBindingRegistry:
    return DiscoveryBindingRegistry.get_instance()


# =============================================================================
# MCP Discovery Engine
# =============================================================================


class MCPDiscoveryEngine:
    """Discovers MCP servers across configs, ports, processes, and catalogs."""

    @classmethod
    def get_standard_config_paths(cls) -> list[Path]:
        """Return list of standard filesystem locations where MCP configs reside."""
        paths: list[Path] = []
        home = Path.home()

        # 1. Claude Desktop configuration
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
        paths.append(home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
        paths.append(home / ".config" / "Claude" / "claude_desktop_config.json")

        # 2. Standard user MCP config
        paths.append(home / ".config" / "mcp" / "config.json")
        paths.append(home / ".mcp" / "config.json")

        # 3. Workspace / Project config
        paths.append(Path(".agents") / "mcp_config.json")
        paths.append(Path(".mcp.json"))
        paths.append(Path("mcp.json"))

        return paths

    @classmethod
    def discover_config_servers(cls, extra_paths: list[Path] | None = None) -> tuple[list[MCPDiscoveredServer], list[str]]:
        """Scan configuration files on disk and extract declared MCP servers."""
        candidate_paths = cls.get_standard_config_paths()
        if extra_paths:
            candidate_paths.extend(extra_paths)

        servers: list[MCPDiscoveredServer] = []
        scanned_paths: list[str] = []

        for p in candidate_paths:
            p_str = str(p.resolve()) if p.is_absolute() else str(p)
            if not p.is_file():
                continue

            scanned_paths.append(p_str)
            try:
                content = p.read_text(encoding="utf-8")
                data = json.loads(content)
                if not isinstance(data, dict):
                    continue

                mcp_servers = data.get("mcpServers") or data.get("servers") or {}
                if not isinstance(mcp_servers, dict):
                    continue

                for s_name, s_conf in mcp_servers.items():
                    if not isinstance(s_conf, dict):
                        continue

                    # Check transport & endpoints
                    url = s_conf.get("url") or s_conf.get("endpoint_url")
                    cmd = s_conf.get("command")
                    args = s_conf.get("args") or s_conf.get("arguments") or []
                    env = s_conf.get("env") or {}

                    transport_val: Literal["sse", "stdio"] = "sse" if url else "stdio"

                    # Verify if binary is actually installed on PATH if stdio
                    is_installed = True
                    if cmd and not shutil.which(cmd):
                        is_installed = False

                    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    sid = f"cfg_{re.sub(r'[^a-zA-Z0-9_]', '_', s_name).lower()}"
                    servers.append(
                        MCPDiscoveredServer(
                            server_id=sid,
                            name=str(s_name),
                            transport=transport_val,
                            source=MCPDiscoverySource.CONFIG_FILE,
                            endpoint_url=url,
                            command=cmd,
                            arguments=[str(a) for a in args] if isinstance(args, list) else [],
                            env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {},
                            config_path=p_str,
                            is_active=is_installed,
                            discovered_at=now_str,
                        )
                    )
            except Exception as exc:
                log.warning("mcp_discovery.config_read_error", path=p_str, error=str(exc))

        return servers, scanned_paths

    @classmethod
    def probe_tcp_port(cls, host: str, port: int, timeout: float = 0.1) -> bool:
        """Perform a real non-destructive socket connect check."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, TimeoutError):
            return False

    @classmethod
    async def discover_local_sse_servers(cls, ports: list[int]) -> tuple[list[MCPDiscoveredServer], list[int]]:
        """Probe local network ports for active MCP SSE servers."""
        active_servers: list[MCPDiscoveredServer] = []
        probed_ports: list[int] = []

        for port in ports:
            probed_ports.append(port)
            # 1. Quick socket check
            if not cls.probe_tcp_port("127.0.0.1", port, timeout=0.15):
                continue

            # 2. HTTP check for SSE endpoint
            candidate_urls = [
                f"http://127.0.0.1:{port}/sse",
                f"http://127.0.0.1:{port}/mcp/sse",
                f"http://127.0.0.1:{port}/",
            ]

            for url in candidate_urls:
                try:
                    async with httpx.AsyncClient(timeout=0.6) as client:
                        resp = await client.get(url, headers={"Accept": "text/event-stream, application/json"})
                        ct = resp.headers.get("content-type", "").lower()
                        # If endpoint is streaming SSE or reports MCP/JSON-RPC signature
                        is_mcp = "text/event-stream" in ct or "mcp" in resp.text.lower() or "jsonrpc" in resp.text.lower()
                        if resp.status_code in (200, 204, 307) and is_mcp:
                            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            active_servers.append(
                                MCPDiscoveredServer(
                                    server_id=f"sse_127_0_0_1_{port}",
                                    name=f"Local MCP SSE Server (Port {port})",
                                    transport="sse",
                                    source=MCPDiscoverySource.LOCAL_SSE_PORT,
                                    endpoint_url=url,
                                    is_active=True,
                                    discovered_at=now_str,
                                )
                            )
                            break
                except Exception:
                    continue

        return active_servers, probed_ports

    @classmethod
    def discover_running_mcp_processes(cls) -> list[MCPDiscoveredServer]:
        """Inspect running operating system processes for active MCP server processes."""
        discovered: list[MCPDiscoveredServer] = []
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = proc.info.get("cmdline") or []
                    if not cmdline:
                        continue
                    cmdline_str = " ".join(cmdline).lower()
                    if any(token in cmdline_str for token in ("mcp-server", "@modelcontextprotocol", "uvx mcp-", "mcp_server")):
                        p_name = proc.info.get("name") or "mcp_proc"
                        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        discovered.append(
                            MCPDiscoveredServer(
                                server_id=f"proc_{proc.info['pid']}",
                                name=f"Running Process: {p_name} (PID {proc.info['pid']})",
                                transport="stdio",
                                source=MCPDiscoverySource.RUNNING_PROCESS,
                                command=cmdline[0],
                                arguments=cmdline[1:],
                                pid=proc.info["pid"],
                                is_active=True,
                                discovered_at=now_str,
                            )
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as exc:
            log.warning("mcp_discovery.process_scan_failed", error=str(exc))

        return discovered

    @classmethod
    def discover_catalog_servers(cls, target_app: str | None = None) -> list[MCPDiscoveredServer]:
        """Match application against authoritative open-source MCP catalog."""
        suggestions: list[MCPDiscoveredServer] = []
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        target_norm = IntegrationResolver.normalize_app_name(target_app) if target_app else None

        for key, entry in AUTHORITATIVE_MCP_CATALOG.items():
            if target_norm and key != target_norm and target_norm not in key and key not in target_norm:
                continue

            # Verify if executor exists on system PATH
            cmd = entry.get("command")
            is_avail = bool(cmd and shutil.which(cmd))

            tool_defs = [{"name": t, "description": f"{entry['name']} action: {t}"} for t in entry.get("tools", [])]

            suggestions.append(
                MCPDiscoveredServer(
                    server_id=f"catalog_{key}",
                    name=entry["name"],
                    transport="stdio" if entry.get("transport") == "stdio" else "sse",
                    source=MCPDiscoverySource.AUTHORITATIVE_CATALOG,
                    command=entry.get("command"),
                    arguments=entry.get("arguments", []),
                    is_active=is_avail,
                    tools_count=len(tool_defs),
                    discovered_tools=tool_defs,
                    discovered_at=now_str,
                )
            )

        return suggestions

    @classmethod
    async def scan(cls, request: MCPDiscoveryRequest) -> MCPDiscoveryResult:
        """Execute full MCP discovery scan across all requested vectors."""
        start_time = time.perf_counter()
        active_servers: list[MCPDiscoveredServer] = []
        catalog_suggestions: list[MCPDiscoveredServer] = []
        configs_scanned: list[str] = []
        ports_scanned: list[int] = []

        # 1. Config file scan
        if request.scan_configs:
            cfg_servers, paths = cls.discover_config_servers()
            configs_scanned.extend(paths)
            active_servers.extend(cfg_servers)

        # 2. Local SSE port scan
        if request.scan_ports:
            sse_servers, ports = await cls.discover_local_sse_servers(request.ports_to_scan)
            ports_scanned.extend(ports)
            active_servers.extend(sse_servers)

        # 3. Running process scan
        if request.scan_processes:
            proc_servers = cls.discover_running_mcp_processes()
            active_servers.extend(proc_servers)

        # 4. Catalog matching
        if request.include_catalog:
            catalog_suggestions = cls.discover_catalog_servers(request.target_app)

        # Filter by target_app if specified
        if request.target_app:
            needle = request.target_app.lower()
            active_servers = [
                s for s in active_servers
                if needle in s.name.lower() or (s.command and needle in s.command.lower())
            ]

        # Deduplicate by server_id
        seen_ids: set[str] = set()
        deduped_active: list[MCPDiscoveredServer] = []
        for s in active_servers:
            if s.server_id not in seen_ids:
                seen_ids.add(s.server_id)
                deduped_active.append(s)

        elapsed = round((time.perf_counter() - start_time) * 1000, 2)
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        return MCPDiscoveryResult(
            total_found=len(deduped_active) + len(catalog_suggestions),
            active_servers=deduped_active,
            catalog_suggestions=catalog_suggestions,
            configs_scanned=configs_scanned,
            ports_scanned=ports_scanned,
            scan_duration_ms=elapsed,
            scanned_at=now_str,
        )

    @classmethod
    async def bind_server(cls, request: MCPToolBindingRequest) -> MCPToolBindingResult:
        """Connect to an MCP server, discover its tools via JSON-RPC, and register into ToolRegistry."""
        server = request.server
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        binding_id = f"bind_mcp_{uuid.uuid4().hex[:8]}"

        client = MCPClient(
            server_id=server.server_id,
            name=server.name,
            transport=server.transport,
            endpoint_url=server.endpoint_url,
            command=server.command,
            arguments=server.arguments,
            env=server.env,
        )

        tools_to_bind: list[MCPToolDefinition] = []

        if request.auto_handshake:
            try:
                await client.initialize()
                tools_to_bind = await client.list_tools()
            except Exception as exc:
                err_msg = f"Handshake failed with MCP server '{server.name}': {exc}"
                log.warning("mcp_discovery.handshake_failed", server=server.name, error=str(exc))
                return MCPToolBindingResult(
                    success=False,
                    server_id=server.server_id,
                    server_name=server.name,
                    binding_id=binding_id,
                    verification_status="failed",
                    error=err_msg,
                    bound_at=now_str,
                )
        else:
            # Bind pre-declared tool definitions
            tools_to_bind = [
                MCPToolDefinition(
                    name=t.get("name", "tool"),
                    description=t.get("description", ""),
                    inputSchema=t.get("input_schema") or t.get("inputSchema") or {},
                )
                for t in server.discovered_tools
            ]

        # Convert to AgentTools and register in ToolRegistry
        agent_tools = client.convert_to_agent_tools(tools_to_bind)
        bound_ids: list[str] = []
        registry = ToolRegistry.get_instance()

        for atool, mtool in zip(agent_tools, tools_to_bind, strict=False):
            t_name = mtool.name

            # Dynamic execution handler wrapping MCPClient.call_tool
            async def _mcp_handler(c: MCPClient = client, tn: str = t_name, **kwargs: Any) -> dict[str, Any]:
                return await c.call_tool(tn, kwargs)

            registry.register(atool, _mcp_handler)
            bound_ids.append(atool.id)

        # Track in DiscoveryBindingRegistry
        get_discovery_binding_registry().register_binding(
            binding_id=binding_id,
            source_type="mcp",
            source_id=server.server_id,
            name=server.name,
            bound_tools=bound_ids,
            client=client,
        )

        return MCPToolBindingResult(
            success=True,
            server_id=server.server_id,
            server_name=server.name,
            bound_tools=bound_ids,
            total_bound=len(bound_ids),
            binding_id=binding_id,
            verification_status="verified" if request.auto_handshake else "unverified",
            bound_at=now_str,
        )


# =============================================================================
# Connector Discovery Engine
# =============================================================================


class ConnectorDiscoveryEngine:
    """Discovers Cloud Connectors, active instances, local OpenAPI endpoints, and credentials."""

    @classmethod
    def discover_environment_credentials(cls) -> list[ConnectorDiscoveredItem]:
        """Detect available API keys or tokens in environment variables."""
        discovered: list[ConnectorDiscoveredItem] = []
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        env_map: dict[str, tuple[str, str, str]] = {
            "GITHUB_TOKEN": ("github", "GitHub API", "Personal Access Token discovered in GITHUB_TOKEN"),
            "GH_TOKEN": ("github", "GitHub API", "CLI token discovered in GH_TOKEN"),
            "SLACK_BOT_TOKEN": ("slack", "Slack Workspace", "Bot token discovered in SLACK_BOT_TOKEN"),
            "SLACK_API_TOKEN": ("slack", "Slack Workspace", "API token discovered in SLACK_API_TOKEN"),
            "NOTION_API_KEY": ("notion", "Notion Workspace", "Internal integration token discovered in NOTION_API_KEY"),
            "NOTION_TOKEN": ("notion", "Notion Workspace", "Integration token discovered in NOTION_TOKEN"),
            "OPENAI_API_KEY": ("openapi", "OpenAI REST API", "API key discovered in OPENAI_API_KEY"),
            "ANTHROPIC_API_KEY": ("openapi", "Anthropic REST API", "API key discovered in ANTHROPIC_API_KEY"),
        }

        seen_types: set[str] = set()
        for env_var, (ctype, title, desc) in env_map.items():
            if os.environ.get(env_var) and ctype not in seen_types:
                seen_types.add(ctype)
                discovered.append(
                    ConnectorDiscoveredItem(
                        connector_id=f"env_{ctype}",
                        connector_type=ctype,
                        title=title,
                        description=desc,
                        source=ConnectorDiscoverySource.ENVIRONMENT_CREDENTIALS,
                        has_credentials=True,
                        auth_methods=["token"],
                        health_status="healthy",
                        discovered_at=now_str,
                    )
                )

        return discovered

    @classmethod
    async def discover_openapi_endpoints(cls, ports: list[int]) -> list[ConnectorDiscoveredItem]:
        """Scan localhost ports for live OpenAPI 3.0 / Swagger specifications."""
        endpoints: list[ConnectorDiscoveredItem] = []
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        candidate_paths = [
            "/openapi.json",
            "/swagger.json",
            "/api/v1/openapi.json",
            "/docs/openapi.json",
        ]

        for port in ports:
            # Socket check first
            if not MCPDiscoveryEngine.probe_tcp_port("127.0.0.1", port, timeout=0.15):
                continue

            base_url = f"http://127.0.0.1:{port}"
            for path in candidate_paths:
                full_url = f"{base_url}{path}"
                try:
                    async with httpx.AsyncClient(timeout=0.6) as client:
                        resp = await client.get(full_url)
                        if resp.status_code == 200:
                            data = resp.json()
                            if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
                                info = data.get("info", {})
                                title = info.get("title") or f"OpenAPI Service (Port {port})"
                                desc = info.get("description") or f"Dynamic REST API discovered at {full_url}"

                                # Parse available operations
                                actions: list[str] = []
                                paths_dict = data.get("paths", {})
                                if isinstance(paths_dict, dict):
                                    for p_url, p_item in paths_dict.items():
                                        if isinstance(p_item, dict):
                                            for method in ["get", "post", "put", "delete", "patch"]:
                                                if method in p_item:
                                                    op_data = p_item[method]
                                                    op_id = op_data.get("operationId") or f"{method}_{p_url.strip('/').replace('/', '_')}"
                                                    actions.append(op_id)

                                endpoints.append(
                                    ConnectorDiscoveredItem(
                                        connector_id=f"openapi_port_{port}",
                                        connector_type="openapi",
                                        title=str(title),
                                        description=str(desc),
                                        source=ConnectorDiscoverySource.OPENAPI_ENDPOINT,
                                        has_credentials=False,
                                        auth_methods=["none", "bearer"],
                                        base_url=base_url,
                                        spec_url=full_url,
                                        available_actions=actions,
                                        action_count=len(actions),
                                        health_status="healthy",
                                        discovered_at=now_str,
                                    )
                                )
                                break
                except Exception:
                    continue

        return endpoints

    @classmethod
    def discover_catalog_connectors(cls, target_app: str | None = None) -> list[ConnectorDiscoveredItem]:
        """Discover connectors supported in Roxy's authoritative connector catalog."""
        catalog_items: list[ConnectorDiscoveredItem] = []
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        target_norm = IntegrationResolver.normalize_app_name(target_app) if target_app else None

        for app_key, entry in KNOWN_CONNECTOR_CATALOG.items():
            if target_norm and app_key != target_norm and target_norm not in app_key and app_key not in target_norm:
                continue

            actions = list(entry.get("capabilities", {}).values())
            catalog_items.append(
                ConnectorDiscoveredItem(
                    connector_id=f"catalog_{app_key}",
                    connector_type=entry["connector_type"],
                    title=entry["title"],
                    description=f"Official {entry['title']} Cloud / SaaS Connector.",
                    source=ConnectorDiscoverySource.AUTHORITATIVE_CATALOG,
                    has_credentials=False,
                    auth_methods=["oauth2", "api_key"],
                    available_actions=actions,
                    action_count=len(actions),
                    health_status="unauthenticated",
                    discovered_at=now_str,
                )
            )

        return catalog_items

    @classmethod
    async def scan(cls, request: ConnectorDiscoveryRequest, user_id: str = "default") -> ConnectorDiscoveryResult:
        """Scan across active instances, OpenAPI endpoints, credentials, and catalog."""
        start_time = time.perf_counter()
        active_connectors: list[ConnectorDiscoveredItem] = []
        openapi_endpoints: list[ConnectorDiscoveredItem] = []
        catalog_connectors: list[ConnectorDiscoveredItem] = []

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # 1. Environment credentials
        if request.include_environment:
            env_items = cls.discover_environment_credentials()
            active_connectors.extend(env_items)

        # 2. Local OpenAPI endpoints
        if request.scan_openapi_ports:
            openapi_endpoints = await cls.discover_openapi_endpoints(request.openapi_ports)

        # 3. Active configured connectors from ConnectorService
        try:
            conn_service = ConnectorService()
            user_conns = await conn_service.list_connectors(user_id)
            for c in user_conns:
                active_connectors.append(
                    ConnectorDiscoveredItem(
                        connector_id=c.id,
                        connector_type=c.connector_type,
                        title=c.name,
                        description=c.description or f"Configured {c.connector_type} connector",
                        source=ConnectorDiscoverySource.ACTIVE_INSTANCE,
                        has_credentials=True,
                        auth_methods=[c.auth_type] if c.auth_type else ["token"],
                        health_status="healthy" if c.status == "active" else "untested",
                        action_count=c.action_count,
                        discovered_at=now_str,
                    )
                )
        except Exception as exc:
            log.warning("connector_discovery.service_list_failed", error=str(exc))

        # 4. Catalog connectors
        if request.include_catalog:
            catalog_connectors = cls.discover_catalog_connectors(request.target_app)

        # Filter by target_app if specified
        if request.target_app:
            needle = request.target_app.lower()
            active_connectors = [
                c for c in active_connectors
                if needle in c.title.lower() or needle in c.connector_type.lower()
            ]
            openapi_endpoints = [
                c for c in openapi_endpoints
                if needle in c.title.lower() or (c.base_url and needle in c.base_url.lower())
            ]

        elapsed = round((time.perf_counter() - start_time) * 1000, 2)

        return ConnectorDiscoveryResult(
            total_found=len(active_connectors) + len(openapi_endpoints) + len(catalog_connectors),
            active_connectors=active_connectors,
            openapi_endpoints=openapi_endpoints,
            catalog_connectors=catalog_connectors,
            scan_duration_ms=elapsed,
            scanned_at=now_str,
        )

    @classmethod
    async def bind_connector(cls, request: ConnectorToolBindingRequest) -> ConnectorToolBindingResult:
        """Instantiate a connector and register its actions as AgentTools in ToolRegistry."""
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        binding_id = f"bind_conn_{uuid.uuid4().hex[:8]}"
        cid = f"conn_{uuid.uuid4().hex[:8]}"

        connector: BaseConnector | None = None

        if request.connector_type.lower() == "openapi":
            spec = request.openapi_spec or {}
            base_url = request.openapi_base_url or request.config.get("base_url", "http://127.0.0.1:8000")
            config = {"spec": spec, "base_url": base_url}
            connector = OpenAPIConnector(instance_id=cid, name=request.name, config=config, credentials=request.credentials)
        else:
            conn_service = ConnectorService()
            connector = conn_service._instantiate_connector(
                instance_id=cid,
                connector_type=request.connector_type,
                name=request.name,
                config=request.config,
                credentials=request.credentials,
            )

        if not connector:
            return ConnectorToolBindingResult(
                success=False,
                connector_id=cid,
                connector_name=request.name,
                connector_type=request.connector_type,
                binding_id=binding_id,
                health_status="error",
                error=f"Unsupported connector type: {request.connector_type}",
                bound_at=now_str,
            )

        # Register tools in ToolRegistry
        actions = connector.list_actions()
        registry = ToolRegistry.get_instance()
        bound_ids: list[str] = []

        for action_tool in actions:
            act_id = action_tool.id

            async def _exec_action(c: BaseConnector = connector, a: str = act_id, **kwargs: Any) -> dict[str, Any]:
                return await c.execute_action(a, kwargs)

            registry.register(action_tool, _exec_action)
            bound_ids.append(action_tool.id)

        # Test live connection under Zero Simulation
        test_res = await connector.test_connection()

        # Track in DiscoveryBindingRegistry
        get_discovery_binding_registry().register_binding(
            binding_id=binding_id,
            source_type="connector",
            source_id=cid,
            name=request.name,
            bound_tools=bound_ids,
            connector=connector,
        )

        return ConnectorToolBindingResult(
            success=True,
            connector_id=cid,
            connector_name=request.name,
            connector_type=request.connector_type,
            bound_tools=bound_ids,
            total_bound=len(bound_ids),
            binding_id=binding_id,
            health_status="healthy" if test_res.success else "untested",
            bound_at=now_str,
        )


# =============================================================================
# Unified Discovery Engine
# =============================================================================


class UnifiedMCPConnectorDiscoveryEngine:
    """Unified engine coordinating runtime MCP and Connector discovery and auto-binding."""

    @classmethod
    async def discover_and_bind(
        cls,
        request: UnifiedDiscoveryRequest,
        user_id: str = "default",
    ) -> UnifiedDiscoveryResult:
        """Execute unified discovery and optional dynamic tool binding."""
        start_time = time.perf_counter()

        # 1. MCP Discovery
        mcp_res = MCPDiscoveryResult()
        if request.scan_mcp:
            mcp_req = MCPDiscoveryRequest(
                device_id=request.device_id,
                target_app=request.target_app,
                scan_configs=True,
                scan_ports=True,
                scan_processes=True,
                include_catalog=True,
            )
            mcp_res = await MCPDiscoveryEngine.scan(mcp_req)

        # 2. Connector Discovery
        conn_res = ConnectorDiscoveryResult()
        if request.scan_connectors:
            conn_req = ConnectorDiscoveryRequest(
                device_id=request.device_id,
                target_app=request.target_app,
                scan_openapi_ports=True,
                include_environment=True,
                include_catalog=True,
            )
            conn_res = await ConnectorDiscoveryEngine.scan(conn_req, user_id=user_id)

        # 3. Dynamic Tool Auto-Binding (if requested)
        bound_tool_ids: list[str] = []

        if request.auto_bind:
            # Bind active MCP servers
            for s in mcp_res.active_servers:
                if s.is_active:
                    bind_req = MCPToolBindingRequest(device_id=request.device_id, server=s, auto_handshake=False)
                    b_res = await MCPDiscoveryEngine.bind_server(bind_req)
                    if b_res.success:
                        bound_tool_ids.extend(b_res.bound_tools)

            # Bind active OpenAPI endpoints
            for o in conn_res.openapi_endpoints:
                if o.spec_url and o.base_url:
                    try:
                        async with httpx.AsyncClient(timeout=1.0) as client:
                            spec_resp = await client.get(o.spec_url)
                            if spec_resp.status_code == 200:
                                spec_dict = spec_resp.json()
                                c_bind_req = ConnectorToolBindingRequest(
                                    device_id=request.device_id,
                                    connector_type="openapi",
                                    name=o.title,
                                    openapi_spec=spec_dict,
                                    openapi_base_url=o.base_url,
                                )
                                c_bind_res = await ConnectorDiscoveryEngine.bind_connector(c_bind_req)
                                if c_bind_res.success:
                                    bound_tool_ids.extend(c_bind_res.bound_tools)
                    except Exception as exc:
                        log.warning("unified_discovery.openapi_bind_failed", url=o.spec_url, error=str(exc))

        # 4. Generate Ranked Integration Pathways (Tiers 1 & 2)
        ranked_pathways: list[DiscoveredIntegrationPathway] = []

        # Tier 1: Cloud Connectors & OpenAPI
        for c in conn_res.active_connectors:
            ranked_pathways.append(
                DiscoveredIntegrationPathway(
                    pathway_id=f"connector_{c.connector_type}_{c.connector_id}",
                    integration_tier="connector",
                    priority_rank=1,
                    name=f"Connector: {c.title}",
                    description=f"Active Cloud Connector ({c.title}) with available credentials.",
                    confidence_score=0.95 if c.has_credentials else 0.55,
                    estimated_latency_ms=120.0,
                    risk_level="LOW",
                    execution_adapter="connector_service",
                    verification_strategy="connection_health_check",
                    required_permission=f"connector:{c.connector_type}:execute",
                    requires_confirmation=False,
                )
            )

        for o in conn_res.openapi_endpoints:
            ranked_pathways.append(
                DiscoveredIntegrationPathway(
                    pathway_id=f"openapi_{o.connector_id}",
                    integration_tier="connector",
                    priority_rank=1,
                    name=f"OpenAPI: {o.title}",
                    description=f"Local OpenAPI REST endpoint exposing {o.action_count} dynamic operations.",
                    confidence_score=0.90,
                    estimated_latency_ms=80.0,
                    risk_level="LOW",
                    execution_adapter="openapi_connector",
                    verification_strategy="http_status_probe",
                    required_permission="openapi:execute",
                    requires_confirmation=False,
                )
            )

        # Tier 2: MCP Servers
        for s in mcp_res.active_servers:
            ranked_pathways.append(
                DiscoveredIntegrationPathway(
                    pathway_id=f"mcp_{s.server_id}",
                    integration_tier="mcp_tool",
                    priority_rank=2,
                    name=f"MCP: {s.name}",
                    description=f"Model Context Protocol ({s.name}) server over {s.transport.upper()} transport.",
                    confidence_score=0.92 if s.is_active else 0.60,
                    estimated_latency_ms=150.0,
                    risk_level="LOW",
                    execution_adapter="mcp_client",
                    verification_strategy="mcp_handshake_probe",
                    required_permission="mcp:execute",
                    requires_confirmation=False,
                )
            )

        # Sort by priority rank ascending, then confidence score descending
        ranked_pathways.sort(key=lambda p: (p.priority_rank, -p.confidence_score))

        elapsed = round((time.perf_counter() - start_time) * 1000, 2)
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        return UnifiedDiscoveryResult(
            target_app=request.target_app,
            mcp_discovery=mcp_res,
            connector_discovery=conn_res,
            bound_tools=bound_tool_ids,
            total_tools_bound=len(bound_tool_ids),
            ranked_pathways=ranked_pathways,
            duration_ms=elapsed,
            discovered_at=now_str,
        )
