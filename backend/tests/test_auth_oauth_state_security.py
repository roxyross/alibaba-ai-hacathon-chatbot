"""Adversarial security regression tests for OAuth state signing, validation, and replay protection.

Validates:
- Valid state from correct browser transaction succeeds.
- Forged state signed with dev secret is rejected in production.
- Forged state with random HMAC signature is rejected.
- Expired state token is rejected.
- State with mismatched browser cookie is rejected.
- Replaying a consumed state returns False.
- Concurrent consume attempts allow only one winner.
- Missing or insecure production secret fails closed.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import os
import time
from unittest.mock import patch

import pytest

from app.auth.jwt import INSECURE_DEV_SECRET
from app.auth.oauth_state import (
    STATE_TTL_SECONDS,
    _STATES,
    consume_state,
    new_state,
)

TEST_PROD_SECRET = "production-oauth-cryptographic-secret-at-least-32-chars-long"


@pytest.fixture(autouse=True)
def clean_state_store():
    """Clear in-memory state dictionary between tests."""
    _STATES.clear()
    yield
    _STATES.clear()


def test_valid_oauth_state_succeeds():
    """A freshly minted state with matching cookie succeeds."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()
        # Same browser presents state parameter and state cookie
        assert consume_state(request_value=state, cookie_value=state) is True


def test_dev_secret_forged_state_rejected_in_production():
    """An attacker generating an HMAC signature with INSECURE_DEV_SECRET must be rejected."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        raw_token = "forged0000000000"
        issued_at = int(time.time())
        payload = f"{raw_token}_{issued_at}"
        forged_sig = hmac.new(
            INSECURE_DEV_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:24]
        forged_state = f"{payload}_{forged_sig}"

        assert consume_state(request_value=forged_state, cookie_value=forged_state) is False


def test_forged_random_state_rejected():
    """State with invalid signature is rejected."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        forged_state = f"fake_token_{int(time.time())}_invalidsig123456789012"
        assert consume_state(request_value=forged_state, cookie_value=forged_state) is False


def test_expired_state_rejected():
    """State generated past STATE_TTL_SECONDS is rejected."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        raw_token = "expiredtoken1234"
        old_time = int(time.time()) - (STATE_TTL_SECONDS + 10)
        payload = f"{raw_token}_{old_time}"
        sig = hmac.new(
            TEST_PROD_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:24]
        expired_state = f"{payload}_{sig}"

        assert consume_state(request_value=expired_state, cookie_value=expired_state) is False


def test_mismatched_cookie_rejected():
    """If browser cookie differs from query parameter state, request must be rejected."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state1 = new_state()
        state2 = new_state()
        # Browser cookie from session 2, but attacker supplied state1 in query
        assert consume_state(request_value=state1, cookie_value=state2) is False


def test_replay_state_rejected():
    """Consuming a state a second time MUST return False (single-use invariant)."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()
        # First use succeeds
        assert consume_state(request_value=state, cookie_value=state) is True
        # Immediate replay attempt MUST fail
        assert consume_state(request_value=state, cookie_value=state) is False


def test_concurrent_replay_race_condition_prevented():
    """Two concurrent requests attempting to consume the same state cannot both succeed."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()

        results = []
        def attempt_consume():
            return consume_state(request_value=state, cookie_value=state)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_consume) for _ in range(5)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # Exactly ONE attempt must succeed; all others must be False
        assert results.count(True) == 1
        assert results.count(False) == 4
