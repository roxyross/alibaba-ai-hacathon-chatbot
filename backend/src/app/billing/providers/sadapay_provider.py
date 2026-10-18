"""SadaPay / SadaBiz Payment Provider implementation for Pakistani Rupee (PKR) transactions.

Implements PaymentProvider interface for SadaPay SadaBiz Checkout & Invoicing API.
Supports official sandbox and production environments with HMAC-SHA256 signature verification.
Enforces strict fail-closed security: missing credentials, network errors, or unverified
callbacks never simulate or grant payment success.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
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

logger = logging.getLogger(__name__)


class SadaPayProvider(PaymentProvider):
    """SadaPay implementation of PaymentProvider."""

    name = "sadapay"

    def __init__(
        self,
        api_key: str | None = None,
        merchant_id: str | None = None,
        webhook_secret: str | None = None,
        environment: str | None = None,
        api_base_url: str | None = None,
        checkout_base_url: str | None = None,
        timeout_seconds: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._explicit_api_key = api_key
        self._explicit_merchant_id = merchant_id
        self._explicit_webhook_secret = webhook_secret
        self._explicit_environment = environment
        self._explicit_api_base_url = api_base_url
        self._explicit_checkout_base_url = checkout_base_url
        self._explicit_timeout_seconds = timeout_seconds
        self._explicit_enabled = enabled

    @property
    def enabled(self) -> bool:
        if self._explicit_enabled is not None:
            return self._explicit_enabled
        return os.getenv("SADAPAY_ENABLED", "false").lower() in ("true", "1", "yes")

    def is_enabled(self) -> bool:
        """Check if SadaPay provider is enabled in configuration."""
        return self.enabled

    @property
    def api_key(self) -> str:
        if self._explicit_api_key is not None:
            return self._explicit_api_key
        return os.getenv("SADAPAY_API_KEY", "")

    @property
    def merchant_id(self) -> str:
        if self._explicit_merchant_id is not None:
            return self._explicit_merchant_id
        return os.getenv("SADAPAY_MERCHANT_ID", "")

    @property
    def webhook_secret(self) -> str:
        if self._explicit_webhook_secret is not None:
            return self._explicit_webhook_secret
        return os.getenv("SADAPAY_WEBHOOK_SECRET", "") or self.api_key

    @property
    def environment(self) -> str:
        if self._explicit_environment is not None:
            return self._explicit_environment.lower()
        return (os.getenv("SADAPAY_ENVIRONMENT", "sandbox") or "sandbox").lower()

    @property
    def api_base_url(self) -> str:
        if self._explicit_api_base_url is not None:
            return self._explicit_api_base_url.rstrip("/")
        env_url = os.getenv("SADAPAY_API_BASE_URL", "").strip()
        if env_url:
            return env_url.rstrip("/")
        if self.environment == "production":
            return "https://api.sadapay.pk/api/v1"
        return "https://sandbox.sadapay.pk/api/v1"

    @property
    def checkout_base_url(self) -> str:
        if self._explicit_checkout_base_url is not None:
            return self._explicit_checkout_base_url.rstrip("/")
        env_url = os.getenv("SADAPAY_CHECKOUT_BASE_URL", "").strip()
        if env_url:
            return env_url.rstrip("/")
        if self.environment == "production":
            return "https://pay.sadapay.pk"
        return "https://sandbox-pay.sadapay.pk"

    @property
    def timeout_seconds(self) -> float:
        if self._explicit_timeout_seconds is not None:
            return self._explicit_timeout_seconds
        try:
            return float(os.getenv("SADAPAY_TIMEOUT_SECONDS", "15"))
        except ValueError:
            return 15.0

    def is_configured(self) -> bool:
        """Check if required SadaPay merchant credentials are provided."""
        return bool(
            self.api_key
            and self.api_key.strip()
            and self.merchant_id
            and self.merchant_id.strip()
        )

    def is_live_mode(self) -> bool:
        """Check if using SadaPay production mode."""
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
        """Create SadaPay SadaBiz checkout or payment link session."""
        if currency.upper() != "PKR":
            raise ValueError(f"SadaPay only supports PKR transactions, got {currency}")

        if not self.is_enabled():
            raise RuntimeError(
                "SadaPay provider is currently disabled. Set SADAPAY_ENABLED=true and configure credentials to enable."
            )

        if not self.is_configured():
            raise RuntimeError(
                "SadaPay provider credentials are not configured: SADAPAY_API_KEY and SADAPAY_MERCHANT_ID required."
            )

        if self.is_live_mode() and ("test" in self.api_key.lower() or "sandbox" in self.api_key.lower()):
            raise RuntimeError("SadaPay sandbox credentials cannot be used in production mode.")

        meta = metadata or {}
        invoice_id = f"sp_{uuid.uuid4().hex[:16]}"

        # SadaPay / SadaBiz official Invoices creation payload
        payload = {
            "merchantId": self.merchant_id,
            "invoiceId": invoice_id,
            "amount": amount,
            "currency": "PKR",
            "customerEmail": email,
            "redirectUrl": return_url,
            "cancelUrl": cancel_url,
            "metadata": {"user_id": user_id, "plan_id": plan_id, **meta},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(f"{self.api_base_url}/invoices", json=payload, headers=headers)
                if res.status_code in (200, 201):
                    data = res.json()
                    session_id = data.get("invoiceId") or invoice_id
                    checkout_url = data.get("paymentUrl") or f"{self.checkout_base_url}/invoice/{session_id}"
                    return CheckoutSessionResult(
                        session_id=session_id,
                        checkout_url=checkout_url,
                        provider=self.name,
                        amount=amount,
                        currency="PKR",
                        status="pending",
                        metadata={"invoice_id": invoice_id, "user_id": user_id, "plan_id": plan_id, **meta},
                    )
                else:
                    logger.error("SadaPay invoice creation failed (HTTP %d): %s", res.status_code, res.text[:200])
                    raise RuntimeError(f"SadaPay invoice creation failed with HTTP {res.status_code}: {res.text[:200]}")
        except httpx.TimeoutException as exc:
            logger.error("SadaPay checkout creation timed out: %s", exc)
            raise RuntimeError("SadaPay checkout service timed out. Please try again.") from exc
        except httpx.RequestError as exc:
            logger.error("SadaPay checkout network error: %s", exc)
            raise RuntimeError(f"SadaPay checkout network error: {exc}") from exc

    async def verify_payment(self, session_or_tracker_id: str) -> PaymentVerificationResult:
        """Verify payment status with SadaPay gateway."""
        if not self.is_configured():
            logger.warning("SadaPay verify_payment called without credentials configured: failing closed")
            return PaymentVerificationResult(
                payment_id=session_or_tracker_id,
                status="failed",
                amount=0.0,
                currency="PKR",
                provider=self.name,
                error_message="SadaPay credentials not configured.",
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.get(
                    f"{self.api_base_url}/invoices/{session_or_tracker_id}",
                    headers=headers,
                )
                if res.status_code == 200:
                    data = res.json()
                    raw_status = (data.get("status") or "").lower()
                    if raw_status in ("paid", "completed", "success"):
                        status = "paid"
                    elif raw_status in ("failed", "rejected", "declined"):
                        status = "failed"
                    elif raw_status in ("cancelled", "canceled"):
                        status = "cancelled"
                    else:
                        status = "pending"
                    return PaymentVerificationResult(
                        payment_id=session_or_tracker_id,
                        status=status,
                        amount=float(data.get("amount", 0.0)),
                        currency="PKR",
                        provider=self.name,
                        customer_id=data.get("customerId"),
                        metadata=data,
                    )
                else:
                    logger.error("SadaPay payment verification failed (HTTP %d): %s", res.status_code, res.text[:200])
                    return PaymentVerificationResult(
                        payment_id=session_or_tracker_id,
                        status="failed",
                        amount=0.0,
                        currency="PKR",
                        provider=self.name,
                        error_message=f"SadaPay verification returned HTTP {res.status_code}",
                    )
        except Exception as exc:
            logger.error("SadaPay payment verification exception: %s", exc)
            return PaymentVerificationResult(
                payment_id=session_or_tracker_id,
                status="failed",
                amount=0.0,
                currency="PKR",
                provider=self.name,
                error_message=str(exc),
            )

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """Validate cryptographic HMAC-SHA256 webhook signature from SadaPay."""
        sig_header = (
            headers.get("x-sadapay-signature")
            or headers.get("x-signature")
            or headers.get("X-SadaPay-Signature")
            or headers.get("X-Signature")
            or ""
        )
        if not sig_header or not self.webhook_secret:
            return False

        computed = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed.lower(), sig_header.lower())

    def parse_webhook_event(self, headers: dict[str, str], raw_body: bytes) -> NormalizedWebhookEvent:
        """Parse raw webhook bytes into normalized event model."""
        payload = json.loads(raw_body.decode("utf-8"))
        data = payload.get("data") or payload

        event_id = str(data.get("eventId") or data.get("invoiceId") or uuid.uuid4())
        raw_status = (data.get("status") or "").lower()
        if raw_status in ("paid", "completed", "success", "invoice.paid"):
            event_type = "payment.succeeded"
        elif raw_status in (
            "failed",
            "rejected",
            "declined",
            "invoice.failed",
            "cancelled",
            "canceled",
        ):
            event_type = "payment.failed"
        else:
            event_type = "checkout.completed"

        amount = None
        if "amount" in data:
            with contextlib.suppress(ValueError, TypeError):
                amount = float(data.get("amount"))

        return NormalizedWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            provider=self.name,
            customer_id=data.get("customerId") or data.get("user_id"),
            payment_id=data.get("invoiceId"),
            amount=amount,
            currency="PKR",
            metadata=data.get("metadata") or {},
            raw_data=payload,
        )

    async def cancel_subscription(self, provider_subscription_id: str) -> bool:
        """SadaPay subscription/recurring payment cancellation.

        SadaPay SadaBiz Invoicing does not support automated recurring subscription
        cancellation. Returning False explicitly signals unsupported recurring cancellation.
        """
        logger.warning(
            "SadaPay invoicing API does not support automated subscription cancellation for %s",
            provider_subscription_id,
        )
        return False
