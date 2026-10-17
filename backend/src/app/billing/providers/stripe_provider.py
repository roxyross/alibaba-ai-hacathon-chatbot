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
    is_production_environment,
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
        self._explicit_api_key = api_key
        self._explicit_webhook_secret = webhook_secret
        self._explicit_publishable_key = publishable_key

    @property
    def api_key(self) -> str:
        if self._explicit_api_key is not None:
            return self._explicit_api_key
        return os.getenv("STRIPE_SECRET_KEY", "")

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._explicit_api_key = value

    @property
    def webhook_secret(self) -> str:
        if self._explicit_webhook_secret is not None:
            return self._explicit_webhook_secret
        return os.getenv("STRIPE_WEBHOOK_SECRET", "")

    @webhook_secret.setter
    def webhook_secret(self, value: str) -> None:
        self._explicit_webhook_secret = value

    @property
    def publishable_key(self) -> str:
        if self._explicit_publishable_key is not None:
            return self._explicit_publishable_key
        return os.getenv("STRIPE_PUBLISHABLE_KEY", "")

    @publishable_key.setter
    def publishable_key(self, value: str) -> None:
        self._explicit_publishable_key = value

    @property
    def additional_webhook_secrets(self) -> list[str]:
        return [
            s.strip()
            for s in [
                os.getenv("STRIPE_WEBHOOK_SNAPSHOT_SECRET", ""),
                os.getenv("STRIPE_WEBHOOK_THIN_SECRET", ""),
            ]
            if s and s.strip()
        ]

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
        is_prod = is_production_environment()

        # In production, check prerequisites strictly and fail closed
        if is_prod:
            if not self.is_configured():
                raise RuntimeError("Stripe secret key is not configured in production environment.")
            if not stripe:
                raise RuntimeError("Stripe SDK is not installed in production environment.")

        meta = metadata.copy() if metadata else {}
        meta.setdefault("user_id", user_id)
        meta.setdefault("plan_id", plan_id)

        # Real Stripe integration if configured and stripe SDK available
        if self.is_configured() and stripe:
            stripe.api_key = self.api_key
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

                session_id = getattr(session, "id", None)
                checkout_url = getattr(session, "url", None)
                if not session_id or not isinstance(session_id, str) or not session_id.strip():
                    raise RuntimeError("Stripe returned an invalid or empty session ID.")
                if not checkout_url or not isinstance(checkout_url, str) or not checkout_url.strip():
                    raise RuntimeError("Stripe returned an invalid or empty checkout URL.")

                return CheckoutSessionResult(
                    session_id=session_id,
                    checkout_url=checkout_url,
                    provider=self.name,
                    amount=amount,
                    currency=currency.upper(),
                    status="pending",
                    client_secret=getattr(session, "client_secret", None),
                    metadata=meta,
                )
            except Exception as exc:
                if is_prod:
                    raise RuntimeError(f"Stripe checkout session creation failed: {exc}") from exc

        if is_prod:
            raise RuntimeError("Stripe checkout failed to initialize in production environment.")

        # Simulated / Test session when Stripe keys are unset or in test mocks (non-production only)
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
            stripe.api_key = self.api_key
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

        # In production, unconfigured provider must never return simulated payment success
        if is_production_environment():
            return PaymentVerificationResult(
                payment_id=session_or_tracker_id,
                status="failed",
                amount=0.0,
                currency="USD",
                provider=self.name,
                error_message="Stripe provider is not configured for payment verification in production.",
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
        if is_production_environment() and (not self.is_configured() or not stripe):
            return False
        if self.is_configured() and stripe:
            stripe.api_key = self.api_key
            try:
                stripe.Subscription.modify(
                    provider_subscription_id,
                    cancel_at_period_end=True,
                )
                return True
            except Exception:
                return False
        return True
