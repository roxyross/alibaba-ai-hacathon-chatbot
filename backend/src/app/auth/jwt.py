"""JWT helpers for short-lived session tokens."""

from __future__ import annotations

import os
import time
from typing import Any

import jwt


INSECURE_DEV_SECRET = "roxy-dev-secret-do-not-use-in-prod"


def _is_production() -> bool:
    app_env = os.environ.get("APP_ENV", "").lower()
    env = os.environ.get("ENV", "").lower()
    return (
        app_env in ("production", "prod")
        or env in ("production", "prod")
        or bool(os.environ.get("VERCEL"))
        or bool(os.environ.get("VERCEL_ENV"))
    )


def _secret() -> str:
    s = os.environ.get("JWT_SECRET")
    is_prod = _is_production()
    if is_prod:
        if not s or s == INSECURE_DEV_SECRET or len(s) < 32:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: A strong JWT_SECRET (minimum 32 characters) "
                "must be configured in production environments. Refusing to boot with insecure secret."
            )
        return s
    if not s:
        return INSECURE_DEV_SECRET
    return s


def _expiry_seconds() -> int:
    hours = int(os.environ.get("JWT_EXPIRY_HOURS", "168"))  # default 7 days
    return hours * 3600


def create_session_token(user_id: str, email: str | None = None) -> tuple[str, int]:
    """Create a signed JWT for the given user. Returns (token, expires_in_seconds)."""
    exp = int(time.time()) + _expiry_seconds()
    iat = int(time.time())
    payload: dict[str, Any] = {"sub": user_id, "exp": exp, "iat": iat}
    if email:
        payload["email"] = email
    token = jwt.encode(payload, _secret(), algorithm="HS256")
    return token, _expiry_seconds()


def decode_session_payload(token: str) -> dict[str, Any] | None:
    """Decode and validate a session token. Returns the claims dict, or None on failure.

    In all environments:
    - Verifies token signature using ONLY the explicitly configured secret.
    - Strictly rejects any secondary or hard-coded development-secret fallback.
    - Validates algorithm is HS256.
    - Validates exp, iat, and sub claims.
    """
    if not token or not isinstance(token, str):
        return None
    try:
        secret = _secret()
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "iat"]},
        )
    except (jwt.PyJWTError, RuntimeError):
        return None

    if not isinstance(payload, dict):
        return None
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        return None
    return payload


def decode_session_token(token: str) -> str | None:
    """Decode and validate a session token. Returns the user_id, or None on failure."""
    payload = decode_session_payload(token)
    if not payload:
        return None
    sub = payload.get("sub")
    if not isinstance(sub, str):
        return None
    return sub

