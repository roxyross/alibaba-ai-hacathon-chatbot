"""Model Context Protocol (MCP) Server Configuration and Cache ORM model.

Manages external MCP server endpoints (SSE and stdio), negotiated protocol versions,
and cached discovered tools, resources, and prompts.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MCPServerConfig(Base):
    """An external MCP server connected to ROXY-AI 2.0."""

    __tablename__ = "mcp_server_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transport: Mapped[str] = mapped_column(
        String(16), default="sse", nullable=False
    )  # sse, stdio

    # SSE endpoint or stdio command
    endpoint_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arguments_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    env_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default="disconnected", nullable=False, index=True
    )  # connected, disconnected, error
    protocol_version: Mapped[str] = mapped_column(String(32), default="2024-11-05", nullable=False)

    # Discovered capabilities cache
    discovered_tools_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    discovered_resources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    discovered_prompts_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_mcp_user_name", "user_id", "name"),
    )

    def get_arguments(self) -> list[str]:
        try:
            val = json.loads(self.arguments_json) if self.arguments_json else []
            return [str(x) for x in val] if isinstance(val, list) else []
        except Exception:
            return []

    def set_arguments(self, args: list[str]) -> None:
        self.arguments_json = json.dumps(args)

    def get_env(self) -> dict[str, str]:
        try:
            val = json.loads(self.env_json) if self.env_json else {}
            return {str(k): str(v) for k, v in val.items()} if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_env(self, env: dict[str, str]) -> None:
        self.env_json = json.dumps(env)

    def get_discovered_tools(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.discovered_tools_json) if self.discovered_tools_json else []
            return val if isinstance(val, list) else []
        except Exception:
            return []

    def set_discovered_tools(self, tools: list[dict[str, Any]]) -> None:
        self.discovered_tools_json = json.dumps(tools)

    def get_discovered_resources(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.discovered_resources_json) if self.discovered_resources_json else []
            return val if isinstance(val, list) else []
        except Exception:
            return []

    def set_discovered_resources(self, resources: list[dict[str, Any]]) -> None:
        self.discovered_resources_json = json.dumps(resources)

    def get_discovered_prompts(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.discovered_prompts_json) if self.discovered_prompts_json else []
            return val if isinstance(val, list) else []
        except Exception:
            return []

    def set_discovered_prompts(self, prompts: list[dict[str, Any]]) -> None:
        self.discovered_prompts_json = json.dumps(prompts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "description": self.description,
            "transport": self.transport,
            "endpoint_url": self.endpoint_url,
            "command": self.command,
            "arguments": self.get_arguments(),
            "status": self.status,
            "protocol_version": self.protocol_version,
            "discovered_tools": self.get_discovered_tools(),
            "discovered_resources": self.get_discovered_resources(),
            "discovered_prompts": self.get_discovered_prompts(),
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at is not None else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
        }
