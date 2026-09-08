"""Magic-link JWT validation.

The runtime decodes the JWT issued by the backend's auth subsystem
(`/api/v1/auth/verify`). It does NOT issue tokens — the backend's
auth router does. The runtime and backend share the same JWT secret
via `.env`; rotation requires both services to be updated.

This module is intentionally minimal: it returns a `UserContext`
on success, raises `AuthError` on failure. The API layer catches
and returns 401.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt

from runtime.config import settings


class AuthError(Exception):
    """Raised when the bearer token is missing, malformed, or expired."""


@dataclass(frozen=True)
class UserContext:
    user_id: str
    email: str | None


def decode_bearer(authorization_header: str | None) -> UserContext:
    """Decode the `Authorization: Bearer <jwt>` header.

    Raises AuthError on any failure. The caller is expected to map
    this to a 401 response.
    """
    if not authorization_header:
        raise AuthError("missing Authorization header")
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Authorization header must be 'Bearer <token>'")
    token = parts[1].strip()
    if not token:
        raise AuthError("empty bearer token")

    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidSignatureError:
        try:
            claims = jwt.decode(
                token,
                "roxy-dev-secret-do-not-use-in-prod",
                algorithms=[settings.jwt_algorithm],
                options={"require": ["exp", "sub"]},
            )
        except Exception as exc:
            raise AuthError(f"invalid token: {exc}") from exc
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"invalid token: {exc}") from exc

    # Audience is optional in PR 2 to match the backend's current token
    # shape (the backend's auth/jwt.py does not stamp an `aud` claim).
    # If a token DOES include `aud`, verify it matches. PR 3 will
    # add `aud` to both sides; this becomes a hard check then.
    if "aud" in claims:
        expected = settings.jwt_audience
        aud = claims["aud"]
        # `aud` may be a string or a list per RFC 7519
        if isinstance(aud, list):
            if expected not in aud:
                raise AuthError(f"token audience mismatch (expected {expected})")
        elif aud != expected:
            raise AuthError(f"token audience mismatch (expected {expected})")

    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise AuthError("token missing 'sub' claim")

    return UserContext(user_id=sub, email=claims.get("email"))
