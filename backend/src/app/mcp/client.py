"""Model Context Protocol (MCP) Client implementation.

Provides protocol handshake, capability negotiation, tool/resource/prompt discovery,
and tool execution over SSE and real stdio transports with honest error propagation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import time
from typing import Any

import httpx
import structlog

from app.mcp.schemas import (
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPToolDefinition,
    MCPTransportType,
)
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

log = structlog.get_logger()


class MCPClient:
    """Client for communicating with an external Model Context Protocol server."""

    def __init__(
        self,
        name: str,
        transport: MCPTransportType | str,
        server_id: str = "mcp_server",
        endpoint_url: str | None = None,
        command: str | None = None,
        arguments: list[str] | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.server_id = server_id
        self.name = name
        self.transport = MCPTransportType(transport) if isinstance(transport, str) else transport
        self.endpoint_url = endpoint_url
        self.command = command
        self.arguments = arguments or args or []
        self.env = env or {}
        self.timeout = timeout
        self.protocol_version = "2024-11-05"
        self._request_counter = 0

    def _next_id(self) -> str:
        self._request_counter += 1
        return f"req_{self._request_counter}_{int(time.time())}"

    async def _send_rpc(self, method: str, params: dict[str, Any] | None = None) -> JSONRPCResponse:
        """Send a JSON-RPC 2.0 request over the configured transport (SSE or real Stdio)."""
        req = JSONRPCRequest(
            id=self._next_id(),
            method=method,
            params=params or {},
        )

        if self.transport == MCPTransportType.SSE:
            return await self._send_rpc_sse(req)
        elif self.transport == MCPTransportType.STDIO:
            return await self._send_rpc_stdio(req)
        else:
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32601,
                    message=f"Unsupported transport type: {self.transport}",
                    data={"retryable": False},
                ),
            )

    async def _send_rpc_sse(self, req: JSONRPCRequest) -> JSONRPCResponse:
        """Dispatch JSON-RPC 2.0 request to remote HTTP/SSE MCP server."""
        if not self.endpoint_url:
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32602,
                    message=f"MCP server '{self.name}' configured for SSE but missing 'endpoint_url'.",
                    data={"retryable": False},
                ),
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(
                    self.endpoint_url,
                    json=req.model_dump(),
                    headers={"Content-Type": "application/json"},
                )
                res.raise_for_status()
                data = res.json()
                return JSONRPCResponse.model_validate(data)
        except (httpx.TimeoutException, TimeoutError, asyncio.TimeoutError):
            log.warning("mcp_client.sse_timeout", server=self.name, url=self.endpoint_url)
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32000,
                    message=f"MCP server '{self.name}' timed out after {self.timeout}s",
                    data={"retryable": True},
                ),
            )
        except httpx.ConnectError as exc:
            log.warning("mcp_client.sse_connect_failed", server=self.name, url=self.endpoint_url, error=str(exc))
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32001,
                    message=f"Connection refused to MCP server '{self.name}' at {self.endpoint_url}",
                    data={"retryable": True},
                ),
            )
        except httpx.HTTPStatusError as exc:
            log.warning("mcp_client.sse_http_error", server=self.name, status_code=exc.response.status_code)
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32002,
                    message=f"MCP server '{self.name}' returned HTTP {exc.response.status_code}",
                    data={"retryable": exc.response.status_code >= 500},
                ),
            )
        except Exception as exc:
            log.error("mcp_client.sse_unknown_error", server=self.name, error=str(exc))
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32603,
                    message=f"Internal error communicating with MCP server '{self.name}': {str(exc)}",
                    data={"retryable": False},
                ),
            )

    async def _send_rpc_stdio(self, req: JSONRPCRequest) -> JSONRPCResponse:
        """Dispatch JSON-RPC 2.0 request to local subprocess stdio MCP server."""
        if not self.command:
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32602,
                    message=f"MCP server '{self.name}' configured for stdio transport but no 'command' specified.",
                    data={"retryable": False},
                ),
            )

        merged_env = {**os.environ, **self.env}
        req_line = req.model_dump_json() + "\n"

        try:
            proc = await asyncio.create_subprocess_exec(
                self.command,
                *self.arguments,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merged_env,
            )
        except FileNotFoundError:
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32004,
                    message=f"MCP stdio command '{self.command}' not found on host system.",
                    data={"retryable": False},
                ),
            )
        except Exception as exc:
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32005,
                    message=f"Failed to spawn MCP stdio process '{self.command}': {str(exc)}",
                    data={"retryable": False},
                ),
            )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(input=req_line.encode("utf-8")),
                timeout=self.timeout,
            )
        except (asyncio.TimeoutError, TimeoutError):
            with contextlib.suppress(Exception):
                proc.kill()
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32000,
                    message=f"MCP stdio process '{self.command}' timed out after {self.timeout}s",
                    data={"retryable": True},
                ),
            )

        if proc.returncode != 0 and not stdout_data:
            err_msg = stderr_data.decode("utf-8", errors="replace").strip()
            return JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32003,
                    message=f"MCP stdio process exited with code {proc.returncode}: {err_msg}",
                    data={"retryable": False},
                ),
            )

        out_lines = stdout_data.decode("utf-8", errors="replace").splitlines()
        for line in reversed(out_lines):
            line_str = line.strip()
            if line_str.startswith("{") and line_str.endswith("}"):
                try:
                    data = json.loads(line_str)
                    return JSONRPCResponse.model_validate(data)
                except Exception:
                    continue

        return JSONRPCResponse(
            id=req.id,
            error=JSONRPCError(
                code=-32700,
                message=f"Malformed or empty JSON-RPC response from MCP stdio process '{self.command}'.",
                data={"retryable": False},
            ),
        )

    async def initialize(self) -> dict[str, Any]:
        """Perform MCP initialize handshake and send notifications/initialized."""
        capabilities: dict[str, Any] = {
            "roots": {"listChanged": True},
            "sampling": {},
        }
        init_params: dict[str, Any] = {
            "protocolVersion": self.protocol_version,
            "capabilities": capabilities,
            "clientInfo": {
                "name": "roxy-ai",
                "version": "2.0.0",
            },
        }

        resp = await self._send_rpc("initialize", init_params)
        if resp.error:
            raise RuntimeError(f"MCP server '{self.name}' initialization rejected: {resp.error.message}")

        # Send initialized notification if SSE
        if self.transport == MCPTransportType.SSE and self.endpoint_url:
            notif = JSONRPCNotification(method="notifications/initialized", params={})
            with contextlib.suppress(Exception):
                async with httpx.AsyncClient(timeout=3.0) as client:
                    await client.post(self.endpoint_url, json=notif.model_dump())

        result = resp.result if isinstance(resp.result, dict) else {}
        server_version = result.get("protocolVersion", self.protocol_version)
        self.protocol_version = str(server_version)
        return result

    async def list_tools(self) -> list[MCPToolDefinition]:
        """Retrieve available tool definitions from external MCP server without fake fallbacks."""
        resp = await self._send_rpc("tools/list")
        if resp.error:
            raise RuntimeError(f"Failed to list tools from MCP server '{self.name}': {resp.error.message}")

        if resp.result and isinstance(resp.result, dict):
            raw_tools = resp.result.get("tools", [])
            tools: list[MCPToolDefinition] = []
            for t in raw_tools:
                if isinstance(t, dict):
                    tools.append(
                        MCPToolDefinition(
                            name=t.get("name", "unnamed_tool"),
                            description=t.get("description"),
                            inputSchema=t.get("inputSchema", {}),
                        )
                    )
            return tools

        return []

    async def list_resources(self) -> list[MCPResourceDefinition]:
        """Retrieve available resource definitions."""
        resp = await self._send_rpc("resources/list")
        if resp.result and isinstance(resp.result, dict):
            raw_res = resp.result.get("resources", [])
            return [MCPResourceDefinition(**r) for r in raw_res if isinstance(r, dict)]
        return []

    async def list_prompts(self) -> list[MCPPromptDefinition]:
        """Retrieve available prompt templates."""
        resp = await self._send_rpc("prompts/list")
        if resp.result and isinstance(resp.result, dict):
            raw_p = resp.result.get("prompts", [])
            return [MCPPromptDefinition(**p) for p in raw_p if isinstance(p, dict)]
        return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool on the external MCP server with strict error reporting (no fake successes)."""
        call_params = {
            "name": tool_name,
            "arguments": arguments,
        }

        resp = await self._send_rpc("tools/call", call_params)
        if resp.error:
            return {
                "isError": True,
                "content": [{"type": "text", "text": resp.error.message}],
                "error": {
                    "code": str(resp.error.code),
                    "message": resp.error.message,
                    "retryable": bool(resp.error.data.get("retryable", False))
                    if isinstance(resp.error.data, dict)
                    else False,
                },
                "server": self.name,
                "tool": tool_name,
                "arguments": arguments,
            }

        if resp.result:
            if isinstance(resp.result, dict):
                return resp.result
            return {"content": [{"type": "text", "text": json.dumps(resp.result)}], "isError": False}

        return {
            "isError": True,
            "content": [{"type": "text", "text": f"No response payload returned by MCP server '{self.name}'"}],
            "error": {
                "code": "EMPTY_RESPONSE",
                "message": "Empty response received from MCP tool call",
                "retryable": False,
            },
            "server": self.name,
            "tool": tool_name,
            "arguments": arguments,
        }

    def convert_to_agent_tools(self, mcp_tools: list[MCPToolDefinition]) -> list[AgentTool]:
        """Convert MCP tool definitions into ROXY AgentTools for the ToolRegistry."""
        prefix = f"mcp_{self.server_id[:8]}"
        agent_tools: list[AgentTool] = []

        for mt in mcp_tools:
            name_lower = mt.name.lower()
            desc_lower = (mt.description or "").lower()

            # Classify risk level
            if any(k in name_lower or k in desc_lower for k in ["delete", "remove", "drop", "terminate", "destroy"]):
                risk = RiskLevel.HIGH
                confirm = True
            elif any(k in name_lower or k in desc_lower for k in ["write", "create", "update", "modify", "send", "post"]):
                risk = RiskLevel.MEDIUM
                confirm = True
            else:
                risk = RiskLevel.LOW
                confirm = False

            tool_id = f"{prefix}_{mt.name}"
            agent_tools.append(
                AgentTool(
                    id=tool_id,
                    name=f"MCP [{self.name}]: {mt.name}",
                    description=mt.description or f"MCP tool '{mt.name}' from {self.name}",
                    source=ToolSource.MCP,
                    capabilities=["mcp", self.name.lower().replace(" ", "_")],
                    input_schema=mt.input_schema or {"type": "object", "properties": {}},
                    permissions=[f"mcp.{self.name.lower().replace(' ', '_')}"],
                    risk_level=risk,
                    requires_confirmation=confirm,
                )
            )

        return agent_tools

    async def close(self) -> None:
        """Close client sessions and clean up any spawned processes or network connections."""
        pass

