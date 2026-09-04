"""Token usage repository — persists TokenUsageLog entries.

T027: SQLAlchemy async implementation.
In-memory fallback remains active when DATABASE_URL is not configured.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    pass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_gateway.models.schemas import TokenUsageLogCreate
from app.models.token_usage import TokenUsageLog

# In-memory fallback when DB is not configured
_storage: list[dict] = []


class TokenUsageRepository:
    """Repository for token usage logs — SQLAlchemy async with in-memory fallback."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    async def create(self, log: TokenUsageLogCreate) -> dict:
        """Persist a token usage log entry. Returns the created record."""
        if self._session is None:
            # In-memory fallback
            record = {
                "id": str(uuid4()),
                "request_id": str(log.request_id),
                "provider_id": str(log.provider_id),
                "model_id": str(log.model_id),
                "input_tokens": log.input_tokens,
                "output_tokens": log.output_tokens,
                "cost_usd": log.cost_usd,
                "latency_ms": log.latency_ms,
                "provider_response_ms": log.provider_response_ms,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _storage.append(record)
            return record

        record = TokenUsageLog(
            request_id=str(log.request_id),
            provider_id=str(log.provider_id),
            model_id=str(log.model_id),
            input_tokens=log.input_tokens,
            output_tokens=log.output_tokens,
            cost_usd=log.cost_usd,
            latency_ms=log.latency_ms,
            provider_response_ms=log.provider_response_ms,
        )
        self._session.add(record)
        await self._session.flush()
        return {
            "id": record.id,
            "request_id": record.request_id,
            "provider_id": record.provider_id,
            "model_id": record.model_id,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "cost_usd": record.cost_usd,
            "latency_ms": record.latency_ms,
            "provider_response_ms": record.provider_response_ms,
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        }

    async def find_recent(
        self,
        limit: int = 100,
        provider: str | None = None,
    ) -> list[dict]:
        """Return the most recent token usage logs, newest first."""
        if self._session is None:
            records = sorted(_storage, key=lambda r: r["timestamp"], reverse=True)
            if provider:
                records = [r for r in records if provider in r.get("provider_id", "")]
            return records[:limit]

        stmt = select(TokenUsageLog).order_by(TokenUsageLog.timestamp.desc()).limit(limit)
        if provider:
            stmt = stmt.where(TokenUsageLog.provider_id.contains(provider))
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "request_id": r.request_id,
                "provider_id": r.provider_id,
                "model_id": r.model_id,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "provider_response_ms": r.provider_response_ms,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ]

    async def delete_by_request_id(self, request_id: str) -> int:
        """Delete all logs for a given request_id. Returns count deleted."""
        if self._session is None:
            global _storage
            before = len(_storage)
            _storage = [r for r in _storage if r["request_id"] != str(request_id)]
            return before - len(_storage)

        stmt = select(TokenUsageLog).where(TokenUsageLog.request_id == str(request_id))
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        for r in rows:
            await self._session.delete(r)
        await self._session.flush()
        return len(rows)
