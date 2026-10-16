"""Permanent Real-PostgreSQL Integration Test for Legacy Payment Events Migration.

Validates Section 1 P0 requirements:
1. Construct legacy schema variants of `payment_events`:
   - `event_id` instead of `provider_event_id`
   - `raw_payload` (Text) instead of `payload` (JSONB)
   - missing `processed` boolean
   - missing or non-nullable `processed_at`
   - missing `provider`
   - duplicate event identifiers in legacy data
2. Insert representative historical rows with payloads.
3. Apply migration 012 on isolated PostgreSQL (roxy_isolated_test_db).
4. Verify complete data preservation via raw SQL and SQLAlchemy ORM:
   - Zero dropped rows.
   - Historical payloads parsed and preserved in JSONB `payload`.
   - `provider_event_id` and `event_id` populated and synchronized.
   - `processed` correctly backfilled based on `processed_at`.
   - Unique constraint safely created without dropping duplicate audit records.
   - Webhook idempotency and ORM persistence verified on migrated schema.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.repository import BillingRepository, clear_in_memory_stores
from app.db import _session_factory, get_engine, normalize_database_url
from app.models.subscription import PaymentEvent

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
def setup_test_env():
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
async def test_legacy_payment_events_schema_reconciliation_and_preservation(pg_engine: AsyncEngine) -> None:
    """Test full legacy schema migration, payload preservation, and ORM compatibility."""
    
    # Step 1: Deliberately construct a legacy payment_events schema in PostgreSQL
    async with pg_engine.begin() as conn:
        await conn.execute(text("UPDATE alembic_version SET version_num = '011_trust_reliability_hardening'"))
        await conn.execute(text("DROP TABLE IF EXISTS payment_events CASCADE"))
        await conn.execute(text("""
            CREATE TABLE payment_events (
                id VARCHAR(64) PRIMARY KEY,
                event_id VARCHAR(128) NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                raw_payload TEXT NOT NULL,
                processed_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            )
        """))

        # Step 2: Seed representative historical records
        # Row A: Standard JSON payload in raw_payload, processed
        await conn.execute(text("""
            INSERT INTO payment_events (id, event_id, event_type, raw_payload, processed_at)
            VALUES (
                'pe_leg_001',
                'evt_stripe_1001',
                'payment_intent.succeeded',
                '{"amount": 5000, "currency": "usd", "customer": "cus_test_123"}',
                NOW()
            )
        """))

        # Row B: Unprocessed event with nested JSON string
        await conn.execute(text("""
            INSERT INTO payment_events (id, event_id, event_type, raw_payload, processed_at)
            VALUES (
                'pe_leg_002',
                'evt_safepay_2002',
                'payment.completed',
                '{"tracker": "track_safe_456", "amount_pkr": 14000}',
                NULL
            )
        """))

        # Row C: Non-JSON raw text payload (must be preserved in payload JSONB as raw wrapper)
        await conn.execute(text("""
            INSERT INTO payment_events (id, event_id, event_type, raw_payload, processed_at)
            VALUES (
                'pe_leg_003',
                'evt_raw_3003',
                'custom.log',
                'raw unformatted webhook payload test string',
                NOW()
            )
        """))

        # Rows D & E: Duplicate event_ids in legacy data
        await conn.execute(text("""
            INSERT INTO payment_events (id, event_id, event_type, raw_payload, processed_at)
            VALUES (
                'pe_leg_004',
                'evt_dup_4004',
                'payment_intent.created',
                '{"attempt": 1}',
                NOW()
            ),
            (
                'pe_leg_005',
                'evt_dup_4004',
                'payment_intent.created',
                '{"attempt": 2}',
                NULL
            )
        """))

    # Step 3: Run Alembic upgrade head to execute migration 012
    alembic_ini = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
    cfg = Config(alembic_ini)
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(alembic_ini), "alembic"))

    await asyncio.to_thread(command.upgrade, cfg, "head")

    # Step 4: SQL Assertions — Verify schema and data preservation
    async with pg_engine.connect() as conn:
        res = await conn.execute(text("SELECT count(*) FROM payment_events"))
        total_count = res.scalar()
        assert total_count == 5, f"Expected exactly 5 preserved rows, got {total_count}"

        # Verify Row A: JSON payload migrated, provider backfilled, processed = True
        res_a = await conn.execute(
            text("SELECT provider, provider_event_id, event_id, processed, processed_at, payload FROM payment_events WHERE id = 'pe_leg_001'")
        )
        row_a = res_a.first()
        assert row_a is not None
        assert row_a[0] == "stripe"
        assert row_a[1] == "evt_stripe_1001"  # provider_event_id migrated from event_id
        assert row_a[2] == "evt_stripe_1001"  # event_id mirror populated
        assert row_a[3] is True  # processed backfilled from non-null processed_at
        assert row_a[4] is not None
        payload_a = row_a[5]
        if isinstance(payload_a, str):
            payload_a = json.loads(payload_a)
        assert payload_a["amount"] == 5000
        assert payload_a["customer"] == "cus_test_123"

        # Verify Row B: Unprocessed event has processed = False
        res_b = await conn.execute(
            text("SELECT processed, processed_at, payload FROM payment_events WHERE id = 'pe_leg_002'")
        )
        row_b = res_b.first()
        assert row_b is not None
        assert row_b[0] is False  # processed is False
        assert row_b[1] is None
        payload_b = row_b[2]
        if isinstance(payload_b, str):
            payload_b = json.loads(payload_b)
        assert payload_b["tracker"] == "track_safe_456"

        # Verify Row C: Non-JSON raw text payload preserved cleanly
        res_c = await conn.execute(
            text("SELECT payload FROM payment_events WHERE id = 'pe_leg_003'")
        )
        row_c = res_c.first()
        assert row_c is not None
        payload_c = row_c[0]
        if isinstance(payload_c, str):
            payload_c = json.loads(payload_c)
        assert "raw unformatted webhook payload test string" in str(payload_c)

        # Verify Rows D & E: Duplicate rows were preserved without dropping either row!
        res_d = await conn.execute(
            text("SELECT id, provider_event_id, payload FROM payment_events WHERE id IN ('pe_leg_004', 'pe_leg_005') ORDER BY id")
        )
        dup_rows = res_d.fetchall()
        assert len(dup_rows) == 2
        # One kept original provider_event_id, other has deduplication suffix
        eids = {r[1] for r in dup_rows}
        assert "evt_dup_4004" in eids
        assert any("-legacy-dup-" in eid for eid in eids)

    # Step 5: ORM Assertions — Query and persist via SQLAlchemy models
    repo = BillingRepository()
    async with (repo._get_factory())() as session:
        # Query Row A through ORM
        stmt = select(PaymentEvent).where(PaymentEvent.id == "pe_leg_001")
        res_orm = await session.execute(stmt)
        event_orm = res_orm.scalars().first()
        assert event_orm is not None
        assert event_orm.provider_event_id == "evt_stripe_1001"
        assert event_orm.event_id == "evt_stripe_1001"
        assert event_orm.processed is True
        assert event_orm.payload["amount"] == 5000

        # Insert a new event through ORM on the migrated schema
        new_event = PaymentEvent(
            provider="safepay",
            event_id="evt_new_5005",
            event_type="payment.completed",
            payload={"test": "ok"},
            processed=False,
        )
        session.add(new_event)
        await session.commit()

        # Query back
        stmt_new = select(PaymentEvent).where(PaymentEvent.provider_event_id == "evt_new_5005")
        res_new = await session.execute(stmt_new)
        saved_new = res_new.scalars().first()
        assert saved_new is not None
        assert saved_new.provider == "safepay"
        assert saved_new.event_id == "evt_new_5005"
        assert saved_new.processed is False

    # Step 6: Webhook Idempotency Verification on Migrated Database
    # Attempting to record pe_leg_001 (processed=True) must return False (idempotent reject)
    can_process_completed = await repo.record_webhook_event(
        event_id="evt_stripe_1001",
        provider="stripe",
        event_type="payment_intent.succeeded",
    )
    assert can_process_completed is False

    # Attempting to record pe_leg_002 (processed=False) must return True (retry allowed)
    can_process_retry = await repo.record_webhook_event(
        event_id="evt_safepay_2002",
        provider="stripe",
        event_type="payment.completed",
    )
    assert can_process_retry is True

    # Teardown: drop legacy table and re-run upgrade head to restore canonical schema
    async with pg_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS payment_events CASCADE"))
        await conn.execute(text("UPDATE alembic_version SET version_num = '011_trust_reliability_hardening'"))
    await asyncio.to_thread(command.upgrade, cfg, "head")
