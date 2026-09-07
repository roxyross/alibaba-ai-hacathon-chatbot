"""Budget ORM model — maps to `budgets` table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

if TYPE_CHECKING:
    pass


class Budget(Base):
    """User-defined spending budget per category."""

    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_limit: Mapped[float] = mapped_column(Float, nullable=False)
    alert_threshold: Mapped[float] = mapped_column(
        Float, default=0.8
    )  # fraction of limit to trigger alert (default 80%)
    current_spent: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Budget user={self.user_id} category={self.category} limit={self.monthly_limit}>"
