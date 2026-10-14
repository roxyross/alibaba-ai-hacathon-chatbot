"""Single-use CSRF `state` cookie and distributed replay protection for OAuth flows.

The `state` value is a cryptographically signed HMAC token bound to the browser session.
The flow:
  1. `start` endpoint calls `new_state()` and attaches it via `set_state(response, state)`.
  2. Google/GitHub redirects back to `callback` with query parameter `?state=...`.
  3. `consume_state(request_value, cookie_value)`:
     - In production: strictly requires the browser-bound `roxy.oauth_state` cookie.
     - Verifies cryptographic HMAC signature against configured JWT_SECRET.
     - Rejects expired (past STATE_TTL_SECONDS) or clock-skewed state tokens.
     - Validates constant-time equality between query parameter state and browser cookie.
     - Atomically marks the token as consumed in a distributed shared store (Redis),
       failing closed if the production replay store is unavailable or missing.
     - Deletes/clears the cookie to prevent client-side replay.

Cookie attributes:
  - `HttpOnly`: True (JS cannot read or exfiltrate).
  - `SameSite`: "none" in production (for top-level cross-site OAuth redirects with Secure)
    or "lax" in non-production.
  - `Secure`: True in production or HTTPS environments.
  - `Path`: "/" (available across all subpaths).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Annotated, Protocol

import structlog
from fastapi import Cookie, Response

from app.auth.jwt import _secret

log = structlog.get_logger()

STATE_COOKIE = "roxy.oauth_state"
ORIGIN_COOKIE = "roxy.oauth_origin"
STATE_TTL_SECONDS = 10 * 60  # 10 minutes


def _is_production() -> bool:
    """Detect whether current execution environment is a production deployment."""
    app_env = os.environ.get("APP_ENV", "").lower()
    env = os.environ.get("ENV", "").lower()
    environment = os.environ.get("ENVIRONMENT", "").lower()
    return (
        app_env in ("production", "prod")
        or env in ("production", "prod")
        or environment in ("production", "prod")
        or bool(os.environ.get("VERCEL"))
        or bool(os.environ.get("VERCEL_ENV"))
        or bool(os.environ.get("VERCEL_URL"))
        or os.environ.get("OAUTH_REDIRECT_BASE_URL", "").startswith("https://")
        or os.environ.get("APP_BASE_URL", "").startswith("https://")
    )


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Replay Store Abstraction (Distributed Redis / In-Memory / Fail-Closed)
# ---------------------------------------------------------------------------

class ReplayStore(Protocol):
    def mark_consumed(self, state_value: str) -> bool:
        """Atomically mark a state as consumed. Returns True on success, False if already consumed or store error."""
        ...

    def is_consumed(self, state_value: str) -> bool:
        ...

    def clear(self) -> None:
        ...


class InMemoryReplayStore:
    """Thread-safe in-memory store for local development and non-production testing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consumed: dict[str, float] = {}  # state -> consumed_at

    def mark_consumed(self, state_value: str) -> bool:
        with self._lock:
            now = _now()
            # Evict expired entries
            cutoff = now - (STATE_TTL_SECONDS * 2)
            for k in [k for k, t in self._consumed.items() if t < cutoff]:
                self._consumed.pop(k, None)

            if state_value in self._consumed:
                return False
            self._consumed[state_value] = now
            return True

    def is_consumed(self, state_value: str) -> bool:
        with self._lock:
            return state_value in self._consumed

    def clear(self) -> None:
        with self._lock:
            self._consumed.clear()


class RedisReplayStore:
    """Distributed Redis store for atomic single-use state consumption across workers."""

    def __init__(self, redis_url: str) -> None:
        import redis
        self._redis_url = redis_url
        self._client: redis.Redis = redis.Redis.from_url(
            redis_url,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            decode_responses=True,
        )

    def _key(self, state_value: str) -> str:
        digest = hashlib.sha256(state_value.encode("utf-8")).hexdigest()
        return f"roxy:oauth:consumed:{digest}"

    def mark_consumed(self, state_value: str) -> bool:
        key = self._key(state_value)
        try:
            # SET key "1" EX ttl NX -> returns True if key was set, None if key already existed
            res = self._client.set(key, "1", ex=STATE_TTL_SECONDS, nx=True)
            return bool(res)
        except Exception as exc:
            log.error("oauth_state.redis_store_error", error=str(exc))
            # Fails closed on Redis outage or connection failure
            return False

    def is_consumed(self, state_value: str) -> bool:
        key = self._key(state_value)
        try:
            return bool(self._client.exists(key))
        except Exception as exc:
            log.error("oauth_state.redis_store_error", error=str(exc))
            return True  # Fail closed: assume consumed if store check fails

    def clear(self) -> None:
        try:
            keys = self._client.keys("roxy:oauth:consumed:*")
            if keys:
                self._client.delete(*keys)
        except Exception as exc:
            log.warning("oauth_state.redis_clear_error", error=str(exc))


