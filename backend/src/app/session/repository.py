"""ChatSessionRepository — SQLAlchemy async with in-memory fallback."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.db import get_session_factory
from app.session.models import ChatSession


@dataclass
class _MemSession:
    """In-memory mirror of ChatSession for dev without a DB."""

    id: str
    user_id: str
    title: str | None
    provider: str
    model: str
    session_type: str = "chat"
    pinned: bool = False
    archived_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    message_count: int = 0


# Module-level in-memory fallback shared by every ChatSessionRepository instance.
_MEM_SESSIONS: dict[str, _MemSession] = {}


class ChatSessionRepository:
    """All session persistence. Falls back to in-memory if DATABASE_URL is unset."""

    _mem: dict[str, _MemSession] = _MEM_SESSIONS

    def __init__(self) -> None:
        self._mem = _MEM_SESSIONS

    async def create(
        self,
        user_id: str,
        provider: str,
        model: str,
        title: str | None = None,
        session_type: str = "chat",
        pinned: bool = False,
    ) -> _MemSession | ChatSession:
        factory = get_session_factory()
        now = datetime.now(UTC)
        if factory is None:
            mem_row = _MemSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
                provider=provider,
                model=model,
                session_type=session_type,
                pinned=pinned,
                created_at=now,
                updated_at=now,
            )
            self._mem[mem_row.id] = mem_row
            return mem_row

        async with factory() as session:
            db_row = ChatSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
                provider=provider,
                model=model,
                session_type=session_type,
                pinned=pinned,
                created_at=now,
                updated_at=now,
            )
            session.add(db_row)
            await session.commit()
            await session.refresh(db_row)
            return db_row

    async def list_for_user(
        self,
        user_id: str,
        session_type: str | None = None,
        include_archived: bool = False,
    ) -> list[ChatSession | _MemSession]:
        factory = get_session_factory()
        if factory is None:
            filtered = [
                s
                for s in self._mem.values()
                if s.user_id == user_id
                and (session_type is None or getattr(s, "session_type", "chat") == session_type)
                and (include_archived or getattr(s, "archived_at", None) is None)
            ]
            return sorted(
                filtered,
                key=lambda s: (getattr(s, "pinned", False), s.updated_at),
                reverse=True,
            )

        async with factory() as session:
            query = select(ChatSession).where(ChatSession.user_id == user_id)
            if session_type:
                query = query.where(ChatSession.session_type == session_type)
            if not include_archived:
                query = query.where(ChatSession.archived_at.is_(None))
            rows = (
                await session.execute(
                    query.order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
                )
            ).scalars().all()
            return list(rows)

    async def get(self, session_id: str, user_id: str) -> ChatSession | _MemSession | None:
        factory = get_session_factory()
        if factory is None:
            mem_row = self._mem.get(session_id)
            if mem_row is None or mem_row.user_id != user_id:
                return None
            return mem_row
        async with factory() as session:
            db_row = (
                await session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()
            if db_row is None or db_row.user_id != user_id:
                return None
            return db_row

    async def get_by_id(self, session_id: str) -> ChatSession | _MemSession | None:
        """Fetch session by ID without user check (internal system lookup)."""
        factory = get_session_factory()
        if factory is None:
            return self._mem.get(session_id)
        async with factory() as session:
            return (
                await session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()

    async def update(
        self,
        session_id: str,
        user_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> ChatSession | _MemSession | None:
        factory = get_session_factory()
        now = datetime.now(UTC)
        if factory is None:
            mem_row = self._mem.get(session_id)
            if mem_row is None or mem_row.user_id != user_id:
                return None
            if title is not None:
                mem_row.title = title
            if pinned is not None:
                mem_row.pinned = pinned
            if archived is not None:
                mem_row.archived_at = now if archived else None
            mem_row.updated_at = now
            return mem_row

        async with factory() as session:
            db_row = (
                await session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()
            if db_row is None or db_row.user_id != user_id:
                return None
            if title is not None:
                db_row.title = title
            if pinned is not None:
                db_row.pinned = pinned
            if archived is not None:
                db_row.archived_at = now if archived else None
            db_row.updated_at = now
            await session.commit()
            await session.refresh(db_row)
            return db_row

    async def rename(
        self, session_id: str, user_id: str, title: str
    ) -> ChatSession | _MemSession | None:
        return await self.update(session_id, user_id, title=title)

    async def delete(self, session_id: str, user_id: str) -> bool:
        factory = get_session_factory()
        if factory is None:
            mem_row = self._mem.get(session_id)
            if mem_row is None or mem_row.user_id != user_id:
                return False
            del self._mem[session_id]
            return True
        async with factory() as session:
            db_row = (
                await session.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()
            if db_row is None or db_row.user_id != user_id:
                return False
            from app.chat_history.models import ChatMessage
            await session.execute(
                delete(ChatMessage).where(ChatMessage.session_id == session_id)
            )
            await session.execute(
                delete(ChatSession).where(ChatSession.id == session_id)
            )
            await session.commit()
            return True
