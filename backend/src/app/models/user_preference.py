"""UserPreference ORM model — maps to `user_preferences` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

if TYPE_CHECKING:
    pass


class UserPreference(Base):
    """Per-user settings and preferences (AI persona, streaming speed, theme, sounds, audio)."""

    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    preferred_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    theme: Mapped[str] = mapped_column(
        String(20), default="dark", server_default="dark", nullable=False
    )
    custom_persona: Mapped[str | None] = mapped_column(
        Text, default="", server_default="", nullable=True
    )
    stream_speed: Mapped[str] = mapped_column(
        String(20), default="fast", server_default="fast", nullable=False
    )
    sound_effects: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    auto_scroll: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    voice_id: Mapped[str | None] = mapped_column(
        String(50), default="aura-asteria-en", server_default="aura-asteria-en", nullable=True
    )
    extra_settings: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=dict, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<UserPreference user={self.user_id} theme={self.theme} speed={self.stream_speed}>"
