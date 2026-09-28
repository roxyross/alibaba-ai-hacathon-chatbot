"""Pydantic schemas for Agent Runtime (Tasks, Steps, Lifecycles, and Streaming Events)."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TaskStatusEnum(str, Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    objective: str = Field(..., min_length=1, description="High-level user goal or prompt")
    context: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str | None = None
    auto_run: bool = Field(default=True, description="Immediately plan and begin execution")


class TaskStepResponse(BaseModel):
    id: str
    task_id: str
    step_number: int
    description: str
    tool_id: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_output: Any = None
    status: str
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class TaskResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    title: str
    objective: str
    status: str
    plan: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    deliverables: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    steps: list[TaskStepResponse] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None


class TaskProgressEvent(BaseModel):
    task_id: str
    status: str
    milestone: str
    step_number: int | None = None
    tool_id: str | None = None
    action_id: str | None = None
    message: str
    timestamp: str
