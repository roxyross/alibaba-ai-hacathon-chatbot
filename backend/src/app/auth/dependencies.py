"""FastAPI dependency that resolves the current user from a Bearer JWT."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.auth.jwt import decode_session_payload, decode_session_token
from app.auth.models import User
from app.auth.service import MagicLinkService


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> User:
    """Resolve the authenticated user from the Authorization header.

    Raises 401 if the header is missing, malformed, or the token is invalid.
    """
    token = _bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_session_payload(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = str(payload["sub"])
    email = payload.get("email")

    service = MagicLinkService()
    try:
        user = await service.get_user(user_id)
        if user is not None:
            return user
    except Exception:
        pass

    # If DB is cold, unavailable, or user created in memory, reconstruct
    # verified user from the cryptographically verified JWT.
    if email and isinstance(email, str):
        return User(id=user_id, email=email)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not found",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_current_user(
    authorization: str | None = Header(default=None),
) -> User | None:
    """Resolve the authenticated user if Authorization header is provided, or None if guest."""
    token = _bearer(authorization)
    if not token:
        return None
    payload = decode_session_payload(token)
    if not payload or not payload.get("sub"):
        return None
    user_id = str(payload["sub"])
    email = payload.get("email")
    try:
        service = MagicLinkService()
        user = await service.get_user(user_id)
        if user is not None:
            return user
    except Exception:
        pass
    if email and isinstance(email, str):
        return User(id=user_id, email=email)
    return None
