"""Magic-link service: create-or-fetch user, mint token, verify & issue JWT."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.auth.email import build_magic_link, send_magic_link
from app.auth.jwt import create_session_token
from app.auth.models import MagicLinkToken, User
from app.db import get_session_factory

if TYPE_CHECKING:
    pass


def _ttl_minutes() -> int:
    from os import getenv
    return int(getenv("MAGIC_LINK_TTL_MINUTES", "15"))


# Module-level in-memory fallback shared by every MagicLinkService instance.
# This matters because FastAPI instantiates the service inside dependencies
# on every request, so a per-instance dict would lose state between the
# request that mints a token and the request that verifies it.
_MEM_USERS: dict[str, User] = {}
_MEM_TOKENS: dict[str, MagicLinkToken] = {}


class MagicLinkService:
    """Handles request-link and verify flows.

    Uses SQLAlchemy async session when DATABASE_URL is configured; falls back
    to in-memory storage otherwise so dev still works without Postgres.
    """

    def __init__(self) -> None:
        # Reference the module-level singletons so the in-memory store is
        # shared across all instances (e.g. test fixtures vs request deps).
        self._mem_users = _MEM_USERS
        self._mem_tokens = _MEM_TOKENS

    async def request_link(self, email: str) -> str:
        """Create-or-fetch user, mint a magic link token, email it. Returns the token."""
        factory = get_session_factory()
        token_value = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=_ttl_minutes()
        )

        if factory is None:
            user = self._mem_users.get(email)
            if user is None:
                user = User(
                    id=secrets.token_urlsafe(16),
                    email=email,
                    created_at=datetime.now(timezone.utc),
                )
                self._mem_users[email] = user
            link = MagicLinkToken(
                token=token_value,
                user_id=user.id,
                expires_at=expires_at,
                created_at=datetime.now(timezone.utc),
            )
            self._mem_tokens[token_value] = link
            asyncio.create_task(send_magic_link(email, build_magic_link(token_value), token_value))
            return token_value

        async with factory() as session:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is None:
                user = User(email=email)
                session.add(user)
                await session.flush()
            else:
                user = existing
            link_row = MagicLinkToken(
                token=token_value, user_id=user.id, expires_at=expires_at
            )
            session.add(link_row)
            await session.commit()

        asyncio.create_task(send_magic_link(email, build_magic_link(token_value), token_value))
        return token_value

    async def verify(self, token_value: str) -> tuple[User, str, int] | None:
        """Consume a magic-link token and issue a JWT. Returns (user, jwt, ttl)."""
        factory = get_session_factory()
        now = datetime.now(timezone.utc)

        if factory is None:
            row = self._mem_tokens.get(token_value)
            if row is None or row.consumed_at is not None or row.expires_at < now:
                return None
            row.consumed_at = now
            user = self._mem_users.get(next(
                (u.email for u in self._mem_users.values() if u.id == row.user_id),
                "",
            ))
            if user is None:
                return None
            user.last_login_at = now
            jwt, ttl = create_session_token(user.id)
            return user, jwt, ttl

        async with factory() as session:
            row = (
                await session.execute(
                    select(MagicLinkToken).where(MagicLinkToken.token == token_value)
                )
            ).scalar_one_or_none()
            if row is None or row.consumed_at is not None or row.expires_at < now:
                return None
            row.consumed_at = now
            user = (
                await session.execute(
                    select(User).where(User.id == row.user_id)
                )
            ).scalar_one_or_none()
            if user is None:
                return None
            user.last_login_at = now
            await session.commit()

        jwt, ttl = create_session_token(user.id)
        return user, jwt, ttl

    async def get_user(self, user_id: str) -> User | None:
        # Check in-memory registry first for 0ms resolution
        for u in self._mem_users.values():
            if str(u.id) == str(user_id):
                return u

        factory = get_session_factory()
        if factory is None:
            return None

        try:
            import asyncio
            async with asyncio.timeout(1.5):
                async with factory() as session:
                    return (
                        await session.execute(select(User).where(User.id == user_id))
                    ).scalar_one_or_none()
        except Exception:
            return None

