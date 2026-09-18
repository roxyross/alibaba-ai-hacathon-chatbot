"""Image Studio GeneratedImage and UploadedMedia ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GeneratedImage(Base):
    """Media generation record for Roxy-AI Image Studio."""

    __tablename__ = "generated_images"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    revised_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), default="image")  # image, video
    style_preset: Mapped[str] = mapped_column(String(64), default="photorealistic")
    speed: Mapped[str] = mapped_column(String(32), default="Fast")  # Fast, Quality, Cinematic
    quality: Mapped[str] = mapped_column(String(32), default="Quality 2.0")  # Quality 1.0, Quality 2.0, Ultra HD
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="1:1")  # 1:1, 16:9, 9:16, 2:3, 3:2, 4:5
    width: Mapped[int] = mapped_column(Integer, default=1024)
    height: Mapped[int] = mapped_column(Integer, default=1024)
    model: Mapped[str] = mapped_column(String(64), default="flux")
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    vault_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class UploadedMedia(Base):
    """Uploaded reference image/video asset for Roxy-AI Image Studio."""

    __tablename__ = "uploaded_media"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), default="image")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
