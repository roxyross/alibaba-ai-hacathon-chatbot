"""MCP Service managing server configurations, sync, and ToolRegistry registration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.db import get_session_factory
from app.mcp.client import MCPClient
from app.mcp.schemas import (
    MCPServerCreateRequest,
    MCPServerResponse,
    MCPServerStatus,
    MCPServerUpdateRequest,
    MCPSyncResult,
)
from app.models.mcp import MCPServerConfig
from app.tools.registry import ToolRegistry

log = structlog.get_logger()


class MCPService:
    """Manages MCP server registrations, discovery synchronization, and tool bridging."""

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()
        self._mem_servers: dict[str, dict[str, Any]] = {}
        self._active_clients: dict[str, MCPClient] = {}

    def _get_or_create_client(self, config_dict: dict[str, Any]) -> MCPClient:
        sid = config_dict["id"]
        if sid in self._active_clients:
            return self._active_clients[sid]

        client = MCPClient(
            server_id=sid,
            name=config_dict.get("name", "MCP Server"),
            transport=config_dict.get("transport", "sse"),
            endpoint_url=config_dict.get("endpoint_url"),
            command=config_dict.get("command"),
            arguments=config_dict.get("arguments", []),
            env=config_dict.get("env", {}),
        )
        self._active_clients[sid] = client
        return client

    async def create_server(self, user_id: str, req: MCPServerCreateRequest) -> MCPServerResponse:
        """Register a new MCP server configuration and optionally trigger initial sync."""
        sid = str(uuid.uuid4())
        now = datetime.now(UTC)

        record_dict: dict[str, Any] = {
            "id": sid,
            "user_id": user_id,
            "workspace_id": req.workspace_id,
            "name": req.name,
            "description": req.description,
            "transport": req.transport.value,
            "endpoint_url": req.endpoint_url,
            "command": req.command,
            "arguments": req.arguments,
            "env": req.env,
            "status": MCPServerStatus.DISCONNECTED.value,
            "protocol_version": "2024-11-05",
            "discovered_tools": [],
            "discovered_resources": [],
            "discovered_prompts": [],
            "last_synced_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    db_obj = MCPServerConfig(
                        id=sid,
                        user_id=user_id,
                        workspace_id=req.workspace_id,
                        name=req.name,
                        description=req.description,
                        transport=req.transport.value,
                        endpoint_url=req.endpoint_url,
                        command=req.command,
                        status=MCPServerStatus.DISCONNECTED.value,
                        protocol_version="2024-11-05",
                        created_at=now,
                        updated_at=now,
                    )
                    db_obj.set_arguments(req.arguments)
                    db_obj.set_env(req.env)
                    session.add(db_obj)
                    await session.commit()
            except Exception as exc:
                log.warning("mcp_service.db_create_failed", error=str(exc))

        self._mem_servers[sid] = record_dict

        # Auto-sync initially to discover tools
        try:
            await self.sync_server(user_id=user_id, server_id=sid)
        except Exception as exc:
            log.warning("mcp_service.initial_sync_failed", error=str(exc))

        updated = await self.get_server(user_id=user_id, server_id=sid)
        return updated or MCPServerResponse.model_validate(record_dict)

    async def get_server(self, user_id: str, server_id: str) -> MCPServerResponse | None:
        """Fetch MCP server by ID."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(MCPServerConfig).where(
                        MCPServerConfig.id == server_id,
                        MCPServerConfig.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        d = item.to_dict()
                        d["tool_count"] = len(d.get("discovered_tools", []))
                        return MCPServerResponse.model_validate(d)
            except Exception as exc:
                log.warning("mcp_service.db_get_failed", error=str(exc))

        mem = self._mem_servers.get(server_id)
        if mem and mem.get("user_id") == user_id:
            d = dict(mem)
            d["tool_count"] = len(d.get("discovered_tools", []))
            return MCPServerResponse.model_validate(d)

        return None

    async def list_servers(self, user_id: str) -> list[MCPServerResponse]:
        """List all MCP servers registered by user."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = (
                        select(MCPServerConfig)
                        .where(MCPServerConfig.user_id == user_id)
                        .order_by(MCPServerConfig.created_at.desc())
                    )
                    res = await session.execute(stmt)
                    items = res.scalars().all()
                    if items:
                        results: list[MCPServerResponse] = []
                        for it in items:
                            d = it.to_dict()
                            d["tool_count"] = len(d.get("discovered_tools", []))
                            results.append(MCPServerResponse.model_validate(d))
                        return results
            except Exception as exc:
                log.warning("mcp_service.db_list_failed", error=str(exc))

        user_servers = [s for s in self._mem_servers.values() if s.get("user_id") == user_id]
        results = []
        for mem in user_servers:
            d = dict(mem)
            d["tool_count"] = len(d.get("discovered_tools", []))
            results.append(MCPServerResponse.model_validate(d))
        return results

    async def update_server(
        self,
        user_id: str,
        server_id: str,
        req: MCPServerUpdateRequest,
    ) -> MCPServerResponse:
        """Update MCP server configuration and trigger re-handshake."""
        existing = await self.get_server(user_id, server_id)
        if not existing:
            raise ValueError(f"MCP server '{server_id}' not found.")

        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(MCPServerConfig).where(
                        MCPServerConfig.id == server_id,
                        MCPServerConfig.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        if req.name is not None:
                            item.name = req.name
                        if req.description is not None:
                            item.description = req.description
                        if req.endpoint_url is not None:
                            item.endpoint_url = req.endpoint_url
                        if req.command is not None:
                            item.command = req.command
                        if req.arguments is not None:
                            item.set_arguments(req.arguments)
                        if req.env is not None:
                            item.set_env(req.env)
                        item.updated_at = now
                        await session.commit()
            except Exception as exc:
                log.warning("mcp_service.db_update_failed", error=str(exc))

        mem = self._mem_servers.get(server_id, {})
        if req.name is not None:
            mem["name"] = req.name
        if req.description is not None:
            mem["description"] = req.description
        if req.endpoint_url is not None:
            mem["endpoint_url"] = req.endpoint_url
        if req.command is not None:
            mem["command"] = req.command
        if req.arguments is not None:
            mem["arguments"] = req.arguments
        if req.env is not None:
            mem["env"] = req.env
        mem["updated_at"] = now.isoformat()
        self._mem_servers[server_id] = mem

        # Clear active client cache so it reconnects with new config
        self._active_clients.pop(server_id, None)

        # Trigger sync
        await self.sync_server(user_id, server_id)
        return await self.get_server(user_id, server_id) or MCPServerResponse.model_validate(mem)

    async def delete_server(self, user_id: str, server_id: str) -> bool:
        """Remove an MCP server and unregister all its discovered tools from ToolRegistry."""
        existing = await self.get_server(user_id, server_id)
        if not existing:
            return False

        # Unregister tools
        prefix = f"mcp_{server_id[:8]}"
        for t in existing.discovered_tools:
            t_name = t.get("name")
            if t_name:
                self._tool_registry.unregister(f"{prefix}_{t_name}")

        self._active_clients.pop(server_id, None)

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(MCPServerConfig).where(
                        MCPServerConfig.id == server_id,
                        MCPServerConfig.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        await session.delete(item)
                        await session.commit()
            except Exception as exc:
                log.warning("mcp_service.db_delete_failed", error=str(exc))

        self._mem_servers.pop(server_id, None)
        return True

    async def sync_server(self, user_id: str, server_id: str) -> MCPSyncResult:
        """Execute MCP handshake, discover tools/resources/prompts, and register tools into ToolRegistry."""
        server = await self.get_server(user_id, server_id)
        if not server:
            raise ValueError(f"MCP server '{server_id}' not found.")

        client = self._get_or_create_client(server.model_dump())

        # Unregister previously discovered tools to avoid stale registrations
        prefix = f"mcp_{server_id[:8]}"
        for old_t in server.discovered_tools:
            old_name = old_t.get("name")
            if old_name:
                self._tool_registry.unregister(f"{prefix}_{old_name}")

        # 1. Initialize Handshake
        await client.initialize()

        # 2. Discover Tools, Resources, Prompts
        mcp_tools = await client.list_tools()
        mcp_resources = await client.list_resources()
        mcp_prompts = await client.list_prompts()

        # 3. Convert and register into ToolRegistry
        agent_tools = client.convert_to_agent_tools(mcp_tools)
        for atool, mtool in zip(agent_tools, mcp_tools, strict=False):
            target_tool_name = mtool.name

            async def _mcp_handler(c: MCPClient = client, tname: str = target_tool_name, **kwargs: Any) -> dict[str, Any]:
                return await c.call_tool(tname, kwargs)

            self._tool_registry.register(atool, _mcp_handler)

        # 4. Save discovered artifacts to Database & Memory
        tools_dict = [t.model_dump() for t in mcp_tools]
        resources_dict = [r.model_dump() for r in mcp_resources]
        prompts_dict = [p.model_dump() for p in mcp_prompts]

        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(MCPServerConfig).where(
                        MCPServerConfig.id == server_id,
                        MCPServerConfig.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        item.status = MCPServerStatus.CONNECTED.value
                        item.protocol_version = client.protocol_version
                        item.set_discovered_tools(tools_dict)
                        item.set_discovered_resources(resources_dict)
                        item.set_discovered_prompts(prompts_dict)
                        item.last_synced_at = now
                        item.error_message = None
                        await session.commit()
            except Exception as exc:
                log.warning("mcp_service.db_sync_save_failed", error=str(exc))

        mem = self._mem_servers.get(server_id, {})
        mem["status"] = MCPServerStatus.CONNECTED.value
        mem["protocol_version"] = client.protocol_version
        mem["discovered_tools"] = tools_dict
        mem["discovered_resources"] = resources_dict
        mem["discovered_prompts"] = prompts_dict
        mem["last_synced_at"] = now.isoformat()
        mem["error_message"] = None
        self._mem_servers[server_id] = mem

        return MCPSyncResult(
            server_id=server_id,
            name=server.name,
            status=MCPServerStatus.CONNECTED.value,
            protocol_version=client.protocol_version,
            tools_count=len(tools_dict),
            resources_count=len(resources_dict),
            prompts_count=len(prompts_dict),
            tools=tools_dict,
        )

    async def call_tool(
        self,
        user_id: str,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke an MCP tool directly via its client."""
        server = await self.get_server(user_id, server_id)
        if not server:
            raise ValueError(f"MCP server '{server_id}' not found.")

        client = self._get_or_create_client(server.model_dump())
        return await client.call_tool(tool_name, arguments)
