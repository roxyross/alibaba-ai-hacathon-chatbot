"""Schemas for Open Work Agent long-running autonomous tasks."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class OpenWorkTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OpenWorkSubtask(BaseModel):
    id: str
    index: int
    title: str
    description: str
    tool_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: OpenWorkTaskStatus = OpenWorkTaskStatus.PENDING
    result: Any | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float = 0.0


class OpenWorkTask(BaseModel):
    id: str
    user_id: str
    title: str
    objective: str
    status: OpenWorkTaskStatus = OpenWorkTaskStatus.PENDING
    subtasks: list[OpenWorkSubtask] = Field(default_factory=list)
    current_subtask_index: int = 0
    progress_percent: float = 0.0
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None


class CreateOpenWorkTaskRequest(BaseModel):
    title: str
    objective: str
    auto_start: bool = True
    context: dict[str, Any] = Field(default_factory=dict)


class TaskControlRequest(BaseModel):
    reason: str | None = None
