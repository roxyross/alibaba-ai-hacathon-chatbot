"""Async PostgreSQL engine with pgvector support.

Shares the same DATABASE_URL pattern as the backend (Neon PostgreSQL).
The pgvector extension must be enabled in the database:
  CREATE EXTENSION IF NOT EXISTS vector;

Schema (run once or via Alembic):
  CREATE TABLE document_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_name TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   vector(768),
    created_at  TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100) WHERE user_id = current_user_id;  -- per-user index

Uses asyncpg directly for performance-critical vector operations, with
SQLAlchemy 2.0 async for ORM-level queries.
"""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from runtime.config import settings

log = structlog.get_logger()


def _normalize_database_url(raw: str) -> tuple[str, dict]:
    """Convert `postgresql://` to `postgresql+asyncpg://` and handle sslmode."""
    if not raw:
        return "postgresql+asyncpg://", {}
    if raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
    elif raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw[len("postgres://") :]
    parts = urlsplit(raw)
    qs = parse_qs(parts.query, keep_blank_values=True)
    sslmode = qs.pop("sslmode", [None])[0]
    qs.pop("channel_binding", None)
    new_query = urlencode({k: v[0] for k, v in qs.items()}, doseq=False)
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    if sslmode in ("require", "verify-ca", "verify-full"):
        connect_args = {"ssl": True}
    elif sslmode == "disable":
        connect_args = {"ssl": False}
    else:
        connect_args = {}
    return url, connect_args


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Cached async engine from DATABASE_URL."""
    raw = os.environ.get("DATABASE_URL", settings.database_url or "").strip()
    if not raw:
        log.warning("db.no_url_configured")
        raw = ""
    url, connect_args = _normalize_database_url(raw)
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
    """Public accessor; returns None if no DATABASE_URL is set."""
    raw = os.environ.get("DATABASE_URL", settings.database_url or "").strip()
    if not raw:
        return None
    return _session_factory()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a request-scoped async session."""
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


async def ensure_vector_extension() -> None:
    """Ensure pgvector extension is enabled. Idempotent; run at startup."""
    factory = get_session_factory()
    if factory is None:
        log.warning("db.not_configured.skip_extension_check")
        return
    async with factory() as session:
        await session.execute(
            "CREATE EXTENSION IF NOT EXISTS vector"
        )
        await session.commit()
        log.info("db.pgvector.extension.ready")
