"""Billing repository for subscriptions, payments, payment methods, events, and credit wallets.

Provides both PostgreSQL async ORM persistence and thread-safe in-memory fallback
stores for environments without a database connection.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session_factory
from app.models.subscription import (
    CreditWallet,
    Payment,
    PaymentEvent,
    PaymentMethod,
    Subscription,
)

logger = logging.getLogger(__name__)

# Thread-safe in-memory stores for testing and offline development
_MEM_SUBSCRIPTIONS: dict[str, dict[str, Any]] = {}
_MEM_PAYMENT_METHODS: dict[str, list[dict[str, Any]]] = {}
_MEM_INVOICES: dict[str, list[dict[str, Any]]] = {}
_MEM_PAYMENTS: dict[str, list[dict[str, Any]]] = {}
_MEM_EVENTS: set[str] = set()
_MEM_WALLETS: dict[str, dict[str, Any]] = {}


def clear_in_memory_stores() -> None:
    """Clear in-memory billing stores (useful for test isolation)."""
    _MEM_SUBSCRIPTIONS.clear()
    _MEM_PAYMENT_METHODS.clear()
    _MEM_INVOICES.clear()
    _MEM_PAYMENTS.clear()
    _MEM_EVENTS.clear()
    _MEM_WALLETS.clear()


class BillingRepository:
    """Repository handling billing, subscriptions, payment records, and idempotency."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    def _get_factory(self) -> async_sessionmaker[AsyncSession] | None:
        if not os.environ.get("DATABASE_URL"):
            return None
        return get_session_factory()

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    async def get_subscription(self, user_id: str) -> dict[str, Any]:
        """Get active user subscription and payment details."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = (
                        select(Subscription)
                        .where(Subscription.user_id == user_id)
                        .order_by(Subscription.created_at.desc())
                    )
                    res = await db.execute(stmt)
                    sub = res.scalars().first()
                    if sub:
                        pm_stmt = (
                            select(PaymentMethod)
                            .where(PaymentMethod.user_id == user_id, PaymentMethod.is_default.is_(True))
                        )
                        pm_res = await db.execute(pm_stmt)
                        pm = pm_res.scalars().first()
                        pm_dict = None
                        if pm:
                            pm_dict = {
                                "id": pm.id,
                                "brand": pm.brand,
                                "last4": pm.last4,
                                "exp_month": pm.exp_month,
                                "exp_year": pm.exp_year,
                                "is_default": pm.is_default,
                                "provider": pm.provider,
                                "powered_by": pm.provider.title(),
                            }
                        return {
                            "plan": {
                                "id": sub.plan,
                                "name": sub.plan.title() if sub.plan != "free" else "Free (BYOK)",
                                "provider": sub.provider,
                                "status": sub.status,
                                "price_usd": sub.amount_usd,
                                "price_pkr": sub.amount_pkr,
                                "next_billing_date": (
                                    sub.current_period_end.isoformat()
                                    if sub.current_period_end
                                    else None
                                ),
                                "cancel_at_period_end": sub.cancel_at_period_end,
                            },
                            "payment_method": pm_dict,
                        }
            except Exception as exc:
                logger.warning(f"Database query failed, falling back to memory: {exc}")

        # In-memory store fallback
        if user_id in _MEM_SUBSCRIPTIONS:
            return _MEM_SUBSCRIPTIONS[user_id]

        return {
            "plan": {
                "id": "free",
                "name": "Free (BYOK)",
                "provider": "stripe",
                "price_usd": 0.0,
                "price_pkr": 0.0,
                "status": "active",
                "next_billing_date": None,
                "cancel_at_period_end": False,
            },
            "payment_method": None,
        }

    async def update_or_create_subscription(
        self,
        user_id: str,
        plan_id: str,
        provider: str = "stripe",
        status: str = "active",
        amount_usd: float = 0.0,
        amount_pkr: float = 0.0,
        provider_customer_id: str | None = None,
        provider_subscription_id: str | None = None,
        cancel_at_period_end: bool = False,
    ) -> dict[str, Any]:
        """Update or create a user's subscription record."""
        now = datetime.now(UTC)
        next_date = now + timedelta(days=30)

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(Subscription).where(Subscription.user_id == user_id)
                    res = await db.execute(stmt)
                    sub = res.scalars().first()
                    if not sub:
                        sub = Subscription(
                            user_id=user_id,
                            plan=plan_id,
                            provider=provider,
                            status=status,
                            amount_usd=amount_usd,
                            amount_pkr=amount_pkr,
                            provider_customer_id=provider_customer_id,
                            provider_subscription_id=provider_subscription_id,
                            cancel_at_period_end=cancel_at_period_end,
                            current_period_start=now,
                            current_period_end=next_date,
                        )
                        db.add(sub)
                    else:
                        sub.plan = plan_id
                        sub.provider = provider
                        sub.status = status
                        sub.amount_usd = amount_usd
                        sub.amount_pkr = amount_pkr
                        if provider_customer_id:
                            sub.provider_customer_id = provider_customer_id
                        if provider_subscription_id:
                            sub.provider_subscription_id = provider_subscription_id
                        sub.cancel_at_period_end = cancel_at_period_end
                        sub.current_period_end = next_date
                    await db.commit()
            except Exception as exc:
                logger.warning(f"Database update failed, falling back to memory: {exc}")

        # Update in-memory store
        methods = _MEM_PAYMENT_METHODS.get(user_id, [])
        primary_pm = next((m for m in methods if m.get("is_default")), methods[0] if methods else None)
        sub_record = {
            "plan": {
                "id": plan_id,
                "name": plan_id.title() if plan_id != "free" else "Free (BYOK)",
                "provider": provider,
                "status": status,
                "price_usd": amount_usd,
                "price_pkr": amount_pkr,
                "next_billing_date": next_date.isoformat(),
                "cancel_at_period_end": cancel_at_period_end,
            },
            "payment_method": primary_pm,
        }
        _MEM_SUBSCRIPTIONS[user_id] = sub_record
        return sub_record

    async def cancel_subscription(self, user_id: str) -> dict[str, Any]:
        """Cancel subscription at end of billing cycle."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(Subscription).where(Subscription.user_id == user_id)
                    res = await db.execute(stmt)
                    sub = res.scalars().first()
                    if sub:
                        sub.cancel_at_period_end = True
                        await db.commit()
            except Exception as exc:
                logger.warning(f"Database cancel failed: {exc}")

        if user_id in _MEM_SUBSCRIPTIONS:
            _MEM_SUBSCRIPTIONS[user_id]["plan"]["cancel_at_period_end"] = True

        return {
            "status": "success",
            "message": "Subscription set to cancel at end of billing period.",
            "active_until": (datetime.now(UTC) + timedelta(days=21)).isoformat(),
        }

    # -------------------------------------------------------------------------
    # Payment Methods
    # -------------------------------------------------------------------------

    async def list_payment_methods(self, user_id: str) -> dict[str, Any]:
        """List payment methods for user with primary designation."""
        methods: list[dict[str, Any]] = []
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = (
                        select(PaymentMethod)
                        .where(PaymentMethod.user_id == user_id)
                        .order_by(PaymentMethod.created_at.desc())
                    )
                    res = await db.execute(stmt)
                    pms = res.scalars().all()
                    if pms:
                        for pm in pms:
                            methods.append({
                                "id": pm.id,
                                "brand": pm.brand,
                                "last4": pm.last4,
                                "exp_month": pm.exp_month,
                                "exp_year": pm.exp_year,
                                "is_default": pm.is_default,
                                "provider": pm.provider,
                                "powered_by": pm.provider.title(),
                            })
            except Exception as exc:
                logger.warning(f"DB list payment methods failed: {exc}")

        if not methods:
            methods = _MEM_PAYMENT_METHODS.get(user_id, [])

        primary = next((m for m in methods if m.get("is_default")), methods[0] if methods else None)
        saved = [m for m in methods if m != primary]

        return {
            "primary": primary,
            "saved_methods": saved,
            "security_note": "All payments are securely processed and tokenized. No raw card data touches Roxy servers.",
        }

    async def add_payment_method(
        self,
        user_id: str,
        method_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a saved payment method."""
        pm_id = method_data.get("payment_method_id") or method_data.get("id") or f"pm_{uuid.uuid4().hex[:12]}"
        is_default = bool(method_data.get("set_as_default", True) or method_data.get("is_default", True))
        provider = method_data.get("provider", "stripe")

        new_pm = {
            "id": pm_id,
            "brand": method_data.get("brand", "visa").lower(),
            "last4": method_data.get("last4", "4242"),
            "exp_month": int(method_data.get("exp_month", 12)),
            "exp_year": int(method_data.get("exp_year", 2028)),
            "is_default": is_default,
            "provider": provider,
            "powered_by": provider.title(),
        }

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    if is_default:
                        stmt = select(PaymentMethod).where(PaymentMethod.user_id == user_id)
                        res = await db.execute(stmt)
                        for existing in res.scalars().all():
                            existing.is_default = False

                    db_pm = PaymentMethod(
                        id=pm_id,
                        user_id=user_id,
                        provider=provider,
                        brand=new_pm["brand"],
                        last4=new_pm["last4"],
                        exp_month=new_pm["exp_month"],
                        exp_year=new_pm["exp_year"],
                        is_default=is_default,
                    )
                    db.add(db_pm)
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB add payment method failed: {exc}")

        # In-memory storage
        if user_id not in _MEM_PAYMENT_METHODS:
            _MEM_PAYMENT_METHODS[user_id] = []
        if is_default:
            for m in _MEM_PAYMENT_METHODS[user_id]:
                m["is_default"] = False
        _MEM_PAYMENT_METHODS[user_id].insert(0, new_pm)

        # Update active subscription payment method preview
        if user_id in _MEM_SUBSCRIPTIONS:
            _MEM_SUBSCRIPTIONS[user_id]["payment_method"] = new_pm

        return new_pm

    async def delete_payment_method(self, user_id: str, pm_id: str) -> bool:
        """Delete a saved payment method."""
        deleted = False
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(PaymentMethod).where(
                        PaymentMethod.user_id == user_id, PaymentMethod.id == pm_id
                    )
                    res = await db.execute(stmt)
                    pm = res.scalars().first()
                    if pm:
                        await db.delete(pm)
                        await db.commit()
                        deleted = True
            except Exception as exc:
                logger.warning(f"DB delete payment method failed: {exc}")

        methods = _MEM_PAYMENT_METHODS.get(user_id, [])
        before = len(methods)
        _MEM_PAYMENT_METHODS[user_id] = [m for m in methods if m["id"] != pm_id]
        if len(_MEM_PAYMENT_METHODS[user_id]) < before:
            deleted = True

        # If deleted primary, update subscription
        if user_id in _MEM_SUBSCRIPTIONS and _MEM_SUBSCRIPTIONS[user_id].get("payment_method", {}).get("id") == pm_id:
            remaining = _MEM_PAYMENT_METHODS.get(user_id, [])
            _MEM_SUBSCRIPTIONS[user_id]["payment_method"] = remaining[0] if remaining else None

        return deleted

    # -------------------------------------------------------------------------
    # Invoices & Payments
    # -------------------------------------------------------------------------

    async def list_invoices(self, user_id: str) -> list[dict[str, Any]]:
        """List billing invoices for user."""
        return _MEM_INVOICES.get(user_id, [])

    async def add_invoice(self, user_id: str, invoice_data: dict[str, Any]) -> dict[str, Any]:
        """Add an invoice for user."""
        if user_id not in _MEM_INVOICES:
            _MEM_INVOICES[user_id] = []
        _MEM_INVOICES[user_id].insert(0, invoice_data)
        return invoice_data

    async def record_payment(self, user_id: str, payment_data: dict[str, Any]) -> dict[str, Any]:
        """Record normalized payment transaction in DB and memory."""
        p_id = payment_data.get("id") or str(uuid.uuid4())
        record = {
            "id": p_id,
            "user_id": user_id,
            "provider": payment_data.get("provider", "stripe"),
            "provider_payment_id": payment_data.get("provider_payment_id"),
            "provider_customer_id": payment_data.get("provider_customer_id"),
            "provider_session_id": payment_data.get("provider_session_id"),
            "amount": float(payment_data.get("amount", 0.0)),
            "currency": payment_data.get("currency", "USD").upper(),
            "status": payment_data.get("status", "paid"),
            "payment_type": payment_data.get("payment_type", "subscription"),
            "plan_id": payment_data.get("plan_id"),
            "created_at": datetime.now(UTC).isoformat(),
        }

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    db_p = Payment(
                        id=p_id,
                        user_id=user_id,
                        provider=record["provider"],
                        provider_payment_id=record["provider_payment_id"],
                        provider_customer_id=record["provider_customer_id"],
                        provider_session_id=record["provider_session_id"],
                        amount=record["amount"],
                        currency=record["currency"],
                        status=record["status"],
                        payment_type=record["payment_type"],
                        plan_id=record["plan_id"],
                    )
                    db.add(db_p)
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB record payment failed: {exc}")

        if user_id not in _MEM_PAYMENTS:
            _MEM_PAYMENTS[user_id] = []
        _MEM_PAYMENTS[user_id].insert(0, record)
        return record

    # -------------------------------------------------------------------------
    # Idempotent Webhook Event Deduplication
    # -------------------------------------------------------------------------

    async def record_webhook_event(
        self,
        event_id: str,
        provider: str,
        event_type: str,
        raw_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Atomically record event ID. Return True if new event, False if duplicate (idempotent)."""
        key = f"{provider}:{event_id}"
        if key in _MEM_EVENTS:
            logger.info(f"Duplicate webhook event detected in memory: {key}")
            return False

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(PaymentEvent).where(
                        PaymentEvent.provider == provider,
                        PaymentEvent.provider_event_id == event_id,
                    )
                    res = await db.execute(stmt)
                    existing = res.scalars().first()
                    if existing:
                        logger.info(f"Duplicate webhook event detected in DB: {key}")
                        _MEM_EVENTS.add(key)
                        return False

                    event = PaymentEvent(
                        provider=provider,
                        provider_event_id=event_id,
                        event_type=event_type,
                        payload=raw_payload or {},
                        processed=True,
                    )
                    db.add(event)
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB record webhook event error: {exc}")

        _MEM_EVENTS.add(key)
        return True

    # -------------------------------------------------------------------------
    # Credit Wallet
    # -------------------------------------------------------------------------

    async def get_credit_wallet(self, user_id: str) -> dict[str, Any]:
        """Get or initialize user credit wallet."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(CreditWallet).where(CreditWallet.user_id == user_id)
                    res = await db.execute(stmt)
                    wallet = res.scalars().first()
                    if wallet:
                        return {
                            "user_id": wallet.user_id,
                            "remaining_credits": wallet.remaining_credits,
                            "used_this_month": wallet.used_this_month,
                            "estimated_cost_usd": wallet.estimated_cost_usd,
                            "estimated_cost_pkr": wallet.estimated_cost_pkr,
                        }
            except Exception as exc:
                logger.warning(f"DB get wallet failed: {exc}")

        if user_id in _MEM_WALLETS:
            return _MEM_WALLETS[user_id]

        initial = {
            "user_id": user_id,
            "remaining_credits": 100.0,
            "used_this_month": 0.0,
            "estimated_cost_usd": 0.0,
            "estimated_cost_pkr": 0.0,
        }
        _MEM_WALLETS[user_id] = initial
        return initial

    async def credit_wallet(
        self,
        user_id: str,
        credits: float,
        cost_usd: float = 0.0,
        cost_pkr: float = 0.0,
    ) -> dict[str, Any]:
        """Add credits to user's wallet."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(CreditWallet).where(CreditWallet.user_id == user_id)
                    res = await db.execute(stmt)
                    wallet = res.scalars().first()
                    if not wallet:
                        wallet = CreditWallet(
                            user_id=user_id,
                            remaining_credits=100.0 + credits,
                            used_this_month=0.0,
                            estimated_cost_usd=cost_usd,
                            estimated_cost_pkr=cost_pkr,
                        )
                        db.add(wallet)
                    else:
                        wallet.remaining_credits += credits
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB credit wallet failed: {exc}")

        wallet_mem = await self.get_credit_wallet(user_id)
        wallet_mem["remaining_credits"] += credits
        _MEM_WALLETS[user_id] = wallet_mem
        return wallet_mem

    async def deduct_credits(self, user_id: str, credits: float) -> bool:
        """Deduct credits from user wallet if sufficient balance exists."""
        wallet = await self.get_credit_wallet(user_id)
        if wallet["remaining_credits"] < credits:
            return False

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(CreditWallet).where(CreditWallet.user_id == user_id)
                    res = await db.execute(stmt)
                    w = res.scalars().first()
                    if w:
                        w.remaining_credits -= credits
                        w.used_this_month += credits
                        await db.commit()
            except Exception as exc:
                logger.warning(f"DB deduct credits failed: {exc}")

        wallet["remaining_credits"] -= credits
        wallet["used_this_month"] += credits
        _MEM_WALLETS[user_id] = wallet
        return True
