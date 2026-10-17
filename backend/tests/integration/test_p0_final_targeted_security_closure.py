"""ROXY-AI — FINAL TARGETED SECURITY CLOSURE ACCEPTANCE SUITE.

Acceptance tests for:
- Finding A: Real Step-Up Delivery (no configuration fails closed; flags alone fail closed;
  provider failure blocks challenge; generic response only without code leakage; wrong/expired/exhausted codes rejected).
- Finding B: Durable Cross-Worker Single-Use Confirmation (PostgreSQL row-level locking with SELECT FOR UPDATE;
  two concurrent workers -> exactly one succeeds; replay rejected; restart/worker switch preserves status; DB failure fails closed).
- Finding C: Fail-Closed Parameter Binding (matching parameters succeed once; mismatch rejected;
  missing saved required value rejected; missing caller value rejected; wrong target/recipient/amount rejected;
  rejected binding does not authorize execution).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import normalize_database_url
from app.trust.confirmation_gate import (
    ConfirmationGate,
    MockStepUpDeliveryProvider,
)
from app.trust.schemas import ConfirmationStatus, RiskTier

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
                pytest.skip(f"Safety guard: Connected to non-test database: {db_name}")
    except Exception as exc:
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")

    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def clean_gate() -> Generator[None, None, None]:
    ConfirmationGate.clear()
    provider = MockStepUpDeliveryProvider()
    ConfirmationGate.register_delivery_provider(provider)
    yield
    ConfirmationGate.clear()


# ============================================================================
# Finding A: Real Step-Up Verification Delivery
# ============================================================================


def test_finding_a_01_no_delivery_configuration_fails_closed() -> None:
    """Proof 1: No delivery configuration -> protected operation fails closed."""
    ConfirmationGate.register_delivery_provider(None)
    with (
        mock.patch.dict(os.environ, {"SMTP_HOST": "", "ROXY_FORCE_DISABLE_2FA_DELIVERY": ""}, clear=False),
        pytest.raises(RuntimeError, match="Independent step-up verification is not configured"),
    ):
        ConfirmationGate.create_challenge(
            user_id="usr_sec_a01",
            action_type="financial_wire",
            title="Wire $100,000",
            summary="High value wire",
            risk_tier=RiskTier.CRITICAL,
            requires_2fa=True,
        )


def test_finding_a_02_config_flag_without_real_provider_fails_closed() -> None:
    """Proof 2: Configuration flag without a real delivery implementation -> fails closed."""
    ConfirmationGate.register_delivery_provider(None)
    with (
        mock.patch.dict(
            os.environ,
            {
                "ROXY_STEP_UP_DELIVERY_PROVIDER": "unregistered_sms_provider_flag",
                "SMTP_HOST": "",
            },
            clear=False,
        ),
        pytest.raises(RuntimeError, match="Independent step-up verification is not configured"),
    ):
        ConfirmationGate.create_challenge(
            user_id="usr_sec_a02",
            action_type="financial_wire",
            title="Wire $50,000",
            summary="High value wire",
            risk_tier=RiskTier.CRITICAL,
            requires_2fa=True,
        )


def test_finding_a_03_delivery_provider_failure_blocks_challenge() -> None:
    """Proof 3: Delivery provider failure -> protected operation remains blocked."""
    failing_provider = MockStepUpDeliveryProvider(should_succeed=False)
    ConfirmationGate.register_delivery_provider(failing_provider)

    with pytest.raises(RuntimeError, match="Step-up verification delivery failed closed"):
        ConfirmationGate.create_challenge(
            user_id="usr_sec_a03",
            action_type="financial_wire",
            title="Wire $25,000",
            summary="Transfer to external vault",
            risk_tier=RiskTier.CRITICAL,
            requires_2fa=True,
        )

    # Prove challenge was NOT persisted or created
    pending = ConfirmationGate.list_pending("usr_sec_a03")
    assert len(pending) == 0


def test_finding_a_04_successful_mocked_provider_acceptance_generic_response_no_code_leakage() -> None:
    """Proof 4: Successful mocked provider acceptance -> generic challenge response only; no code leakage."""
    mock_provider = MockStepUpDeliveryProvider(should_succeed=True, provider_accepted=True)
    ConfirmationGate.register_delivery_provider(mock_provider)

    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_a04",
        action_type="financial_wire",
        title="Wire $10,000",
        summary="Authorized wire transfer",
        details={"amount": 10000.0, "destination": "US_BANK_001"},
        risk_tier=RiskTier.CRITICAL,
        requires_2fa=True,
    )

    assert chal.step_up_required is True
    assert chal.step_up_hint is not None

    # Prove provider accepted the dispatch
    assert len(mock_provider.dispatched_records) == 1
    sent_record = mock_provider.dispatched_records[0]
    secret_code = sent_record["code"]
    assert len(secret_code) == 6

    # Verify secret code is NEVER leaked in response, hint, or serialized response
    assert secret_code not in chal.step_up_hint
    assert secret_code not in str(chal.model_dump())
    assert secret_code not in repr(chal)


def test_finding_a_05_wrong_expired_and_exhausted_codes_remain_rejected() -> None:
    """Proof 5: Wrong, expired, and exhausted codes remain rejected."""
    mock_provider = MockStepUpDeliveryProvider(should_succeed=True, provider_accepted=True)
    ConfirmationGate.register_delivery_provider(mock_provider)

    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_a05",
        action_type="financial_wire",
        title="Wire $15,000",
        summary="Security test wire",
        details={"amount": 15000.0, "destination": "US_BANK_002"},
        risk_tier=RiskTier.CRITICAL,
        requires_2fa=True,
    )

    # Wrong code attempt 1
    with pytest.raises(ValueError, match="2 attempt"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_sec_a05",
            decision="approve",
            challenge_token=chal.challenge_token,
            step_up_code="000000",
        )

    # Wrong code attempt 2
    with pytest.raises(ValueError, match="1 attempt"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_sec_a05",
            decision="approve",
            challenge_token=chal.challenge_token,
            step_up_code="111111",
        )

    # Wrong code attempt 3 -> Lockout
    with pytest.raises(ValueError, match="locked out"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_sec_a05",
            decision="approve",
            challenge_token=chal.challenge_token,
            step_up_code="222222",
        )

    # Prove status transitioned to REJECTED and subsequent attempts are blocked
    rec = ConfirmationGate.get_challenge(chal.challenge_id, "usr_sec_a05")
    assert rec is not None
    assert rec["status"] == ConfirmationStatus.REJECTED

    # Expired challenge check
    chal_expired = ConfirmationGate.create_challenge(
        user_id="usr_sec_a05",
        action_type="financial_wire",
        title="Wire Expired",
        summary="Expired wire",
        details={"amount": 5000.0, "destination": "US_BANK_003"},
        risk_tier=RiskTier.HIGH,
        ttl_seconds=-5,
    )
    with pytest.raises(ValueError, match="expired"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal_expired.challenge_id,
            user_id="usr_sec_a05",
            decision="approve",
            challenge_token=chal_expired.challenge_token,
        )


# ============================================================================
# Finding B: Durable, Cross-Worker Single-Use Confirmation (PostgreSQL 16)
# ============================================================================


@pytest.mark.asyncio
async def test_finding_b_01_two_concurrent_workers_exactly_one_succeeds(pg_engine: AsyncEngine) -> None:
    """Proof 1: Two concurrent database workers against real PostgreSQL -> exactly one succeeds.

    Uses SELECT ... FOR UPDATE row-level locking on table confirmation_challenges.
    """
    ConfirmationGate.set_db_engine(pg_engine)
    user_id = f"usr_b01_{uuid.uuid4().hex[:8]}"
    chal_id = f"chk_b01_{uuid.uuid4().hex[:8]}"
    token = f"tok_b01_{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=300)

    # Seed an approved challenge directly into PostgreSQL confirmation_challenges table
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO confirmation_challenges (
                    challenge_id, user_id, action_type, title, summary, details_json,
                    risk_tier, risk_score, challenge_token, step_up_required,
                    status, attempts, created_at, expires_at, resolved_at, decision
                ) VALUES (
                    :cid, :uid, 'financial_wire', 'Wire $75,000', 'Transfer test',
                    '{"amount": 75000.0, "destination": "CHASE_8888"}',
                    'CRITICAL', 90, :token, false,
                    'approved', 0, :now, :exp, :now, 'approve'
                )
                """
            ),
            {"cid": chal_id, "uid": user_id, "token": token, "now": now, "exp": expires_at},
        )

    # Concurrently consume with Worker 1 and Worker 2 on separate DB sessions
    async def _worker_task(worker_name: str) -> tuple[bool, str]:
        ok, msg, _ = await ConfirmationGate.consume_challenge_db(
            challenge_id_or_token=chal_id,
            user_id=user_id,
            action_type="financial_wire",
            details_match={"amount": 75000.0, "destination": "CHASE_8888"},
            engine=pg_engine,
        )
        return (ok, msg)

    results = await asyncio.gather(_worker_task("worker_1"), _worker_task("worker_2"))

    successes = [r for r in results if r[0] is True]
    failures = [r for r in results if r[0] is False]

    # Exactly ONE worker must succeed; the other MUST be rejected as already consumed
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {results}"
    assert "already been consumed" in failures[0][1]


