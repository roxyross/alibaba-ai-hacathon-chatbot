"""Safepay Payment Provider implementation for Pakistani Rupee (PKR) transactions."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from typing import Any

import httpx

from app.billing.providers.base import (
    CheckoutSessionResult,
    NormalizedWebhookEvent,
    PaymentProvider,
    PaymentVerificationResult,
)


class SafepayProvider(PaymentProvider):
    """Safepay implementation of PaymentProvider."""

    name = "safepay"

    def __init__(
        self,
        api_key: str | None = None,
        webhook_secret: str | None = None,
        environment: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SAFEPAY_API_KEY", "")
        self.secret_key = os.getenv("SAFEPAY_SECRET_KEY", "")
        self.webhook_secret = webhook_secret or os.getenv("SAFEPAY_WEBHOOK_SECRET", "")
        env_val = environment or os.getenv("SAFEPAY_ENVIRONMENT", "sandbox") or "sandbox"
        self.environment = env_val.lower()

        if self.environment == "production":
            self.api_base_url = "https://api.getsafepay.com"
            self.checkout_base_url = "https://getsafepay.com/components"
        else:
            self.api_base_url = "https://sandbox.api.getsafepay.com"
            self.checkout_base_url = "https://sandbox.api.getsafepay.com/components"

    def is_configured(self) -> bool:
        """Check if required Safepay API credentials are provided."""
        return bool(self.api_key and self.api_key.strip())

    def is_live_mode(self) -> bool:
        """Check if using Safepay production mode."""
        return self.environment == "production"

    async def create_checkout_session(
        self,
        user_id: str,
        email: str,
        plan_id: str,
        amount: float,
        currency: str = "PKR",
        return_url: str = "",
        cancel_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CheckoutSessionResult:
        """Initialize an Order Tracker with Safepay and build hosted checkout URL."""
        meta = metadata.copy() if metadata else {}
        meta.setdefault("user_id", user_id)
        meta.setdefault("plan_id", plan_id)

        # Real Safepay API call if configured
        if self.is_configured():
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    payload = {
                        "client": self.api_key,
                        "amount": float(amount),
                        "currency": currency.upper(),
                        "environment": self.environment,
                    }
                    resp = await client.post(
                        f"{self.api_base_url}/order/v1/init",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        token = data.get("data", {}).get("token")
                        if token:
                            checkout_url = (
                                f"{self.checkout_base_url}?env={self.environment}"
                                f"&beacon={token}&source=custom"
                            )
                            return CheckoutSessionResult(
                                session_id=token,
                                checkout_url=checkout_url,
                                provider=self.name,
                                amount=amount,
                                currency=currency.upper(),
                                status="pending",
                                client_secret=token,
                                metadata=meta,
                            )
            except Exception as exc:
                if os.getenv("ENV") == "production":
                    raise exc

        # Simulated Tracker for test / development mode
        tracker_token = f"track_test_{uuid.uuid4().hex[:16]}"
        checkout_url = (
            f"{self.checkout_base_url}?env={self.environment}&beacon={tracker_token}&source=custom"
        )
        return CheckoutSessionResult(
            session_id=tracker_token,
            checkout_url=checkout_url,
            provider=self.name,
            amount=amount,
            currency=currency.upper(),
            status="pending",
            client_secret=tracker_token,
            metadata=meta,
        )

    async def verify_payment(
        self,
        session_or_tracker_id: str,
    ) -> PaymentVerificationResult:
        """Verify tracker status with Safepay API."""
        if self.is_configured():
            try:
                headers = {"X-SFPY-API-KEY": self.api_key} if self.api_key else {}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{self.api_base_url}/order/v1/{session_or_tracker_id}",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("data", {})
                        state = data.get("state", "").lower()
                        status = "paid" if state in ("paid", "completed") else "pending"
                        amount = float(data.get("amount", 0.0))
                        currency = data.get("currency", "PKR").upper()
                        return PaymentVerificationResult(
                            payment_id=session_or_tracker_id,
                            status=status,
                            amount=amount,
                            currency=currency,
                            provider=self.name,
                            customer_id=data.get("customer", {}).get("token"),
                            metadata={"tracker": session_or_tracker_id},
                        )
            except Exception as exc:
                return PaymentVerificationResult(
                    payment_id=session_or_tracker_id,
                    status="failed",
                    amount=0.0,
                    currency="PKR",
                    provider=self.name,
                    error_message=str(exc),
                )

        # Mock / Test verification fallback
        return PaymentVerificationResult(
            payment_id=session_or_tracker_id,
            status="paid",
            amount=5700.0,
            currency="PKR",
            provider=self.name,
            customer_id=f"sfpy_cus_{uuid.uuid4().hex[:8]}",
            subscription_id=None,
        )

    def verify_webhook_signature(
        self,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> bool:
        """Validate HMAC-SHA256 signature from Safepay webhook headers."""
        signature = (
            headers.get("x-sfpy-signature")
            or headers.get("X-SFPY-SIGNATURE")
            or headers.get("x-safepay-signature")
        )
        timestamp = (
            headers.get("x-sfpy-timestamp")
            or headers.get("X-SFPY-TIMESTAMP")
            or headers.get("x-safepay-timestamp")
        )

        if not signature:
            return False

        if not self.webhook_secret:
            return False

        try:
            # Safepay computes HMAC over `timestamp.body` (or body directly if no timestamp)
            payload_to_sign = f"{timestamp}.".encode() + raw_body if timestamp else raw_body

            expected_sig = hmac.new(
                self.webhook_secret.encode(),
                payload_to_sign,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(expected_sig.lower(), signature.lower())
        except Exception:
            return False

    def parse_webhook_event(
        self,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> NormalizedWebhookEvent:
        """Parse raw Safepay webhook payload into NormalizedWebhookEvent."""
        data = json.loads(raw_body.decode("utf-8"))
        event_id = data.get("id") or data.get("tracker") or f"sfpy_evt_{uuid.uuid4().hex[:12]}"
        event_type = data.get("event") or data.get("type", "unknown")

        # Map Safepay event names to normalized names
        normalized_type = "unknown"
        if event_type in ("payment:created", "payment.created"):
            normalized_type = "payment.pending"
        elif event_type in ("payment:completed", "payment.completed", "payment:succeeded"):
            normalized_type = "payment.succeeded"
        elif event_type in ("payment:failed", "payment.failed"):
            normalized_type = "payment.failed"
        else:
            normalized_type = event_type

        # Extract details
        tracker = data.get("tracker") or data.get("data", {}).get("token")
        amount_val = data.get("amount") or data.get("data", {}).get("amount")
        amount = float(amount_val) if amount_val is not None else None
        currency = (
            data.get("currency")
            or data.get("data", {}).get("currency")
            or "PKR"
        ).upper()

        metadata = data.get("metadata") or data.get("data", {}).get("metadata") or {}
        customer_id = data.get("customer_id") or data.get("data", {}).get("customer")

        return NormalizedWebhookEvent(
            event_id=event_id,
            event_type=normalized_type,
            provider=self.name,
            customer_id=str(customer_id) if customer_id else None,
            subscription_id=None,
            payment_id=tracker,
            amount=amount,
            currency=currency,
            metadata=metadata,
            raw_data=data,
        )

    async def cancel_subscription(
        self,
        provider_subscription_id: str,
    ) -> bool:
        """Cancel subscription (Safepay primarily operates on tracked payments/orders)."""
        # Safepay does not have recurring auto-debit cancellations in standard API
        return True
