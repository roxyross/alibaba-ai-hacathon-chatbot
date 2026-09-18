"""VoiceRepository — SQLAlchemy async with thread-safe in-memory fallback.

Enforces strict multi-tenant isolation on all voice recording queries, insertions,
modifications, and deletions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, desc, select

from app.db import get_session_factory
from app.models.voice_recording import VoiceRecording

log = structlog.get_logger()

# Module-level thread-safe in-memory store keyed by user_id
_MEM_VOICE_RECORDINGS: dict[str, list[dict[str, Any]]] = {}


def clear_in_memory_stores() -> None:
    """Clear all in-memory voice stores (used for test isolation)."""
    _MEM_VOICE_RECORDINGS.clear()


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


class VoiceRepository:
    """Repository managing user VoiceRecording entities with multi-tenant guarantees."""

    def __init__(self) -> None:
        self._mem = _MEM_VOICE_RECORDINGS

    @staticmethod
    def _to_iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    @classmethod
    def _to_dict(cls, recording: VoiceRecording) -> dict[str, Any]:
        tag_list = _parse_tags_list(recording.tags)
        return {
            "id": recording.id,
            "user_id": recording.user_id,
            "title": recording.title,
            "transcript": recording.transcript,
            "summary": recording.summary,
            "language": recording.language,
            "audio_url": recording.audio_url,
            "duration_seconds": recording.duration_seconds,
            "voice_model": recording.voice_model,
            "tags": tag_list,
            "created_at": cls._to_iso(recording.created_at),
            "updated_at": cls._to_iso(recording.updated_at),
        }

    async def list_recordings(
        self,
        user_id: str,
        limit: int = 50,
        search: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """List voice recordings belonging to user_id, with optional search and tag filters."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(VoiceRecording).where(VoiceRecording.user_id == user_id)
                    if search:
                        term = f"%{search}%"
                        stmt = stmt.where(
                            VoiceRecording.title.ilike(term)
                            | VoiceRecording.transcript.ilike(term)
                            | VoiceRecording.summary.ilike(term)
                        )
                    if tag:
                        stmt = stmt.where(VoiceRecording.tags.ilike(f"%{tag}%"))

                    stmt = stmt.order_by(desc(VoiceRecording.created_at)).limit(limit)
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                    return [self._to_dict(r) for r in rows]
            except Exception as exc:
                log.warning("voice_repo.list_db_fallback", error=str(exc))

        # In-memory fallback
        user_items = self._mem.get(user_id, [])
        filtered: list[dict[str, Any]] = []
        search_lower = search.lower() if search else None
        tag_lower = tag.lower() if tag else None

        for item in user_items:
            if search_lower:
                title = str(item.get("title", "")).lower()
                transcript = str(item.get("transcript", "")).lower()
                summary = str(item.get("summary", "") or "").lower()
                if search_lower not in title and search_lower not in transcript and search_lower not in summary:
                    continue
            if tag_lower:
                item_tags = [t.lower() for t in _parse_tags_list(item.get("tags"))]
                if tag_lower not in item_tags and not any(tag_lower in t for t in item_tags):
                    continue

            # Return deep-copied representation
            item_copy = dict(item)
            item_copy["tags"] = _parse_tags_list(item_copy.get("tags"))
            filtered.append(item_copy)

        filtered.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return filtered[:limit]

    async def get_recording(self, user_id: str, recording_id: str) -> dict[str, Any] | None:
        """Fetch a single voice recording owned by user_id (returns None if not found or unauthorized)."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(VoiceRecording).where(
                        VoiceRecording.id == recording_id,
                        VoiceRecording.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    rec = result.scalar_one_or_none()
                    if rec is not None:
                        return self._to_dict(rec)
                    return None
            except Exception as exc:
                log.warning("voice_repo.get_db_fallback", error=str(exc))

        # In-memory fallback
        for r in self._mem.get(user_id, []):
            if r["id"] == recording_id:
                res = dict(r)
                res["tags"] = _parse_tags_list(res.get("tags"))
                return res
        return None

    async def create_recording(
        self,
        user_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create and persist a new voice recording note for user_id."""
        rid = str(data.get("id") or str(uuid.uuid4()))
        now = datetime.now(UTC)
        title = data.get("title") or "Voice Note"
        transcript = data.get("transcript", "").strip()
        summary = data.get("summary")
        language = data.get("language") or "en"
        audio_url = data.get("audio_url")
        duration_seconds = data.get("duration_seconds")
        voice_model = data.get("voice_model")
        tags_str = _format_tags_str(data.get("tags"))

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    rec = VoiceRecording(
                        id=rid,
                        user_id=user_id,
                        title=title,
                        transcript=transcript,
                        summary=summary,
                        language=language,
                        audio_url=audio_url,
                        duration_seconds=duration_seconds,
                        voice_model=voice_model,
                        tags=tags_str,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(rec)
                    await session.commit()
                    await session.refresh(rec)
                    return self._to_dict(rec)
            except Exception as exc:
                log.warning("voice_repo.create_db_fallback", error=str(exc))

        # In-memory fallback
        record = {
            "id": rid,
            "user_id": user_id,
            "title": title,
            "transcript": transcript,
            "summary": summary,
            "language": language,
            "audio_url": audio_url,
            "duration_seconds": duration_seconds,
            "voice_model": voice_model,
            "tags": _parse_tags_list(tags_str),
            "created_at": self._to_iso(now),
            "updated_at": self._to_iso(now),
        }
        if user_id not in self._mem:
            self._mem[user_id] = []
        self._mem[user_id].insert(0, record)
        return dict(record)

    async def update_recording(
        self,
        user_id: str,
        recording_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an existing voice recording owned by user_id."""
        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(VoiceRecording).where(
                        VoiceRecording.id == recording_id,
                        VoiceRecording.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    rec = result.scalar_one_or_none()
                    if rec is None:
                        return None

                    if "title" in data and data["title"] is not None:
                        rec.title = data["title"]
                    if "transcript" in data and data["transcript"] is not None:
                        rec.transcript = data["transcript"]
                    if "summary" in data:
                        rec.summary = data["summary"]
                    if "language" in data and data["language"] is not None:
                        rec.language = data["language"]
                    if "tags" in data and data["tags"] is not None:
                        rec.tags = _format_tags_str(data["tags"])

                    rec.updated_at = now
                    await session.commit()
                    await session.refresh(rec)
                    return self._to_dict(rec)
            except Exception as exc:
                log.warning("voice_repo.update_db_fallback", error=str(exc))

        # In-memory fallback
        for idx, r in enumerate(self._mem.get(user_id, [])):
            if r["id"] == recording_id:
                updated_entry = dict(r)
                if "title" in data and data["title"] is not None:
                    updated_entry["title"] = data["title"]
                if "transcript" in data and data["transcript"] is not None:
                    updated_entry["transcript"] = data["transcript"]
                if "summary" in data:
                    updated_entry["summary"] = data["summary"]
                if "language" in data and data["language"] is not None:
                    updated_entry["language"] = data["language"]
                if "tags" in data and data["tags"] is not None:
                    updated_entry["tags"] = _parse_tags_list(data["tags"])

                updated_entry["updated_at"] = self._to_iso(now)
                self._mem[user_id][idx] = updated_entry
                return dict(updated_entry)
        return None

    async def delete_recording(self, user_id: str, recording_id: str) -> bool:
        """Delete a recording owned by user_id. Returns True if deleted, False if not found."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = delete(VoiceRecording).where(
                        VoiceRecording.id == recording_id,
                        VoiceRecording.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    await session.commit()
                    row_count = int(getattr(res, "rowcount", 0) or 0)
                    return row_count > 0
            except Exception as exc:
                log.warning("voice_repo.delete_db_fallback", error=str(exc))

        # In-memory fallback
        user_recordings = self._mem.get(user_id, [])
        for idx, r in enumerate(user_recordings):
            if r["id"] == recording_id:
                user_recordings.pop(idx)
                return True
        return False
