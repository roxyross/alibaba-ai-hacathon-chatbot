"""Billing, Subscription, and Payment Methods API router.

Supports dual-provider architecture: Stripe (USD/international) and Safepay (PKR local),
provider-aware checkout, cryptographic webhook verification, and idempotent event logging.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.billing.repository import BillingRepository
from app.billing.service import PLANS, TOP_UP_PACKS, PaymentService

router = APIRouter(prefix="/billing", tags=["billing"])
_service = PaymentService()
_repo = _service.repo


# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------

class SubscribeRequest(BaseModel):
    plan_id: str
    currency: str = "usd"  # usd or pkr
    provider: str | None = None


class CheckoutRequest(BaseModel):
    plan_id: str
    currency: str = "usd"
    provider: str | None = None
    return_url: str = ""
    cancel_url: str = ""


class TopUpCheckoutRequest(BaseModel):
    pack_id: str
    currency: str = "usd"
    provider: str | None = None
    return_url: str = ""
    cancel_url: str = ""


class AddPaymentMethodRequest(BaseModel):
    payment_method_id: str = ""
    brand: str = "visa"
    last4: str = "4242"
    exp_month: int = 12
    exp_year: int = 2028
    set_as_default: bool = True
    provider: str = "stripe"


class TopUpRequest(BaseModel):
    pack_id: str


# -----------------------------------------------------------------------------
# Configuration & Plans
# -----------------------------------------------------------------------------

@router.get("/config")
async def get_billing_config() -> dict[str, Any]:
    """Expose public provider configuration and active mode (no secrets leaked)."""
    return _service.get_public_config()


@router.get("/plans")
async def get_plans() -> dict[str, Any]:
    """Return available Roxy-AI subscription plans and top-up packages."""
    return {"plans": PLANS, "top_up_packs": TOP_UP_PACKS}


# -----------------------------------------------------------------------------
# Subscription & Checkout
# -----------------------------------------------------------------------------

@router.get("/subscription")
async def get_subscription(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get active user subscription and primary payment method."""
    user_id = str(user.id)
    return await _repo.get_subscription(user_id)


