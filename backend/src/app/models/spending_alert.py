"""SpendingAlert ORM model — maps to `spending_alerts` table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

if TYPE_CHECKING:
    pass


class SpendingAlert(Base):
    """User-defined spending alert — triggers when a threshold is exceeded."""

    __tablename__ = "spending_alerts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "over_budget" | "unusual_charge" | "bill_reminder"
    threshold_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<SpendingAlert user={self.user_id} name={self.name} type={self.alert_type}>"
