"""Permanent Real-PostgreSQL Integration Tests for P0 Financial Integrity and Webhook Idempotency.

Mandatory failure-injection scenarios executed on isolated PostgreSQL (127.0.0.1:5433):
1. A new valid webhook succeeds and atomically credits the wallet.
2. A completed duplicate event is rejected without duplicate credit.
3. The wallet credit commits but a later operation fails; retry does not add credits again.
4. Failure before wallet credit permits safe retry.
5. Database failure during event insertion returns a failure and never falls back to in-memory success in production.
6. Database failure during event completion cannot silently acknowledge success.
7. Two workers process the same event concurrently without duplicate credits.
8. Process restart between steps does not permit double-crediting.
9. Invalid signatures cannot alter payment or wallet state.
10. Two distinct valid payment events credit only the amounts each event is entitled to credit.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Generator
from unittest import mock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.providers.base import NormalizedWebhookEvent
from app.billing.repository import BillingRepository, clear_in_memory_stores
from app.billing.service import PaymentService
from app.db import _session_factory, get_engine, normalize_database_url

VALID_TEST_DB_NAMES = {"roxy_isolated_test_db", "roxy_test"}
PROD_DB_MARKERS = {"prod", "production", "neon.tech", "aws.neon", "cloudsql"}


def _resolve_test_database_url() -> str:
    url = os.environ.get("ROXY_TEST_DATABASE_URL")
    if url:
        return url
    env_db = os.environ.get("DATABASE_URL", "").strip()
    if env_db and not any(marker in env_db.lower() for marker in PROD_DB_MARKERS):
        return env_db
    return "postgresql+asyncpg://roxy_test_usr:roxy_test_secure_pwd_123@127.0.0.1:5433/roxy_isolated_test_db"


TEST_DATABASE_URL = _resolve_test_database_url()


@pytest_asyncio.fixture(scope="function")
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    norm_url, connect_args = normalize_database_url(TEST_DATABASE_URL)
    engine = create_async_engine(norm_url, connect_args=connect_args, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT current_database()"))
            db_name = res.scalar()
            if db_name not in VALID_TEST_DB_NAMES and not (str(db_name).endswith("_test") or "test" in str(db_name)):
                pytest.skip(f"Refusing to execute on non-test DB '{db_name}'.")
    except Exception as exc:
        pytest.skip(f"PostgreSQL test service unreachable: {exc}")

    yield engine
    await engine.dispose()


@pytest.fixture(scope="function", autouse=True)
def setup_test_env() -> Generator[None, None, None]:
    prev_db = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    clear_in_memory_stores()
    get_engine.cache_clear()
    _session_factory.cache_clear()

    yield

    clear_in_memory_stores()
    if prev_db is not None:
        os.environ["DATABASE_URL"] = prev_db
    else:
        os.environ.pop("DATABASE_URL", None)
    get_engine.cache_clear()
    _session_factory.cache_clear()


@pytest.mark.asyncio
async def test_01_new_webhook_succeeds_and_credits_wallet(pg_engine: AsyncEngine) -> None:
    """Scenario 1: A new valid webhook succeeds and credits the wallet atomically."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_success_{uuid.uuid4().hex[:12]}"

    initial_wallet = await repo.get_credit_wallet(user_id)
    initial_credits = initial_wallet["remaining_credits"]

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=10.0,
        currency="USD",
        customer_id=f"cus_{uuid.uuid4().hex[:8]}",
        payment_id=f"pi_{uuid.uuid4().hex[:8]}",
        metadata={"user_id": user_id, "pack_id": "pack_10", "credits": "1200000"},
        raw_data={"test": True},
    )

    result = await svc.process_webhook_event("stripe", event)
    assert result["status"] == "success"

    # Verify wallet credits incremented accurately in PostgreSQL
    async with pg_engine.connect() as conn:
        res = await conn.execute(
            text("SELECT remaining_credits FROM credit_wallets WHERE user_id = :uid"),
            {"uid": user_id},
        )
        balance = res.scalar()
        assert balance == initial_credits + 1200000.0

        # Verify event marked processed=True
        ev_res = await conn.execute(
            text("SELECT processed, processed_at, payload FROM payment_events WHERE provider_event_id = :eid"),
            {"eid": event_id},
        )
        row = ev_res.first()
        assert row is not None
        assert row[0] is True  # processed
        assert row[1] is not None  # processed_at
        assert row[2].get("wallet_credited") is True


