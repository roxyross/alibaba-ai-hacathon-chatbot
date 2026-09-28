"""Pydantic schemas for the ROXY Permission Engine."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PermissionPolicy(str, Enum):
    ALWAYS_ASK = "always_ask"
    ASK_ONCE = "ask_once"
    ALLOW_AUTOMATICALLY = "allow_automatically"
    NEVER_ALLOW = "never_allow"


class PermissionCheckRequest(BaseModel):
    tool_id: str = Field(..., min_length=1)
    permission: str = Field(..., min_length=1)
    scope: str = Field(default="global")


class PermissionCheckResult(BaseModel):
    granted: bool
    policy: str
    requires_confirmation: bool
    reason: str


class PermissionGrantCreate(BaseModel):
    tool_id: str = Field(..., min_length=1)
    permission: str = Field(..., min_length=1)
    policy: PermissionPolicy = Field(default=PermissionPolicy.ALLOW_AUTOMATICALLY)
    scope: str = Field(default="global")


class PermissionGrantResponse(BaseModel):
    id: str
    user_id: str
    tool_id: str
    permission: str
    policy: str
    scope: str
    granted_at: str | None = None
    updated_at: str | None = None
