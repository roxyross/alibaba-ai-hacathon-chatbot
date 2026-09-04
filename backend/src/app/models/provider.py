"""Provider ORM model — maps to `providers` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.model import Model
    from app.models.token_usage import TokenUsageLog


class Provider(Base):
    """AI provider (DeepSeek, Grok, OpenAI, Gemini)."""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(50), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key_env_var: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(String(255))
    timeout_seconds: Mapped[float] = mapped_column(Float, default=10.0)
    routing_priority: Mapped[int] = mapped_column(Integer, unique=True)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    models: Mapped[list["Model"]] = relationship(
        "Model", back_populates="provider", cascade="all, delete-orphan"
    )
    token_logs: Mapped[list["TokenUsageLog"]] = relationship(
        "TokenUsageLog", back_populates="provider", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Provider {self.name} enabled={self.enabled}>"
