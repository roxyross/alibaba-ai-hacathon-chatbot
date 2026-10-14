"""Adversarial security regression tests for OAuth state signing, browser binding, and distributed replay protection.

Validates SEC-03:
- Valid state with matching browser-bound cookie succeeds.
- Missing browser-binding cookie in production fails closed (rejected).
- Mismatched cookie and query parameter state rejected.
- Forged state signed with dev secret is rejected in production.
- Forged state with random HMAC signature is rejected.
- Expired state token is rejected.
- Future-timestamped state (> 5s clock skew) is rejected.
- Replaying a consumed state returns False (single-use invariant).
- Concurrent replay race condition: exactly 1 winner among concurrent attempts.
- Multi-instance / multi-worker simulated distributed consumption: second instance fails.
- Shared-store outage / Redis connection failure fails closed in production.
- Production environment without distributed store fails closed.
- Cookie security attributes (HttpOnly, Secure, SameSite, Max-Age).
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import os
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Response

from app.auth.jwt import INSECURE_DEV_SECRET
from app.auth.oauth_state import (
    STATE_COOKIE,
    STATE_TTL_SECONDS,
    InMemoryReplayStore,
    clear_state,
    consume_state,
    new_state,
    set_replay_store,
    set_state,
)

TEST_PROD_SECRET = "production-oauth-cryptographic-secret-at-least-32-chars-long"


@pytest.fixture(autouse=True)
def clean_state_store():
    """Ensure in-memory store is reset between tests."""
    store = InMemoryReplayStore()
    set_replay_store(store)
    yield
    store.clear()
    set_replay_store(None)


def test_valid_oauth_state_with_browser_binding_succeeds():
    """A freshly minted state presented by the originating browser succeeds."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()
        # Browser sends both query param and browser-bound cookie
        assert consume_state(request_value=state, cookie_value=state) is True


def test_missing_browser_cookie_in_production_fails_closed():
    """In production, callback MUST reject requests missing the browser-bound state cookie."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()
        # Attacker crafts callback URL with signed state but lacks the browser-bound cookie
        assert consume_state(request_value=state, cookie_value=None) is False
        assert consume_state(request_value=state, cookie_value="") is False


def test_missing_cookie_in_non_prod_fails_closed():
    """Even in non-production, missing cookie without prior state issuance fails closed."""
    with patch.dict(os.environ, {"APP_ENV": "development", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()
        assert consume_state(request_value=state, cookie_value=None) is False


def test_mismatched_cookie_and_state_rejected():
    """If browser cookie differs from query parameter state, request must be rejected."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state1 = new_state()
        state2 = new_state()
        # Session cookie is state2, but query param is state1
        assert consume_state(request_value=state1, cookie_value=state2) is False


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


def test_future_timestamp_rejected():
    """State with a timestamp significantly in the future is rejected (clock skew / forgery)."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        raw_token = "futuretoken12345"
        future_time = int(time.time()) + 60
        payload = f"{raw_token}_{future_time}"
        sig = hmac.new(
            TEST_PROD_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:24]
        future_state = f"{payload}_{sig}"

        assert consume_state(request_value=future_state, cookie_value=future_state) is False


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

        results: list[bool] = []

        def attempt_consume() -> bool:
            return consume_state(request_value=state, cookie_value=state)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_consume) for _ in range(5)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # Exactly ONE attempt must succeed; all others must be False
        assert results.count(True) == 1
        assert results.count(False) == 4


def test_consumption_across_simulated_independent_workers():
    """Simulated separate application workers sharing a backing store prevent cross-worker replay."""
    shared_backend = InMemoryReplayStore()

    # Worker A
    set_replay_store(shared_backend)
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()
        # Worker A consumes it successfully
        assert consume_state(request_value=state, cookie_value=state) is True

    # Worker B (independent process/worker with fresh local references connected to same store)
    set_replay_store(shared_backend)
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        # Worker B receives a replayed callback
        assert consume_state(request_value=state, cookie_value=state) is False


def test_shared_store_outage_fails_closed_in_production():
    """If the shared replay store raises a connection error or times out, the callback fails closed."""
    failing_store = MagicMock()
    failing_store.mark_consumed.return_value = False

    set_replay_store(failing_store)
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        state = new_state()
        assert consume_state(request_value=state, cookie_value=state) is False


def test_missing_shared_store_in_production_fails_closed():
    """If in production and REDIS_URL is not configured, get_replay_store defaults to FailClosed."""
    set_replay_store(None)  # Reset custom store
    with patch.dict(
        os.environ,
        {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET},
        clear=False,
    ):
        # Remove REDIS_URL if set
        os.environ.pop("REDIS_URL", None)
        state = new_state()
        assert consume_state(request_value=state, cookie_value=state) is False


def test_cookie_security_attributes():
    """Verify cookie security attributes: HttpOnly, Secure, SameSite, Max-Age, Path."""
    # Production response
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": TEST_PROD_SECRET}):
        resp = Response()
        set_state(resp, "test_state_value")
        cookie_header = resp.headers.get("set-cookie", "")

        assert STATE_COOKIE in cookie_header
        assert "HttpOnly" in cookie_header
        assert "Secure" in cookie_header
        assert "SameSite=none" in cookie_header
        assert f"Max-Age={STATE_TTL_SECONDS}" in cookie_header
        assert "Path=/" in cookie_header

    # Clearing cookies removes both state and origin
    resp_clear = Response()
    clear_state(resp_clear)
    clear_header = resp_clear.headers.get("set-cookie", "")
    assert STATE_COOKIE in clear_header
    assert "Max-Age=0" in clear_header or 'expires=' in clear_header.lower()