@pytest.mark.asyncio
async def test_02_duplicate_webhook_rejected_without_second_credit(pg_engine: AsyncEngine) -> None:
    """Scenario 2: A completed duplicate is rejected without a second credit."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_dup_{uuid.uuid4().hex[:12]}"

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=5.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_5", "credits": "500000"},
        raw_data={},
    )

    # First delivery -> succeeds
    res1 = await svc.process_webhook_event("stripe", event)
    assert res1["status"] == "success"

    wallet_after_first = await repo.get_credit_wallet(user_id)
    credits_after_first = wallet_after_first["remaining_credits"]

    # Second delivery (duplicate retry) -> rejected with already_processed
    res2 = await svc.process_webhook_event("stripe", event)
    assert res2["status"] == "already_processed"

    # Balance must remain unchanged
    wallet_after_second = await repo.get_credit_wallet(user_id)
    assert wallet_after_second["remaining_credits"] == credits_after_first


@pytest.mark.asyncio
async def test_03_credit_commits_then_failure_occurs_retry_prevents_double_credit(pg_engine: AsyncEngine) -> None:
    """Scenario 3: The wallet credit commits but a later operation fails; retry does not add credits again."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_partial_fail_{uuid.uuid4().hex[:12]}"

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=10.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_10", "credits": "1200000"},
        raw_data={},
    )

    # Simulate failure in mark_webhook_event_processed (e.g. temporary network glitch or DB blip after wallet credit)
    with mock.patch.object(repo, "mark_webhook_event_processed", side_effect=RuntimeError("Simulated failure after credit")):
        res_fail = await svc.process_webhook_event("stripe", event)
        assert res_fail["status"] == "error"

    # Wallet was credited in DB
    async with pg_engine.connect() as conn:
        res = await conn.execute(
            text("SELECT remaining_credits FROM credit_wallets WHERE user_id = :uid"),
            {"uid": user_id},
        )
        credited_bal = res.scalar()
        assert credited_bal is not None
        assert float(credited_bal) >= 1200000.0

        # Event is NOT marked processed yet
        ev_res = await conn.execute(
            text("SELECT processed FROM payment_events WHERE provider_event_id = :eid"),
            {"eid": event_id},
        )
        assert ev_res.scalar() is False

    # Retry the webhook now that failure is resolved:
    res_retry = await svc.process_webhook_event("stripe", event)
    # The event completes successfully or acknowledges already credited without adding duplicate credits
    assert res_retry["status"] in ("success", "already_processed")

    # Balance MUST NOT have been doubled!
    async with pg_engine.connect() as conn:
        res_after = await conn.execute(
            text("SELECT remaining_credits FROM credit_wallets WHERE user_id = :uid"),
            {"uid": user_id},
        )
        final_bal = res_after.scalar()
        assert final_bal == credited_bal  # ZERO duplicate credits!


@pytest.mark.asyncio
async def test_04_failure_before_wallet_credit_permits_safe_retry(pg_engine: AsyncEngine) -> None:
    """Scenario 4: Failure before wallet credit permits safe retry."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_precredit_fail_{uuid.uuid4().hex[:12]}"

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=5.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_5", "credits": "500000"},
        raw_data={},
    )

    # Injected failure before credit_wallet (e.g. record_payment fails)
    with mock.patch.object(repo, "record_payment", side_effect=RuntimeError("Transient DB connection glitch")):
        res_fail = await svc.process_webhook_event("stripe", event)
        assert res_fail["status"] == "error"

    # Wallet not credited
    wallet_mid = await repo.get_credit_wallet(user_id)
    assert wallet_mid["remaining_credits"] == 100.0

    # Retry without failure -> succeeds and credits
    res_retry = await svc.process_webhook_event("stripe", event)
    assert res_retry["status"] == "success"

    wallet_final = await repo.get_credit_wallet(user_id)
    assert wallet_final["remaining_credits"] == 100.0 + 500000.0


@pytest.mark.asyncio
async def test_05_db_failure_during_event_insert_returns_failure_in_production(pg_engine: AsyncEngine) -> None:
    """Scenario 5: Database failure during event insertion returns failure and never falls back to in-memory success."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_db_insert_fail_{uuid.uuid4().hex[:12]}"

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=5.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_5", "credits": "500000"},
        raw_data={},
    )

    with (
        mock.patch.dict(os.environ, {"ENVIRONMENT": "production", "APP_ENV": "production"}),
        mock.patch.object(repo, "record_webhook_event", side_effect=RuntimeError("Postgres I/O connection lost")),
    ):
        result = await svc.process_webhook_event("stripe", event)
        assert result["status"] == "error"
        assert "Postgres I/O connection lost" in result["message"]

    # Verify no unpersisted credit occurred
    wallet = await repo.get_credit_wallet(user_id)
    assert wallet["remaining_credits"] == 100.0


