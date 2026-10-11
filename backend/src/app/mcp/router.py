"""FastAPI router for Model Context Protocol (MCP) server management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.mcp.schemas import (
    MCPCallToolRequest,
    MCPServerCreateRequest,
    MCPServerResponse,
    MCPServerUpdateRequest,
    MCPSyncResult,
)
from app.mcp.service import MCPService

router = APIRouter(prefix="/mcp", tags=["mcp"])
_service = MCPService()


def get_mcp_service() -> MCPService:
    return _service


@router.get("/servers", response_model=list[MCPServerResponse])
async def list_servers(
    user: User = Depends(get_current_user),
) -> list[MCPServerResponse]:
    """List all MCP servers registered by user."""
    return await _service.list_servers(user_id=user.id)


@router.post("/servers", response_model=MCPServerResponse, status_code=status.HTTP_201_CREATED)
async def create_server(
    req: MCPServerCreateRequest,
    user: User = Depends(get_current_user),
) -> MCPServerResponse:
    """Register a new MCP server and discover its capabilities."""
    try:
        return await _service.create_server(user_id=user.id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_server(
    server_id: str,
    user: User = Depends(get_current_user),
) -> MCPServerResponse:
    """Retrieve details of an MCP server and its discovered tools."""
    server = await _service.get_server(user_id=user.id, server_id=server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MCP server '{server_id}' not found.")
    return server


@router.put("/servers/{server_id}", response_model=MCPServerResponse)
async def update_server(
    server_id: str,
    req: MCPServerUpdateRequest,
    user: User = Depends(get_current_user),
) -> MCPServerResponse:
    """Update MCP server configuration."""
    try:
        return await _service.update_server(user_id=user.id, server_id=server_id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_server(
    server_id: str,
    user: User = Depends(get_current_user),
) -> Response:
    """Delete an MCP server and unregister all its discovered tools."""
    deleted = await _service.delete_server(user_id=user.id, server_id=server_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MCP server '{server_id}' not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.post("/servers/{server_id}/sync", response_model=MCPSyncResult)
async def sync_server(
    server_id: str,
    user: User = Depends(get_current_user),
) -> MCPSyncResult:
    """Perform protocol handshake and synchronize discovered tools into Tool Registry."""
    try:
        return await _service.sync_server(user_id=user.id, server_id=server_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MCP handshake failed: {exc}") from exc


@router.post("/servers/{server_id}/call")
async def call_server_tool(
    server_id: str,
    req: MCPCallToolRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Directly call a tool on an external MCP server."""
    try:
        return await _service.call_tool(
            user_id=user.id,
            server_id=server_id,
            tool_name=req.tool_name,
            arguments=req.arguments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MCP call failed: {exc}") from exc
