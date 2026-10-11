"""Pydantic schemas for the ROXY Target-Scoped Permission Engine."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PermissionPolicy(StrEnum):
    ALWAYS_ASK = "always_ask"
    ASK_ONCE = "ask_once"
    ALLOW_AUTOMATICALLY = "allow_automatically"
    NEVER_ALLOW = "never_allow"
    ALLOW_ONCE = "allow_once"
    ALLOW_FOR_DURATION = "allow_for_duration"
    ALLOW_FOR_DEVICE = "allow_for_device"
    ALLOW_FOR_APP = "allow_for_app"
    ALLOW_FOR_RESOURCE = "allow_for_resource"
    REVOKED = "revoked"


class PermissionUXDetails(BaseModel):
    """Human-readable UX details for user confirmation and permission inspection."""

    application: str = Field(
        ...,
        description="Human-readable application name (e.g. 'Spotify', 'Slack', 'System Shell')",
    )
    capability: str = Field(
        ...,
        description="Action capability category (e.g. 'Send Message', 'Launch App', 'Read Files')",
    )
    target: str = Field(
        default="system",
        description="Target resource, endpoint, recipient, or path (e.g. '#general', 'user@example.com')",
    )
    action: str = Field(..., description="Clear human-readable summary of requested action")
    data_involved: str = Field(
        default="", description="Sanitized, human-readable summary of parameters/payload"
    )
    risk: str = Field(default="medium", description="Risk level: low, medium, high, critical")
    duration: str = Field(
        default="Single execution",
        description="Policy or grant duration (e.g. 'Single execution', '1 hour', 'Permanent')",
    )
    device: str = Field(default="Local Device", description="Target device identifier or name")


class PermissionCheckRequest(BaseModel):
    tool_id: str | None = Field(default=None)
    permission: str | None = Field(default=None)
    target_app: str | None = Field(default=None)
    capability: str | None = Field(default=None)
    resource: str | None = Field(default=None)
    device_id: str | None = Field(default=None)
    scope: str = Field(default="global")
    parameters: dict[str, Any] = Field(default_factory=dict)


class PermissionCheckResult(BaseModel):
    granted: bool
    policy: str
    requires_confirmation: bool
    reason: str
    grant_id: str | None = None
    ux_details: PermissionUXDetails | None = None
    matched_scope: str | None = None


class PermissionGrantCreate(BaseModel):
    tool_id: str | None = Field(default=None)
    permission: str = Field(default="execute")
    policy: PermissionPolicy = Field(default=PermissionPolicy.ALLOW_AUTOMATICALLY)
    scope: str = Field(default="global")
    device_id: str | None = Field(default=None)
    target_app: str | None = Field(default=None)
    capability: str | None = Field(default=None)
    resource: str | None = Field(default=None)
    parameter_constraints: dict[str, Any] = Field(default_factory=dict)
    risk_level: str | None = Field(default=None)
    grant_source: str = Field(default="user_manual")
    duration_seconds: int | None = Field(
        default=None, description="TTL in seconds for allow_for_duration"
    )
    expires_at: datetime | None = Field(default=None)


class PermissionGrantResponse(BaseModel):
    id: str
    user_id: str
    tool_id: str | None = None
    permission: str = "execute"
    policy: str
    scope: str = "global"
    device_id: str | None = None
    target_app: str | None = None
    capability: str | None = None
    resource: str | None = None
    parameter_constraints: dict[str, Any] = Field(default_factory=dict)
    risk_level: str | None = None
    grant_source: str = "user_manual"
    expires_at: str | None = None
    revoked_at: str | None = None
    granted_at: str | None = None
    updated_at: str | None = None
    is_active: bool = True
