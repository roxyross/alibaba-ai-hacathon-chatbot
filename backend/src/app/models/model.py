"""Model ORM model — maps to `models` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY as ArrayType, Boolean, DateTime, Float, ForeignKey
from sqlalchemy import Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.provider import Provider
    from app.models.token_usage import TokenUsageLog


class Model(Base):
    """Provider-native model (e.g. deepseek-chat-v3, gemini-2.0-flash)."""

    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider_id", "name", name="uq_model_provider_name"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(100))
    task_types: Mapped[list[str]] = mapped_column(ArrayType(String), default=list)
    cost_per_1k_input_tokens: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_1k_output_tokens: Mapped[float] = mapped_column(Float, default=0.0)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    provider: Mapped["Provider"] = relationship("Provider", back_populates="models")
    token_logs: Mapped[list["TokenUsageLog"]] = relationship(
        "TokenUsageLog", back_populates="model", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Model {self.name} provider={self.provider_id}>"
