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
    created_at: datetime
    updated_at: datetime
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
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_for_user(self, user_id: str) -> list[ChatSession | _MemSession]:
        factory = get_session_factory()
        if factory is None:
            return sorted(
                (s for s in self._mem.values() if s.user_id == user_id),
                key=lambda s: s.updated_at,
                reverse=True,
            )
        async with factory() as session:
            rows = (
                await session.execute(
                    select(ChatSession)
                    .where(ChatSession.user_id == user_id)
                    .order_by(ChatSession.updated_at.desc())
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
            await session.execute(
                delete(ChatSession).where(ChatSession.id == session_id)
            )
            await session.commit()
            return True
