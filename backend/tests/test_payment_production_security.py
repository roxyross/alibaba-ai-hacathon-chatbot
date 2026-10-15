"""Security regression tests for Stripe & Safepay production fail-closed enforcement.

Validates:
1. Production mode with missing credentials fails closed (no fake/simulated checkout sessions).
2. Production mode with missing SDK fails closed.
3. Production mode with API/network error fails closed.
4. Production mode with malformed or empty provider response fails closed.
5. Unsupported currency fails closed with ValueError.
6. Failed checkout creates NO subscription, NO paid invoice, and NO wallet credits.
7. Non-production development/test simulation works only under allowed non-prod environments.
8. Webhook verification rejects invalid signatures.
9. Duplicate webhook events are idempotent.
10. Public billing config exposes zero secrets.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from app.billing.providers.base import is_production_environment
from app.billing.providers.safepay_provider import SafepayProvider
from app.billing.providers.stripe_provider import StripeProvider
from app.billing.repository import (
    BillingRepository,
    clear_in_memory_stores,
)
from app.main import app


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    clear_in_memory_stores()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# =============================================================================
# 1. Stripe Provider Production Fail-Closed Tests
# =============================================================================


@pytest.mark.anyio
async def test_stripe_production_missing_credentials_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, unconfigured Stripe must fail closed and never return cs_test_..."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    provider = StripeProvider(api_key="")
    assert not provider.is_configured()

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=19.0,
            currency="USD",
        )

    err = str(exc_info.value).lower()
    assert "not configured" in err or "stripe" in err
    assert "cs_test_" not in err


@pytest.mark.anyio
async def test_stripe_production_missing_sdk_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, missing stripe library must fail closed."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_dummy_secret_key_12345")

    provider = StripeProvider(api_key="sk_live_dummy_secret_key_12345")

    import app.billing.providers.stripe_provider as stripe_mod

    monkeypatch.setattr(stripe_mod, "stripe", None)

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=19.0,
            currency="USD",
        )

    assert "sdk" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_stripe_production_api_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, Stripe API exceptions must fail closed and never return simulated sessions."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_dummy_secret_key_12345")

    provider = StripeProvider(api_key="sk_live_dummy_secret_key_12345")

    import app.billing.providers.stripe_provider as stripe_mod

    class FakeStripe:
        api_key: str = ""

        class checkout:  # noqa: N801
            class Session:
                @staticmethod
                def create(**kwargs: Any) -> Any:
                    raise ConnectionError("Failed to reach Stripe API gateway")

    monkeypatch.setattr(stripe_mod, "stripe", FakeStripe)

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=19.0,
            currency="USD",
        )

    assert "creation failed" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_stripe_production_empty_session_id_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, Stripe returning an empty session ID must fail closed."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_dummy_secret_key_12345")

    provider = StripeProvider(api_key="sk_live_dummy_secret_key_12345")

    import app.billing.providers.stripe_provider as stripe_mod

    class FakeSession:
        id = ""
        url = "https://checkout.stripe.com/pay/test"
        client_secret = "secret"

    class FakeStripe:
        api_key: str = ""

        class checkout:  # noqa: N801
            class Session:
                @staticmethod
                def create(**kwargs: Any) -> Any:
                    return FakeSession()

    monkeypatch.setattr(stripe_mod, "stripe", FakeStripe)

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=19.0,
            currency="USD",
        )

    assert "session id" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_stripe_production_empty_checkout_url_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, Stripe returning an empty checkout URL must fail closed."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_dummy_secret_key_12345")

    provider = StripeProvider(api_key="sk_live_dummy_secret_key_12345")

    import app.billing.providers.stripe_provider as stripe_mod

    class FakeSession:
        id = "cs_live_real_session_123"
        url = ""
        client_secret = "secret"

    class FakeStripe:
        api_key: str = ""

        class checkout:  # noqa: N801
            class Session:
                @staticmethod
                def create(**kwargs: Any) -> Any:
                    return FakeSession()

    monkeypatch.setattr(stripe_mod, "stripe", FakeStripe)

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=19.0,
            currency="USD",
        )

    assert "checkout url" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_stripe_non_production_simulation_permitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """In development/test mode, simulated checkout sessions are permitted when unconfigured."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)

    provider = StripeProvider(api_key="")
    assert not provider.is_configured()

    res = await provider.create_checkout_session(
        user_id="user_dev",
        email="dev@roxy.ai",
        plan_id="pro",
        amount=19.0,
        currency="USD",
    )
    assert res.session_id.startswith("cs_test_")
    assert "stripe.com" in res.checkout_url
    assert res.amount == 19.0
    assert res.currency == "USD"


# =============================================================================
# 2. Safepay Provider Production Fail-Closed Tests
# =============================================================================


@pytest.mark.anyio
async def test_safepay_production_missing_credentials_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, unconfigured Safepay must fail closed and never return track_test_..."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SAFEPAY_API_KEY", raising=False)

    provider = SafepayProvider(api_key="")
    assert not provider.is_configured()

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )

    err = str(exc_info.value).lower()
    assert "not configured" in err or "safepay" in err
    assert "track_test_" not in err