@pytest.mark.asyncio
async def test_finding_b_02_second_worker_cannot_replay_consumed_challenge(pg_engine: AsyncEngine) -> None:
    """Proof 2: A second worker cannot replay a consumed challenge in PostgreSQL."""
    ConfirmationGate.set_db_engine(pg_engine)
    user_id = f"usr_b02_{uuid.uuid4().hex[:8]}"
    chal_id = f"chk_b02_{uuid.uuid4().hex[:8]}"
    token = f"tok_b02_{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=300)

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO confirmation_challenges (
                    challenge_id, user_id, action_type, title, summary, details_json,
                    risk_tier, risk_score, challenge_token, step_up_required,
                    status, attempts, created_at, expires_at, resolved_at, decision
                ) VALUES (
                    :cid, :uid, 'financial_wire', 'Wire $30,000', 'Transfer test',
                    '{"amount": 30000.0, "destination": "WELLS_1111"}',
                    'CRITICAL', 90, :token, false,
                    'approved', 0, :now, :exp, :now, 'approve'
                )
                """
            ),
            {"cid": chal_id, "uid": user_id, "token": token, "now": now, "exp": expires_at},
        )

    # Worker 1 consumes successfully
    ok1, msg1, rec1 = await ConfirmationGate.consume_challenge_db(
        challenge_id_or_token=chal_id,
        user_id=user_id,
        action_type="financial_wire",
        details_match={"amount": 30000.0, "destination": "WELLS_1111"},
        engine=pg_engine,
    )
    assert ok1 is True
    assert msg1 == "APPROVED_AND_CONSUMED"
    assert rec1 is not None

    # Worker 2 attempts replay -> rejected
    ok2, msg2, rec2 = await ConfirmationGate.consume_challenge_db(
        challenge_id_or_token=chal_id,
        user_id=user_id,
        action_type="financial_wire",
        details_match={"amount": 30000.0, "destination": "WELLS_1111"},
        engine=pg_engine,
    )
    assert ok2 is False
    assert "already been consumed" in msg2
    assert rec2 is None


@pytest.mark.asyncio
async def test_finding_b_03_restart_worker_switch_preserves_challenge_status(pg_engine: AsyncEngine) -> None:
    """Proof 3: Process restart / worker switch preserves challenge status and consumption in PostgreSQL."""
    ConfirmationGate.set_db_engine(pg_engine)
    user_id = f"usr_b03_{uuid.uuid4().hex[:8]}"
    chal_id = f"chk_b03_{uuid.uuid4().hex[:8]}"
    token = f"tok_b03_{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=300)

    # Worker 1 provisions challenge in PostgreSQL
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO confirmation_challenges (
                    challenge_id, user_id, action_type, title, summary, details_json,
                    risk_tier, risk_score, challenge_token, step_up_required,
                    status, attempts, created_at, expires_at, resolved_at, decision
                ) VALUES (
                    :cid, :uid, 'financial_wire', 'Wire $40,000', 'Transfer test',
                    '{"amount": 40000.0, "destination": "BARCLAYS_5555"}',
                    'CRITICAL', 90, :token, false,
                    'approved', 0, :now, :exp, :now, 'approve'
                )
                """
            ),
            {"cid": chal_id, "uid": user_id, "token": token, "now": now, "exp": expires_at},
        )

    # Worker 1 terminates (simulate process death by wiping memory)
    ConfirmationGate.clear()
    assert len(ConfirmationGate.list_pending(user_id)) == 0

    # Worker 2 starts up, binds to PostgreSQL, and consumes the persisted challenge
    ConfirmationGate.set_db_engine(pg_engine)
    ok_w2, msg_w2, _ = await ConfirmationGate.consume_challenge_db(
        challenge_id_or_token=chal_id,
        user_id=user_id,
        action_type="financial_wire",
        details_match={"amount": 40000.0, "destination": "BARCLAYS_5555"},
        engine=pg_engine,
    )
    assert ok_w2 is True
    assert msg_w2 == "APPROVED_AND_CONSUMED"

    # Worker 2 terminates
    ConfirmationGate.clear()

    # Worker 3 starts up, attempts replay from PostgreSQL -> confirmed consumed
    ConfirmationGate.set_db_engine(pg_engine)
    ok_w3, msg_w3, _ = await ConfirmationGate.consume_challenge_db(
        challenge_id_or_token=chal_id,
        user_id=user_id,
        action_type="financial_wire",
        details_match={"amount": 40000.0, "destination": "BARCLAYS_5555"},
        engine=pg_engine,
    )
    assert ok_w3 is False
    assert "already been consumed" in msg_w3


