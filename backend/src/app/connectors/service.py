"""Connector Service managing life cycle, health checks, and tool registry bridging."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.connectors.base import BaseConnector
from app.connectors.github import GitHubConnector
from app.connectors.google import GoogleWorkspaceConnector
from app.connectors.notion import NotionConnector
from app.connectors.openapi import OpenAPIConnector
from app.connectors.schemas import (
    ConnectionTestResult,
    ConnectorCreateRequest,
    ConnectorResponse,
    ConnectorStatus,
    ConnectorType,
    ConnectorTypeInfo,
    ConnectorUpdateRequest,
    OpenAPIImportRequest,
    OpenAPIImportResponse,
)
from app.connectors.slack import SlackConnector
from app.connectors.webhook import WebhookConnector
from app.db import get_session_factory
from app.models.connector import ConnectorInstance
from app.tools.registry import ToolRegistry

log = structlog.get_logger()


class ConnectorService:
    """Manages connector instances and synchronizes capabilities with the Tool Registry."""

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()
        self._mem_connectors: dict[str, dict[str, Any]] = {}
        self._active_connectors: dict[str, BaseConnector] = {}

    def get_supported_types(self) -> list[ConnectorTypeInfo]:
        """Return catalog of all supported connector types and their configuration requirements."""
        return [
            ConnectorTypeInfo(
                type=ConnectorType.GOOGLE,
                title="Google Workspace",
                description="Connect Gmail, Google Calendar, and Drive to search emails, read calendars, and schedule events.",
                auth_methods=["oauth2", "api_key"],
                default_config={"email": ""},
                required_credentials=["access_token"],
                supported_actions=["search_emails", "send_email", "list_calendar_events", "create_calendar_event"],
                icon="google",
            ),
            ConnectorTypeInfo(
                type=ConnectorType.GITHUB,
                title="GitHub",
                description="Interact with repositories, inspect issues and PRs, and search codebases.",
                auth_methods=["personal_access_token", "oauth2"],
                default_config={"owner": ""},
                required_credentials=["personal_access_token"],
                supported_actions=["search_code", "list_issues", "create_issue"],
                icon="github",
            ),
            ConnectorTypeInfo(
                type=ConnectorType.SLACK,
                title="Slack",
                description="Send channel messages, inspect public channels, and receive notification events.",
                auth_methods=["bot_token", "webhook_url"],
                default_config={"team": ""},
                required_credentials=["bot_token"],
                supported_actions=["post_message", "list_channels"],
                icon="slack",
            ),
            ConnectorTypeInfo(
                type=ConnectorType.NOTION,
                title="Notion",
                description="Search documents, query databases, and create rich notes in your Notion workspace.",
                auth_methods=["internal_integration_token"],
                default_config={"workspace_name": ""},
                required_credentials=["internal_integration_token"],
                supported_actions=["search", "create_page"],
                icon="notion",
            ),
            ConnectorTypeInfo(
                type=ConnectorType.OPENAPI,
                title="OpenAPI / Swagger REST",
                description="Import any OpenAPI 3.0 / Swagger specification to dynamically turn all endpoints into agent tools.",
                auth_methods=["api_key", "bearer", "basic", "none"],
                default_config={"base_url": "", "spec": {}},
                required_credentials=[],
                supported_actions=["Dynamic based on spec operations"],
                icon="openapi",
            ),
            ConnectorTypeInfo(
                type=ConnectorType.WEBHOOK,
                title="Custom Webhook",
                description="Dispatch HTTP payloads to external event receivers or internal automation hooks.",
                auth_methods=["api_key", "none"],
                default_config={"target_url": ""},
                required_credentials=[],
                supported_actions=["dispatch_payload"],
                icon="webhook",
            ),
        ]

    def _instantiate_connector(
        self,
        instance_id: str,
        connector_type: str,
        name: str,
        config: dict[str, Any],
        credentials: dict[str, Any],
    ) -> BaseConnector | None:
        """Instantiate the concrete connector class from type identifier."""
        t = connector_type.lower()
        if t == ConnectorType.GOOGLE.value:
            return GoogleWorkspaceConnector(instance_id, name, config, credentials)
        elif t == ConnectorType.GITHUB.value:
            return GitHubConnector(instance_id, name, config, credentials)
        elif t == ConnectorType.SLACK.value:
            return SlackConnector(instance_id, name, config, credentials)
        elif t == ConnectorType.NOTION.value:
            return NotionConnector(instance_id, name, config, credentials)
        elif t == ConnectorType.OPENAPI.value:
            return OpenAPIConnector(instance_id, name, config, credentials)
        elif t == ConnectorType.WEBHOOK.value:
            return WebhookConnector(instance_id, name, config, credentials)
        return None

    def sync_connector_tools_to_registry(self, connector: BaseConnector) -> int:
        """Register all actions exposed by this connector into the central Tool Registry."""
        actions = connector.list_actions()
        count = 0
        for tool in actions:
            action_id = tool.id

            async def _exec_wrapper(c: BaseConnector = connector, a: str = action_id, **kwargs: Any) -> dict[str, Any]:
                return await c.execute_action(a, kwargs)

            self._tool_registry.register(tool, _exec_wrapper)
            count += 1

        self._active_connectors[connector.instance_id] = connector
        return count

    async def create_connector(self, user_id: str, req: ConnectorCreateRequest) -> ConnectorResponse:
        """Create and configure a new connector instance, syncing its tools."""
        cid = str(uuid.uuid4())
        now = datetime.now(UTC)

        record_dict: dict[str, Any] = {
            "id": cid,
            "user_id": user_id,
            "workspace_id": req.workspace_id,
            "connector_type": req.connector_type.value,
            "name": req.name,
            "description": req.description,
            "auth_type": req.auth_type,
            "config": req.config,
            "credentials": req.credentials,
            "status": ConnectorStatus.ACTIVE.value,
            "last_health_check_at": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # Persist to database
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    db_obj = ConnectorInstance(
                        id=cid,
                        user_id=user_id,
                        workspace_id=req.workspace_id,
                        connector_type=req.connector_type.value,
                        name=req.name,
                        description=req.description,
                        auth_type=req.auth_type,
                        status=ConnectorStatus.ACTIVE.value,
                        created_at=now,
                        updated_at=now,
                    )
                    db_obj.set_config(req.config)
                    db_obj.set_credentials(req.credentials)
                    session.add(db_obj)
                    await session.commit()
            except Exception as exc:
                log.warning("connector_service.db_create_failed", error=str(exc))

        self._mem_connectors[cid] = record_dict

        # Instantiate & register tools
        conn = self._instantiate_connector(cid, req.connector_type.value, req.name, req.config, req.credentials)
        action_count = 0
        if conn:
            action_count = self.sync_connector_tools_to_registry(conn)

        resp_dict = dict(record_dict)
        resp_dict["action_count"] = action_count
        resp_dict["credentials"] = {k: "••••••••" if len(str(v)) > 0 else "" for k, v in req.credentials.items()}
        return ConnectorResponse.model_validate(resp_dict)

    async def get_connector(self, user_id: str, connector_id: str) -> ConnectorResponse | None:
        """Fetch connector instance by ID."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ConnectorInstance).where(
                        ConnectorInstance.id == connector_id,
                        ConnectorInstance.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        d = item.to_dict(mask_credentials=True)
                        conn = self._active_connectors.get(connector_id)
                        d["action_count"] = len(conn.list_actions()) if conn else 0
                        return ConnectorResponse.model_validate(d)
            except Exception as exc:
                log.warning("connector_service.db_get_failed", error=str(exc))

        mem = self._mem_connectors.get(connector_id)
        if mem and mem.get("user_id") == user_id:
            d = dict(mem)
            d["credentials"] = {k: "••••••••" if len(str(v)) > 0 else "" for k, v in d.get("credentials", {}).items()}
            conn = self._active_connectors.get(connector_id)
            d["action_count"] = len(conn.list_actions()) if conn else 0
            return ConnectorResponse.model_validate(d)

        return None

    async def list_connectors(self, user_id: str) -> list[ConnectorResponse]:
        """List all configured connector instances for a user."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = (
                        select(ConnectorInstance)
                        .where(ConnectorInstance.user_id == user_id)
                        .order_by(ConnectorInstance.created_at.desc())
                    )
                    res = await session.execute(stmt)
                    items = res.scalars().all()
                    if items:
                        results: list[ConnectorResponse] = []
                        for it in items:
                            d = it.to_dict(mask_credentials=True)
                            conn = self._active_connectors.get(it.id)
                            d["action_count"] = len(conn.list_actions()) if conn else 0
                            results.append(ConnectorResponse.model_validate(d))
                        return results
            except Exception as exc:
                log.warning("connector_service.db_list_failed", error=str(exc))

        user_conns = [c for c in self._mem_connectors.values() if c.get("user_id") == user_id]
        results = []
        for mem in user_conns:
            d = dict(mem)
            d["credentials"] = {k: "••••••••" if len(str(v)) > 0 else "" for k, v in d.get("credentials", {}).items()}
            conn = self._active_connectors.get(mem["id"])
            d["action_count"] = len(conn.list_actions()) if conn else 0
            results.append(ConnectorResponse.model_validate(d))
        return results

    async def update_connector(
        self,
        user_id: str,
        connector_id: str,
        req: ConnectorUpdateRequest,
    ) -> ConnectorResponse:
        """Update connector config, credentials, or state."""
        existing = await self.get_connector(user_id, connector_id)
        if not existing:
            raise ValueError(f"Connector '{connector_id}' not found.")

        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ConnectorInstance).where(
                        ConnectorInstance.id == connector_id,
                        ConnectorInstance.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        if req.name is not None:
                            item.name = req.name
                        if req.description is not None:
                            item.description = req.description
                        if req.config is not None:
                            item.set_config(req.config)
                        if req.credentials is not None:
                            item.set_credentials(req.credentials)
                        if req.status is not None:
                            item.status = req.status.value
                        item.updated_at = now
                        await session.commit()
            except Exception as exc:
                log.warning("connector_service.db_update_failed", error=str(exc))

        mem = self._mem_connectors.get(connector_id, {})
        if req.name is not None:
            mem["name"] = req.name
        if req.description is not None:
            mem["description"] = req.description
        if req.config is not None:
            mem["config"] = req.config
        if req.credentials is not None:
            mem["credentials"] = req.credentials
        if req.status is not None:
            mem["status"] = req.status.value
        mem["updated_at"] = now.isoformat()
        self._mem_connectors[connector_id] = mem

        # Re-instantiate connector if config or credentials updated
        conn = self._instantiate_connector(
            connector_id,
            existing.connector_type,
            mem.get("name", existing.name),
            mem.get("config", existing.config),
            mem.get("credentials", {}),
        )
        if conn:
            self.sync_connector_tools_to_registry(conn)

        return await self.get_connector(user_id, connector_id) or ConnectorResponse.model_validate(mem)

    async def delete_connector(self, user_id: str, connector_id: str) -> bool:
        """Remove a connector instance and unregister its tools."""
        existing = await self.get_connector(user_id, connector_id)
        if not existing:
            return False

        # Unregister tools from ToolRegistry
        conn = self._active_connectors.pop(connector_id, None)
        if conn:
            for tool in conn.list_actions():
                self._tool_registry.unregister(tool.id)

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ConnectorInstance).where(
                        ConnectorInstance.id == connector_id,
                        ConnectorInstance.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        await session.delete(item)
                        await session.commit()
            except Exception as exc:
                log.warning("connector_service.db_delete_failed", error=str(exc))

        self._mem_connectors.pop(connector_id, None)
        return True

    async def test_connector(self, user_id: str, connector_id: str) -> ConnectionTestResult:
        """Execute a live health check on the specified connector instance."""
        existing = await self.get_connector(user_id, connector_id)
        if not existing:
            raise ValueError(f"Connector '{connector_id}' not found.")

        # Retrieve raw credentials for testing
        raw_creds: dict[str, Any] = {}
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ConnectorInstance).where(
                        ConnectorInstance.id == connector_id,
                        ConnectorInstance.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        raw_creds = item.get_credentials()
            except Exception:
                pass

        if not raw_creds:
            raw_creds = self._mem_connectors.get(connector_id, {}).get("credentials", {})

        conn = self._instantiate_connector(
            connector_id,
            existing.connector_type,
            existing.name,
            existing.config,
            raw_creds,
        )
        if not conn:
            return ConnectionTestResult(
                success=False,
                status="error",
                message=f"Could not instantiate connector of type '{existing.connector_type}'.",
                latency_ms=0.0,
            )

        result = await conn.test_connection()

        # Update last health check in database
        now = datetime.now(UTC)
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ConnectorInstance).where(
                        ConnectorInstance.id == connector_id,
                        ConnectorInstance.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        item.last_health_check_at = now
                        item.status = result.status
                        item.error_message = None if result.success else result.message
                        await session.commit()
            except Exception:
                pass

        if connector_id in self._mem_connectors:
            self._mem_connectors[connector_id]["last_health_check_at"] = now.isoformat()
            self._mem_connectors[connector_id]["status"] = result.status
            self._mem_connectors[connector_id]["error_message"] = None if result.success else result.message

        return result

    async def import_openapi_spec(
        self,
        user_id: str,
        req: OpenAPIImportRequest,
    ) -> OpenAPIImportResponse:
        """Import an OpenAPI 3.0 specification from URL or string, creating an active connector with tools."""
        spec_dict: dict[str, Any] = {}

        if req.spec_json:
            spec_dict = json.loads(req.spec_json)
        elif req.spec_url:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(req.spec_url)
                spec_dict = res.json()
        else:
            raise ValueError("Either 'spec_json' or 'spec_url' must be provided.")

        base_url = req.base_url
        if not base_url:
            servers = spec_dict.get("servers", [])
            if servers and isinstance(servers, list):
                base_url = servers[0].get("url")
        if not base_url:
            base_url = "https://api.example.com"

        create_req = ConnectorCreateRequest(
            connector_type=ConnectorType.OPENAPI,
            name=req.name,
            description=spec_dict.get("info", {}).get("description") or f"OpenAPI tools for {req.name}",
            auth_type="api_key" if req.api_key else "none",
            config={
                "base_url": base_url,
                "spec": spec_dict,
                "auth_header": req.auth_header,
                "auth_prefix": req.auth_prefix,
            },
            credentials={"api_key": req.api_key} if req.api_key else {},
        )

        connector_res = await self.create_connector(user_id=user_id, req=create_req)

        # Retrieve parsed operations
        conn = self._active_connectors.get(connector_res.id)
        operations = list(conn.operations.keys()) if isinstance(conn, OpenAPIConnector) else []

        return OpenAPIImportResponse(
            connector_id=connector_res.id,
            name=req.name,
            base_url=base_url,
            tools_generated=len(operations),
            operations=operations,
        )
