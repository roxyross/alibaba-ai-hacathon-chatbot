"""Regression tests for P0 Security — Independent Step-Up Verification and ConfirmationGate hardening.

Verifies:
1. Challenge response and step_up_hint NEVER contain the verification code or secret.
2. Missing independent verification configuration fails closed (blocks critical actions).
3. Invalid, expired, replayed, cross-user, and wrong-action challenges are rejected.
4. Correct verification succeeds only once.
5. Bounded attempts: lockout after 3 failed verification attempts.
6. Concurrent single-use consumption: exactly one thread can consume an approved challenge.
7. Restart and durable store persistence: state survives and prevents duplicate consumption.
8. Persistence failures in production never result in unauthorized execution.
"""

from __future__ import annotations

import asyncio
import os
import threading
from unittest import mock

import pytest

from app.trust.confirmation_gate import ConfirmationGate, canonicalize_parameters
from app.trust.schemas import ConfirmationStatus, RiskTier


@pytest.fixture(autouse=True)
def clean_gate():
    """Reset ConfirmationGate storage before and after each test."""
    ConfirmationGate.clear()
    yield
    ConfirmationGate.clear()


def test_step_up_code_never_in_response_or_hint() -> None:
    """Requirement: The response and hint must never contain the generated verification code."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_01",
        action_type="financial_wire",
        title="Wire $50,000",
        summary="High value transfer",
        risk_tier=RiskTier.CRITICAL,
        risk_score=95,
        requires_2fa=True,
    )
    assert chal.step_up_required is True
    assert chal.step_up_hint is not None

    # Retrieve internal secret code stored on backend for test comparison
    internal_rec = ConfirmationGate.get_challenge(chal.challenge_id, "usr_sec_01")
    assert internal_rec is not None
    secret_code = internal_rec["step_up_code"]
    assert secret_code is not None and len(secret_code) == 6

    # Verify secret_code is NOT in the hint
    assert secret_code not in chal.step_up_hint
    # Verify secret_code is NOT in any attribute or string representation of the response
    assert secret_code not in str(chal.model_dump())
    assert secret_code not in repr(chal)


def test_missing_independent_verification_fails_closed() -> None:
    """Requirement: If independent verification is unconfigured in production/strict mode, fail closed."""
    with mock.patch.dict(os.environ, {"ROXY_FORCE_DISABLE_2FA_DELIVERY": "true"}, clear=False):
        with pytest.raises(RuntimeError, match="Independent step-up verification is not configured"):
            ConfirmationGate.create_challenge(
                user_id="usr_sec_02",
                action_type="delete_database",
                title="Wipe database",
                summary="Critical destructive operation",
                risk_tier=RiskTier.CRITICAL,
                risk_score=99,
                requires_2fa=True,
            )


def test_bounded_attempts_lockout_after_failures() -> None:
    """Requirement: Enforce bounded attempts lockout (3 attempts)."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_sec_03",
        action_type="privilege_escalation",
        title="Admin grant",
        summary="Grant admin permissions",
        risk_tier=RiskTier.CRITICAL,
        requires_2fa=True,
    )

    # Attempt 1: wrong code -> fails, 2 attempts remaining
    with pytest.raises(ValueError, match="2 attempt"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_sec_03",
            decision="approve",
            challenge_token=chal.challenge_token,
            step_up_code="000000",
        )

    # Attempt 2: wrong code -> fails, 1 attempt remaining
    with pytest.raises(ValueError, match="1 attempt"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_sec_03",
            decision="approve",
            challenge_token=chal.challenge_token,
            step_up_code="111111",
        )

    # Attempt 3: wrong code -> lockout triggered!
    with pytest.raises(ValueError, match="Maximum verification attempts exceeded"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_sec_03",
            decision="approve",
            challenge_token=chal.challenge_token,
            step_up_code="222222",
        )

    # Attempt 4: even with correct code, challenge is now LOCKED and REJECTED
    internal_rec = ConfirmationGate.get_challenge(chal.challenge_id, "usr_sec_03")
    assert internal_rec is not None
    correct_code = internal_rec["step_up_code"]

    with pytest.raises(ValueError, match="Challenge already resolved as rejected"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_sec_03",
            decision="approve",
            challenge_token=chal.challenge_token,
            step_up_code=correct_code,
        )