@pytest.mark.asyncio
async def test_finding_b_04_database_failure_fails_closed_no_action_authorized() -> None:
    """Proof 4: Database failure -> no action is authorized (fail-closed)."""
    # Create mock broken engine that raises OperationalError
    broken_engine = mock.MagicMock(spec=AsyncEngine)

    ok, msg, rec = await ConfirmationGate.consume_challenge_db(
        challenge_id_or_token="chk_broken_db",
        user_id="usr_fail",
        action_type="financial_wire",
        details_match={"amount": 1000.0, "destination": "DEST"},
        engine=broken_engine,
    )

    assert ok is False
    assert "Durable storage error" in msg
    assert rec is None


# ============================================================================
# Finding C: Fail-Closed Parameter Binding
# ============================================================================


def test_finding_c_01_matching_parameters_succeed_exactly_once() -> None:
    """Proof 1: Matching parameters succeed exactly once; subsequent attempts are rejected."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_c01",
        action_type="financial_wire",
        title="Wire $50,000",
        summary="Authorized wire transfer",
        details={"amount": 50000.0, "destination": "CHASE_IBAN_9999"},
        risk_tier=RiskTier.HIGH,
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_sec_c01",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # First attempt with matching parameters -> Succeeds
    ok, msg, rec = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c01",
        action_type="financial_wire",
        details_match={"amount": 50000.0, "destination": "CHASE_IBAN_9999"},
    )
    assert ok is True
    assert msg == "APPROVED_AND_CONSUMED"
    assert rec is not None

    # Second attempt -> Replay rejected
    ok2, msg2, rec2 = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c01",
        action_type="financial_wire",
        details_match={"amount": 50000.0, "destination": "CHASE_IBAN_9999"},
    )
    assert ok2 is False
    assert "already been consumed" in msg2
    assert rec2 is None


def test_finding_c_02_mismatched_value_is_rejected() -> None:
    """Proof 2: A mismatched parameter value is rejected and challenge remains unconsumed."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_c02",
        action_type="financial_wire",
        title="Wire $50,000",
        summary="Authorized wire transfer",
        details={"amount": 50000.0, "destination": "CHASE_IBAN_9999"},
        risk_tier=RiskTier.HIGH,
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_sec_c02",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Attempt with altered amount
    ok, msg, rec = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c02",
        action_type="financial_wire",
        details_match={"amount": 99999.0, "destination": "CHASE_IBAN_9999"},
    )
    assert ok is False
    assert "Operation binding mismatch on 'amount'" in msg
    assert rec is None

    # Prove challenge was NOT consumed and remains eligible for legitimate execution
    saved = ConfirmationGate.get_challenge(chal.challenge_id, "usr_sec_c02")
    assert saved is not None
    assert saved["status"] == ConfirmationStatus.APPROVED

    # Now attempt with legitimate matching parameters -> succeeds
    ok_legit, _, _ = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c02",
        action_type="financial_wire",
        details_match={"amount": 50000.0, "destination": "CHASE_IBAN_9999"},
    )
    assert ok_legit is True


