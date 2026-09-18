"""Stripe Payment Provider implementation."""

from __future__ import annotations

import os
import uuid
from typing import Any

from app.billing.providers.base import (
    CheckoutSessionResult,
    NormalizedWebhookEvent,
    PaymentProvider,
    PaymentVerificationResult,
)

try:
    import stripe
except ImportError:  # pragma: no cover
    stripe = None  # type: ignore[assignment]


class StripeProvider(PaymentProvider):
    """Stripe implementation of PaymentProvider."""

    name = "stripe"

    def __init__(
        self,
        api_key: str | None = None,
        webhook_secret: str | None = None,
        publishable_key: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("STRIPE_SECRET_KEY", "")
        self.webhook_secret = webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.publishable_key = publishable_key or os.getenv("STRIPE_PUBLISHABLE_KEY", "")
        self.additional_webhook_secrets = [
            s.strip() for s in [
                os.getenv("STRIPE_WEBHOOK_SNAPSHOT_SECRET", ""),
                os.getenv("STRIPE_WEBHOOK_THIN_SECRET", ""),
            ] if s and s.strip()
        ]
        if self.api_key and stripe:
            stripe.api_key = self.api_key

    def is_configured(self) -> bool:
        """Check if required Stripe API key is provided."""
        return bool(self.api_key and self.api_key.strip())

    def is_live_mode(self) -> bool:
        """Check if using Stripe live keys."""
        return bool(self.api_key and self.api_key.startswith("sk_live_"))

    async def create_checkout_session(
        self,
        user_id: str,
        email: str,
        plan_id: str,
        amount: float,
        currency: str = "usd",
        return_url: str = "",
        cancel_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CheckoutSessionResult:
        """Create a Stripe Checkout Session for subscription or one-time payment."""
        meta = metadata.copy() if metadata else {}
        meta.setdefault("user_id", user_id)
        meta.setdefault("plan_id", plan_id)

        # Real Stripe integration if configured and stripe SDK available
        if self.is_configured() and stripe:
            try:
                # Mode is subscription for recurring plans, payment for top-ups
                is_topup = plan_id.startswith("pack_") or meta.get("type") == "topup"
                session_mode = "payment" if is_topup else "subscription"

                # Unit amount in cents
                unit_amount = int(round(amount * 100))

                line_items = [
                    {
                        "price_data": {
                            "currency": currency.lower(),
                            "product_data": {
                                "name": meta.get("item_name", f"Roxy-AI {plan_id.title()}"),
                                "description": meta.get("description", f"Roxy-AI subscription: {plan_id}"),
                            },
                            "unit_amount": unit_amount,
                            **(
                                {"recurring": {"interval": "month"}}
                                if session_mode == "subscription"
                                else {}
                            ),
                        },
                        "quantity": 1,
                    }
                ]

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode=session_mode,
                    customer_email=email,
                    line_items=line_items,  # type: ignore[arg-type]
                    success_url=return_url or "https://roxy.ai/billing?session_id={CHECKOUT_SESSION_ID}",
                    cancel_url=cancel_url or "https://roxy.ai/billing?canceled=true",
                    metadata=meta,
                )

                return CheckoutSessionResult(
                    session_id=session.id,
                    checkout_url=session.url or "",
                    provider=self.name,
                    amount=amount,
                    currency=currency.upper(),
                    status="pending",
                    client_secret=getattr(session, "client_secret", None),
                    metadata=meta,
                )
            except Exception as exc:
                # In testing or development, fall through to simulation if live call fails
                if os.getenv("ENV") == "production":
                    raise exc

        # Simulated / Test session when Stripe keys are unset or in test mocks
        session_id = f"cs_test_{uuid.uuid4().hex}"
        checkout_url = f"https://checkout.stripe.com/c/pay/{session_id}"
        return CheckoutSessionResult(
            session_id=session_id,
            checkout_url=checkout_url,
            provider=self.name,
            amount=amount,
            currency=currency.upper(),
            status="pending",
            client_secret=f"pi_mock_{uuid.uuid4().hex[:16]}_secret",
            metadata=meta,
        )

    async def verify_payment(
        self,
        session_or_tracker_id: str,
    ) -> PaymentVerificationResult:
        """Verify Stripe payment/checkout session status."""
        if self.is_configured() and stripe:
            try:
                session = stripe.checkout.Session.retrieve(session_or_tracker_id)
                status = "paid" if session.payment_status == "paid" else session.payment_status
                amount = float(session.amount_total or 0) / 100.0
                currency = (session.currency or "usd").upper()
                return PaymentVerificationResult(
                    payment_id=session.id,
                    status=status,
                    amount=amount,
                    currency=currency,
                    provider=self.name,
                    customer_id=str(getattr(session.customer, "id", session.customer)) if session.customer else None,
                    subscription_id=str(getattr(session.subscription, "id", session.subscription)) if session.subscription else None,
                    metadata=dict(session.metadata or {}),  # type: ignore[arg-type]
                )
            except Exception as exc:
                return PaymentVerificationResult(
                    payment_id=session_or_tracker_id,
                    status="failed",
                    amount=0.0,
                    currency="USD",
                    provider=self.name,
                    error_message=str(exc),
                )

        # Mock / Test verification fallback
        return PaymentVerificationResult(
            payment_id=session_or_tracker_id,
            status="paid",
            amount=19.0,
            currency="USD",
            provider=self.name,
            customer_id=f"cus_mock_{uuid.uuid4().hex[:8]}",
            subscription_id=f"sub_mock_{uuid.uuid4().hex[:8]}",
        )

    def verify_webhook_signature(
        self,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> bool:
        """Validate cryptographic Stripe webhook signature using stripe-signature header."""
        sig_header = headers.get("stripe-signature") or headers.get("Stripe-Signature")
        if not sig_header:
            return False

        secrets = [self.webhook_secret] + [s for s in self.additional_webhook_secrets if s != self.webhook_secret]
        valid_secrets = [s for s in secrets if s]

        if not valid_secrets:
            # If webhook secret is not configured in development/test, reject for security
            return False

        if stripe:
            for sec in valid_secrets:
                try:
                    stripe.Webhook.construct_event(
                        raw_body,
                        sig_header,
                        sec,
                    )
                    return True
                except Exception:
                    continue
            return False

        return False

    def parse_webhook_event(
        self,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> NormalizedWebhookEvent:
        """Parse raw Stripe webhook into NormalizedWebhookEvent."""
        import json

        data = json.loads(raw_body.decode("utf-8"))
        event_id = data.get("id", f"evt_{uuid.uuid4().hex[:12]}")
        event_type = data.get("type", "unknown")
        obj = data.get("data", {}).get("object", {})

        # Normalize common Stripe events
        normalized_type = "unknown"
        if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
            normalized_type = "payment.succeeded"
        elif event_type in ("payment_intent.payment_failed", "invoice.payment_failed"):
            normalized_type = "payment.failed"
        elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
            normalized_type = "subscription.deleted"
        elif event_type in ("customer.subscription.updated",):
            normalized_type = "subscription.updated"
        else:
            normalized_type = event_type

        # Extract payment/subscription info
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        payment_id = obj.get("id")
        amount_raw = obj.get("amount_total") or obj.get("amount")
        amount = float(amount_raw) / 100.0 if amount_raw is not None else None
        currency = obj.get("currency", "usd").upper() if obj.get("currency") else None
        metadata = obj.get("metadata", {})

        return NormalizedWebhookEvent(
            event_id=event_id,
            event_type=normalized_type,
            provider=self.name,
            customer_id=customer_id,
            subscription_id=subscription_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            metadata=metadata,
            raw_data=data,
        )

    async def cancel_subscription(
        self,
        provider_subscription_id: str,
    ) -> bool:
        """Cancel a subscription with Stripe."""
        if self.is_configured() and stripe:
            try:
                stripe.Subscription.modify(
                    provider_subscription_id,
                    cancel_at_period_end=True,
                )
                return True
            except Exception:
                return False
        return True
