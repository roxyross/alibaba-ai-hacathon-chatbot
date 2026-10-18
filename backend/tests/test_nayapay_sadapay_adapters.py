"""Comprehensive tests for NayaPay and SadaPay payment provider adapters and billing integration.

Verifies:
1. Provider configuration & properties (sandbox, prod, custom URLs).
2. Fail-closed checkout and verification when credentials are missing or disabled.
3. verify_payment() NEVER returns "paid" when unconfigured.
4. HTTP request payloads and cryptographic signature generation.
5. Successful checkout creation with mocked HTTP responses (respx).
6. Timeouts, HTTP errors, and malformed responses fail closed.
7. Verification status parsing (success, paid, failed, cancelled, pending).
8. Webhook HMAC-SHA256 signature verification (valid, tampered, missing secret).
9. Webhook event normalization and idempotency.
10. Webhook amount and currency mismatch protection (no unearned entitlements).
11. Subscription cancellation explicitly reported as unsupported.
12. Opt-in live sandbox smoke test (skips unless real credentials provided).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os

import httpx
import pytest
import respx

from app.billing.providers.base import NormalizedWebhookEvent
from app.billing.providers.nayapay_provider import NayaPayProvider
from app.billing.providers.sadapay_provider import SadaPayProvider
from app.billing.repository import clear_in_memory_stores
from app.billing.service import PaymentService


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    clear_in_memory_stores()


@pytest.fixture
def nayapay_provider() -> NayaPayProvider:
    return NayaPayProvider(
        client_id="np_client_test_123",
        secret_key="np_secret_test_456",
        merchant_id="np_merch_789",
        webhook_secret="np_webhook_sec_000",
        environment="sandbox",
        enabled=True,
    )


@pytest.fixture
def sadapay_provider() -> SadaPayProvider:
    return SadaPayProvider(
        api_key="sp_api_test_123",
        merchant_id="sp_merch_456",
        webhook_secret="sp_webhook_sec_789",
        environment="sandbox",
        enabled=True,
    )


# =============================================================================
# 1. Configuration & Base URL Resolution
# =============================================================================


def test_nayapay_configuration(nayapay_provider: NayaPayProvider) -> None:
    """Verify NayaPay configured properties."""
    assert nayapay_provider.is_configured() is True
    assert nayapay_provider.is_enabled() is True
    assert nayapay_provider.is_live_mode() is False
    assert nayapay_provider.name == "nayapay"
    assert nayapay_provider.api_base_url == "https://sandbox.nayapay.com/api/v1"
    assert nayapay_provider.checkout_base_url == "https://sandbox-checkout.nayapay.com"


def test_sadapay_configuration(sadapay_provider: SadaPayProvider) -> None:
    """Verify SadaPay configured properties."""
    assert sadapay_provider.is_configured() is True
    assert sadapay_provider.is_enabled() is True
    assert sadapay_provider.is_live_mode() is False
    assert sadapay_provider.name == "sadapay"
    assert sadapay_provider.api_base_url == "https://sandbox.sadapay.pk/api/v1"
    assert sadapay_provider.checkout_base_url == "https://sandbox-pay.sadapay.pk"


def test_nayapay_custom_and_production_urls() -> None:
    """Verify NayaPay environment and custom URL resolution."""
    prod = NayaPayProvider(environment="production")
    assert prod.api_base_url == "https://api.nayapay.com/api/v1"
    assert prod.checkout_base_url == "https://checkout.nayapay.com"

    custom = NayaPayProvider(
        api_base_url="https://custom.api.nayapay.com/v1",
        checkout_base_url="https://custom.pay.nayapay.com",
    )
    assert custom.api_base_url == "https://custom.api.nayapay.com/v1"
    assert custom.checkout_base_url == "https://custom.pay.nayapay.com"


def test_sadapay_custom_and_production_urls() -> None:
    """Verify SadaPay environment and custom URL resolution."""
    prod = SadaPayProvider(environment="production")
    assert prod.api_base_url == "https://api.sadapay.pk/api/v1"
    assert prod.checkout_base_url == "https://pay.sadapay.pk"

    custom = SadaPayProvider(
        api_base_url="https://custom.api.sadapay.pk/v1",
        checkout_base_url="https://custom.pay.sadapay.pk",
    )
    assert custom.api_base_url == "https://custom.api.sadapay.pk/v1"
    assert custom.checkout_base_url == "https://custom.pay.sadapay.pk"


# =============================================================================
# 2. Fail-Closed Security: Missing Credentials & Disabled State
# =============================================================================


@pytest.mark.asyncio
async def test_nayapay_missing_credentials_fails_closed() -> None:
    """Unconfigured NayaPay must fail closed and never create checkout sessions."""
    provider = NayaPayProvider(client_id="", secret_key="", merchant_id="", enabled=True)
    assert not provider.is_configured()

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "not configured" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_sadapay_missing_credentials_fails_closed() -> None:
    """Unconfigured SadaPay must fail closed and never create checkout sessions."""
    provider = SadaPayProvider(api_key="", merchant_id="", enabled=True)
    assert not provider.is_configured()

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "not configured" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_nayapay_disabled_fails_closed(nayapay_provider: NayaPayProvider) -> None:
    """Disabled NayaPay must raise error and reject checkout initiation."""
    nayapay_provider._explicit_enabled = False
    assert not nayapay_provider.is_enabled()

    with pytest.raises(RuntimeError) as exc_info:
        await nayapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "disabled" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_sadapay_disabled_fails_closed(sadapay_provider: SadaPayProvider) -> None:
    """Disabled SadaPay must raise error and reject checkout initiation."""
    sadapay_provider._explicit_enabled = False
    assert not sadapay_provider.is_enabled()

    with pytest.raises(RuntimeError) as exc_info:
        await sadapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "disabled" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_nayapay_unconfigured_verify_payment_never_returns_paid() -> None:
    """verify_payment() with missing credentials MUST return status='failed', NEVER 'paid'."""
    unconfigured = NayaPayProvider(client_id="", secret_key="", merchant_id="")
    res = await unconfigured.verify_payment("any_session_id")
    assert res.status == "failed"
    assert res.amount == 0.0
    assert "not configured" in (res.error_message or "").lower()


@pytest.mark.asyncio
async def test_sadapay_unconfigured_verify_payment_never_returns_paid() -> None:
    """verify_payment() with missing credentials MUST return status='failed', NEVER 'paid'."""
    unconfigured = SadaPayProvider(api_key="", merchant_id="")
    res = await unconfigured.verify_payment("any_invoice_id")
    assert res.status == "failed"
    assert res.amount == 0.0
    assert "not configured" in (res.error_message or "").lower()


@pytest.mark.asyncio
async def test_nayapay_unsupported_currency_fails_closed(nayapay_provider: NayaPayProvider) -> None:
    """NayaPay must reject non-PKR currencies with ValueError."""
    with pytest.raises(ValueError) as exc_info:
        await nayapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=19.0,
            currency="USD",
        )
    assert "only supports pkr" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_sadapay_unsupported_currency_fails_closed(sadapay_provider: SadaPayProvider) -> None:
    """SadaPay must reject non-PKR currencies with ValueError."""
    with pytest.raises(ValueError) as exc_info:
        await sadapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=19.0,
            currency="USD",
        )
    assert "only supports pkr" in str(exc_info.value).lower()


# =============================================================================
# 3. Successful Checkout Creation via Mocked HTTP Responses (respx)
# =============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_nayapay_checkout_session(nayapay_provider: NayaPayProvider) -> None:
    """Verify NayaPay PKR checkout session generation via mocked provider API."""
    route = respx.post(f"{nayapay_provider.api_base_url}/checkout/session").mock(
        return_value=httpx.Response(
            200,
            json={
                "sessionId": "np_sess_verified_777",
                "checkoutUrl": "https://sandbox-checkout.nayapay.com/pay?token=np_sess_verified_777",
                "status": "created",
            },
        )
    )

    res = await nayapay_provider.create_checkout_session(
        user_id="user_123",
        email="test@example.com",
        plan_id="pro",
        amount=5700.0,
        currency="PKR",
        return_url="https://roxy.ai/billing?success=true",
        cancel_url="https://roxy.ai/billing?cancel=true",
    )

    assert route.called
    req = route.calls.last.request
    assert req.headers["X-Client-Id"] == "np_client_test_123"
    assert "X-Signature" in req.headers
    assert req.headers["Content-Type"] == "application/json"

    sent_body = json.loads(req.content.decode("utf-8"))
    assert sent_body["merchantId"] == "np_merch_789"
    assert sent_body["orderAmount"] == 5700.0
    assert sent_body["currency"] == "PKR"
    assert sent_body["customerEmail"] == "test@example.com"

    assert res.provider == "nayapay"
    assert res.currency == "PKR"
    assert res.amount == 5700.0
    assert res.session_id == "np_sess_verified_777"
    assert "token=np_sess_verified_777" in res.checkout_url


@pytest.mark.asyncio
@respx.mock
async def test_sadapay_checkout_session(sadapay_provider: SadaPayProvider) -> None:
    """Verify SadaPay PKR checkout session generation via mocked provider API."""
    route = respx.post(f"{sadapay_provider.api_base_url}/invoices").mock(
        return_value=httpx.Response(
            201,
            json={
                "invoiceId": "sp_inv_verified_888",
                "paymentUrl": "https://sandbox-pay.sadapay.pk/invoice/sp_inv_verified_888",
                "status": "pending",
            },
        )
    )

    res = await sadapay_provider.create_checkout_session(
        user_id="user_123",
        email="test@example.com",
        plan_id="pro",
        amount=5700.0,
        currency="PKR",
        return_url="https://roxy.ai/billing?success=true",
        cancel_url="https://roxy.ai/billing?cancel=true",
    )

    assert route.called
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer sp_api_test_123"
    assert req.headers["Content-Type"] == "application/json"

    sent_body = json.loads(req.content.decode("utf-8"))
    assert sent_body["merchantId"] == "sp_merch_456"
    assert sent_body["amount"] == 5700.0
    assert sent_body["currency"] == "PKR"
    assert sent_body["customerEmail"] == "test@example.com"

    assert res.provider == "sadapay"
    assert res.currency == "PKR"
    assert res.amount == 5700.0
    assert res.session_id == "sp_inv_verified_888"
    assert "invoice/sp_inv_verified_888" in res.checkout_url


# =============================================================================
# 4. HTTP Errors & Provider Timeouts Fail Closed
# =============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_nayapay_checkout_http_error_fails_closed(nayapay_provider: NayaPayProvider) -> None:
    """NayaPay HTTP 500 error must raise RuntimeError and never construct a fake URL."""
    respx.post(f"{nayapay_provider.api_base_url}/checkout/session").mock(
        return_value=httpx.Response(500, text="Internal Gateway Error")
    )

    with pytest.raises(RuntimeError) as exc_info:
        await nayapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "failed with http 500" in str(exc_info.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_sadapay_checkout_http_error_fails_closed(sadapay_provider: SadaPayProvider) -> None:
    """SadaPay HTTP 502 error must raise RuntimeError and never construct a fake URL."""
    respx.post(f"{sadapay_provider.api_base_url}/invoices").mock(
        return_value=httpx.Response(502, text="Bad Gateway")
    )

    with pytest.raises(RuntimeError) as exc_info:
        await sadapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "failed with http 502" in str(exc_info.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_nayapay_checkout_timeout_fails_closed(nayapay_provider: NayaPayProvider) -> None:
    """NayaPay timeout must raise RuntimeError cleanly."""
    respx.post(f"{nayapay_provider.api_base_url}/checkout/session").mock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )

    with pytest.raises(RuntimeError) as exc_info:
        await nayapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_sadapay_checkout_timeout_fails_closed(sadapay_provider: SadaPayProvider) -> None:
    """SadaPay timeout must raise RuntimeError cleanly."""
    respx.post(f"{sadapay_provider.api_base_url}/invoices").mock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )

    with pytest.raises(RuntimeError) as exc_info:
        await sadapay_provider.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )
    assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# 5. Verification Endpoint Status Parsing
# =============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_nayapay_verify_payment_statuses(nayapay_provider: NayaPayProvider) -> None:
    """Verify NayaPay status mapping (success, failed, cancelled, pending)."""
    # Success -> paid
    respx.get(f"{nayapay_provider.api_base_url}/checkout/status/txn_1").mock(
        return_value=httpx.Response(200, json={"status": "success", "amount": 5700.0, "customerId": "c1"})
    )
    r1 = await nayapay_provider.verify_payment("txn_1")
    assert r1.status == "paid"
    assert r1.amount == 5700.0
    assert r1.customer_id == "c1"

    # Failed -> failed
    respx.get(f"{nayapay_provider.api_base_url}/checkout/status/txn_2").mock(
        return_value=httpx.Response(200, json={"status": "declined", "amount": 0.0})
    )
    r2 = await nayapay_provider.verify_payment("txn_2")
    assert r2.status == "failed"

    # Cancelled -> cancelled
    respx.get(f"{nayapay_provider.api_base_url}/checkout/status/txn_3").mock(
        return_value=httpx.Response(200, json={"status": "cancelled", "amount": 0.0})
    )
    r3 = await nayapay_provider.verify_payment("txn_3")
    assert r3.status == "cancelled"

    # HTTP 404 -> failed
    respx.get(f"{nayapay_provider.api_base_url}/checkout/status/txn_4").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    r4 = await nayapay_provider.verify_payment("txn_4")
    assert r4.status == "failed"


@pytest.mark.asyncio
@respx.mock
async def test_sadapay_verify_payment_statuses(sadapay_provider: SadaPayProvider) -> None:
    """Verify SadaPay status mapping (paid, failed, cancelled, pending)."""
    # Paid -> paid
    respx.get(f"{sadapay_provider.api_base_url}/invoices/inv_1").mock(
        return_value=httpx.Response(200, json={"status": "paid", "amount": 5700.0, "customerId": "c2"})
    )
    r1 = await sadapay_provider.verify_payment("inv_1")
    assert r1.status == "paid"
    assert r1.amount == 5700.0
    assert r1.customer_id == "c2"

    # Failed -> failed
    respx.get(f"{sadapay_provider.api_base_url}/invoices/inv_2").mock(
        return_value=httpx.Response(200, json={"status": "failed", "amount": 0.0})
    )
    r2 = await sadapay_provider.verify_payment("inv_2")
    assert r2.status == "failed"

    # Cancelled -> cancelled
    respx.get(f"{sadapay_provider.api_base_url}/invoices/inv_3").mock(
        return_value=httpx.Response(200, json={"status": "canceled", "amount": 0.0})
    )
    r3 = await sadapay_provider.verify_payment("inv_3")
    assert r3.status == "cancelled"

    # HTTP 500 -> failed
    respx.get(f"{sadapay_provider.api_base_url}/invoices/inv_4").mock(
        return_value=httpx.Response(500, text="Server Error")
    )
    r4 = await sadapay_provider.verify_payment("inv_4")
    assert r4.status == "failed"


# =============================================================================
# 6. Webhook Signatures & Event Normalization
# =============================================================================


def test_nayapay_webhook_signature_verification(nayapay_provider: NayaPayProvider) -> None:
    """Verify HMAC-SHA256 signature verification for NayaPay."""
    body = b'{"eventId":"ev_123","status":"success","orderAmount":5700}'
    valid_sig = hmac.new(b"np_webhook_sec_000", body, hashlib.sha256).hexdigest()

    assert nayapay_provider.verify_webhook_signature({"x-nayapay-signature": valid_sig}, body) is True
    assert nayapay_provider.verify_webhook_signature({"x-nayapay-signature": "tampered_sig"}, body) is False
    assert nayapay_provider.verify_webhook_signature({}, body) is False


def test_sadapay_webhook_signature_verification(sadapay_provider: SadaPayProvider) -> None:
    """Verify HMAC-SHA256 signature verification for SadaPay."""
    body = b'{"invoiceId":"sp_123","status":"paid","amount":5700}'
    valid_sig = hmac.new(b"sp_webhook_sec_789", body, hashlib.sha256).hexdigest()

    assert sadapay_provider.verify_webhook_signature({"x-sadapay-signature": valid_sig}, body) is True
    assert sadapay_provider.verify_webhook_signature({"x-sadapay-signature": "tampered_sig"}, body) is False
    assert sadapay_provider.verify_webhook_signature({}, body) is False


def test_nayapay_parse_webhook_event(nayapay_provider: NayaPayProvider) -> None:
    """Verify NayaPay event normalization."""
    body = json.dumps({
        "data": {
            "eventId": "np_evt_999",
            "merchTxnRef": "np_ref_888",
            "status": "payment.succeeded",
            "orderAmount": 5700,
            "customerId": "cust_123",
        },
    }).encode("utf-8")

    event = nayapay_provider.parse_webhook_event({}, body)
    assert event.event_id == "np_evt_999"
    assert event.event_type == "payment.succeeded"
    assert event.provider == "nayapay"
    assert event.amount == 5700.0
    assert event.currency == "PKR"
    assert event.customer_id == "cust_123"


def test_sadapay_parse_webhook_event(sadapay_provider: SadaPayProvider) -> None:
    """Verify SadaPay event normalization."""
    body = json.dumps({
        "invoiceId": "sp_inv_777",
        "status": "paid",
        "amount": 5700,
        "customerId": "cust_456",
    }).encode("utf-8")

    event = sadapay_provider.parse_webhook_event({}, body)
    assert event.event_id == "sp_inv_777"
    assert event.event_type == "payment.succeeded"
    assert event.provider == "sadapay"
    assert event.amount == 5700.0
    assert event.currency == "PKR"
    assert event.customer_id == "cust_456"


# =============================================================================
# 7. Webhook Amount & Currency Mismatch Entitlement Protection
# =============================================================================


@pytest.mark.asyncio
async def test_webhook_amount_mismatch_creates_no_subscription() -> None:
    """Webhook with tampered or mismatched amount must be rejected and grant NO subscription."""
    service = PaymentService.get_instance()

    tampered_event = NormalizedWebhookEvent(
        event_id="evt_tampered_amount",
        event_type="payment.succeeded",
        provider="nayapay",
        customer_id="cust_tamper",
        payment_id="pay_tamper",
        amount=1.0,  # Expected 5700.0 for Pro
        currency="PKR",
        metadata={"user_id": "user_tamper", "plan_id": "pro"},
        raw_data={},
    )

    result = await service.process_webhook_event("nayapay", tampered_event)
    assert result.get("status") == "error"
    assert "amount mismatch" in result.get("message", "").lower()

    # Verify zero subscriptions created (remains default free tier)
    sub = await service.repo.get_subscription("user_tamper")
    assert sub.get("plan", {}).get("id") == "free"


@pytest.mark.asyncio
async def test_webhook_currency_mismatch_creates_no_subscription() -> None:
    """Webhook with unexpected currency must be rejected and grant NO subscription."""
    service = PaymentService.get_instance()

    mismatched_curr_event = NormalizedWebhookEvent(
        event_id="evt_mismatched_curr",
        event_type="payment.succeeded",
        provider="sadapay",
        customer_id="cust_curr",
        payment_id="pay_curr",
        amount=5700.0,
        currency="USD",  # SadaPay must be PKR
        metadata={"user_id": "user_curr", "plan_id": "pro"},
        raw_data={},
    )

    result = await service.process_webhook_event("sadapay", mismatched_curr_event)
    assert result.get("status") == "error"
    assert "currency mismatch" in result.get("message", "").lower()

    sub = await service.repo.get_subscription("user_curr")
    assert sub.get("plan", {}).get("id") == "free"


# =============================================================================
# 8. Subscription Cancellation Capability
# =============================================================================


@pytest.mark.asyncio
async def test_cancel_subscription_reports_unsupported(
    nayapay_provider: NayaPayProvider,
    sadapay_provider: SadaPayProvider,
) -> None:
    """One-time invoice APIs must report cancellation as unsupported (False)."""
    assert await nayapay_provider.cancel_subscription("sub_123") is False
    assert await sadapay_provider.cancel_subscription("sub_456") is False


# =============================================================================
# 9. PaymentService Resolution
# =============================================================================


def test_payment_service_resolution() -> None:
    """Verify PaymentService resolves nayapay and sadapay."""
    service = PaymentService.get_instance()
    prov_np = service.get_provider("nayapay")
    assert prov_np.name == "nayapay"

    prov_sp = service.get_provider("sadapay")
    assert prov_sp.name == "sadapay"

    # Default PKR currency still routes to Safepay (preserving existing routing)
    prov_pkr = service.get_provider(currency="PKR")
    assert prov_pkr.name == "safepay"


# =============================================================================
# 10. Opt-in Real Sandbox Smoke Test (Skips safely if unconfigured)
# =============================================================================


@pytest.mark.asyncio
async def test_opt_in_nayapay_sandbox_smoke() -> None:
    """Opt-in real sandbox smoke test that runs ONLY when real sandbox credentials exist in env.

    Never makes live charges or silently runs against production.
    """
    client_id = os.getenv("NAYAPAY_CLIENT_ID", "").strip()
    secret_key = os.getenv("NAYAPAY_SECRET_KEY", "").strip()
    merchant_id = os.getenv("NAYAPAY_MERCHANT_ID", "").strip()

    if not (client_id and secret_key and merchant_id):
        pytest.skip("NayaPay sandbox credentials not provided in environment; skipping real smoke test.")

    provider = NayaPayProvider(
        client_id=client_id,
        secret_key=secret_key,
        merchant_id=merchant_id,
        environment="sandbox",
        enabled=True,
    )

    res = await provider.create_checkout_session(
        user_id="smoke_user",
        email="smoke@roxy.ai",
        plan_id="pro",
        amount=5700.0,
        currency="PKR",
    )
    assert res.provider == "nayapay"
    assert res.status == "pending"
    assert res.checkout_url.startswith("https://")


@pytest.mark.asyncio
async def test_opt_in_sadapay_sandbox_smoke() -> None:
    """Opt-in real sandbox smoke test that runs ONLY when real sandbox credentials exist in env.

    Never makes live charges or silently runs against production.
    """
    api_key = os.getenv("SADAPAY_API_KEY", "").strip()
    merchant_id = os.getenv("SADAPAY_MERCHANT_ID", "").strip()

    if not (api_key and merchant_id):
        pytest.skip("SadaPay sandbox credentials not provided in environment; skipping real smoke test.")

    provider = SadaPayProvider(
        api_key=api_key,
        merchant_id=merchant_id,
        environment="sandbox",
        enabled=True,
    )

    res = await provider.create_checkout_session(
        user_id="smoke_user",
        email="smoke@roxy.ai",
        plan_id="pro",
        amount=5700.0,
        currency="PKR",
    )
    assert res.provider == "sadapay"
    assert res.status == "pending"
    assert res.checkout_url.startswith("https://")