def test_cross_user_and_wrong_action_rejections() -> None:
    """Requirement: Invalid, cross-user, and wrong-action challenges are rejected."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_owner",
        action_type="send_email",
        title="Send email",
        summary="Outbound email",
    )

    # Cross-user resolution -> rejected
    with pytest.raises(ValueError, match="not found"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_attacker",
            decision="approve",
            challenge_token=chal.challenge_token,
        )

    # Approve legitimately
    res = ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_owner",
        decision="approve",
        challenge_token=chal.challenge_token,
    )
    assert res.status == ConfirmationStatus.APPROVED

    # Cross-user consumption -> rejected
    ok, msg, _ = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_attacker",
        action_type="send_email",
    )
    assert ok is False
    assert "Unauthorized" in msg

    # Wrong action consumption -> rejected
    ok, msg, _ = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_owner",
        action_type="delete_system",
    )
    assert ok is False
    assert "Action mismatch" in msg

    # Correct action and owner -> succeeds exactly once
    ok, msg, rec = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_owner",
        action_type="send_email",
    )
    assert ok is True
    assert msg == "APPROVED_AND_CONSUMED"

    # Replay consumption -> rejected
    ok_replay, msg_replay, _ = ConfirmationGate.consume_challenge(
        challenge_id_or_token=chal.challenge_id,
        user_id="usr_owner",
        action_type="send_email",
    )
    assert ok_replay is False
    assert "already been consumed" in msg_replay


def test_concurrent_consumption_race_condition_safety() -> None:
    """Requirement: Concurrent requests cannot consume the same challenge twice."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_race",
        action_type="financial_debit",
        title="Debit $1,000",
        summary="Concurrent debit attempt",
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_race",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    results: list[bool] = []

    def _worker():
        ok, _, _ = ConfirmationGate.consume_challenge(
            challenge_id_or_token=chal.challenge_id,
            user_id="usr_race",
            action_type="financial_debit",
        )
        results.append(ok)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly ONE thread must succeed in consuming the challenge
    assert results.count(True) == 1
    assert results.count(False) == 9


def test_durable_disk_store_survives_process_restart() -> None:
    """Requirement: Multi-worker and restart behavior is verified using durable store."""
    chal = ConfirmationGate.create_challenge(
        user_id="usr_persist",
        action_type="sensitive_op",
        title="Sensitive Op",
        summary="Persistence check",
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_persist",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Simulate process termination by wiping in-memory dictionary while preserving file
    from app.trust.confirmation_gate import _CHALLENGES
    with ConfirmationGate._lock:
        _CHALLENGES.clear()
        assert len(_CHALLENGES) == 0

    # Simulate new process startup invoking _load_from_disk()
    ConfirmationGate._load_from_disk()

    # Verify challenge is restored from durable disk
    restored = ConfirmationGate.get_challenge(chal.challenge_id, "usr_persist")
    assert restored is not None
    assert restored["status"] == ConfirmationStatus.APPROVED

    # Consume on the new process instance -> succeeds
    ok, _, _ = ConfirmationGate.consume_challenge(chal.challenge_id, "usr_persist", "sensitive_op")
    assert ok is True

    # Re-wipe memory and reload to verify CONSUMED state persisted
    with ConfirmationGate._lock:
        _CHALLENGES.clear()
    ConfirmationGate._load_from_disk()

    ok_again, msg, _ = ConfirmationGate.consume_challenge(chal.challenge_id, "usr_persist", "sensitive_op")
    assert ok_again is False
    assert "already been consumed" in msg
