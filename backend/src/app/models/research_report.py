"""SQLAlchemy ORM model for Research Reports (Phase 14).

Supports multi-tenant persistence of autonomous deep research investigations,
query decompositions, synthesized findings, verified sources, and citations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


class ResearchReport(Base):
    """Research Report entity storing synthesized multi-source investigations."""

    __tablename__ = "research_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Research Investigation")
    query: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    depth: Mapped[str] = mapped_column(String(16), nullable=False, default="deep")
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Comma-separated tags
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
        Index("ix_research_reports_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize research report to dictionary with type-safe fields."""
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
            "query": self.query,
            "summary": self.summary,
            "findings": self.findings if isinstance(self.findings, list) else [],
            "sources": self.sources if isinstance(self.sources, list) else [],
            "confidence": self.confidence,
            "depth": self.depth,
            "tags": tag_list,
            "created_at": created_at_str,
            "updated_at": updated_at_str,
        }
