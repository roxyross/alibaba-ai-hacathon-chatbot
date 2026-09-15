"""Finance ORM models — `finance_accounts`, `finance_transactions`, `finance_alerts`.

Supports Plaid and Raast (Deewan / PISP Mode), dual USD and PKR currencies,
statement periods, and account toggles.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FinanceAccount(Base):
    """Connected or virtual financial account (Plaid or Raast Deewan/PISP)."""

    __tablename__ = "finance_accounts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    account_holder: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(64), default="checking")  # checking, savings, credit
    account_number_full: Mapped[str] = mapped_column(String(64), nullable=False)
    account_number_masked: Mapped[str] = mapped_column(String(32), nullable=False)
    balance_usd: Mapped[float] = mapped_column(Float, default=0.0)
    balance_pkr: Mapped[float] = mapped_column(Float, default=0.0)
    budget_limit_usd: Mapped[float] = mapped_column(Float, default=1000.0)
    budget_limit_pkr: Mapped[float] = mapped_column(Float, default=300000.0)
    provider: Mapped[str] = mapped_column(String(32), default="plaid")  # plaid, raast
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, paused, disconnected
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    transactions: Mapped[list["FinanceTransaction"]] = relationship(
        "FinanceTransaction", back_populates="account", cascade="all, delete-orphan"
    )


class FinanceTransaction(Base):
    """Financial transaction with description, reason, date/time, and statement period."""

    __tablename__ = "finance_transactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("finance_accounts.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="Operational expense")
    category: Mapped[str] = mapped_column(String(64), default="General")
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    amount_pkr: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(16), default="debit")  # debit, credit
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    account: Mapped["FinanceAccount"] = relationship("FinanceAccount", back_populates="transactions")


class FinanceAlert(Base):
    """Spending, budget, or transaction alert."""

    __tablename__ = "finance_alerts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), default="budget_warning")
    threshold_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_pkr: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, paused, resolved
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
