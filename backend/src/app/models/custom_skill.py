"""Custom Skill ORM model for user-defined reusable skills.

Supports prompt-template skills, composition pipelines, and sandboxed python skills.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CustomSkill(Base):
    """A user or workspace defined custom skill registered into the Tool Registry."""

    __tablename__ = "custom_skills"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    skill_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    trigger_phrases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    parameters_schema_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    execution_type: Mapped[str] = mapped_column(
        String(32), default="prompt", nullable=False
    )  # prompt, pipeline, python_sandbox
    code_or_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    risk_level: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
        Index("idx_custom_skill_user_key", "user_id", "skill_key", unique=True),
    )

    def get_trigger_phrases(self) -> list[str]:
        try:
            val = json.loads(self.trigger_phrases_json)
            return [str(x) for x in val] if isinstance(val, list) else []
        except Exception:
            return []

    def set_trigger_phrases(self, phrases: list[str]) -> None:
        self.trigger_phrases_json = json.dumps(phrases)

    def get_parameters_schema(self) -> dict[str, Any]:
        try:
            val = json.loads(self.parameters_schema_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_parameters_schema(self, schema: dict[str, Any]) -> None:
        self.parameters_schema_json = json.dumps(schema)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "skill_key": self.skill_key,
            "description": self.description,
            "trigger_phrases": self.get_trigger_phrases(),
            "parameters_schema": self.get_parameters_schema(),
            "execution_type": self.execution_type,
            "code_or_prompt_template": self.code_or_prompt_template,
            "timeout_seconds": self.timeout_seconds,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at is not None else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at is not None else None,
        }
