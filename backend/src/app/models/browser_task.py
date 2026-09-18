"""SQLAlchemy ORM model for Browser Automation Tasks (Phase 15).

Supports multi-tenant persistence of autonomous web tasks, DOM element extractions,
navigation journeys, form-filling operations, and execution logs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class BrowserTask(Base):
    """Browser Task entity storing autonomous web navigation and extraction flows."""

    __tablename__ = "browser_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, default="Browser Automation Task"
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending, running, completed, failed
    action_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="navigate"
    )  # navigate, extract, fill_form, screenshot, multi_step
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    result_data: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_browser_tasks_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize browser task to dictionary with type-safe fields."""
        tag_list: list[str] = []
        if isinstance(self.tags, str):
            tag_list = [t.strip() for t in self.tags.split(",") if t.strip()]
        elif isinstance(self.tags, (list, tuple)):
            tag_list = [str(t).strip() for t in self.tags if str(t).strip()]

        created_at_str = (
            self.created_at.isoformat()
            if hasattr(self.created_at, "isoformat")
            else (str(self.created_at) if self.created_at else None)
        )
        updated_at_str = (
            self.updated_at.isoformat()
            if hasattr(self.updated_at, "isoformat")
            else (str(self.updated_at) if self.updated_at else None)
        )

        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "url": self.url,
            "status": self.status,
            "action_type": self.action_type,
            "actions": self.actions if isinstance(self.actions, list) else [],
            "result_data": (
                self.result_data if isinstance(self.result_data, dict) else {}
            ),
            "error_message": self.error_message,
            "requires_confirmation": bool(self.requires_confirmation),
            "is_sensitive": bool(self.is_sensitive),
            "tags": tag_list,
            "created_at": created_at_str,
            "updated_at": updated_at_str,
        }
