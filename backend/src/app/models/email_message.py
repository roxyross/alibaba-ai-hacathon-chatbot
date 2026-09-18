"""SQLAlchemy ORM model for Email Messages and Drafts (Phase 12).

Supports multi-tenant persistence of drafted, queued, sent, and failed emails.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EmailMessage(Base):
    """Email Message entity supporting drafts, outbox, and delivery history."""

    __tablename__ = "email_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    to: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bcc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", index=True
    )  # draft, queued, sent, failed
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        Index("ix_email_messages_user_status", "user_id", "status"),
        Index("ix_email_messages_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize email message to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "cc": self.cc.split(", ") if self.cc else [],
            "bcc": self.bcc.split(", ") if self.bcc else [],
            "status": self.status,
            "delivery_error": self.delivery_error,
            "message_id": self.message_id,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