@pytest.mark.asyncio
async def test_06_db_failure_during_event_completion_cannot_silently_acknowledge_success(pg_engine: AsyncEngine) -> None:
    """Scenario 6: Database failure during event completion cannot silently acknowledge success."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_db_complete_fail_{uuid.uuid4().hex[:12]}"

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=5.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_5", "credits": "500000"},
        raw_data={},
    )

    with mock.patch.object(repo, "mark_webhook_event_processed", side_effect=RuntimeError("Commit failed")):
        result = await svc.process_webhook_event("stripe", event)
        assert result["status"] == "error"


@pytest.mark.asyncio
async def test_07_concurrent_delivery_two_workers_zero_double_credits(pg_engine: AsyncEngine) -> None:
    """Scenario 7: Two workers process the same event concurrently without duplicate credits."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_concurrent_{uuid.uuid4().hex[:12]}"

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=10.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_10", "credits": "1200000"},
        raw_data={},
    )

    # Launch two concurrent workers delivering the exact same event simultaneously
    task1 = asyncio.create_task(svc.process_webhook_event("stripe", event))
    task2 = asyncio.create_task(svc.process_webhook_event("stripe", event))
    res1, res2 = await asyncio.gather(task1, task2)

    statuses = {res1["status"], res2["status"]}
    # One worker must succeed, other must be already_processed (or both idempotent)
    assert "success" in statuses or "already_processed" in statuses

    # Verify wallet credits in PostgreSQL: EXACTLY one pack of 1,200,000 added
    async with pg_engine.connect() as conn:
        res = await conn.execute(
            text("SELECT remaining_credits FROM credit_wallets WHERE user_id = :uid"),
            {"uid": user_id},
        )
        balance = res.scalar()
        assert balance == 100.0 + 1200000.0


@pytest.mark.asyncio
async def test_08_restart_between_steps_does_not_permit_double_crediting(pg_engine: AsyncEngine) -> None:
    """Scenario 8: Process restart between steps does not permit double-crediting."""
    repo1 = BillingRepository()
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id = f"evt_restart_{uuid.uuid4().hex[:12]}"

    event = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type="payment.succeeded",
        amount=5.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_5", "credits": "500000"},
        raw_data={},
    )

    # Step 1: Worker 1 records event and credits wallet, but terminates before mark_webhook_event_processed
    await repo1.record_webhook_event(event_id, "stripe", "payment.succeeded")
    await repo1.credit_wallet(user_id=user_id, credits=500000.0, event_id=event_id, provider="stripe")

    # Step 2: Simulate process termination & restart by clearing all memory and creating fresh service instance
    clear_in_memory_stores()
    repo2 = BillingRepository()
    svc2 = PaymentService(repository=repo2)

    # Redeliver event on new worker instance
    res_retry = await svc2.process_webhook_event("stripe", event)
    assert res_retry["status"] in ("success", "already_processed")

    # Verify wallet credits in PostgreSQL: remains 100 + 500,000 (NOT 100 + 1,000,000)
    async with pg_engine.connect() as conn:
        res_db = await conn.execute(
            text("SELECT remaining_credits FROM credit_wallets WHERE user_id = :uid"),
            {"uid": user_id},
        )
        balance = res_db.scalar()
        assert balance == 100.0 + 500000.0


@pytest.mark.asyncio
async def test_09_invalid_signature_cannot_alter_payment_or_wallet_state(pg_engine: AsyncEngine) -> None:
    """Scenario 9: Invalid signatures cannot alter payment or wallet state."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)

    raw_body = b'{"id": "evt_fake", "type": "payment.succeeded"}'
    fake_headers = {"stripe-signature": "t=123456,v1=invalidsignature0000000000"}

    with mock.patch.dict(os.environ, {"ENVIRONMENT": "production", "APP_ENV": "production"}):
        res = await svc.process_webhook("stripe", fake_headers, raw_body)
        assert res["status"] == "error"
        assert "Invalid webhook signature" in res["message"]

    # Verify no records added to DB
    async with pg_engine.connect() as conn:
        db_res = await conn.execute(
            text("SELECT count(*) FROM payment_events WHERE provider_event_id = 'evt_fake'")
        )
        assert db_res.scalar() == 0


@pytest.mark.asyncio
async def test_10_two_distinct_valid_events_credit_only_respective_amounts(pg_engine: AsyncEngine) -> None:
    """Scenario 10: Two distinct valid payment events credit only the amounts each event is entitled to credit."""
    repo = BillingRepository()
    svc = PaymentService(repository=repo)
    user_id = f"usr_test_{uuid.uuid4().hex[:8]}"
    event_id_a = f"evt_dist_a_{uuid.uuid4().hex[:12]}"
    event_id_b = f"evt_dist_b_{uuid.uuid4().hex[:12]}"

    event_a = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id_a,
        event_type="payment.succeeded",
        amount=5.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_5", "credits": "500000"},
        raw_data={},
    )
    event_b = NormalizedWebhookEvent(
        provider="stripe",
        event_id=event_id_b,
        event_type="payment.succeeded",
        amount=10.0,
        currency="USD",
        metadata={"user_id": user_id, "pack_id": "pack_10", "credits": "1200000"},
        raw_data={},
    )

    res_a = await svc.process_webhook_event("stripe", event_a)
    assert res_a["status"] == "success"

    res_b = await svc.process_webhook_event("stripe", event_b)
    assert res_b["status"] == "success"

    async with pg_engine.connect() as conn:
        res = await conn.execute(
            text("SELECT remaining_credits FROM credit_wallets WHERE user_id = :uid"),
            {"uid": user_id},
        )
        balance = res.scalar()
        # Exactly 100 starter + 500,000 (pack 5) + 1,200,000 (pack 10) = 1,700,100
        assert balance == 100.0 + 500000.0 + 1200000.0
