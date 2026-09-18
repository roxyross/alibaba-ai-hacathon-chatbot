"""ChatMessageRepository — SQLAlchemy async with in-memory fallback."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.chat_history.models import ChatMessage
from app.db import get_session_factory


@dataclass
class _MemMessage:
    id: str
    session_id: str
    role: str
    content: str
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime


# Module-level in-memory fallback shared by every ChatMessageRepository instance.
_MEM_MESSAGES: dict[str, list[_MemMessage]] = {}


class ChatMessageRepository:
    """Persist and list chat messages. In-memory fallback when no DB."""

    _mem: dict[str, list[_MemMessage]] = _MEM_MESSAGES

    def __init__(self) -> None:
        self._mem = _MEM_MESSAGES

    async def append(
        self,
        session_id: str,
        role: str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
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
                created_at=datetime.now(UTC),
            )
            self._mem.setdefault(session_id, []).append(row)
            from app.session.repository import ChatSessionRepository
            sess = await ChatSessionRepository().get_by_id(session_id)
            if sess is not None:
                sess.updated_at = datetime.now(UTC)
            return row
        async with factory() as session:
            db_row = ChatMessage(
                session_id=session_id,
                role=role,
                content=content,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
            session.add(db_row)
            from sqlalchemy import update

            from app.session.models import ChatSession
            await session.execute(
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(updated_at=datetime.now(UTC))
            )
            await session.commit()
            await session.refresh(db_row)
            return db_row

    async def list_for_session(
        self,
        session_id: str,
        user_id: str = "",
        limit: int = 200,
    ) -> list[ChatMessage | _MemMessage]:
        """Return all messages for a session, oldest first.

        If user_id is provided, enforces session ownership at query level.
        """
        factory = get_session_factory()
        if factory is None:
            if user_id:
                from app.session.repository import ChatSessionRepository
                sess = await ChatSessionRepository().get(session_id, user_id)
                if sess is None:
                    return []
            from typing import cast
            return cast(list[ChatMessage | _MemMessage], list(self._mem.get(session_id, [])))[:limit]
        async with factory() as session:
            if user_id:
                from app.session.models import ChatSession
                query = (
                    select(ChatMessage)
                    .join(ChatSession, ChatMessage.session_id == ChatSession.id)
                    .where(
                        ChatMessage.session_id == session_id,
                        ChatSession.user_id == user_id,
                    )
                    .order_by(ChatMessage.created_at.asc())
                    .limit(limit)
                )
            else:
                query = (
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at.asc())
                    .limit(limit)
                )
            rows = (await session.execute(query)).scalars().all()
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

    async def delete_for_session(self, session_id: str) -> None:
        """Delete all messages for a session."""
        self._mem.pop(session_id, None)
        factory = get_session_factory()
        if factory is not None:
            async with factory() as session:
                from sqlalchemy import delete
                await session.execute(
                    delete(ChatMessage).where(ChatMessage.session_id == session_id)
                )
                await session.commit()
