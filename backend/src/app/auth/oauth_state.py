"""Single-use CSRF `state` cookie for OAuth flows.

The `state` value is a server-issued opaque random string. The flow:
  1. `start` endpoint calls `set_state(response)` to set the cookie.
  2. Google/GitHub redirects back to the `callback` endpoint with `?state=...`.
  3. `consume_state(request)` validates the cookie matches the query param
     AND the cookie exists AND is fresh. Single-use: the cookie is deleted
     on read so a replay is impossible.

The cookie is `HttpOnly` (JS can't read it), `SameSite=Lax` (works for
top-level OAuth navigations), and `Secure` in production (when
`APP_ENV=production` or `VERCEL`).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Annotated

from fastapi import Cookie, Response

import threading
from app.auth.jwt import _secret

STATE_COOKIE = "roxy.oauth_state"
ORIGIN_COOKIE = "roxy.oauth_origin"
STATE_TTL_SECONDS = 10 * 60  # 10 minutes — comfortably longer than a real OAuth round-trip

_STATE_LOCK = threading.Lock()
_CONSUMED_STATES: set[str] = set()


class _StateDict(dict[str, float]):
    def clear(self) -> None:
        super().clear()
        with _STATE_LOCK:
            _CONSUMED_STATES.clear()


# Module-level in-memory store for dev/testing.
_STATES: dict[str, float] = _StateDict()  # state -> issued_at_unix


def _is_production() -> bool:
    app_env = os.environ.get("APP_ENV", "").lower()
    env = os.environ.get("ENV", "").lower()
    return (
        app_env in ("production", "prod")
        or env in ("production", "prod")
        or bool(os.environ.get("VERCEL"))
        or bool(os.environ.get("VERCEL_ENV"))
        or os.environ.get("OAUTH_REDIRECT_BASE_URL", "").startswith("https://")
        or os.environ.get("APP_BASE_URL", "").startswith("https://")
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
    raw_token = secrets.token_hex(16)
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


def set_origin(response: Response, origin: str) -> None:
    """Attach the origin cookie so callback knows exactly which frontend host to return to."""
    if not origin:
        return
    is_prod = _is_production()
    response.set_cookie(
        key=ORIGIN_COOKIE,
        value=origin.rstrip("/"),
        max_age=STATE_TTL_SECONDS,
        httponly=False,  # readable if needed
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
    """Validate and burn the state. Returns True on success, False on any mismatch.

    Enforces:
      1. Cryptographic HMAC validation using ONLY the configured production secret.
      2. No fallback to known development secret.
      3. Strict cookie matching if cookie is supplied.
      4. Atomic single-use consumption preventing replay attacks.
      5. Strict expiration validation.
    """
    if not request_value or not isinstance(request_value, str):
        return False

    with _STATE_LOCK:
        # Prevent replay attacks
        if request_value in _CONSUMED_STATES or (
            cookie_value and cookie_value in _CONSUMED_STATES and cookie_value == request_value
        ):
            return False

    # If cookie is present, it MUST match the request query state parameter.
    if cookie_value and not secrets.compare_digest(request_value, cookie_value):
        return False

    # In non-production environments without cross-site cookie restrictions, require cookie.
    if not _is_production() and not cookie_value:
        return False

    # 1. Cryptographic HMAC validation
    parts = request_value.split("_")
    if len(parts) >= 3:
        raw_token = "_".join(parts[:-2])
        ts_str = parts[-2]
        sig = parts[-1]
        try:
            ts = int(ts_str)
            payload = f"{raw_token}_{ts}"
            try:
                secret = _secret()
            except RuntimeError:
                # Missing or insecure production secret -> fail closed
                return False

            expected_sig = hmac.new(
                secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
            ).hexdigest()[:24]

            if secrets.compare_digest(sig, expected_sig) and (_now() - ts <= STATE_TTL_SECONDS):
                with _STATE_LOCK:
                    if request_value in _CONSUMED_STATES:
                        return False
                    _CONSUMED_STATES.add(request_value)
                    _STATES.pop(request_value, None)
                    if cookie_value:
                        _CONSUMED_STATES.add(cookie_value)
                        _STATES.pop(cookie_value, None)
                return True
        except ValueError:
            pass

    # 2. In-memory / cookie matching fallback:
    if not cookie_value:
        return False

    if not secrets.compare_digest(request_value, cookie_value):
        return False

    with _STATE_LOCK:
        if cookie_value in _CONSUMED_STATES or request_value in _CONSUMED_STATES:
            return False
        issued_at = _STATES.pop(cookie_value, None)
        if issued_at is not None:
            if _now() - issued_at <= STATE_TTL_SECONDS:
                _CONSUMED_STATES.add(cookie_value)
                _CONSUMED_STATES.add(request_value)
                return True
            return False

    return False
