"""Payment Provider base abstraction interface and standardized data models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckoutSessionResult:
    """Standardized checkout session result across providers."""

    session_id: str
    checkout_url: str
    provider: str
    amount: float
    currency: str
    status: str = "pending"
    client_secret: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "checkout_url": self.checkout_url,
            "provider": self.provider,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "client_secret": self.client_secret,
            "metadata": self.metadata,
        }


@dataclass
class PaymentVerificationResult:
    """Standardized payment verification result."""

    payment_id: str
    status: str  # paid, pending, failed, canceled
    amount: float
    currency: str
    provider: str
    customer_id: str | None = None
    subscription_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "status": self.status,
            "amount": self.amount,
            "currency": self.currency,
            "provider": self.provider,
            "customer_id": self.customer_id,
            "subscription_id": self.subscription_id,
            "metadata": self.metadata,
            "error_message": self.error_message,
        }


@dataclass
class NormalizedWebhookEvent:
    """Standardized webhook event payload across providers."""

    event_id: str
    event_type: str  # checkout.completed, payment.succeeded, payment.failed, subscription.deleted
    provider: str
    customer_id: str | None = None
    subscription_id: str | None = None
    payment_id: str | None = None
    amount: float | None = None
    currency: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)


class PaymentProvider(ABC):
    """Abstract base payment provider interface."""

    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required API credentials for this provider are present."""
        ...

    @abstractmethod
    def is_live_mode(self) -> bool:
        """Return True if provider is using production/live credentials, False for test/sandbox."""
        ...

    @abstractmethod
    async def create_checkout_session(
        self,
        user_id: str,
        email: str,
        plan_id: str,
        amount: float,
        currency: str,
        return_url: str,
        cancel_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> CheckoutSessionResult:
        """Create a payment or subscription checkout session."""
        ...

    @abstractmethod
    async def verify_payment(
        self,
        session_or_tracker_id: str,
    ) -> PaymentVerificationResult:
        """Verify payment status server-side."""
        ...

    @abstractmethod
    def verify_webhook_signature(
        self,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> bool:
        """Validate cryptographic webhook signature from provider."""
        ...

    @abstractmethod
    def parse_webhook_event(
        self,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> NormalizedWebhookEvent:
        """Parse raw webhook bytes into normalized event model."""
        ...

    @abstractmethod
    async def cancel_subscription(
        self,
        provider_subscription_id: str,
    ) -> bool:
        """Cancel a subscription with the payment provider."""
        ...
