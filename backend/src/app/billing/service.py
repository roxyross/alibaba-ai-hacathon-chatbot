"""PaymentService orchestrating dual Stripe and Safepay providers, checkout, webhooks, and billing."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from app.billing.providers.base import (
    CheckoutSessionResult,
    NormalizedWebhookEvent,
    PaymentProvider,
    PaymentVerificationResult,
)
from app.billing.providers.safepay_provider import SafepayProvider
from app.billing.providers.stripe_provider import StripeProvider
from app.billing.repository import BillingRepository
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

logger = logging.getLogger(__name__)

# Canonical Roxy-AI plans
PLANS: list[dict[str, Any]] = [
    {
        "id": "free",
        "name": "Free (BYOK)",
        "price_usd": 0.0,
        "price_pkr": 0.0,
        "billing_period": "month",
        "description": "Start exploring Roxy-AI. Perfect for students and early testers.",
        "features": [
            "Unlimited basic chat",
            "Local document memory",
            "Voice input",
        ],
        "cta_text": "Start Free",
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_usd": 19.0,
        "price_pkr": 5700.0,
        "billing_period": "month",
        "description": "Full autonomous assistant that schedules jobs, tracks finance, and sends emails for you.",
        "features": [
            "Everything in Free",
            "Schedule jobs & automated workflows",
            "Finance tracking & expense logging",
            "Email send & meeting action items",
            "Cross-device continuity",
            "Smart-home control (Matter)",
            "20 GB private vector memory",
        ],
        "cta_text": "Go Pro",
    },
    {
        "id": "team",
        "name": "Team / Business",
        "price_usd": 39.0,
        "price_pkr": 11000.0,
        "billing_period": "seat / month",
        "description": "Shared workspace for teams with advanced permissions, audit logs, and priority support.",
        "features": [
            "Everything in Pro",
            "Shared team memory",
            "Role-based access",
            "Full audit logs",
            "Priority AI model access",
            "Dedicated onboarding",
        ],
        "cta_text": "Contact Sales",
    },
]

TOP_UP_PACKS: list[dict[str, Any]] = [
    {"id": "pack_5", "name": "Starter Boost", "usd": 5.0, "pkr": 1400.0, "credits": 500000},
    {"id": "pack_10", "name": "Power Surge", "usd": 10.0, "pkr": 2800.0, "credits": 1200000},
    {"id": "pack_20", "name": "Studio Ultra", "usd": 20.0, "pkr": 5600.0, "credits": 2800000},
]


class PaymentService:
    """Unified service for payment operations across Stripe and Safepay."""

    _instance: ClassVar[PaymentService | None] = None

    def __init__(
        self,
        repository: BillingRepository | None = None,
        stripe_provider: StripeProvider | None = None,
        safepay_provider: SafepayProvider | None = None,
    ) -> None:
        self.repo = repository or BillingRepository()
        self.stripe = stripe_provider or StripeProvider()
        self.safepay = safepay_provider or SafepayProvider()

    @classmethod
    def get_instance(
        cls,
        repository: BillingRepository | None = None,
        stripe_provider: StripeProvider | None = None,
        safepay_provider: SafepayProvider | None = None,
    ) -> PaymentService:
        """Get or initialize singleton instance of PaymentService."""
        if cls._instance is None:
            cls._instance = cls(
                repository=repository,
                stripe_provider=stripe_provider,
                safepay_provider=safepay_provider,
            )
        return cls._instance

    @property
    def mode(self) -> str:
        """Global mode: automatic, stripe, or safepay."""
        return os.getenv("PAYMENT_PROVIDER_MODE", "automatic").lower()

    def get_provider(
        self,
        requested_provider: str | None = None,
        currency: str = "USD",
    ) -> PaymentProvider:
        """Resolve the appropriate PaymentProvider according to configuration and request."""
        # 1. If explicit mode is forced in environment
        if self.mode == "stripe":
            return self.stripe
        if self.mode == "safepay":
            return self.safepay

        # 2. If caller requested a specific provider
        req = (requested_provider or "").lower().strip()
        if req == "safepay":
            return self.safepay
        if req == "stripe":
            return self.stripe

        # 3. Automatic routing based on currency
        curr = currency.upper().strip()
        if curr == "PKR":
            # Prefer Safepay for PKR if configured or in automatic mode
            if self.safepay.is_configured() or not self.stripe.is_configured():
                return self.safepay
            return self.stripe

        # USD and international transactions default to Stripe
        if self.stripe.is_configured() or not self.safepay.is_configured():
            return self.stripe
        return self.safepay

    def get_public_config(self) -> dict[str, Any]:
        """Expose safe public billing configuration without leaking secrets."""
        return {
            "mode": self.mode,
            "providers": {
                "stripe": {
                    "configured": self.stripe.is_configured(),
                    "publishable_key": self.stripe.publishable_key,
                    "live_mode": self.stripe.is_live_mode(),
                    "supported_currencies": ["USD", "EUR", "GBP"],
                },
                "safepay": {
                    "configured": self.safepay.is_configured(),
                    "environment": self.safepay.environment,
                    "live_mode": self.safepay.is_live_mode(),
                    "supported_currencies": ["PKR"],
                },
            },
            "plans": PLANS,
            "top_up_packs": TOP_UP_PACKS,
        }

    async def create_checkout_session(
        self,
        user_id: str,
        email: str,
        plan_id: str,
        currency: str = "USD",
        provider_name: str | None = None,
        return_url: str = "",
        cancel_url: str = "",
    ) -> CheckoutSessionResult:
        """Create checkout session for a subscription plan."""
        matched = next((p for p in PLANS if p["id"] == plan_id), None)
        if not matched:
            raise ValueError(f"Invalid plan ID: {plan_id}")

        curr = currency.upper()
        provider = self.get_provider(requested_provider=provider_name, currency=curr)

        # Calculate amount for currency
        amount = float(matched["price_pkr"]) if curr == "PKR" else float(matched["price_usd"])

        metadata = {
            "user_id": user_id,
            "plan_id": plan_id,
            "type": "subscription",
            "item_name": f"Roxy-AI {matched['name']}",
        }

        return await provider.create_checkout_session(
            user_id=user_id,
            email=email,
            plan_id=plan_id,
            amount=amount,
            currency=curr,
            return_url=return_url,
            cancel_url=cancel_url,
            metadata=metadata,
        )

    async def create_topup_checkout_session(
        self,
        user_id: str,
        email: str,
        pack_id: str,
        currency: str = "USD",
        provider_name: str | None = None,
        return_url: str = "",
        cancel_url: str = "",
    ) -> CheckoutSessionResult:
        """Create checkout session for credit top-up pack."""
        matched = next((p for p in TOP_UP_PACKS if p["id"] == pack_id), None)
        if not matched:
            raise ValueError(f"Invalid top-up pack ID: {pack_id}")

        curr = currency.upper()
        provider = self.get_provider(requested_provider=provider_name, currency=curr)

        amount = float(matched["pkr"]) if curr == "PKR" else float(matched["usd"])

        metadata = {
            "user_id": user_id,
            "pack_id": pack_id,
            "credits": matched["credits"],
            "type": "topup",
            "item_name": f"Roxy-AI {matched['name']} Top-Up",
        }

        return await provider.create_checkout_session(
            user_id=user_id,
            email=email,
            plan_id=pack_id,
            amount=amount,
            currency=curr,
            return_url=return_url,
            cancel_url=cancel_url,
            metadata=metadata,
        )

    async def verify_payment(
        self,
        session_id: str,
        provider_name: str | None = None,
    ) -> PaymentVerificationResult:
        """Verify payment status with the corresponding provider."""
        provider = self.safepay if provider_name == "safepay" else self.stripe
        return await provider.verify_payment(session_id)

    async def process_webhook(
        self,
        provider_name: str,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> dict[str, Any]:
        """Verify, deduplicate, and process a payment webhook."""
        prov_name = provider_name.lower()
        provider: PaymentProvider = self.safepay if prov_name == "safepay" else self.stripe

        # 1. Cryptographic signature check
        # In test mode without secrets configured, allow if signature is explicitly provided or mocked
        is_valid = provider.verify_webhook_signature(headers, raw_body)
        if not is_valid:
            # In production, test headers are strictly prohibited from bypassing cryptographic signature checks
            is_prod = os.getenv("APP_ENV", "").lower() in ("production", "prod") or os.getenv("ENV", "").lower() in ("production", "prod")
            is_test = headers.get("x-roxy-test") == "true" and not is_prod
            if not is_test:
                logger.warning(f"Webhook signature verification failed for {prov_name}")
                return {"status": "error", "message": "Invalid webhook signature"}

        # 2. Parse normalized event
        try:
            event: NormalizedWebhookEvent = provider.parse_webhook_event(headers, raw_body)
        except Exception as exc:
            logger.error(f"Failed to parse webhook event: {exc}")
            return {"status": "error", "message": f"Malformed webhook body: {exc}"}

        # 3. Idempotent deduplication check
        is_new = await self.repo.record_webhook_event(
            event_id=event.event_id,
            provider=prov_name,
            event_type=event.event_type,
            raw_payload=event.raw_data,
        )
        if not is_new:
            logger.info(f"Duplicate webhook ignored for event_id: {event.event_id}")
            return {
                "status": "already_processed",
                "event_id": event.event_id,
                "message": "Event already processed (idempotent).",
            }

        # 4. Handle normalized event actions
        user_id = event.metadata.get("user_id")
        plan_id = event.metadata.get("plan_id")
        pack_id = event.metadata.get("pack_id")
        event_type = event.event_type

        if user_id:
            now = datetime.now(UTC)
            # Record payment record
            if event.amount is not None:
                await self.repo.record_payment(
                    user_id=user_id,
                    payment_data={
                        "provider": prov_name,
                        "provider_payment_id": event.payment_id or event.event_id,
                        "provider_customer_id": event.customer_id,
                        "amount": event.amount,
                        "currency": event.currency or ("PKR" if prov_name == "safepay" else "USD"),
                        "status": "paid" if event_type == "payment.succeeded" else "failed",
                        "payment_type": "topup" if pack_id else "subscription",
                        "plan_id": plan_id or pack_id,
                    },
                )

            # Handle successful payment
            if event_type == "payment.succeeded":
                # A. Subscription checkout
                if plan_id and not pack_id:
                    matched_plan = next((p for p in PLANS if p["id"] == plan_id), None)
                    name = matched_plan["name"] if matched_plan else plan_id.title()
                    p_usd = matched_plan["price_usd"] if matched_plan else 0.0
                    p_pkr = matched_plan["price_pkr"] if matched_plan else 0.0

                    await self.repo.update_or_create_subscription(
                        user_id=user_id,
                        plan_id=plan_id,
                        provider=prov_name,
                        status="active",
                        amount_usd=p_usd,
                        amount_pkr=p_pkr,
                        provider_customer_id=event.customer_id,
                        provider_subscription_id=event.subscription_id,
                    )

                    await self.repo.add_invoice(
                        user_id=user_id,
                        invoice_data={
                            "id": f"inv_{uuid.uuid4().hex[:8]}",
                            "date": now.strftime("%b %d, %Y"),
                            "description": f"Roxy-AI {name} Subscription ({prov_name.title()})",
                            "amount_usd": p_usd,
                            "amount_pkr": p_pkr,
                            "status": "Paid",
                            "invoice_pdf_url": "#",
                        },
                    )

                # B. Credit Top-Up checkout
                elif pack_id:
                    credits = float(event.metadata.get("credits", 500000))
                    cost_usd = event.amount if (event.currency or "").upper() == "USD" else 0.0
                    cost_pkr = event.amount if (event.currency or "").upper() == "PKR" else 0.0

                    await self.repo.credit_wallet(
                        user_id=user_id,
                        credits=credits,
                        cost_usd=cost_usd or 0.0,
                        cost_pkr=cost_pkr or 0.0,
                    )

                    await self.repo.add_invoice(
                        user_id=user_id,
                        invoice_data={
                            "id": f"inv_{uuid.uuid4().hex[:8]}",
                            "date": now.strftime("%b %d, %Y"),
                            "description": f"Credit Top-Up ({pack_id}) ({prov_name.title()})",
                            "amount_usd": cost_usd or 0.0,
                            "amount_pkr": cost_pkr or 0.0,
                            "status": "Paid",
                            "invoice_pdf_url": "#",
                        },
                    )

            # Handle subscription cancellation
            elif event_type == "subscription.deleted":
                await self.repo.cancel_subscription(user_id)

        return {
            "status": "success",
            "event_id": event.event_id,
            "event_type": event.event_type,
            "provider": prov_name,
        }

    def register_billing_tools(self) -> None:
        """Register billing, wallet, and checkout tools into the Central ToolRegistry."""
        reg = ToolRegistry.get_instance()

        async def _tool_billing_get_wallet(user_id: str | None = None) -> dict[str, Any]:
            uid = user_id or "default"
            wallet = await self.repo.get_credit_wallet(uid)
            sub = await self.repo.get_subscription(uid)
            plan_name = sub.get("plan", {}).get("name", "Free (BYOK)")
            plan_status = sub.get("plan", {}).get("status", "active")
            remaining = float(wallet.get("remaining_credits", 100.0))
            used = float(wallet.get("used_this_month", 0.0))
            cost_usd = float(wallet.get("estimated_cost_usd", 0.0))
            cost_pkr = float(wallet.get("estimated_cost_pkr", 0.0))

            return {
                "user_id": uid,
                "remaining_credits": remaining,
                "used_this_month": used,
                "estimated_cost_usd": cost_usd,
                "estimated_cost_pkr": cost_pkr,
                "active_plan": plan_name,
                "plan_status": plan_status,
                "summary": (
                    f"Wallet balance: {remaining:,.0f} credits remaining "
                    f"({used:,.0f} consumed this month). Active plan: {plan_name}."
                ),
            }

        async def _tool_billing_list_plans() -> dict[str, Any]:
            return {
                "plans": PLANS,
                "top_up_packs": TOP_UP_PACKS,
                "mode": self.mode,
                "supported_currencies": ["USD", "PKR"],
                "summary": f"{len(PLANS)} subscription plans and {len(TOP_UP_PACKS)} top-up packs available.",
            }

        async def _tool_billing_create_checkout(
            plan_id: str = "pro",
            currency: str = "usd",
            provider: str | None = None,
            return_url: str = "",
            cancel_url: str = "",
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            email = f"{uid}@roxy.ai"
            res = await self.create_checkout_session(
                user_id=uid,
                email=email,
                plan_id=plan_id.lower().strip(),
                currency=currency.upper().strip(),
                provider_name=provider,
                return_url=return_url,
                cancel_url=cancel_url,
            )
            return {
                "status": "success",
                "checkout_url": res.checkout_url,
                "session_id": res.session_id,
                "provider": res.provider,
                "plan_id": plan_id,
                "currency": currency.upper().strip(),
                "amount": res.amount,
                "summary": f"Checkout session created for {plan_id.title()} plan via {res.provider.title()}.",
            }

        async def _tool_billing_topup_credits(
            pack_id: str = "pack_10",
            currency: str = "usd",
            provider: str | None = None,
            return_url: str = "",
            cancel_url: str = "",
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            email = f"{uid}@roxy.ai"
            res = await self.create_topup_checkout_session(
                user_id=uid,
                email=email,
                pack_id=pack_id.lower().strip(),
                currency=currency.upper().strip(),
                provider_name=provider,
                return_url=return_url,
                cancel_url=cancel_url,
            )
            return {
                "status": "success",
                "checkout_url": res.checkout_url,
                "session_id": res.session_id,
                "provider": res.provider,
                "pack_id": pack_id,
                "currency": currency.upper().strip(),
                "amount": res.amount,
                "summary": f"Top-up checkout created for pack '{pack_id}' via {res.provider.title()}.",
            }

        async def _tool_billing_get_invoices(user_id: str | None = None) -> dict[str, Any]:
            uid = user_id or "default"
            invoices = await self.repo.list_invoices(uid)
            return {
                "user_id": uid,
                "total_invoices": len(invoices),
                "invoices": invoices,
                "summary": f"Retrieved {len(invoices)} billing invoices for user.",
            }

        async def _tool_billing_cancel_subscription(user_id: str | None = None) -> dict[str, Any]:
            uid = user_id or "default"
            res = await self.repo.cancel_subscription(uid)
            return {
                "user_id": uid,
                "status": "cancelled",
                "message": res.get("message", "Subscription set to cancel at end of billing period."),
                "active_until": res.get("active_until"),
            }

        # 1. Billing Get Wallet
        reg.register(
            AgentTool(
                id="billing_get_wallet",
                name="Get AI Credit Wallet & Balance",
                description="Retrieve current AI credit wallet balance, consumed credits, and subscription status.",
                source=ToolSource.SYSTEM,
                capabilities=["billing", "wallet", "credits", "balance"],
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                permissions=["billing:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_billing_get_wallet,
        )

        # 2. Billing List Plans
        reg.register(
            AgentTool(
                id="billing_list_plans",
                name="List Subscription Plans & Top-Up Packs",
                description="List available subscription tiers (Free, Pro, Team) and credit top-up packs with USD and PKR pricing.",
                source=ToolSource.SYSTEM,
                capabilities=["billing", "plans", "pricing", "subscriptions"],
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                permissions=["billing:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_billing_list_plans,
        )

        # 3. Billing Create Checkout
        reg.register(
            AgentTool(
                id="billing_create_checkout",
                name="Create Subscription Checkout Session",
                description="Generate a secure checkout link for subscribing or upgrading to a plan (Pro, Team) with Stripe (USD) or Safepay (PKR).",
                source=ToolSource.SYSTEM,
                capabilities=["billing", "checkout", "subscribe", "upgrade"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "plan_id": {"type": "string", "enum": ["pro", "team"], "default": "pro", "description": "Subscription plan ID"},
                        "currency": {"type": "string", "enum": ["usd", "pkr"], "default": "usd", "description": "Payment currency"},
                        "provider": {"type": "string", "description": "Explicit payment provider (stripe or safepay)"},
                    },
                    "required": ["plan_id"],
                },
                permissions=["billing:checkout"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            ),
            _tool_billing_create_checkout,
        )

        # 4. Billing Top-Up Credits
        reg.register(
            AgentTool(
                id="billing_topup_credits",
                name="Create Credit Top-Up Checkout",
                description="Generate a checkout link to purchase extra AI generation credits via top-up packs.",
                source=ToolSource.SYSTEM,
                capabilities=["billing", "topup", "credits", "wallet"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "pack_id": {"type": "string", "enum": ["pack_5", "pack_10", "pack_20"], "default": "pack_10", "description": "Top-up pack ID"},
                        "currency": {"type": "string", "enum": ["usd", "pkr"], "default": "usd", "description": "Payment currency"},
                        "provider": {"type": "string", "description": "Explicit payment provider (stripe or safepay)"},
                    },
                    "required": ["pack_id"],
                },
                permissions=["billing:checkout"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            ),
            _tool_billing_topup_credits,
        )

        # 5. Billing Get Invoices
        reg.register(
            AgentTool(
                id="billing_get_invoices",
                name="List Invoices & Billing History",
                description="Retrieve past invoices, payment history, and receipts for the authenticated user.",
                source=ToolSource.SYSTEM,
                capabilities=["billing", "invoices", "history", "receipts"],
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                permissions=["billing:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_billing_get_invoices,
        )

        # 6. Billing Cancel Subscription
        reg.register(
            AgentTool(
                id="billing_cancel_subscription",
                name="Cancel Subscription Plan",
                description="Cancel active paid subscription plan at the end of the current billing cycle. Requires user confirmation.",
                source=ToolSource.SYSTEM,
                capabilities=["billing", "subscription", "cancellation"],
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                permissions=["billing:write"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            ),
            _tool_billing_cancel_subscription,
        )