class FailClosedReplayStore:
    """Sentinel store used when production requires distributed replay protection but none is configured."""

    def mark_consumed(self, state_value: str) -> bool:
        log.error(
            "oauth_state.missing_production_replay_store",
            detail="Production OAuth requires a distributed replay protection store (REDIS_URL). Failing closed to prevent replay vulnerabilities across horizontal instances.",
        )
        return False

    def is_consumed(self, state_value: str) -> bool:
        return True

    def clear(self) -> None:
        pass


_CUSTOM_REPLAY_STORE: ReplayStore | None = None
_IN_MEMORY_STORE = InMemoryReplayStore()

# Module-level dictionary for backward compatibility with existing tests
_STATES: dict[str, float] = {}  # state -> issued_at_unix


def set_replay_store(store: ReplayStore | None) -> None:
    """Override replay store (used by test fixtures and dependency injection)."""
    global _CUSTOM_REPLAY_STORE
    _CUSTOM_REPLAY_STORE = store


def get_replay_store() -> ReplayStore:
    """Resolve the active replay protection store based on environment and configuration."""
    if _CUSTOM_REPLAY_STORE is not None:
        return _CUSTOM_REPLAY_STORE

    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            return RedisReplayStore(redis_url)
        except Exception as exc:
            log.error("oauth_state.redis_init_failed", error=str(exc))
            if _is_production():
                return FailClosedReplayStore()

    if _is_production():
        return FailClosedReplayStore()

    return _IN_MEMORY_STORE


# ---------------------------------------------------------------------------
# State Generation & Validation
# ---------------------------------------------------------------------------

def new_state() -> str:
    """Generate a fresh cryptographically signed state token."""
    raw_token = secrets.token_hex(16)
    issued_at = int(_now())
    payload = f"{raw_token}_{issued_at}"
    secret = _secret()
    sig = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24]
    value = f"{payload}_{sig}"

    _STATES[value] = float(issued_at)
    return value


def set_state(response: Response, value: str) -> None:
    """Attach the state cookie to an outgoing response with hardened security attributes."""
    is_prod = _is_production()
    response.set_cookie(
        key=STATE_COOKIE,
        value=value,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        path="/",
    )


def set_origin(response: Response, origin: str) -> None:
    """Attach the origin cookie so callback knows exactly which frontend host to return to."""
    if not origin:
        return
    is_prod = _is_production()
    response.set_cookie(
        key=ORIGIN_COOKIE,
        value=origin.rstrip("/"),
        max_age=STATE_TTL_SECONDS,
        httponly=False,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        path="/",
    )


def clear_state(response: Response) -> None:
    """Clear the state and origin cookies from the response."""
    is_prod = _is_production()
    response.delete_cookie(
        key=STATE_COOKIE,
        path="/",
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
    )
    response.delete_cookie(
        key=ORIGIN_COOKIE,
        path="/",
        httponly=False,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
    )


def consume_state(
    request_value: str | None,
    cookie_value: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
) -> bool:
    """Validate and atomically consume the state token.

    Enforces:
      1. Browser binding: browser-bound cookie is strictly REQUIRED in production.
      2. Constant-time digest equality between request query param and browser cookie.
      3. Cryptographic HMAC validation using ONLY the configured production secret.
      4. Freshness within STATE_TTL_SECONDS (and protection against future timestamps).
      5. Atomic single-use consumption in distributed replay store across serverless/worker nodes.
      6. Fail-closed posture if replay store is unavailable or missing in production.
    """
    if not request_value or not isinstance(request_value, str):
        return False

    # 1. Enforce browser-binding cookie
    if not cookie_value:
        log.warning("oauth_state.missing_browser_cookie")
        return False

    # Cookie MUST match request_value constant-time
    if not secrets.compare_digest(request_value, cookie_value):
        log.warning("oauth_state.cookie_mismatch")
        return False

    # 2. Cryptographic HMAC validation & TTL check
    parts = request_value.split("_")
    if len(parts) < 3:
        return False

    raw_token = "_".join(parts[:-2])
    ts_str = parts[-2]
    sig = parts[-1]

    try:
        ts = int(ts_str)
    except ValueError:
        return False

    now = _now()
    # Reject expired state or future-dated state (clock skew allowance max 5s)
    if (now - ts > STATE_TTL_SECONDS) or (ts - now > 5.0):
        log.warning("oauth_state.expired_or_future_timestamp", ts=ts, now=now)
        return False

    payload = f"{raw_token}_{ts}"
    try:
        secret = _secret()
    except RuntimeError:
        # Missing or weak production secret -> fail closed
        log.error("oauth_state.insecure_secret_fail_closed")
        return False

    expected_sig = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24]

    if not secrets.compare_digest(sig, expected_sig):
        log.warning("oauth_state.invalid_signature")
        return False

    # 3. Atomic Single-Use Consumption in Replay Store
    store = get_replay_store()
    if not store.mark_consumed(request_value):
        log.warning("oauth_state.replay_detected_or_store_failure")
        return False

    if cookie_value and cookie_value != request_value:
        store.mark_consumed(cookie_value)

    _STATES.pop(request_value, None)
    if cookie_value:
        _STATES.pop(cookie_value, None)

    return True
