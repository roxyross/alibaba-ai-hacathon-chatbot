"""SQLAlchemy ORM models for Code Snippets and Executions (Phase 17).

Supports multi-tenant persistence of developer code snippets, tags,
favorites, and sandboxed code execution run histories.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CodeSnippet(Base):
    """User-saved code snippet entity with language and metadata."""

    __tablename__ = "code_snippets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="python")
    code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Comma-separated
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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

    executions: Mapped[list[CodeExecution]] = relationship(
        "CodeExecution",
        back_populates="snippet",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_code_snippets_user_created", "user_id", "created_at"),
        Index("ix_code_snippets_user_lang", "user_id", "language"),
        Index("ix_code_snippets_user_fav", "user_id", "is_favorite"),
    )

    def to_dict(self) -> dict[str, Any]:
        tag_list: list[str] = []
        if self.tags:
            tag_list = [t.strip() for t in self.tags.split(",") if t.strip()]

        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "language": self.language,
            "code": self.code,
            "description": self.description,
            "tags": tag_list,
            "is_favorite": self.is_favorite,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CodeExecution(Base):
    """Historical record of a sandboxed code execution run."""

    __tablename__ = "code_executions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    snippet_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("code_snippets.id", ondelete="SET NULL"),
        nullable=True,
    )
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="python")
    code: Mapped[str] = mapped_column(Text, nullable=False)
    stdin: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")  # success, error, timeout
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    snippet: Mapped[CodeSnippet | None] = relationship(
        "CodeSnippet",
        back_populates="executions",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_code_executions_user_created", "user_id", "created_at"),
        Index("ix_code_executions_user_status", "user_id", "status"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "snippet_id": self.snippet_id,
            "language": self.language,
            "code": self.code,
            "stdin": self.stdin,
            "status": self.status,
            "stdout": self.stdout or "",
            "stderr": self.stderr or "",
            "exit_code": self.exit_code,
            "execution_time_ms": self.execution_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
