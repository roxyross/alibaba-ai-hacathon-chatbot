"""Schemas for the ROXY 2.0 Extensible Plugin System."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PluginStatus(str, Enum):
    INSTALLED = "installed"
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"
    ERROR = "error"


class PluginToolDefinition(BaseModel):
    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"
    handler_code: str | None = None  # python script snippet or module function


class PluginManifest(BaseModel):
    plugin_id: str
    name: str
    version: str = "1.0.0"
    author: str = "community"
    description: str
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    tools: list[PluginToolDefinition] = Field(default_factory=list)
    sandbox_level: str = "strict"


class PluginRecord(BaseModel):
    manifest: PluginManifest
    status: PluginStatus = PluginStatus.INSTALLED
    installed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None


class InstallPluginRequest(BaseModel):
    manifest: PluginManifest


class PluginActionRequest(BaseModel):
    reason: str | None = None
