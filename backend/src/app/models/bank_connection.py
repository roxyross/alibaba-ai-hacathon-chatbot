"""BankConnection ORM model — maps to `bank_connections` table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

if TYPE_CHECKING:
    pass


class BankConnection(Base):
    """Stores Plaid access token mappings per user."""

    __tablename__ = "bank_connections"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    institution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<BankConnection user={self.user_id} institution={self.institution}>"
