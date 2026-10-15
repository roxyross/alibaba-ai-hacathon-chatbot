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
    is_production_environment,
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
        self._explicit_api_key = api_key
        self._explicit_webhook_secret = webhook_secret
        self._explicit_environment = environment

    @property
    def api_key(self) -> str:
        if self._explicit_api_key is not None:
            return self._explicit_api_key
        return os.getenv("SAFEPAY_API_KEY", "")

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._explicit_api_key = value

    @property
    def secret_key(self) -> str:
        return getattr(self, "_explicit_secret_key", None) or os.getenv("SAFEPAY_SECRET_KEY", "")

    @secret_key.setter
    def secret_key(self, value: str) -> None:
        self._explicit_secret_key = value

    @property
    def webhook_secret(self) -> str:
        if self._explicit_webhook_secret is not None:
            return self._explicit_webhook_secret
        return os.getenv("SAFEPAY_WEBHOOK_SECRET", "")

    @webhook_secret.setter
    def webhook_secret(self, value: str) -> None:
        self._explicit_webhook_secret = value

    @property
    def environment(self) -> str:
        if self._explicit_environment is not None:
            return self._explicit_environment.lower()
        env_val = os.getenv("SAFEPAY_ENVIRONMENT", "sandbox") or "sandbox"
        return env_val.lower()

    @environment.setter
    def environment(self, value: str) -> None:
        self._explicit_environment = value

    @property
    def api_base_url(self) -> str:
        if self.environment == "production":
            return "https://api.getsafepay.com"
        return "https://sandbox.api.getsafepay.com"

    @property
    def checkout_base_url(self) -> str:
        if self.environment == "production":
            return "https://getsafepay.com/components"
        return "https://sandbox.api.getsafepay.com/components"

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
        is_prod = is_production_environment()

        # Validate currency support
        curr = currency.upper()
        if curr not in ("PKR", "USD"):
            raise ValueError(f"Currency '{currency}' is not supported by Safepay provider. Supported: PKR, USD.")

        # In production, check prerequisites strictly and fail closed
        if is_prod and not self.is_configured():
            raise RuntimeError("Safepay API key is not configured in production environment.")

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
                        "currency": curr,
                        "environment": self.environment,
                    }
                    resp = await client.post(
                        f"{self.api_base_url}/order/v1/init",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except Exception as exc:
                            raise RuntimeError("Safepay returned a malformed response.") from exc

                        token = data.get("data", {}).get("token") if isinstance(data, dict) and isinstance(data.get("data"), dict) else None
                        if not token or not isinstance(token, str) or not token.strip():
                            raise RuntimeError("Safepay returned an invalid or empty tracker token.")

                        checkout_url = (
                            f"{self.checkout_base_url}?env={self.environment}"
                            f"&beacon={token}&source=custom"
                        )
                        return CheckoutSessionResult(
                            session_id=token,
                            checkout_url=checkout_url,
                            provider=self.name,
                            amount=amount,
                            currency=curr,
                            status="pending",
                            client_secret=token,
                            metadata=meta,
                        )
                    else:
                        raise RuntimeError(f"Safepay order init failed with status {resp.status_code}: {resp.text[:200]}")
            except Exception as exc:
                if is_prod:
                    raise RuntimeError(f"Safepay checkout session creation failed: {exc}") from exc

        if is_prod:
            raise RuntimeError("Safepay checkout failed to initialize in production environment.")

        # Simulated Tracker for test / development mode (non-production only)
        tracker_token = f"track_test_{uuid.uuid4().hex[:16]}"
        checkout_url = (
            f"{self.checkout_base_url}?env={self.environment}&beacon={tracker_token}&source=custom"
        )
        return CheckoutSessionResult(
            session_id=tracker_token,
            checkout_url=checkout_url,
            provider=self.name,
            amount=amount,
            currency=curr,
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

        # In production, unconfigured provider must never return simulated payment success
        if is_production_environment():
            return PaymentVerificationResult(
                payment_id=session_or_tracker_id,
                status="failed",
                amount=0.0,
                currency="PKR",
                provider=self.name,
                error_message="Safepay provider is not configured for payment verification in production.",
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
        return not (is_production_environment() and not self.is_configured())
