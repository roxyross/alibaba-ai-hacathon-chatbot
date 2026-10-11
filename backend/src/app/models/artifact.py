"""Cowork Workspace Artifact and Version ORM models.

Maps to:
- `cowork_artifacts`
- `cowork_artifact_versions`
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CoworkArtifact(Base):
    """Authoritative Cowork Workspace artifact storage."""

    __tablename__ = "cowork_artifacts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: f"art-{uuid.uuid4().hex[:10]}"
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(32), default="markdown", nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="markdown", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    versions: Mapped[list[CoworkArtifactVersion]] = relationship(
        "CoworkArtifactVersion",
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="CoworkArtifactVersion.version_number",
    )

    __table_args__ = (
        Index("idx_cowork_artifact_user_status", "user_id", "status"),
        Index("idx_cowork_artifact_task", "task_id"),
    )

    def get_metadata(self) -> dict[str, Any]:
        try:
            val = json.loads(self.metadata_json)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def set_metadata(self, meta: dict[str, Any]) -> None:
        self.metadata_json = json.dumps(meta)


class CoworkArtifactVersion(Base):
    """Historical version snapshot and diff for a Cowork Artifact."""

    __tablename__ = "cowork_artifact_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: f"ver-{uuid.uuid4().hex[:8]}"
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cowork_artifacts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    diff_from_previous: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_summary: Mapped[str] = mapped_column(String(255), default="Update", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    artifact: Mapped[CoworkArtifact] = relationship("CoworkArtifact", back_populates="versions")

    __table_args__ = (
        Index("idx_cowork_version_artifact_num", "artifact_id", "version_number", unique=True),
    )
