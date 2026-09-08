"""Single-use CSRF `state` cookie for OAuth flows.

The `state` value is a server-issued opaque random string. The flow:
  1. `start` endpoint calls `set_state(response)` to set the cookie.
  2. Google redirects back to the `callback` endpoint with `?state=...`.
  3. `consume_state(request)` validates the cookie matches the query param
     AND the cookie exists AND is fresh. Single-use: the cookie is deleted
     on read so a replay is impossible.

The cookie is `HttpOnly` (JS can't read it), `SameSite=Lax` (works for
top-level OAuth navigations), and `Secure` in production (when
`APP_ENV=production`).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Annotated

from fastapi import Cookie, Response

from app.auth.jwt import _secret

STATE_COOKIE = "roxy.oauth_state"
STATE_TTL_SECONDS = 10 * 60  # 10 minutes — comfortably longer than a real OAuth round-trip

# Module-level in-memory store for dev/testing.
_STATES: dict[str, float] = {}  # state -> issued_at_unix


def _is_production() -> bool:
    return (
        os.environ.get("APP_ENV", "").lower() == "production"
        or bool(os.environ.get("VERCEL"))
        or os.environ.get("OAUTH_REDIRECT_BASE_URL", "").startswith("https://")
    )


def _now() -> float:
    import time
    return time.time()


def new_state() -> str:
    """Generate a fresh state value (caller must `set_state` it on a response).
    
    Generates a cryptographically signed HMAC state token that can be verified
    across serverless invocations (e.g. on Vercel) even if the container restarts
    or cookies are partitioned across domains.
    """
    raw_token = secrets.token_urlsafe(20)
    issued_at = int(_now())
    payload = f"{raw_token}_{issued_at}"
    sig = hmac.new(
        _secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24]
    value = f"{payload}_{sig}"

    _STATES[value] = float(issued_at)
    # Lazy GC of expired entries to keep the dict bounded.
    cutoff = _now() - STATE_TTL_SECONDS
    for k in [k for k, t in _STATES.items() if t < cutoff]:
        _STATES.pop(k, None)
    return value


def set_state(response: Response, value: str) -> None:
    """Attach the state cookie to an outgoing response."""
    is_prod = _is_production()
    response.set_cookie(
        key=STATE_COOKIE,
        value=value,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=is_prod,
        samesite="none" if is_prod else "lax",
        path="/",  # root path so all routes and redirects receive it
    )


_CONSUMED_STATES: set[str] = set()


def consume_state(
    request_value: str | None,
    cookie_value: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
) -> bool:
    """Validate and burn the state. Returns True on success, False on any mismatch.

    Supports:
      1. Cookie matching with in-memory store (local dev & tests).
      2. Serverless HMAC cryptographic validation (stateless across Vercel lambdas
         where memory is not shared between invocations).
    """
    if not request_value or not cookie_value:
        return False

    if not secrets.compare_digest(request_value, cookie_value):
        return False

    # Prevent replay attacks
    if cookie_value in _CONSUMED_STATES or request_value in _CONSUMED_STATES:
        return False

    # 1. In-memory exact match check (tests & local dev)
    issued_at = _STATES.pop(cookie_value, None)
    if issued_at is not None:
        if _now() - issued_at <= STATE_TTL_SECONDS:
            _CONSUMED_STATES.add(cookie_value)
            _CONSUMED_STATES.add(request_value)
            return True
        return False

    # 2. Serverless HMAC verification (stateless & cross-container on Vercel)
    parts = request_value.split("_")
    if len(parts) >= 3:
        raw_token = "_".join(parts[:-2])
        ts_str = parts[-2]
        sig = parts[-1]
        try:
            ts = int(ts_str)
            payload = f"{raw_token}_{ts}"
            for secret_candidate in (_secret(), "roxy-dev-secret-do-not-use-in-prod"):
                expected_sig = hmac.new(
                    secret_candidate.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
                ).hexdigest()[:24]

                if secrets.compare_digest(sig, expected_sig):
                    if _now() - ts <= STATE_TTL_SECONDS:
                        _CONSUMED_STATES.add(cookie_value)
                        _CONSUMED_STATES.add(request_value)
                        return True
        except ValueError:
            pass

    return False

