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

import os
import secrets
from typing import Annotated

from fastapi import Cookie, Response

STATE_COOKIE = "roxy.oauth_state"
STATE_TTL_SECONDS = 10 * 60  # 10 minutes — comfortably longer than a real OAuth round-trip

# Module-level in-memory store. Mirrors the dev fallback in auth/service.py:
# in production (DATABASE_URL set), we still keep the in-memory store because
# state is ephemeral and single-use, so a process restart simply invalidates
# in-flight flows — an acceptable trade for not adding a DB round-trip per
# OAuth start.
_STATES: dict[str, float] = {}  # state -> issued_at_unix


def _is_production() -> bool:
    return os.environ.get("APP_ENV", "").lower() == "production"


def _now() -> float:
    import time
    return time.time()


def new_state() -> str:
    """Generate a fresh state value (caller must `set_state` it on a response)."""
    value = secrets.token_urlsafe(32)
    _STATES[value] = _now()
    # Lazy GC of expired entries to keep the dict bounded.
    cutoff = _now() - STATE_TTL_SECONDS
    for k in [k for k, t in _STATES.items() if t < cutoff]:
        _STATES.pop(k, None)
    return value


def set_state(response: Response, value: str) -> None:
    """Attach the state cookie to an outgoing response."""
    response.set_cookie(
        key=STATE_COOKIE,
        value=value,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=_is_production(),
        samesite="lax",
        path="/api/v1/auth",  # only sent to auth routes
    )


def consume_state(
    request_value: str | None,
    cookie_value: Annotated[str | None, Cookie(alias=STATE_COOKIE)] = None,
) -> bool:
    """Validate and burn the state. Returns True on success, False on any mismatch.

    Failure modes (all return False; we don't disclose which):
      - state missing from query
      - state cookie missing
      - state values don't match
      - state expired or already consumed
    """
    if not request_value or not cookie_value:
        return False
    if not secrets.compare_digest(request_value, cookie_value):
        return False
    issued_at = _STATES.pop(cookie_value, None)
    if issued_at is None:
        return False  # already consumed or never issued
    if _now() - issued_at > STATE_TTL_SECONDS:
        return False
    return True
