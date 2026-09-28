"""Schemas and JSON-RPC 2.0 types for the Model Context Protocol (MCP) engine.

Conforms to the MCP specification (protocol version 2024-11-05).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MCPTransportType(StrEnum):
    SSE = "sse"
    STDIO = "stdio"


class MCPServerStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


# --- JSON-RPC 2.0 primitives ---


class JSONRPCRequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: str | int
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JSONRPCNotification(BaseModel):
    jsonrpc: str = Field(default="2.0")
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: str | int | None = None
    result: Any = None
    error: JSONRPCError | None = None


# --- MCP Protocol Objects ---


class MCPToolDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")


class MCPResourceDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    uri: str
    name: str
    description: str | None = None
    mime_type: str | None = Field(default=None, alias="mimeType")


class MCPPromptDefinition(BaseModel):
    name: str
    description: str | None = None
    arguments: list[dict[str, Any]] = Field(default_factory=list)


# --- API Request & Response Models ---


class MCPServerCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=255)
    transport: MCPTransportType = Field(default=MCPTransportType.SSE)
    endpoint_url: str | None = None
    command: str | None = None
    arguments: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    workspace_id: str | None = None


class MCPServerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=255)
    endpoint_url: str | None = None
    command: str | None = None
    arguments: list[str] | None = None
    env: dict[str, str] | None = None


class MCPServerResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    name: str
    description: str | None = None
    transport: str
    endpoint_url: str | None = None
    command: str | None = None
    arguments: list[str] = Field(default_factory=list)
    status: str
    protocol_version: str
    discovered_tools: list[dict[str, Any]] = Field(default_factory=list)
    discovered_resources: list[dict[str, Any]] = Field(default_factory=list)
    discovered_prompts: list[dict[str, Any]] = Field(default_factory=list)
    last_synced_at: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    tool_count: int = 0


class MCPSyncResult(BaseModel):
    server_id: str
    name: str
    status: str
    protocol_version: str
    tools_count: int
    resources_count: int
    prompts_count: int
    tools: list[dict[str, Any]]


class MCPCallToolRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
