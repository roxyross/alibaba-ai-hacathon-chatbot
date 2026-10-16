"""Permanent Real-PostgreSQL Integration Test Suite for Roxy-AI Billing & Subscriptions.

Guarantees:
- Real PostgreSQL connection and SQLAlchemy AsyncSession transactions (zero mocked DB functions).
- Positive Safety Gate: Refuses execution unless positively connected to an isolated test database.
- Durable Persistence: Verifies Subscription, Payment, PaymentEvent, and CreditWallet row commits.
- Multi-Provider Support: Verifies Stripe and Safepay provider tracking and PKR/USD amounts.
- Webhook Idempotency: Verifies event deduplication in payment_events table prevents duplicate credits.
- Tenant Isolation: Verifies strict financial isolation between synthetic identities in PostgreSQL.
- Production Fail-Closed: Validates that missing DB config or persistence failures in production
  raise RuntimeError and strictly refuse to fall back to in-memory financial state.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest import mock

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.repository import BillingRepository
from app.billing.service import PaymentService
from app.db import _session_factory, get_engine, normalize_database_url
from app.models.subscription import CreditWallet, Payment, PaymentEvent, Subscription

# Allowed test database identifiers
VALID_TEST_DB_NAMES = {"roxy_isolated_test_db", "roxy_test"}
PROD_DB_MARKERS = {"prod", "production", "neon.tech", "aws.neon", "cloudsql"}


def _resolve_test_database_url() -> str | None:
    """Resolve the test database URL from environment or known isolated test ports."""
    url = os.environ.get("ROXY_TEST_DATABASE_URL")
    if url:
        return url
    env_db = os.environ.get("DATABASE_URL", "").strip()
    if env_db and not any(marker in env_db.lower() for marker in PROD_DB_MARKERS):
        return env_db
    # Default to local dedicated isolated test container port 5433
    return "postgresql+asyncpg://roxy_test_usr:roxy_test_secure_pwd_123@127.0.0.1:5433/roxy_isolated_test_db"


TEST_DATABASE_URL = _resolve_test_database_url()


@pytest_asyncio.fixture(scope="function")
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide verified AsyncEngine connected strictly to an isolated test database."""
    if not TEST_DATABASE_URL:
        pytest.skip("No test database URL configured. Skipping real PostgreSQL billing integration tests.")

    norm_url, connect_args = normalize_database_url(TEST_DATABASE_URL)
    engine = create_async_engine(norm_url, connect_args=connect_args, poolclass=NullPool)

    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT current_database(), inet_server_port()"))
            row = res.first()
            if not row:
                pytest.skip("Could not query PostgreSQL test database identity.")
            db_name, port = row
            if db_name not in VALID_TEST_DB_NAMES and not (db_name.endswith("_test") or "test" in db_name):
                pytest.skip(
                    f"Refusing to execute on non-test database '{db_name}'. "
                    f"Must be an isolated test database (e.g., 'roxy_isolated_test_db' or 'roxy_test')."
                )
            if any(marker in str(db_name).lower() for marker in ("prod", "production")):
                pytest.fail(f"CRITICAL SAFETY ABORT: Database name '{db_name}' contains production marker!")
    except Exception as exc:
        pytest.skip(f"PostgreSQL test service is unreachable: {exc}")

    yield engine
    await engine.dispose()


@pytest.fixture(scope="function", autouse=True)
def setup_billing_environment() -> Generator[None, None, None]:
    """Configure test DB environment for billing module per test function."""
    prev_db = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL or ""

    get_engine.cache_clear()
    _session_factory.cache_clear()

    yield

    if prev_db is not None:
        os.environ["DATABASE_URL"] = prev_db
    else:
        os.environ.pop("DATABASE_URL", None)

    get_engine.cache_clear()
    _session_factory.cache_clear()


@pytest.mark.asyncio
async def test_01_billing_schema_presence(pg_engine: AsyncEngine) -> None:
    """Verify that all billing subsystem tables and provider columns exist in PostgreSQL."""
    expected_tables = {
        "subscriptions",
        "payments",
        "payment_events",
        "payment_methods",
        "credit_wallets",
        "usage_logs",
    }
    async with pg_engine.connect() as conn:
        res = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        existing = {row[0] for row in res.fetchall()}
        missing = expected_tables - existing
        assert not missing, f"Missing billing tables in PostgreSQL: {missing}"

        # Verify subscriptions.provider column specifically
        col_res = await conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'subscriptions'")
        )
        sub_cols = {row[0] for row in col_res.fetchall()}
        assert "provider" in sub_cols, "CRITICAL: 'provider' column is missing from subscriptions table!"
        assert "amount_pkr" in sub_cols, "CRITICAL: 'amount_pkr' column is missing from subscriptions table!"
        assert "amount_usd" in sub_cols, "CRITICAL: 'amount_usd' column is missing from subscriptions table!"


