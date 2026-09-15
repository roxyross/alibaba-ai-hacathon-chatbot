"""Image Studio GeneratedImage ORM model — maps to `generated_images` table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
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
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), default="image")  # image, video
    speed: Mapped[str] = mapped_column(String(32), default="Fast")  # Fast, Quality, Cinematic
    quality: Mapped[str] = mapped_column(String(32), default="Quality 2.0")  # Quality 1.0, Quality 2.0, Ultra HD
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="1:1")  # 1:1, 16:9, 9:16, 2:3, 3:2
    model: Mapped[str] = mapped_column(String(64), default="imagen-3.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
