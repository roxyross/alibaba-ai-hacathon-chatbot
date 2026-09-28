"""Connector Instance ORM model for external service integrations.

Manages OAuth/API-key credentials, connection state, sync metadata,
and action exposure for Google Workspace, GitHub, Slack, Notion, OpenAPI, and Webhooks.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ConnectorInstance(Base):
    """A configured integration connector instance owned by a user or workspace."""

    __tablename__ = "connector_instances"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    connector_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # google, github, slack, notion, openapi, webhook
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    auth_type: Mapped[str] = mapped_column(
        String(32), default="api_key", nullable=False
    )  # oauth2, api_key, bearer, basic, none
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    encrypted_credentials_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False, index=True
    )  # active, disconnected, error, rate_limited
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        Index("idx_connector_user_type", "user_id", "connector_type"),
    )

    def get_config(self) -> dict[str, Any]:
        try:
            val = json.loads(self.config_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_config(self, config: dict[str, Any]) -> None:
        self.config_json = json.dumps(config)

    def get_credentials(self) -> dict[str, Any]:
        try:
            val = json.loads(self.encrypted_credentials_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_credentials(self, creds: dict[str, Any]) -> None:
        self.encrypted_credentials_json = json.dumps(creds)

    def to_dict(self, mask_credentials: bool = True) -> dict[str, Any]:
        creds = self.get_credentials()
        if mask_credentials:
            masked_creds = {k: "••••••••" if len(str(v)) > 0 else "" for k, v in creds.items()}
        else:
            masked_creds = creds

        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "connector_type": self.connector_type,
            "name": self.name,
            "description": self.description,
            "auth_type": self.auth_type,
            "config": self.get_config(),
            "credentials": masked_creds,
            "status": self.status,
            "last_health_check_at": self.last_health_check_at.isoformat() if self.last_health_check_at is not None else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
        }