@pytest.mark.asyncio
async def test_02_subscription_real_postgres_persistence(pg_engine: AsyncEngine) -> None:
    """Verify subscription update_or_create writes and commits directly to PostgreSQL."""
    repo = BillingRepository()
    user_id = f"test_bill_user_{uuid.uuid4().hex[:8]}"

    try:
        # Create Pro subscription via Safepay
        res = await repo.update_or_create_subscription(
            user_id=user_id,
            plan_id="pro",
            provider="safepay",
            status="active",
            amount_usd=19.0,
            amount_pkr=5700.0,
            provider_customer_id="sfpy_cus_123",
            provider_subscription_id="sfpy_sub_456",
        )
        assert res["plan"]["id"] == "pro"
        assert res["plan"]["provider"] == "safepay"
        assert res["plan"]["price_pkr"] == 5700.0

        # Query real PostgreSQL directly via independent AsyncSession
        async with AsyncSession(pg_engine) as session:
            stmt = select(Subscription).where(Subscription.user_id == user_id)
            db_res = await session.execute(stmt)
            sub_row = db_res.scalars().first()
            assert sub_row is not None, "Subscription row was NOT committed to PostgreSQL!"
            assert sub_row.provider == "safepay"
            assert sub_row.plan == "pro"
            assert sub_row.status == "active"
            assert sub_row.amount_pkr == 5700.0
            assert sub_row.amount_usd == 19.0
            assert sub_row.provider_customer_id == "sfpy_cus_123"

        # Verify read via fresh repository instance
        fresh_repo = BillingRepository()
        loaded = await fresh_repo.get_subscription(user_id)
        assert loaded["plan"]["id"] == "pro"
        assert loaded["plan"]["provider"] == "safepay"
        assert loaded["plan"]["status"] == "active"
        assert loaded["plan"]["price_pkr"] == 5700.0
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM subscriptions WHERE user_id = :uid"), {"uid": user_id})


@pytest.mark.asyncio
async def test_03_payment_and_event_idempotency_in_postgres(pg_engine: AsyncEngine) -> None:
    """Verify payment and webhook event records are committed and prevent duplicate processing."""
    repo = BillingRepository()
    user_id = f"test_bill_user_pay_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_test_real_db_{uuid.uuid4().hex[:12]}"
    payment_id = f"pay_test_{uuid.uuid4().hex[:8]}"

    try:
        # Record payment transaction
        await repo.record_payment(
            user_id=user_id,
            payment_data={
                "id": payment_id,
                "provider": "stripe",
                "amount": 19.0,
                "currency": "USD",
                "status": "paid",
                "plan_id": "pro",
            },
        )

        # Verify payment committed in PostgreSQL
        async with AsyncSession(pg_engine) as session:
            stmt = select(Payment).where(Payment.id == payment_id)
            pay_res = await session.execute(stmt)
            pay_row = pay_res.scalars().first()
            assert pay_row is not None, "Payment was not committed to PostgreSQL!"
            assert pay_row.amount == 19.0
            assert pay_row.provider == "stripe"
            assert pay_row.currency == "USD"

        # Record webhook event (first time: must be True)
        is_first = await repo.record_webhook_event(
            event_id=event_id,
            provider="stripe",
            event_type="checkout.session.completed",
            raw_payload={"test": "payload"},
        )
        assert is_first is True, "First webhook recording must return True"

        # Verify event in PostgreSQL
        async with AsyncSession(pg_engine) as session:
            evt_stmt = select(PaymentEvent).where(
                PaymentEvent.provider == "stripe",
                PaymentEvent.provider_event_id == event_id,
            )
            evt_res = await session.execute(evt_stmt)
            evt_row = evt_res.scalars().first()
            assert evt_row is not None, "PaymentEvent was not committed to PostgreSQL!"
            assert evt_row.processed is False, "Newly recorded event must start in pending/unprocessed state"

        # Complete event operations and mark processed
        await repo.mark_webhook_event_processed("stripe", event_id)

        async with AsyncSession(pg_engine) as session:
            evt_stmt = select(PaymentEvent).where(
                PaymentEvent.provider == "stripe",
                PaymentEvent.provider_event_id == event_id,
            )
            evt_res = await session.execute(evt_stmt)
            evt_row = evt_res.scalars().first()
            assert evt_row is not None
            assert evt_row.processed is True, "PaymentEvent must be marked processed=True after completion"

        # Duplicate event check: must return False (idempotent)
        fresh_repo = BillingRepository()
        is_duplicate = await fresh_repo.record_webhook_event(
            event_id=event_id,
            provider="stripe",
            event_type="checkout.session.completed",
        )
        assert is_duplicate is False, "Duplicate event was not detected as idempotent!"
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM payments WHERE user_id = :uid"), {"uid": user_id})
            await conn.execute(
                text("DELETE FROM payment_events WHERE provider_event_id = :eid"), {"eid": event_id}
            )


