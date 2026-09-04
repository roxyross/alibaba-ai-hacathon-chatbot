"""JWT helpers for short-lived session tokens."""

from __future__ import annotations

import os
import time
from typing import Any

import jwt


def _secret() -> str:
    s = os.environ.get("JWT_SECRET")
    if not s:
        # Dev fallback so the app boots even without env config. NOT for prod.
        s = "roxy-dev-secret-do-not-use-in-prod"
    return s


def _expiry_seconds() -> int:
    hours = int(os.environ.get("JWT_EXPIRY_HOURS", "168"))  # default 7 days
    return hours * 3600


def create_session_token(user_id: str) -> tuple[str, int]:
    """Create a signed JWT for the given user. Returns (token, expires_in_seconds)."""
    exp = int(time.time()) + _expiry_seconds()
    payload: dict[str, Any] = {"sub": user_id, "exp": exp, "iat": int(time.time())}
    token = jwt.encode(payload, _secret(), algorithm="HS256")
    return token, _expiry_seconds()


def decode_session_token(token: str) -> str | None:
    """Decode and validate a session token. Returns the user_id, or None on failure."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    if not isinstance(sub, str):
        return None
    return sub
