"""ChatSessionRepository — SQLAlchemy async with in-memory fallback."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select

from app.db import get_session_factory
from app.session.models import ChatSession


@dataclass
class _MemSession:
    """In-memory mirror of ChatSession for dev without a DB."""

    id: str
    user_id: str
    title: Optional[str]
    provider: str
    model: str
    session_type: str = "chat"
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
    message_count: int = 0


class ChatSessionRepository:
    """All session persistence. Falls back to in-memory if DATABASE_URL is unset."""

    def __init__(self) -> None:
        self._mem: dict[str, _MemSession] = {}

    async def create(
        self,
        user_id: str,
        provider: str,
        model: str,
        title: Optional[str] = None,
        session_type: str = "chat",
    ) -> _MemSession | ChatSession:
        factory = get_session_factory()
        if factory is None:
            now = datetime.now(timezone.utc)
            row = _MemSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
                provider=provider,
                model=model,
                session_type=session_type,
                created_at=now,
                updated_at=now,
            )
            self._mem[row.id] = row
            return row

        async with factory() as session:
            row = ChatSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
                provider=provider,
                model=model,
                session_type=session_type,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_for_user(
        self, user_id: str, session_type: Optional[str] = None
    ) -> list[ChatSession | _MemSession]:
        factory = get_session_factory()
        if factory is None:
            return sorted(
                (
                    s
                    for s in self._mem.values()
                    if s.user_id == user_id
                    and (session_type is None or getattr(s, "session_type", "chat") == session_type)
                ),
                key=lambda s: s.updated_at,
                reverse=True,
            )
        async with factory() as session:
            query = select(ChatSession).where(ChatSession.user_id == user_id)
            if session_type:
                query = query.where(ChatSession.session_type == session_type)
            rows = (
                await session.execute(
                    query.order_by(ChatSession.updated_at.desc())
                )
            ).scalars().all()
            return list(rows)

    async def get(self, session_id: str, user_id: str) -> ChatSession | _MemSession | None:
        factory = get_session_factory()
        if factory is None:
            row = self._mem.get(session_id)
            if row is None or row.user_id != user_id:
                return None
            return row
        async with factory() as session:
            row = (
                await session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()
            if row is None or row.user_id != user_id:
                return None
            return row

    async def rename(
        self, session_id: str, user_id: str, title: str
    ) -> ChatSession | _MemSession | None:
        factory = get_session_factory()
        if factory is None:
            row = self._mem.get(session_id)
            if row is None or row.user_id != user_id:
                return None
            row.title = title
            row.updated_at = datetime.now(timezone.utc)
            return row
        async with factory() as session:
            row = (
                await session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()
            if row is None or row.user_id != user_id:
                return None
            row.title = title
            await session.commit()
            await session.refresh(row)
            return row

    async def delete(self, session_id: str, user_id: str) -> bool:
        factory = get_session_factory()
        if factory is None:
            row = self._mem.get(session_id)
            if row is None or row.user_id != user_id:
                return False
            del self._mem[session_id]
            return True
        async with factory() as session:
            row = (
                await session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()
            if row is None or row.user_id != user_id:
                return False
            # Safely delete any messages associated with this session to prevent FK errors
            from app.chat_history.models import ChatMessage
            await session.execute(
                delete(ChatMessage).where(ChatMessage.session_id == session_id)
            )
            await session.execute(
                delete(ChatSession).where(ChatSession.id == session_id)
            )
            await session.commit()
            return True
