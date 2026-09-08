"""store_memory skill — persist a user memory entry to Neon DB.

Schema (created automatically if not exists):
  CREATE TABLE IF NOT EXISTS memory_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    content         TEXT NOT NULL,
    importance      TEXT NOT NULL DEFAULT 'normal',
    tags            TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retrieved_count INTEGER NOT NULL DEFAULT 0,
    soft_deleted    BOOLEAN NOT NULL DEFAULT FALSE,
    permanent       BOOLEAN NOT NULL DEFAULT FALSE
  );
  CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_entries(user_id);
  CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_entries(user_id, created_at DESC);
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg
import structlog

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_MEM_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    content         TEXT NOT NULL,
    importance      TEXT NOT NULL DEFAULT 'normal',
    tags            TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retrieved_count INTEGER NOT NULL DEFAULT 0,
    soft_deleted    BOOLEAN NOT NULL DEFAULT FALSE,
    permanent       BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_entries(user_id, created_at DESC);
"""

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        url = settings.database_url
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        log.info("memory.store.pool.created")
    return _pool


async def _ensure_table() -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_MEM_TABLE_SQL)


async def store_memory(
    content: str,
    importance: str = "normal",
    tags: list[str] | None = None,
    permanent: bool = False,
    *,
    user_id: str,
) -> SkillResult:
    """Store a memory entry for the user.

    Args:
        content: The memory text to store.
        importance: "low" | "normal" | "forever". Default "normal".
        tags: Optional list of tag strings.
        permanent: If True, marks as permanent (never auto-pruned).
        user_id: The user making the request.

    Returns:
        SkillResult with the stored entry metadata.
    """
    log.info(
        "store_memory.invoked",
        user_id=user_id,
        content_len=len(content),
        importance=importance,
    )

    if importance not in ("low", "normal", "forever"):
        return SkillResult(
            ok=False,
            data=None,
            error="importance must be 'low', 'normal', or 'forever'",
        )

    if not content or not content.strip():
        return SkillResult(ok=False, data=None, error="content cannot be empty")

    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    tags = tags or []
    importance = importance.lower()

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            # Ensure table exists
            await conn.execute(_MEM_TABLE_SQL)

            row = await conn.fetchrow(
                """
                INSERT INTO memory_entries
                    (id, user_id, content, importance, tags, created_at, permanent)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, created_at, importance, tags, retrieved_count, permanent
                """,
                uuid.UUID(entry_id),
                user_id,
                content.strip(),
                importance,
                tags,
                now,
                permanent,
            )

        log.info(
            "store_memory.stored",
            user_id=user_id,
            entry_id=entry_id,
            importance=importance,
        )

        return SkillResult(
            ok=True,
            data={
                "id": str(row["id"]),
                "created_at": row["created_at"].isoformat(),
                "importance": row["importance"],
                "tags": row["tags"],
                "retrieved_count": row["retrieved_count"],
                "permanent": row["permanent"],
            },
        )
    except RuntimeError as exc:
        if "DATABASE_URL" in str(exc):
            return SkillResult(
                ok=False,
                data=None,
                error="Memory storage is not configured. Set DATABASE_URL in your .env file.",
            )
        raise
    except Exception as exc:  # noqa: BLE001
        log.error("store_memory.error", user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(ok=False, data=None, error=f"Failed to store memory: {exc}")
