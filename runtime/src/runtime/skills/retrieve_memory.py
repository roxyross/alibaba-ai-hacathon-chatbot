"""retrieve_memory skill — retrieve user memory entries.

Supports:
  - Recent entries (no query): returns most recently stored entries
  - Keyword search (query set): returns entries whose content matches the query

Vector search (embedding-based) is a v2 follow-up: requires adding
an embedding column to memory_entries and re-embedding existing entries.
v1 uses LIKE-based keyword matching for simplicity.
"""

from __future__ import annotations

import re
import structlog

import asyncpg

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        url = settings.database_url
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
    return _pool


def _keyword_query_clause(query: str) -> tuple[str, list[str]]:
    """Build a LIKE clause and token list for keyword search."""
    tokens = re.findall(r"[a-z0-9]{2,}", query.lower())
    if not tokens:
        return "1=1", []
    conditions = " OR ".join(["content ILIKE $" + str(i + 2) for i in range(len(tokens))])
    params = [f"%{token}%" for token in tokens]
    return conditions, params


async def retrieve_memory(
    query: str | None = None,
    limit: int = 20,
    importance: str | None = None,
    include_soft_deleted: bool = False,
    *,
    user_id: str,
) -> SkillResult:
    """Retrieve memory entries for the user.

    Args:
        query: If set, search entries by keyword (case-insensitive substring match).
               v2 will use vector search via embeddings.
        limit: Maximum number of entries to return (default 20, max 100).
        importance: If set, filter by importance level.
        include_soft_deleted: If True, include soft-deleted entries.
        user_id: The user making the request.

    Returns:
        SkillResult with a list of memory entries.
    """
    log.info(
        "retrieve_memory.invoked",
        user_id=user_id,
        query=query[:80] if query else None,
        limit=limit,
    )

    limit = min(max(1, limit), 100)

    try:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            # Build the WHERE clause
            conditions = ["user_id = $1"]
            params: list = [user_id]
            param_idx = 2

            if not include_soft_deleted:
                conditions.append("soft_deleted = FALSE")

            if importance:
                if importance not in ("low", "normal", "forever"):
                    return SkillResult(
                        ok=False,
                        data=None,
                        error="importance must be 'low', 'normal', or 'forever'",
                    )
                conditions.append(f"importance = ${param_idx}")
                params.append(importance)
                param_idx += 1

            if query:
                kw_clause, kw_params = _keyword_query_clause(query)
                conditions.append(f"({kw_clause})")
                params.extend(kw_params)

            where_clause = " AND ".join(conditions)

            # Order: prioritize keyword matches, then by created_at
            if query:
                order_clause = "created_at DESC"
            else:
                order_clause = "created_at DESC"

            rows = await conn.fetch(
                f"""
                SELECT id, content, importance, tags, created_at,
                       retrieved_count, soft_deleted, permanent
                FROM memory_entries
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT ${param_idx}
                """,
                *params,
                limit,
            )

            entries = [
                {
                    "id": str(row["id"]),
                    "content": row["content"],
                    "importance": row["importance"],
                    "tags": row["tags"],
                    "created_at": row["created_at"].isoformat(),
                    "retrieved_count": row["retrieved_count"],
                    "soft_deleted": row["soft_deleted"],
                    "permanent": row["permanent"],
                }
                for row in rows
            ]

            # Increment retrieved_count for returned entries
            entry_ids = [row["id"] for row in rows]
            if entry_ids:
                await conn.execute(
                    """
                    UPDATE memory_entries
                    SET retrieved_count = retrieved_count + 1
                    WHERE id = ANY($1::uuid[])
                    """,
                    entry_ids,
                )

        log.info(
            "retrieve_memory.done",
            user_id=user_id,
            returned=len(entries),
            query=query[:40] if query else None,
        )

        return SkillResult(
            ok=True,
            data={
                "entries": entries,
                "count": len(entries),
                "query": query,
                "has_more": len(entries) == limit,
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
        log.error("retrieve_memory.error", user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(ok=False, data=None, error=f"Failed to retrieve memories: {exc}")
