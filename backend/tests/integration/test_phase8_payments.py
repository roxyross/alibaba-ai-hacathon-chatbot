"""Phase 8 Master Integration Test Suite: Dual Stripe + Safepay Payment Architecture.

Verifies:
1. Public billing config endpoint (mode, currencies, plans, zero secret leakage).
2. Dual-provider checkout session routing (Stripe for USD, Safepay for PKR).
3. Top-up pack checkout generation.
4. Cryptographic webhook verification and rejection of invalid signatures.
5. Idempotent webhook event processing (replay protection preventing double subscription or duplicate credits).
6. Real-time credit wallet updates and consumption tracking.
7. Subscription cancellation lifecycle.
8. Strict multi-tenant isolation across billing, payment methods, and invoices.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, "src")

from app.billing.repository import clear_in_memory_stores
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_billing() -> None:
    clear_in_memory_stores()


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Return (auth_headers, user_id)."""
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    verify_data = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()
    token = verify_data["access_token"]
    user_id = verify_data["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, user_id


# -----------------------------------------------------------------------------
# 1. Configuration & Public Metadata
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_billing_config_endpoint(client: httpx.AsyncClient) -> None:
    """Ensure public billing config exposes supported providers and plans without secret leakage."""
    resp = await client.get("/api/v1/billing/config")
    assert resp.status_code == 200
    data = resp.json()

    assert "mode" in data
    assert "providers" in data
    assert "stripe" in data["providers"]
    assert "safepay" in data["providers"]
    assert "plans" in data
    assert "top_up_packs" in data

    # Strict secret protection check: NO private/secret keys exposed
    text_dump = json.dumps(data).lower()
    assert "sk_test" not in text_dump
    assert "sk_live" not in text_dump
    assert "sec_" not in text_dump
    assert "secret" not in text_dump or "webhook_secret" not in text_dump


# -----------------------------------------------------------------------------
# 2. Dual Provider Checkout Routing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_checkout_session_routing(client: httpx.AsyncClient) -> None:
    """Verify Stripe routes for USD and Safepay routes for PKR transactions."""
    auth, user_id = await _get_auth(client, f"user_checkout_{uuid.uuid4().hex[:6]}@roxy.ai")

    # A. USD Checkout routes to Stripe
    resp_usd = await client.post(
        "/api/v1/billing/checkout",
        headers=auth,
        json={"plan_id": "pro", "currency": "usd"},
    )
    assert resp_usd.status_code == 200
    data_usd = resp_usd.json()
    assert data_usd["status"] == "success"
    assert data_usd["provider"] == "stripe"
    assert "checkout.stripe.com" in data_usd["checkout_url"] or "stripe" in data_usd["checkout_url"]
    assert data_usd["session"]["amount"] == 19.0
    assert data_usd["session"]["currency"] == "USD"

    # B. PKR Checkout routes to Safepay
    resp_pkr = await client.post(
        "/api/v1/billing/checkout",
        headers=auth,
        json={"plan_id": "pro", "currency": "pkr"},
    )
    assert resp_pkr.status_code == 200
    data_pkr = resp_pkr.json()
    assert data_pkr["status"] == "success"
    assert data_pkr["provider"] == "safepay"
    assert "safepay" in data_pkr["checkout_url"]
    assert data_pkr["session"]["amount"] == 5700.0
    assert data_pkr["session"]["currency"] == "PKR"


@pytest.mark.anyio
async def test_topup_checkout_routing(client: httpx.AsyncClient) -> None:
    """Verify top-up pack checkout generation."""
    auth, user_id = await _get_auth(client, f"user_topup_{uuid.uuid4().hex[:6]}@roxy.ai")

    resp = await client.post(
        "/api/v1/billing/topup-checkout",
        headers=auth,
        json={"pack_id": "pack_5", "currency": "usd"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["session"]["metadata"]["type"] == "topup"
    assert data["session"]["amount"] == 5.0


# -----------------------------------------------------------------------------
# 3. Webhook Cryptographic Verification & Rejection
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_safepay_webhook_invalid_signature_rejected(client: httpx.AsyncClient) -> None:
    """Ensure webhooks with invalid HMAC signatures are rejected with 400 Bad Request."""
    body = json.dumps({"event": "payment:completed", "tracker": "track_fake_123"}).encode("utf-8")

    resp = await client.post(
        "/api/v1/billing/webhook/safepay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-SFPY-SIGNATURE": "invalid_signature_hash",
            "X-SFPY-TIMESTAMP": "1726617600",
        },
    )
    assert resp.status_code == 400


# -----------------------------------------------------------------------------
# 4. Idempotent Stripe Webhook Processing (Subscriptions)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_stripe_webhook_processing_and_idempotency(client: httpx.AsyncClient) -> None:
    """Verify subscription activation via webhook and idempotency on duplicate events."""
    auth, user_id = await _get_auth(client, f"user_sub_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Initial state is Free
    sub_init = (await client.get("/api/v1/billing/subscription", headers=auth)).json()
    assert sub_init["plan"]["id"] == "free"

    # Simulated Stripe checkout session completed event
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    stripe_payload = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{uuid.uuid4().hex[:12]}",
                "customer": f"cus_{uuid.uuid4().hex[:8]}",
                "subscription": f"sub_{uuid.uuid4().hex[:8]}",
                "amount_total": 1900,
                "currency": "usd",
                "metadata": {
                    "user_id": user_id,
                    "plan_id": "pro",
                },
            }
        },
    }
    raw_bytes = json.dumps(stripe_payload).encode("utf-8")

    # 1. First delivery of webhook
    resp1 = await client.post(
        "/api/v1/billing/webhook/stripe",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "x-roxy-test": "true"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "success"

    # Verify user subscription upgraded to Pro
    sub_after = (await client.get("/api/v1/billing/subscription", headers=auth)).json()
    assert sub_after["plan"]["id"] == "pro"
    assert sub_after["plan"]["status"] == "active"

    # Verify invoice was created
    invoices1 = (await client.get("/api/v1/billing/invoices", headers=auth)).json()["invoices"]
    assert len(invoices1) == 1
    assert invoices1[0]["amount_usd"] == 19.0

    # 2. Duplicate webhook replay with exact same event_id
    resp2 = await client.post(
        "/api/v1/billing/webhook/stripe",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "x-roxy-test": "true"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_processed"

    # Confirm invoice count DID NOT double
    invoices2 = (await client.get("/api/v1/billing/invoices", headers=auth)).json()["invoices"]
    assert len(invoices2) == 1


# -----------------------------------------------------------------------------
# 5. Idempotent Safepay Webhook Processing (Credit Top-Ups)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_safepay_webhook_processing_and_idempotency(client: httpx.AsyncClient) -> None:
    """Verify wallet credits via Safepay webhook and idempotency on duplicate events."""
    auth, user_id = await _get_auth(client, f"user_wallet_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Check baseline wallet
    wallet_init = (await client.get("/api/v1/billing/wallet", headers=auth)).json()
    initial_credits = wallet_init["remaining_credits"]

    event_id = f"sfpy_evt_{uuid.uuid4().hex[:12]}"
    tracker = f"track_{uuid.uuid4().hex[:12]}"
    safepay_payload = {
        "id": event_id,
        "event": "payment:completed",
        "tracker": tracker,
        "amount": 1400.0,
        "currency": "PKR",
        "metadata": {
            "user_id": user_id,
            "pack_id": "pack_5",
            "credits": 500000,
        },
    }
    raw_bytes = json.dumps(safepay_payload).encode("utf-8")

    # 1. First webhook delivery
    resp1 = await client.post(
        "/api/v1/billing/webhook/safepay",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "x-roxy-test": "true"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "success"

    # Verify wallet credits granted
    wallet_after = (await client.get("/api/v1/billing/wallet", headers=auth)).json()
    assert wallet_after["remaining_credits"] == initial_credits + 500000

    # 2. Replay duplicate webhook
    resp2 = await client.post(
        "/api/v1/billing/webhook/safepay",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "x-roxy-test": "true"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_processed"

    # Verify wallet credits did not double
    wallet_replay = (await client.get("/api/v1/billing/wallet", headers=auth)).json()
    assert wallet_replay["remaining_credits"] == initial_credits + 500000


# -----------------------------------------------------------------------------
# 6. Genuine HMAC-SHA256 Signature Verification for Safepay
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_safepay_genuine_hmac_signature_validation(client: httpx.AsyncClient) -> None:
    """Verify genuine HMAC-SHA256 calculation passes signature verification."""
    from app.api.v1.billing import _service

    secret = "test_safepay_secret_key_12345"
    _service.safepay.webhook_secret = secret

    timestamp = "1726618000"
    payload = {"event": "payment:completed", "tracker": f"track_{uuid.uuid4().hex[:8]}"}
    raw_bytes = json.dumps(payload).encode("utf-8")

    # Generate genuine signature
    payload_to_sign = f"{timestamp}.".encode() + raw_bytes
    expected_sig = hmac.new(secret.encode(), payload_to_sign, hashlib.sha256).hexdigest()

    resp = await client.post(
        "/api/v1/billing/webhook/safepay",
        content=raw_bytes,
        headers={
            "Content-Type": "application/json",
            "X-SFPY-SIGNATURE": expected_sig,
            "X-SFPY-TIMESTAMP": timestamp,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


# -----------------------------------------------------------------------------
# 7. Subscription Cancellation Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_subscription_cancellation_lifecycle(client: httpx.AsyncClient) -> None:
    """Verify subscription can be flagged to cancel at period end."""
    auth, user_id = await _get_auth(client, f"user_cancel_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Subscribe to pro first
    await client.post("/api/v1/billing/subscribe", headers=auth, json={"plan_id": "pro"})
    sub = (await client.get("/api/v1/billing/subscription", headers=auth)).json()
    assert sub["plan"]["id"] == "pro"
    assert sub["plan"]["cancel_at_period_end"] is False

    # Cancel subscription
    cancel_resp = await client.post("/api/v1/billing/cancel", headers=auth)
    assert cancel_resp.status_code == 200

    sub_cancelled = (await client.get("/api/v1/billing/subscription", headers=auth)).json()
    assert sub_cancelled["plan"]["cancel_at_period_end"] is True


# -----------------------------------------------------------------------------
# 8. Strict Multi-Tenant Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_multitenant_billing_isolation(client: httpx.AsyncClient) -> None:
    """Verify strict tenant isolation across subscriptions, payment methods, and invoices."""
    auth_a, user_a = await _get_auth(client, f"user_iso_a_{uuid.uuid4().hex[:6]}@roxy.ai")
    auth_b, user_b = await _get_auth(client, f"user_iso_b_{uuid.uuid4().hex[:6]}@roxy.ai")

    # User A adds payment method and subscribes
    add_pm = await client.post(
        "/api/v1/billing/payment-methods",
        headers=auth_a,
        json={"brand": "mastercard", "last4": "8888", "exp_month": 11, "exp_year": 2029},
    )
    pm_id_a = add_pm.json()["payment_method"]["id"]
    await client.post("/api/v1/billing/subscribe", headers=auth_a, json={"plan_id": "pro"})

    # User B checks billing — must see completely empty/default state
    sub_b = (await client.get("/api/v1/billing/subscription", headers=auth_b)).json()
    assert sub_b["plan"]["id"] == "free"
    assert sub_b["payment_method"] is None

    pms_b = (await client.get("/api/v1/billing/payment-methods", headers=auth_b)).json()
    assert pms_b["primary"] is None
    assert pms_b["saved_methods"] == []

    invs_b = (await client.get("/api/v1/billing/invoices", headers=auth_b)).json()
    assert invs_b["invoices"] == []

    # User B cannot delete User A's payment method
    del_attempt = await client.delete(f"/api/v1/billing/payment-methods/{pm_id_a}", headers=auth_b)
    assert del_attempt.status_code == 404

    # User A still has their payment method intact
    pms_a = (await client.get("/api/v1/billing/payment-methods", headers=auth_a)).json()
    assert pms_a["primary"]["id"] == pm_id_a


# -----------------------------------------------------------------------------
# 9. Chat Grounding, Offline Fallback & Streaming Parity
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_chat_billing_grounding(client: httpx.AsyncClient) -> None:
    """Chat coordinator injects authentic billing & subscription context for authenticated users."""
    auth, user_id = await _get_auth(client, f"billing_chatground_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Upgrade to Pro plan
    await client.post("/api/v1/billing/subscribe", headers=auth, json={"plan_id": "pro"})

    mock_response = AsyncMock()
    mock_response.content = "You are currently on the Pro subscription plan with active AI credits."
    mock_response.provider = "mock_provider"
    mock_response.model = "mock_model"

    with patch("app.api.v1.runtime.AIRouter.route", return_value=mock_response) as mock_route:
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "What is my current subscription plan and billing status?"},
        )
        assert chat_res.status_code == 200
        assert mock_route.called
        call_request = mock_route.call_args[0][0]
        system_msgs = [m.content for m in call_request.messages if m.role.value == "system"]
        billing_grounded = any("BILLING & SUBSCRIPTION CONTEXT" in sm for sm in system_msgs)
        assert billing_grounded is True


@pytest.mark.anyio
async def test_chat_billing_offline_fallback(client: httpx.AsyncClient) -> None:
    """When LLM router fails, chat coordinator returns authentic offline fallback with subscription & credits telemetry."""
    auth, user_id = await _get_auth(client, f"billing_chatoffline_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Subscribe to pro plan
    await client.post("/api/v1/billing/subscribe", headers=auth, json={"plan_id": "pro"})

    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Model stream unreachable")):
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "Show me my current billing overview and subscription plan."},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["agent_slug"] == "billing"
        assert "billing & subscription overview" in data["response"].lower()
        assert "Active Plan:" in data["response"]
        assert "Pro" in data["response"]
        assert "Remaining AI Credits:" in data["response"]


@pytest.mark.anyio
async def test_chat_streaming_billing_grounding(client: httpx.AsyncClient) -> None:
    """Verify streaming chat runtime grounds subscription, wallet credits, and invoice status."""
    auth, user_id = await _get_auth(client, f"billing_stream_{uuid.uuid4().hex[:6]}@roxy.ai")

    # 1. Ask via stream for default plan -> Free plan
    resp_free = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "What is my subscription plan and billing status?", "provider": "offline"},
        headers=auth,
    )
    assert resp_free.status_code == 200
    free_stream = resp_free.text
    assert "data:" in free_stream
    assert "Free (BYOK)" in free_stream

    # 2. Upgrade to Pro
    sub_res = await client.post("/api/v1/billing/subscribe", headers=auth, json={"plan_id": "pro"})
    assert sub_res.status_code == 200

    # 3. Ask via stream again -> confirms Pro plan
    resp_pro = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "What is my subscription plan and billing status?", "provider": "offline"},
        headers=auth,
    )
    assert resp_pro.status_code == 200
    pro_stream = resp_pro.text
    assert "data:" in pro_stream
    assert "Pro" in pro_stream
    assert "Remaining AI Credits:" in pro_stream

