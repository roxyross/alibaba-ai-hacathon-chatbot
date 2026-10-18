"""Tests for NayaPay and SadaPay payment provider adapters and billing integration."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.billing.providers.nayapay_provider import NayaPayProvider
from app.billing.providers.sadapay_provider import SadaPayProvider
from app.billing.service import PaymentService


@pytest.fixture
def nayapay_provider() -> NayaPayProvider:
    return NayaPayProvider(
        client_id="np_client_test_123",
        secret_key="np_secret_test_456",
        merchant_id="np_merch_789",
        webhook_secret="np_webhook_sec_000",
        environment="sandbox",
    )


@pytest.fixture
def sadapay_provider() -> SadaPayProvider:
    return SadaPayProvider(
        api_key="sp_api_test_123",
        merchant_id="sp_merch_456",
        webhook_secret="sp_webhook_sec_789",
        environment="sandbox",
    )


def test_nayapay_configuration(nayapay_provider: NayaPayProvider) -> None:
    """Verify NayaPay configured properties."""
    assert nayapay_provider.is_configured() is True
    assert nayapay_provider.is_live_mode() is False
    assert nayapay_provider.name == "nayapay"


def test_sadapay_configuration(sadapay_provider: SadaPayProvider) -> None:
    """Verify SadaPay configured properties."""
    assert sadapay_provider.is_configured() is True
    assert sadapay_provider.is_live_mode() is False
    assert sadapay_provider.name == "sadapay"


@pytest.mark.asyncio
async def test_nayapay_checkout_session(nayapay_provider: NayaPayProvider) -> None:
    """Verify NayaPay PKR checkout session generation."""
    res = await nayapay_provider.create_checkout_session(
        user_id="user_123",
        email="test@example.com",
        plan_id="pro",
        amount=5700.0,
        currency="PKR",
        return_url="https://roxy.ai/billing?success=true",
        cancel_url="https://roxy.ai/billing?cancel=true",
    )
    assert res.provider == "nayapay"
    assert res.currency == "PKR"
    assert res.amount == 5700.0
    assert "pay" in res.checkout_url
    assert res.session_id.startswith("np_")


@pytest.mark.asyncio
async def test_sadapay_checkout_session(sadapay_provider: SadaPayProvider) -> None:
    """Verify SadaPay PKR checkout session generation."""
    res = await sadapay_provider.create_checkout_session(
        user_id="user_123",
        email="test@example.com",
        plan_id="pro",
        amount=5700.0,
        currency="PKR",
        return_url="https://roxy.ai/billing?success=true",
        cancel_url="https://roxy.ai/billing?cancel=true",
    )
    assert res.provider == "sadapay"
    assert res.currency == "PKR"
    assert res.amount == 5700.0
    assert "invoice" in res.checkout_url
    assert res.session_id.startswith("sp_")


def test_nayapay_webhook_signature_verification(nayapay_provider: NayaPayProvider) -> None:
    """Verify HMAC-SHA256 signature verification for NayaPay."""
    body = b'{"eventId":"ev_123","status":"success","orderAmount":5700}'
    valid_sig = hmac.new(b"np_webhook_sec_000", body, hashlib.sha256).hexdigest()

    assert nayapay_provider.verify_webhook_signature(
        {"x-nayapay-signature": valid_sig}, body
    ) is True
    assert nayapay_provider.verify_webhook_signature(
        {"x-nayapay-signature": "invalid_sig"}, body
    ) is False


def test_sadapay_webhook_signature_verification(sadapay_provider: SadaPayProvider) -> None:
    """Verify HMAC-SHA256 signature verification for SadaPay."""
    body = b'{"invoiceId":"sp_123","status":"paid","amount":5700}'
    valid_sig = hmac.new(b"sp_webhook_sec_789", body, hashlib.sha256).hexdigest()

    assert sadapay_provider.verify_webhook_signature(
        {"x-sadapay-signature": valid_sig}, body
    ) is True
    assert sadapay_provider.verify_webhook_signature(
        {"x-sadapay-signature": "invalid_sig"}, body
    ) is False


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


def test_payment_service_resolution() -> None:
    """Verify PaymentService resolves nayapay and sadapay."""
    service = PaymentService.get_instance()
    prov_np = service.get_provider("nayapay")
    assert prov_np.name == "nayapay"

    prov_sp = service.get_provider("sadapay")
    assert prov_sp.name == "sadapay"
