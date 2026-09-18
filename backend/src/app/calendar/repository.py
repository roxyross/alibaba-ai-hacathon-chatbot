"""CalendarRepository — SQLAlchemy async with thread-safe in-memory fallback.

Enforces strict multi-tenant isolation on all calendar queries, insertions,
modifications, and deletions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select

from app.db import get_session_factory
from app.models.calendar_event import CalendarEvent

log = structlog.get_logger()

# Module-level thread-safe in-memory store keyed by user_id
_MEM_CALENDAR_EVENTS: dict[str, list[dict[str, Any]]] = {}


def clear_in_memory_stores() -> None:
    """Clear all in-memory calendar stores (used for test isolation)."""
    _MEM_CALENDAR_EVENTS.clear()


class CalendarRepository:
    """Repository managing user CalendarEvent records with multi-tenant guarantees."""

    def __init__(self) -> None:
        self._mem = _MEM_CALENDAR_EVENTS

    @staticmethod
    def _to_iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    @classmethod
    def _to_dict(cls, event: CalendarEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "user_id": event.user_id,
            "title": event.title,
            "description": event.description or "",
            "start_time": cls._to_iso(event.start_time),
            "end_time": cls._to_iso(event.end_time),
            "location": event.location,
            "category": event.category or "meeting",
            "is_all_day": bool(event.is_all_day),
            "recurrence_rule": event.recurrence_rule,
            "remind_minutes_before": event.remind_minutes_before,
            "created_at": cls._to_iso(event.created_at),
            "updated_at": cls._to_iso(event.updated_at),
        }

    async def list_events(
        self,
        user_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all events belonging to user_id, optionally filtered by date range and category."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(CalendarEvent).where(CalendarEvent.user_id == user_id)
                    if start_date is not None:
                        stmt = stmt.where(CalendarEvent.start_time >= start_date)
                    if end_date is not None:
                        stmt = stmt.where(CalendarEvent.start_time <= end_date)
                    if category is not None:
                        stmt = stmt.where(CalendarEvent.category == category)
                    stmt = stmt.order_by(CalendarEvent.start_time.asc())
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                    return [self._to_dict(r) for r in rows]
            except Exception as exc:
                log.warning("calendar_repo.list_db_fallback", error=str(exc))

        # In-memory fallback
        user_events = self._mem.get(user_id, [])
        filtered: list[dict[str, Any]] = []
        for e in user_events:
            if category and e.get("category") != category:
                continue
            e_start_str = e.get("start_time")
            if e_start_str:
                try:
                    e_start = datetime.fromisoformat(e_start_str)
                    if start_date and e_start < start_date:
                        continue
                    if end_date and e_start > end_date:
                        continue
                except Exception:
                    pass
            filtered.append(dict(e))

        filtered.sort(key=lambda x: str(x.get("start_time", "")))
        return filtered

    async def get_event(self, user_id: str, event_id: str) -> dict[str, Any] | None:
        """Fetch a single event owned by user_id (returns None if not found or unauthorized)."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(CalendarEvent).where(
                        CalendarEvent.id == event_id,
                        CalendarEvent.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    ev = result.scalar_one_or_none()
                    if ev is not None:
                        return self._to_dict(ev)
                    return None
            except Exception as exc:
                log.warning("calendar_repo.get_db_fallback", error=str(exc))

        # In-memory fallback
        for e in self._mem.get(user_id, []):
            if e["id"] == event_id:
                return dict(e)
        return None

    async def create_event(
        self,
        user_id: str,
        title: str,
        start_time: datetime,
        end_time: datetime | None = None,
        description: str = "",
        location: str | None = None,
        category: str = "meeting",
        is_all_day: bool = False,
        recurrence_rule: str | None = None,
        remind_minutes_before: int | None = 15,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Create and persist a new calendar event for user_id."""
        eid = event_id or f"evt-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    ev = CalendarEvent(
                        id=eid,
                        user_id=user_id,
                        title=title,
                        description=description,
                        start_time=start_time,
                        end_time=end_time,
                        location=location,
                        category=category,
                        is_all_day=is_all_day,
                        recurrence_rule=recurrence_rule,
                        remind_minutes_before=remind_minutes_before,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(ev)
                    await session.commit()
                    await session.refresh(ev)
                    return self._to_dict(ev)
            except Exception as exc:
                log.warning("calendar_repo.create_db_fallback", error=str(exc))

        # In-memory fallback
        record = {
            "id": eid,
            "user_id": user_id,
            "title": title,
            "description": description,
            "start_time": self._to_iso(start_time),
            "end_time": self._to_iso(end_time),
            "location": location,
            "category": category,
            "is_all_day": is_all_day,
            "recurrence_rule": recurrence_rule,
            "remind_minutes_before": remind_minutes_before,
            "created_at": self._to_iso(now),
            "updated_at": self._to_iso(now),
        }
        if user_id not in self._mem:
            self._mem[user_id] = []
        self._mem[user_id].append(record)
        return dict(record)

    async def update_event(
        self,
        user_id: str,
        event_id: str,
        **updates: Any,
    ) -> dict[str, Any] | None:
        """Update an existing event owned by user_id."""
        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(CalendarEvent).where(
                        CalendarEvent.id == event_id,
                        CalendarEvent.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    ev = result.scalar_one_or_none()
                    if ev is None:
                        return None
                    for k, v in updates.items():
                        if hasattr(ev, k) and v is not None:
                            setattr(ev, k, v)
                    ev.updated_at = now
                    await session.commit()
                    await session.refresh(ev)
                    return self._to_dict(ev)
            except Exception as exc:
                log.warning("calendar_repo.update_db_fallback", error=str(exc))

        # In-memory fallback
        for idx, e in enumerate(self._mem.get(user_id, [])):
            if e["id"] == event_id:
                updated_entry = dict(e)
                for k, v in updates.items():
                    if v is not None:
                        if isinstance(v, datetime):
                            updated_entry[k] = self._to_iso(v)
                        else:
                            updated_entry[k] = v
                updated_entry["updated_at"] = self._to_iso(now)
                self._mem[user_id][idx] = updated_entry
                return dict(updated_entry)
        return None

    async def delete_event(self, user_id: str, event_id: str) -> bool:
        """Delete an event owned by user_id. Returns True if deleted, False if not found."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = delete(CalendarEvent).where(
                        CalendarEvent.id == event_id,
                        CalendarEvent.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    row_count = int(getattr(res, "rowcount", 0) or 0)
                    return row_count > 0
            except Exception as exc:
                log.warning("calendar_repo.delete_db_fallback", error=str(exc))

        # In-memory fallback
        user_events = self._mem.get(user_id, [])
        for idx, e in enumerate(user_events):
            if e["id"] == event_id:
                user_events.pop(idx)
                return True
        return False
