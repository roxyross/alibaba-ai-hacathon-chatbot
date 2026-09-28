"""Schemas for the Connectors Integration Framework."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConnectorType(StrEnum):
    GOOGLE = "google"
    GITHUB = "github"
    SLACK = "slack"
    NOTION = "notion"
    OPENAPI = "openapi"
    WEBHOOK = "webhook"


class ConnectorStatus(StrEnum):
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


class ConnectorTypeInfo(BaseModel):
    """Metadata describing a supported connector integration."""

    type: ConnectorType
    title: str
    description: str
    auth_methods: list[str]
    default_config: dict[str, Any]
    required_credentials: list[str]
    supported_actions: list[str]
    icon: str


class ConnectorCreateRequest(BaseModel):
    connector_type: ConnectorType
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=255)
    auth_type: str = Field(default="api_key")
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = None


class ConnectorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=255)
    config: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    status: ConnectorStatus | None = None


class ConnectorResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    connector_type: str
    name: str
    description: str | None = None
    auth_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, str] = Field(default_factory=dict, description="Masked credentials")
    status: str
    last_health_check_at: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    action_count: int = 0


class ConnectionTestResult(BaseModel):
    success: bool
    status: str
    message: str
    latency_ms: float
    details: dict[str, Any] = Field(default_factory=dict)


class OpenAPIImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    spec_url: str | None = None
    spec_json: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    auth_header: str = Field(default="Authorization")
    auth_prefix: str = Field(default="Bearer")


class OpenAPIImportResponse(BaseModel):
    connector_id: str
    name: str
    base_url: str
    tools_generated: int
    operations: list[str]
