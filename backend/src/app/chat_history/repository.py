"""ChatMessageRepository — SQLAlchemy async with in-memory fallback."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select

from app.chat_history.models import ChatMessage
from app.db import get_session_factory


@dataclass
class _MemMessage:
    id: str
    session_id: str
    role: str
    content: str
    provider: Optional[str]
    model: Optional[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime


class ChatMessageRepository:
    """Persist and list chat messages. In-memory fallback when no DB."""

    def __init__(self) -> None:
        self._mem: dict[str, list[_MemMessage]] = {}  # session_id -> [msg, ...]

    async def append(
        self,
        session_id: str,
        role: str,
        content: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> _MemMessage | ChatMessage:
        factory = get_session_factory()
        if factory is None:
            row = _MemMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role=role,
                content=content,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                created_at=datetime.now(timezone.utc),
            )
            self._mem.setdefault(session_id, []).append(row)
            return row
        async with factory() as session:
            row = ChatMessage(
                session_id=session_id,
                role=role,
                content=content,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_for_session(
        self,
        session_id: str,
        user_id: str,
        limit: int = 200,
    ) -> list[ChatMessage | _MemMessage]:
        """Return all messages for a session, oldest first.

        The user_id is accepted for symmetry with the auth pattern; the actual
        authorization check is performed by the caller against ChatSession.
        """
        del user_id  # authorization done at router layer
        factory = get_session_factory()
        if factory is None:
            return list(self._mem.get(session_id, []))
        async with factory() as session:
            rows = (
                await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at.asc())
                    .limit(limit)
                )
            ).scalars().all()
            return list(rows)

    async def count_for_session(self, session_id: str, user_id: str) -> int:
        """Count messages for a session. Used by the sessions list endpoint."""
        del user_id
        factory = get_session_factory()
        if factory is None:
            return len(self._mem.get(session_id, []))
        async with factory() as session:
            result = await session.execute(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.session_id == session_id
                )
            )
            return int(result.scalar_one())
