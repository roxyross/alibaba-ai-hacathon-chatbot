"""SQLAlchemy ORM model for Voice Recordings and Transcripts (Phase 13).

Supports multi-tenant persistence of audio recordings, transcripts, summaries, and tags.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VoiceRecording(Base):
    """Voice Recording entity supporting transcripts, audio references, and AI summaries."""

    __tablename__ = "voice_recordings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Voice Note")
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True, default="en")
    audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
        Index("ix_voice_recordings_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize voice recording to dictionary."""
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
            "transcript": self.transcript,
            "summary": self.summary,
            "language": self.language,
            "audio_url": self.audio_url,
            "duration_seconds": self.duration_seconds,
            "voice_model": self.voice_model,
            "tags": tag_list,
            "created_at": created_at_str,
            "updated_at": updated_at_str,
        }

