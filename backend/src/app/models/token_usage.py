"""TokenUsageLog ORM model — maps to `token_usage_logs` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.provider import Provider
    from app.models.model import Model


class TokenUsageLog(Base):
    """Per-request token usage record for cost tracking & observability."""

    __tablename__ = "token_usage_logs"
    __table_args__ = (
        Index("ix_token_usage_logs_provider_id", "provider_id"),
        Index("ix_token_usage_logs_timestamp", "timestamp"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="CASCADE")
    )
    model_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("models.id", ondelete="CASCADE")
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    provider_response_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    provider: Mapped["Provider"] = relationship("Provider", back_populates="token_logs")
    model: Mapped["Model"] = relationship("Model", back_populates="token_logs")

    def __repr__(self) -> str:
        return (
            f"<TokenUsageLog request={self.request_id} "
            f"provider={self.provider_id} tokens={self.input_tokens}+{self.output_tokens}>"
        )