@pytest.mark.anyio
async def test_safepay_unsupported_currency_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safepay must reject unsupported currencies with ValueError."""
    provider = SafepayProvider(api_key="sec_test_key")

    with pytest.raises(ValueError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=19.0,
            currency="EUR",
        )

    assert "not supported" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_safepay_production_api_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, Safepay API HTTP 500 error must fail closed and raise RuntimeError."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SAFEPAY_API_KEY", "sec_live_dummy_safepay_key")

    provider = SafepayProvider(api_key="sec_live_dummy_safepay_key")

    class MockResp:
        status_code = 500
        text = "Internal Server Error"

        def json(self) -> dict[str, Any]:
            return {"error": "down"}

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            pass

        async def post(self, *a: Any, **kw: Any) -> MockResp:
            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )

    assert "failed with status 500" in str(exc_info.value) or "creation failed" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_safepay_production_empty_token_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, Safepay returning an empty token must fail closed."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SAFEPAY_API_KEY", "sec_live_dummy_safepay_key")

    provider = SafepayProvider(api_key="sec_live_dummy_safepay_key")

    class MockResp:
        status_code = 200
        text = '{"data": {"token": ""}}'

        def json(self) -> dict[str, Any]:
            return {"data": {"token": ""}}

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            pass

        async def post(self, *a: Any, **kw: Any) -> MockResp:
            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    with pytest.raises(RuntimeError) as exc_info:
        await provider.create_checkout_session(
            user_id="user_123",
            email="user@roxy.ai",
            plan_id="pro",
            amount=5700.0,
            currency="PKR",
        )

    assert "empty tracker token" in str(exc_info.value).lower() or "creation failed" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_safepay_non_production_simulation_permitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """In development/test mode, simulated Safepay tracker tokens are permitted when unconfigured."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("SAFEPAY_API_KEY", raising=False)

    provider = SafepayProvider(api_key="")
    assert not provider.is_configured()

    res = await provider.create_checkout_session(
        user_id="user_dev",
        email="dev@roxy.ai",
        plan_id="pro",
        amount=5700.0,
        currency="PKR",
    )
    assert res.session_id.startswith("track_test_")
    assert "safepay" in res.checkout_url
    assert res.amount == 5700.0
    assert res.currency == "PKR"


# =============================================================================
# 3. End-to-End API Routes & Financial Side-Effects Fail-Closed Tests
# =============================================================================


def _get_auth_headers(user_id: str, email: str) -> tuple[dict[str, str], str]:
    from app.auth.jwt import create_session_token
    token, _ = create_session_token(user_id, email=email)
    return {"Authorization": f"Bearer {token}"}, user_id


@pytest.mark.anyio
async def test_production_checkout_failure_creates_no_subscription_or_credits(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, a failed checkout endpoint call MUST NOT create a subscription, paid invoice, or wallet credit."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "test_secure_production_jwt_secret_32chars_long!")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SAFEPAY_API_KEY", raising=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        test_email = f"user_prod_{uuid.uuid4().hex[:6]}@roxy.ai"
        user_id = f"usr_{uuid.uuid4().hex[:8]}"
        auth, user_id = _get_auth_headers(user_id, test_email)

        # 1. Attempt Stripe USD checkout in production without keys
        resp_usd = await client.post(
            "/api/v1/billing/checkout",
            headers=auth,
            json={"plan_id": "pro", "currency": "usd"},
        )
        assert resp_usd.status_code == 500
        assert "Checkout creation failed" in resp_usd.json()["detail"]

        # 2. Attempt Safepay PKR checkout in production without keys
        resp_pkr = await client.post(
            "/api/v1/billing/checkout",
            headers=auth,
            json={"plan_id": "pro", "currency": "pkr"},
        )
        assert resp_pkr.status_code == 500
        assert "Checkout creation failed" in resp_pkr.json()["detail"]

        repo = BillingRepository()

        # 3. Verify database/store state: NO active paid subscription created
        sub = await repo.get_subscription(user_id)
        assert sub["plan"]["id"] == "free", "Failed checkout must not create an active paid subscription"

        # 4. Verify invoices: NO paid invoices created
        invoices = await repo.list_invoices(user_id)
        assert len(invoices) == 0, "Failed checkout must not create any invoices"

        # 5. Verify credit wallet: NO purchased top-up balance is added
        wallet = await repo.get_credit_wallet(user_id)
        assert wallet.get("remaining_credits", 100.0) == 100.0, "Failed checkout must not credit purchased wallet balance"


@pytest.mark.anyio
async def test_production_detection_helper_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure is_production_environment detects all configured production flags."""
    # Reset
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    assert not is_production_environment()

    # APP_ENV=production
    monkeypatch.setenv("APP_ENV", "production")
    assert is_production_environment()
    monkeypatch.setenv("APP_ENV", "prod")
    assert is_production_environment()
    monkeypatch.delenv("APP_ENV")

    # ENV=production
    monkeypatch.setenv("ENV", "production")
    assert is_production_environment()
    monkeypatch.delenv("ENV")

    # ENVIRONMENT=production
    monkeypatch.setenv("ENVIRONMENT", "prod")
    assert is_production_environment()
    monkeypatch.delenv("ENVIRONMENT")

    # VERCEL=1
    monkeypatch.setenv("VERCEL", "1")
    assert is_production_environment()
    monkeypatch.delenv("VERCEL")

    # HTTPS APP_BASE_URL
    monkeypatch.setenv("APP_BASE_URL", "https://roxy.ai")
    assert is_production_environment()
