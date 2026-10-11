"""Agent Runtime ORM models: tasks, steps, actions, and permissions.

Fulfills Phase 2 requirements for:
- Agent Tasks & Steps tracking
- Action Center & Confirmations
- Permission Engine & Policy Grants
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AgentTask(Base):
    """An autonomous multi-step execution task managed by the Agent Runtime."""

    __tablename__ = "agent_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled Task")
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        index=True,
    )  # draft, planning, running, waiting_for_input, waiting_for_permission, paused, completed, failed, cancelled
    plan_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    context_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    deliverables_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    steps: Mapped[list[AgentStep]] = relationship(
        "AgentStep", back_populates="task", cascade="all, delete-orphan", order_by="AgentStep.step_number"
    )

    __table_args__ = (
        Index("idx_agent_task_user_status", "user_id", "status"),
        Index("idx_agent_task_workspace", "workspace_id"),
    )

    def get_plan(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.plan_json)
            return val if isinstance(val, list) else []
        except Exception:
            return []

    def set_plan(self, plan: list[dict[str, Any]]) -> None:
        self.plan_json = json.dumps(plan)

    def get_context(self) -> dict[str, Any]:
        try:
            val = json.loads(self.context_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_context(self, ctx: dict[str, Any]) -> None:
        self.context_json = json.dumps(ctx)

    def get_deliverables(self) -> list[dict[str, Any]]:
        try:
            val = json.loads(self.deliverables_json)
            return val if isinstance(val, list) else []
        except Exception:
            return []

    def set_deliverables(self, items: list[dict[str, Any]]) -> None:
        self.deliverables_json = json.dumps(items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "objective": self.objective,
            "status": self.status,
            "plan": self.get_plan(),
            "context": self.get_context(),
            "deliverables": self.get_deliverables(),
            "error": self.error,
            "steps": [s.to_dict() for s in self.steps] if self.steps else [],
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at is not None else None,
        }


class AgentStep(Base):
    """An individual milestone or operational step within an AgentTask."""

    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tool_input_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    tool_output_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending, running, waiting_for_approval, completed, failed, skipped
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[AgentTask] = relationship("AgentTask", back_populates="steps")

    def get_tool_input(self) -> dict[str, Any]:
        try:
            val = json.loads(self.tool_input_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_tool_input(self, data: dict[str, Any]) -> None:
        self.tool_input_json = json.dumps(data)

    def get_tool_output(self) -> dict[str, Any]:
        try:
            val = json.loads(self.tool_output_json)
            return val if isinstance(val, dict) else ({"result": val} if val is not None else {})
        except Exception:
            return {}

    def set_tool_output(self, data: Any) -> None:
        self.tool_output_json = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "step_number": self.step_number,
            "description": self.description,
            "tool_id": self.tool_id,
            "tool_input": self.get_tool_input(),
            "tool_output": self.get_tool_output(),
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "started_at": self.started_at.isoformat() if self.started_at is not None else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at is not None else None,
        }


class AgentAction(Base):
    """An action request initiated by the agent requiring permission or verification."""

    __tablename__ = "agent_actions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_tasks.id", ondelete="SET NULL"), index=True, nullable=True
    )
    step_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    tool_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    input_parameters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(16), default="medium", nullable=False
    )  # low, medium, high, critical
    required_permission: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending, approved, rejected, executed, failed, cancelled
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_agent_actions_user_status", "user_id", "status"),
    )

    def get_input_parameters(self) -> dict[str, Any]:
        try:
            val = json.loads(self.input_parameters_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_input_parameters(self, data: dict[str, Any]) -> None:
        self.input_parameters_json = json.dumps(data)

    def get_result(self) -> dict[str, Any]:
        try:
            val = json.loads(self.result_json)
            return val if isinstance(val, dict) else ({"result": val} if val is not None else {})
        except Exception:
            return {}

    def set_result(self, data: Any) -> None:
        self.result_json = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "tool_id": self.tool_id,
            "description": self.description,
            "input_parameters": self.get_input_parameters(),
            "risk_level": self.risk_level,
            "required_permission": self.required_permission,
            "status": self.status,
            "result": self.get_result(),
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at is not None else None,
        }


class PermissionGrant(Base):
    """User-scoped policy and grant for a tool capability."""

    __tablename__ = "permission_grants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    tool_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    permission: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="execute")
    policy: Mapped[str] = mapped_column(
        String(32), default="always_ask", nullable=False
    )  # always_ask, ask_once, allow_automatically, never_allow, allow_once, allow_for_duration, allow_for_device, allow_for_app, allow_for_resource, revoked
    scope: Mapped[str] = mapped_column(String(64), default="global", nullable=False)

    device_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    target_app: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    capability: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    resource: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    parameter_constraints_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    grant_source: Mapped[str] = mapped_column(String(64), default="user_manual", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_perm_user_tool", "user_id", "tool_id"),
        Index("idx_perm_user_app", "user_id", "target_app"),
        Index("idx_perm_user_device", "user_id", "device_id"),
    )

    def get_parameter_constraints(self) -> dict[str, Any]:
        try:
            val = json.loads(self.parameter_constraints_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_parameter_constraints(self, data: dict[str, Any]) -> None:
        self.parameter_constraints_json = json.dumps(data)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return datetime.now(UTC) > exp

    def is_revoked(self) -> bool:
        return self.revoked_at is not None or self.policy == "revoked"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tool_id": self.tool_id,
            "permission": self.permission,
            "policy": self.policy,
            "scope": self.scope,
            "device_id": self.device_id,
            "target_app": self.target_app,
            "capability": self.capability,
            "resource": self.resource,
            "parameter_constraints": self.get_parameter_constraints(),
            "risk_level": self.risk_level,
            "grant_source": self.grant_source,
            "expires_at": self.expires_at.isoformat() if self.expires_at is not None else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at is not None else None,
            "granted_at": self.granted_at.isoformat() if self.granted_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
            "is_active": not self.is_expired() and not self.is_revoked(),
        }

