"""BrowserRepository — SQLAlchemy async with thread-safe in-memory fallback.

Enforces strict multi-tenant isolation on all browser task queries, creations,
mutations, and deletions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, desc, select

from app.db import get_session_factory
from app.models.browser_task import BrowserTask

log = structlog.get_logger()

# Module-level thread-safe in-memory store keyed by user_id
_MEM_BROWSER_TASKS: dict[str, list[dict[str, Any]]] = {}


def clear_in_memory_stores() -> None:
    """Clear all in-memory browser stores (used for test isolation)."""
    _MEM_BROWSER_TASKS.clear()


def _format_tags_str(tags: list[str] | str | None) -> str | None:
    """Safely format tags into a comma-separated string for DB storage."""
    if tags is None:
        return None
    if isinstance(tags, str):
        return tags.strip()
    return ", ".join([t.strip() for t in tags if t.strip()])


def _parse_tags_list(raw_tags: str | list[str] | None) -> list[str]:
    """Parse comma-separated tags string into clean list of strings."""
    if not raw_tags:
        return []
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if str(t).strip()]
    return [t.strip() for t in raw_tags.split(",") if t.strip()]


class BrowserRepository:
    """Repository managing user BrowserTask entities with multi-tenant guarantees."""

    def __init__(self) -> None:
        self._mem = _MEM_BROWSER_TASKS

    @staticmethod
    def _to_iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    @classmethod
    def _to_dict(cls, task: BrowserTask) -> dict[str, Any]:
        tag_list = _parse_tags_list(task.tags)
        return {
            "id": task.id,
            "user_id": task.user_id,
            "title": task.title,
            "url": task.url,
            "status": task.status,
            "action_type": task.action_type,
            "actions": task.actions if isinstance(task.actions, list) else [],
            "result_data": task.result_data if isinstance(task.result_data, dict) else {},
            "error_message": task.error_message,
            "requires_confirmation": bool(task.requires_confirmation),
            "is_sensitive": bool(task.is_sensitive),
            "tags": tag_list,
            "created_at": cls._to_iso(task.created_at),
            "updated_at": cls._to_iso(task.updated_at),
        }

    async def list_tasks(
        self,
        user_id: str,
        limit: int = 50,
        search: str | None = None,
        status: str | None = None,
        action_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List browser tasks belonging to user_id, ordered by most recent."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(BrowserTask).where(BrowserTask.user_id == user_id)
                    if search:
                        term = f"%{search.strip()}%"
                        stmt = stmt.where(
                            BrowserTask.title.ilike(term)
                            | BrowserTask.url.ilike(term)
                            | BrowserTask.tags.ilike(term)
                        )
                    if status:
                        stmt = stmt.where(BrowserTask.status == status.strip())
                    if action_type:
                        stmt = stmt.where(BrowserTask.action_type == action_type.strip())
                    stmt = stmt.order_by(desc(BrowserTask.created_at)).limit(limit)
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                    return [self._to_dict(r) for r in rows]
            except Exception as exc:
                log.warning("browser_repo.list_db_fallback", error=str(exc))

        # In-memory fallback
        items = self._mem.get(user_id, [])
        filtered = items
        if search:
            q = search.lower()
            filtered = [
                r for r in filtered
                if q in r.get("title", "").lower()
                or q in r.get("url", "").lower()
                or any(q in str(t).lower() for t in r.get("tags", []))
            ]
        if status:
            s = status.strip().lower()
            filtered = [r for r in filtered if r.get("status", "").lower() == s]
        if action_type:
            at = action_type.strip().lower()
            filtered = [r for r in filtered if r.get("action_type", "").lower() == at]
        return [dict(r) for r in filtered[:limit]]

    async def get_task(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        """Get a single browser task, strictly checking user_id ownership."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(BrowserTask).where(
                        BrowserTask.id == task_id,
                        BrowserTask.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    task = result.scalar_one_or_none()
                    if task is not None:
                        return self._to_dict(task)
                    return None
            except Exception as exc:
                log.warning("browser_repo.get_db_fallback", error=str(exc))

        # In-memory fallback
        for r in self._mem.get(user_id, []):
            if r.get("id") == task_id:
                return dict(r)
        return None

    async def create_task(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create and persist a new browser task for user_id."""
        tid = data.get("id") or str(uuid.uuid4())
        url = data.get("url", "").strip()
        title = data.get("title") or (f"Browse {url[:50]}" if url else "Browser Task")
        status = data.get("status") or "pending"
        action_type = data.get("action_type") or "navigate"
        actions = data.get("actions") or []
        result_data = data.get("result_data") or {}
        error_message = data.get("error_message")
        requires_confirmation = bool(data.get("requires_confirmation", False))
        is_sensitive = bool(data.get("is_sensitive", False))
        now = datetime.now(UTC)
        tags_str = _format_tags_str(data.get("tags"))

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    task = BrowserTask(
                        id=tid,
                        user_id=user_id,
                        title=title,
                        url=url,
                        status=status,
                        action_type=action_type,
                        actions=actions,
                        result_data=result_data,
                        error_message=error_message,
                        requires_confirmation=requires_confirmation,
                        is_sensitive=is_sensitive,
                        tags=tags_str,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(task)
                    await session.commit()
                    await session.refresh(task)
                    return self._to_dict(task)
            except Exception as exc:
                log.warning("browser_repo.create_db_fallback", error=str(exc))

        # In-memory fallback
        record = {
            "id": tid,
            "user_id": user_id,
            "title": title,
            "url": url,
            "status": status,
            "action_type": action_type,
            "actions": list(actions),
            "result_data": dict(result_data),
            "error_message": error_message,
            "requires_confirmation": requires_confirmation,
            "is_sensitive": is_sensitive,
            "tags": _parse_tags_list(tags_str),
            "created_at": self._to_iso(now),
            "updated_at": self._to_iso(now),
        }
        if user_id not in self._mem:
            self._mem[user_id] = []
        self._mem[user_id].insert(0, record)
        return dict(record)

    async def update_task(
        self, user_id: str, task_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update fields of an existing browser task, ensuring user_id ownership."""
        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(BrowserTask).where(
                        BrowserTask.id == task_id,
                        BrowserTask.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    task = result.scalar_one_or_none()
                    if task is None:
                        return None

                    if "title" in data and data["title"] is not None:
                        task.title = str(data["title"]).strip()
                    if "status" in data and data["status"] is not None:
                        task.status = str(data["status"]).strip()
                    if "result_data" in data and data["result_data"] is not None:
                        task.result_data = dict(data["result_data"])
                    if "error_message" in data:
                        task.error_message = data["error_message"]
                    if "tags" in data and data["tags"] is not None:
                        task.tags = _format_tags_str(data["tags"])
                    task.updated_at = now

                    await session.commit()
                    await session.refresh(task)
                    return self._to_dict(task)
            except Exception as exc:
                log.warning("browser_repo.update_db_fallback", error=str(exc))

        # In-memory fallback
        for r in self._mem.get(user_id, []):
            if r.get("id") == task_id:
                if "title" in data and data["title"] is not None:
                    r["title"] = str(data["title"]).strip()
                if "status" in data and data["status"] is not None:
                    r["status"] = str(data["status"]).strip()
                if "result_data" in data and data["result_data"] is not None:
                    r["result_data"] = dict(data["result_data"])
                if "error_message" in data:
                    r["error_message"] = data["error_message"]
                if "tags" in data and data["tags"] is not None:
                    r["tags"] = _parse_tags_list(_format_tags_str(data["tags"]))
                r["updated_at"] = self._to_iso(now)
                return dict(r)
        return None

    async def delete_task(self, user_id: str, task_id: str) -> bool:
        """Delete a browser task, returning True if deleted and False if not found/unowned."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = delete(BrowserTask).where(
                        BrowserTask.id == task_id,
                        BrowserTask.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    await session.commit()
                    row_count = int(getattr(res, "rowcount", 0) or 0)
                    return row_count > 0
            except Exception as exc:
                log.warning("browser_repo.delete_db_fallback", error=str(exc))

        # In-memory fallback
        items = self._mem.get(user_id, [])
        for idx, r in enumerate(items):
            if r.get("id") == task_id:
                items.pop(idx)
                return True
        return False