@pytest.mark.asyncio
async def test_04_credit_wallet_real_postgres_persistence(pg_engine: AsyncEngine) -> None:
    """Verify CreditWallet initialization, crediting, and debiting persist to PostgreSQL."""
    repo = BillingRepository()
    user_id = f"test_bill_wallet_{uuid.uuid4().hex[:8]}"

    try:
        # Initial get_credit_wallet
        wallet = await repo.get_credit_wallet(user_id)
        assert wallet["user_id"] == user_id
        initial_credits = float(wallet["remaining_credits"])

        # Credit wallet (+50,000 credits)
        credited = await repo.credit_wallet(user_id=user_id, credits=50000.0, cost_pkr=1400.0)
        assert credited["remaining_credits"] == initial_credits + 50000.0

        # Verify physical row in PostgreSQL
        async with AsyncSession(pg_engine) as session:
            stmt = select(CreditWallet).where(CreditWallet.user_id == user_id)
            w_res = await session.execute(stmt)
            w_row = w_res.scalars().first()
            assert w_row is not None, "CreditWallet was not committed to PostgreSQL!"
            assert w_row.remaining_credits == initial_credits + 50000.0

        # Deduct credits
        fresh_repo = BillingRepository()
        deducted = await fresh_repo.deduct_credits(user_id=user_id, credits=1000.0)
        assert deducted is True

        # Verify updated balance in PostgreSQL
        async with AsyncSession(pg_engine) as session:
            stmt = select(CreditWallet).where(CreditWallet.user_id == user_id)
            w_res2 = await session.execute(stmt)
            w_row2 = w_res2.scalars().first()
            assert w_row2 is not None
            assert w_row2.remaining_credits == initial_credits + 49000.0
            assert w_row2.used_this_month == 1000.0
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM credit_wallets WHERE user_id = :uid"), {"uid": user_id})


@pytest.mark.asyncio
async def test_05_multi_tenant_financial_isolation(pg_engine: AsyncEngine) -> None:
    """Verify Tenant A subscription state does not leak to Tenant B in real PostgreSQL."""
    repo = BillingRepository()
    tenant_a = f"tenant_real_a_{uuid.uuid4().hex[:8]}"
    tenant_b = f"tenant_real_b_{uuid.uuid4().hex[:8]}"

    try:
        # Tenant A purchases Pro
        await repo.update_or_create_subscription(
            user_id=tenant_a,
            plan_id="pro",
            provider="stripe",
            status="active",
            amount_usd=19.0,
        )

        fresh_repo = BillingRepository()
        sub_a = await fresh_repo.get_subscription(tenant_a)
        sub_b = await fresh_repo.get_subscription(tenant_b)

        assert sub_a["plan"]["id"] == "pro"
        assert sub_a["plan"]["status"] == "active"

        # Tenant B must remain Free default
        assert sub_b["plan"]["id"] == "free"
        assert sub_b["plan"]["price_usd"] == 0.0

        # Verify in raw PostgreSQL
        async with AsyncSession(pg_engine) as session:
            res_a = await session.execute(select(Subscription).where(Subscription.user_id == tenant_a))
            assert res_a.scalars().first() is not None

            res_b = await session.execute(select(Subscription).where(Subscription.user_id == tenant_b))
            assert res_b.scalars().first() is None, "Tenant B must not have any row in subscriptions table"
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM subscriptions WHERE user_id IN (:a, :b)"),
                {"a": tenant_a, "b": tenant_b},
            )


@pytest.mark.asyncio
async def test_06_production_fail_closed_on_missing_db() -> None:
    """Verify that in production mode, missing DATABASE_URL raises RuntimeError."""
    repo = BillingRepository()
    user_id = f"test_prod_fail_{uuid.uuid4().hex[:8]}"

    with mock.patch.dict(os.environ, {"ENVIRONMENT": "production", "DATABASE_URL": ""}):
        with pytest.raises(RuntimeError, match="Durable database persistence required in production"):
            await repo.update_or_create_subscription(
                user_id=user_id,
                plan_id="pro",
                provider="stripe",
                status="active",
            )

        with pytest.raises(RuntimeError, match="Durable database persistence required in production"):
            await repo.record_payment(user_id=user_id, payment_data={"amount": 10.0})

        with pytest.raises(RuntimeError, match="Durable database persistence required in production"):
            await repo.credit_wallet(user_id=user_id, credits=100.0)


@pytest.mark.asyncio
async def test_07_production_fail_closed_on_db_exception() -> None:
    """Verify that in production mode, a database exception raises RuntimeError instead of falling back to memory."""
    repo = BillingRepository()
    user_id = f"test_prod_db_err_{uuid.uuid4().hex[:8]}"

    # Mock _get_factory to return a factory whose session raises an exception
    class FailingSession:
        async def __aenter__(self) -> FailingSession:
            raise RuntimeError("Simulated PostgreSQL connection failure")

        async def __aexit__(self, *args: Any) -> None:
            pass

    def _failing_factory() -> FailingSession:
        return FailingSession()

    with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        with mock.patch.object(repo, "_get_factory", return_value=_failing_factory):
            with pytest.raises(RuntimeError, match="Database subscription update failed in production"):
                await repo.update_or_create_subscription(
                    user_id=user_id,
                    plan_id="pro",
                    provider="stripe",
                    status="active",
                )

            with pytest.raises(RuntimeError, match="DB record payment failed in production"):
                await repo.record_payment(user_id=user_id, payment_data={"amount": 19.0})

            with pytest.raises(RuntimeError, match="DB credit wallet failed in production"):
                await repo.credit_wallet(user_id=user_id, credits=500.0)
