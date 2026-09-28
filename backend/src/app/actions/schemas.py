"""Schemas for the Action Center & Confirmation Layer."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionCreateRequest(BaseModel):
    tool_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = Field(default="medium")
    required_permission: str = Field(default="execute")
    task_id: str | None = None
    step_id: str | None = None


class ActionEditRequest(BaseModel):
    input_parameters: dict[str, Any] = Field(..., description="Modified tool arguments")


class ActionRejectRequest(BaseModel):
    reason: str | None = Field(default=None, description="Optional explanation for rejection")


class ActionResponse(BaseModel):
    id: str
    user_id: str
    task_id: str | None = None
    step_id: str | None = None
    tool_id: str
    description: str
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    required_permission: str
    status: str
    result: Any = None
    error: str | None = None
    created_at: str | None = None
    resolved_at: str | None = None
