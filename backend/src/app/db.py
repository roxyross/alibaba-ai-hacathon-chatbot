"""SQLAlchemy async engine, session, and declarative Base.

T027: Replaces Prisma with SQLAlchemy 2.0 async ORM.
Import Base from here so all models share one metadata registry.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import lru_cache
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Declarative Base — shared by all models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""
    pass


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------

def normalize_database_url(raw: str) -> tuple[str, dict[str, object]]:
    """Return (url, connect_args) suitable for `create_async_engine`.

    - `postgresql://` (sync) is rewritten to `postgresql+asyncpg://` so the
      async engine picks the right driver.
    - `sslmode=require` in the query string is moved to `connect_args` as
      `ssl=True` because asyncpg doesn't accept `sslmode` as a kwarg.
    - `channel_binding=...` is dropped (asyncpg doesn't accept it either; we
      rely on the server default and don't fail the connection over it).
    """
    if not raw:
        return ("postgresql+asyncpg://user:pass@localhost:5432/roxy", {})

    if raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
    elif raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw[len("postgres://") :]

    parts = urlsplit(raw)
    qs = parse_qs(parts.query, keep_blank_values=True)
    sslmode = qs.pop("sslmode", [None])[0]
    qs.pop("channel_binding", None)
    new_query = urlencode({k: v[0] for k, v in qs.items()}, doseq=False)
    url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )
    if sslmode in ("require", "verify-ca", "verify-full"):
        connect_args: dict[str, object] = {"ssl": True}
    elif sslmode == "disable":
        connect_args = {"ssl": False}
    else:
        connect_args = {}
    return url, connect_args


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return a cached async engine built from the DATABASE_URL env var.

    See `normalize_database_url` for the URL/connect_args transformation.
    """
    raw = os.environ.get("DATABASE_URL", "").strip()
    url, connect_args = normalize_database_url(raw)
    return create_async_engine(
        url,
        echo=False,
        poolclass=NullPool,
        future=True,
        connect_args=connect_args,
    )


@lru_cache(maxsize=1)
def _session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    """Public accessor for the session factory, or None if no DB is configured.

    Returns None when DATABASE_URL is not set so callers can fall back to
    in-memory storage in dev/test environments.
    """
    import os
    if not os.environ.get("DATABASE_URL"):
        return None
    return _session_factory()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async session with auto-commit/rollback."""
    factory = _session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Metadata export (for Alembic autogenerate)
# ---------------------------------------------------------------------------
metadata = Base.metadata