@router.post("/checkout")
async def create_checkout(
    req: CheckoutRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a provider-aware checkout session (Stripe or Safepay)."""
    user_id = str(user.id)
    email = getattr(user, "email", f"{user_id}@roxy.ai")
    try:
        session = await _service.create_checkout_session(
            user_id=user_id,
            email=email,
            plan_id=req.plan_id,
            currency=req.currency,
            provider_name=req.provider,
            return_url=req.return_url,
            cancel_url=req.cancel_url,
        )
        return {
            "status": "success",
            "session": session.to_dict(),
            "checkout_url": session.checkout_url,
            "provider": session.provider,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Checkout creation failed: {exc}")


@router.post("/topup-checkout")
async def create_topup_checkout(
    req: TopUpCheckoutRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a provider-aware checkout session for top-up credits."""
    user_id = str(user.id)
    email = getattr(user, "email", f"{user_id}@roxy.ai")
    try:
        session = await _service.create_topup_checkout_session(
            user_id=user_id,
            email=email,
            pack_id=req.pack_id,
            currency=req.currency,
            provider_name=req.provider,
            return_url=req.return_url,
            cancel_url=req.cancel_url,
        )
        return {
            "status": "success",
            "session": session.to_dict(),
            "checkout_url": session.checkout_url,
            "provider": session.provider,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Top-up checkout creation failed: {exc}")


@router.get("/verify/{session_id}")
async def verify_payment_session(
    session_id: str,
    provider: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Verify payment status server-side."""
    res = await _service.verify_payment(session_id=session_id, provider_name=provider)
    return res.to_dict()


@router.post("/subscribe")
async def subscribe_plan(
    req: SubscribeRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Direct subscription upgrade (mock/elements flow)."""
    user_id = str(user.id)
    matched = next((p for p in PLANS if p["id"] == req.plan_id), None)
    if not matched:
        raise HTTPException(status_code=400, detail="Invalid plan selected.")

    now = datetime.now(UTC)
    prov = req.provider or ("safepay" if req.currency.lower() == "pkr" else "stripe")

    await _repo.update_or_create_subscription(
        user_id=user_id,
        plan_id=matched["id"],
        provider=prov,
        status="active",
        amount_usd=matched["price_usd"],
        amount_pkr=matched["price_pkr"],
    )

    if matched["price_usd"] > 0 or matched["price_pkr"] > 0:
        await _repo.add_invoice(
            user_id=user_id,
            invoice_data={
                "id": f"inv_{uuid.uuid4().hex[:8]}",
                "date": now.strftime("%b %d, %Y"),
                "description": f"Roxy-AI {matched['name']} Subscription",
                "amount_usd": matched["price_usd"],
                "amount_pkr": matched["price_pkr"],
                "status": "Paid",
                "invoice_pdf_url": "#",
            },
        )

    return {
        "status": "success",
        "message": f"Successfully subscribed to {matched['name']}.",
        "plan_id": req.plan_id,
        "amount_usd": matched["price_usd"],
        "amount_pkr": matched["price_pkr"],
        "client_secret": f"pi_mock_{uuid.uuid4().hex[:16]}_secret",
    }


@router.post("/cancel")
async def cancel_subscription(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Cancel subscription at end of billing period."""
    user_id = str(user.id)
    return await _repo.cancel_subscription(user_id)


# -----------------------------------------------------------------------------
# Payment Methods
# -----------------------------------------------------------------------------

@router.get("/payment-methods")
async def list_payment_methods(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """List saved payment methods for authenticated user."""
    user_id = str(user.id)
    return await _repo.list_payment_methods(user_id)


@router.post("/payment-methods")
async def add_payment_method(
    req: AddPaymentMethodRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Add a new card or tokenized payment method."""
    user_id = str(user.id)
    new_method = await _repo.add_payment_method(user_id, req.model_dump())
    return {
        "status": "success",
        "message": "Payment method saved securely.",
        "payment_method": new_method,
    }


@router.delete("/payment-methods/{pm_id}")
async def delete_payment_method(
    pm_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a saved payment method."""
    user_id = str(user.id)
    deleted = await _repo.delete_payment_method(user_id, pm_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Payment method not found.")
    return {"status": "success", "message": "Payment method removed."}


# -----------------------------------------------------------------------------
# Top-Ups & Wallet
# -----------------------------------------------------------------------------

@router.post("/topup")
async def topup_credits(
    req: TopUpRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Purchase a quick credit top-up pack."""
    user_id = str(user.id)
    matched = next((p for p in TOP_UP_PACKS if p["id"] == req.pack_id), None)
    if not matched:
        raise HTTPException(status_code=400, detail="Invalid top-up pack.")

    now = datetime.now(UTC)
    await _repo.credit_wallet(
        user_id=user_id,
        credits=float(matched["credits"]),
        cost_usd=matched["usd"],
        cost_pkr=matched["pkr"],
    )

    await _repo.add_invoice(
        user_id=user_id,
        invoice_data={
            "id": f"inv_{uuid.uuid4().hex[:8]}",
            "date": now.strftime("%b %d, %Y"),
            "description": f"Credit Top-Up ({matched['name']})",
            "amount_usd": matched["usd"],
            "amount_pkr": matched["pkr"],
            "status": "Paid",
            "invoice_pdf_url": "#",
        },
    )

    return {
        "status": "success",
        "pack": matched,
        "message": f"Successfully purchased {matched['name']} for ${matched['usd']} / Rs {matched['pkr']:,.0f}.",
    }


@router.get("/wallet")
async def get_wallet(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get authenticated user's credit wallet balance."""
    user_id = str(user.id)
    return await _repo.get_credit_wallet(user_id)


@router.get("/invoices")
async def get_invoices(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get full billing history and invoices."""
    user_id = str(user.id)
    invoices = await _repo.list_invoices(user_id)
    return {"invoices": invoices}


# -----------------------------------------------------------------------------
# Cryptographic Webhooks
# -----------------------------------------------------------------------------

@router.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> dict[str, Any]:
    """Process incoming Stripe webhook with cryptographic verification and idempotency."""
    raw_body = await request.body()
    headers = dict(request.headers)

    result = await _service.process_webhook("stripe", headers, raw_body)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Webhook verification failed"))
    return {"received": True, **result}


@router.post("/webhook/safepay")
async def safepay_webhook(request: Request) -> dict[str, Any]:
    """Process incoming Safepay webhook with HMAC-SHA256 verification and idempotency."""
    raw_body = await request.body()
    headers = dict(request.headers)

    result = await _service.process_webhook("safepay", headers, raw_body)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Webhook verification failed"))
    return {"received": True, **result}