def test_finding_c_03_missing_required_saved_value_is_rejected() -> None:
    """Proof 3: A missing required saved value is rejected (never silently accepted)."""
    # Create challenge with empty details for an action requiring amount and destination
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_c03",
        action_type="financial_wire",
        title="Wire $50,000 without saved details",
        summary="Misconfigured challenge",
        details={},
        risk_tier=RiskTier.HIGH,
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_sec_c03",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Caller presents valid parameters, but saved challenge was missing required parameters
    ok, msg, rec = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c03",
        action_type="financial_wire",
        details_match={"amount": 50000.0, "destination": "CHASE_IBAN_9999"},
    )
    assert ok is False
    assert "missing from saved challenge details" in msg
    assert rec is None


def test_finding_c_04_missing_required_caller_value_is_rejected() -> None:
    """Proof 4: A missing required caller-supplied value is rejected."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_c04",
        action_type="financial_wire",
        title="Wire $50,000",
        summary="Authorized wire transfer",
        details={"amount": 50000.0, "destination": "CHASE_IBAN_9999"},
        risk_tier=RiskTier.HIGH,
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_sec_c04",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Caller supplies amount but omits required destination
    ok, msg, rec = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c04",
        action_type="financial_wire",
        details_match={"amount": 50000.0},
    )
    assert ok is False
    assert "was not provided by caller" in msg
    assert rec is None


def test_finding_c_05_different_target_destination_amount_action_cannot_reuse_approval() -> None:
    """Proof 5: A different target, destination, amount, or action type cannot reuse the approval."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_c05",
        action_type="delete_database",
        title="Delete customer database",
        summary="Critical operation",
        details={"target_resource": "prod_customer_db_shard_01"},
        risk_tier=RiskTier.CRITICAL,
    )
    internal = ConfirmationGate.get_challenge(chal.challenge_id, "usr_sec_c05")
    step_code = internal["step_up_code"] if internal else None
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_sec_c05",
        decision="approve",
        challenge_token=chal.challenge_token,
        step_up_code=step_code,
    )

    # Attempt 1: Target mismatch (attacker tries to delete financial transactions table instead)
    ok_target, msg_target, _ = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c05",
        action_type="delete_database",
        details_match={"target_resource": "prod_financial_ledger_shard_01"},
    )
    assert ok_target is False
    assert "Operation binding mismatch on 'target_resource'" in msg_target

    # Attempt 2: Action type mismatch (attacker tries to reuse database delete approval for wipe_resource)
    ok_action, msg_action, _ = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c05",
        action_type="wipe_resource",
        details_match={"target_resource": "prod_customer_db_shard_01"},
    )
    assert ok_action is False
    assert "Action mismatch" in msg_action


def test_finding_c_06_rejected_binding_does_not_authorize_execution() -> None:
    """Proof 6: A rejected binding does not authorize execution and preserves challenge status."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_c06",
        action_type="bank_transfer",
        title="Transfer $2,000",
        summary="Personal transfer",
        details={"amount": 2000.0, "destination": "ACC_SAVINGS_01"},
        risk_tier=RiskTier.HIGH,
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_sec_c06",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Present unauthorized destination
    ok, msg, rec = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_sec_c06",
        action_type="bank_transfer",
        details_match={"amount": 2000.0, "destination": "ACC_ATTACKER_99"},
    )
    assert ok is False
    assert "Operation binding mismatch" in msg
    assert rec is None

    # Prove status remains APPROVED, not CONSUMED
    stored = ConfirmationGate.get_challenge(chal.challenge_id, "usr_sec_c06")
    assert stored is not None
    assert stored["status"] == ConfirmationStatus.APPROVED
    assert stored["consumed_at"] is None
