"""Subscription, Payment, PaymentMethod, PaymentEvent, CreditWallet, and UsageLog ORM models.

Maps to:
- `subscriptions`
- `payments`
- `payment_methods`
- `payment_events`
- `credit_wallets`
- `usage_logs`
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Subscription(Base):
    """User subscription plan (Free, Pro, Team/Business) with multi-provider tracking."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="stripe")  # stripe, safepay
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free, pro, team
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, canceled, past_due
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    amount_pkr: Mapped[float] = mapped_column(Float, default=0.0)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class Payment(Base):
    """Normalized payment transaction for both Stripe and Safepay."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # stripe, safepay
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, paid, failed, canceled, refunded
    payment_type: Mapped[str] = mapped_column(String(32), default="subscription")  # subscription, topup
    plan_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PaymentEvent(Base):
    """Webhook event log for deduplication and idempotent processing."""

    __tablename__ = "payment_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # stripe, safepay
    provider_event_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    processed: Mapped[bool] = mapped_column(Boolean, default=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PaymentMethod(Base):
    """Saved payment method (Stripe or Safepay card token)."""

    __tablename__ = "payment_methods"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="stripe")  # stripe, safepay
    stripe_payment_method_id: Mapped[str] = mapped_column(String(128), default="")
    provider_payment_method_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand: Mapped[str] = mapped_column(String(32), default="visa")  # visa, mastercard, paypak, unionpay
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    exp_month: Mapped[int] = mapped_column(Integer, nullable=False)
    exp_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CreditWallet(Base):
    """User credit wallet for pay-as-you-go / top-up tokens."""

    __tablename__ = "credit_wallets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    remaining_credits: Mapped[float] = mapped_column(Float, default=100.0)  # Initial starter credits
    used_this_month: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_pkr: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class UsageLog(Base):
    """Token and operation usage logs for analytics and billing."""

    __tablename__ = "usage_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    feature: Mapped[str] = mapped_column(String(64), default="chat")  # chat, image_studio, jobs, finance
    model: Mapped[str] = mapped_column(String(64), default="gemini-2.0-flash")
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_pkr: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
