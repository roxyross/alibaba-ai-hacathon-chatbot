"""ResearchRepository — SQLAlchemy async with thread-safe in-memory fallback.

Enforces strict multi-tenant isolation on all research report queries, insertions,
modifications, and deletions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, desc, select

from app.db import get_session_factory
from app.models.research_report import ResearchReport

log = structlog.get_logger()

# Module-level thread-safe in-memory store keyed by user_id
_MEM_RESEARCH_REPORTS: dict[str, list[dict[str, Any]]] = {}


def clear_in_memory_stores() -> None:
    """Clear all in-memory research stores (used for test isolation)."""
    _MEM_RESEARCH_REPORTS.clear()


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


class ResearchRepository:
    """Repository managing user ResearchReport entities with multi-tenant guarantees."""

    def __init__(self) -> None:
        self._mem = _MEM_RESEARCH_REPORTS

    @staticmethod
    def _to_iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    @classmethod
    def _to_dict(cls, report: ResearchReport) -> dict[str, Any]:
        tag_list = _parse_tags_list(report.tags)
        return {
            "id": report.id,
            "user_id": report.user_id,
            "title": report.title,
            "query": report.query,
            "summary": report.summary,
            "findings": report.findings if isinstance(report.findings, list) else [],
            "sources": report.sources if isinstance(report.sources, list) else [],
            "confidence": report.confidence,
            "depth": report.depth,
            "tags": tag_list,
            "created_at": cls._to_iso(report.created_at),
            "updated_at": cls._to_iso(report.updated_at),
        }

    async def list_reports(
        self,
        user_id: str,
        limit: int = 50,
        search: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """List research reports belonging to user_id, ordered by most recent."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ResearchReport).where(ResearchReport.user_id == user_id)
                    if search:
                        term = f"%{search.strip()}%"
                        stmt = stmt.where(
                            ResearchReport.title.ilike(term)
                            | ResearchReport.query.ilike(term)
                            | ResearchReport.summary.ilike(term)
                        )
                    if tag:
                        stmt = stmt.where(ResearchReport.tags.ilike(f"%{tag}%"))
                    stmt = stmt.order_by(desc(ResearchReport.created_at)).limit(limit)
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                    return [self._to_dict(r) for r in rows]
            except Exception as exc:
                log.warning("research_repo.list_db_fallback", error=str(exc))

        # In-memory fallback
        items = self._mem.get(user_id, [])
        filtered = items
        if search:
            q = search.lower()
            filtered = [
                r for r in filtered
                if q in r.get("title", "").lower()
                or q in r.get("query", "").lower()
                or q in r.get("summary", "").lower()
            ]
        if tag:
            t = tag.lower()
            filtered = [
                r for r in filtered
                if any(t in str(tag_item).lower() for tag_item in r.get("tags", []))
            ]
        return [dict(r) for r in filtered[:limit]]

    async def get_report(self, user_id: str, report_id: str) -> dict[str, Any] | None:
        """Get a single research report, strictly checking user_id ownership."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ResearchReport).where(
                        ResearchReport.id == report_id,
                        ResearchReport.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    report = result.scalar_one_or_none()
                    if report is not None:
                        return self._to_dict(report)
                    return None
            except Exception as exc:
                log.warning("research_repo.get_db_fallback", error=str(exc))

        # In-memory fallback
        for r in self._mem.get(user_id, []):
            if r.get("id") == report_id:
                return dict(r)
        return None

    async def create_report(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create and persist a new research report for user_id."""
        rid = data.get("id") or str(uuid.uuid4())
        title = data.get("title") or (data.get("query", "Research Report")[:60])
        query = data.get("query", "").strip()
        summary = data.get("summary", "").strip()
        findings = data.get("findings") or []
        sources = data.get("sources") or []
        confidence = data.get("confidence") or "medium"
        depth = data.get("depth") or "deep"
        now = datetime.now(UTC)
        tags_str = _format_tags_str(data.get("tags"))

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    report = ResearchReport(
                        id=rid,
                        user_id=user_id,
                        title=title,
                        query=query,
                        summary=summary,
                        findings=findings,
                        sources=sources,
                        confidence=confidence,
                        depth=depth,
                        tags=tags_str,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(report)
                    await session.commit()
                    await session.refresh(report)
                    return self._to_dict(report)
            except Exception as exc:
                log.warning("research_repo.create_db_fallback", error=str(exc))

        # In-memory fallback
        record = {
            "id": rid,
            "user_id": user_id,
            "title": title,
            "query": query,
            "summary": summary,
            "findings": list(findings),
            "sources": list(sources),
            "confidence": confidence,
            "depth": depth,
            "tags": _parse_tags_list(tags_str),
            "created_at": self._to_iso(now),
            "updated_at": self._to_iso(now),
        }
        if user_id not in self._mem:
            self._mem[user_id] = []
        self._mem[user_id].insert(0, record)
        return dict(record)

    async def update_report(
        self, user_id: str, report_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update fields of an existing research report, ensuring user_id ownership."""
        now = datetime.now(UTC)
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(ResearchReport).where(
                        ResearchReport.id == report_id,
                        ResearchReport.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    report = result.scalar_one_or_none()
                    if report is None:
                        return None

                    if "title" in data and data["title"] is not None:
                        report.title = str(data["title"]).strip()
                    if "summary" in data and data["summary"] is not None:
                        report.summary = str(data["summary"]).strip()
                    if "findings" in data and data["findings"] is not None:
                        report.findings = list(data["findings"])
                    if "sources" in data and data["sources"] is not None:
                        report.sources = list(data["sources"])
                    if "confidence" in data and data["confidence"] is not None:
                        report.confidence = str(data["confidence"]).strip()
                    if "depth" in data and data["depth"] is not None:
                        report.depth = str(data["depth"]).strip()
                    if "tags" in data and data["tags"] is not None:
                        report.tags = _format_tags_str(data["tags"])
                    report.updated_at = now

                    await session.commit()
                    await session.refresh(report)
                    return self._to_dict(report)
            except Exception as exc:
                log.warning("research_repo.update_db_fallback", error=str(exc))

        # In-memory fallback
        for r in self._mem.get(user_id, []):
            if r.get("id") == report_id:
                if "title" in data and data["title"] is not None:
                    r["title"] = str(data["title"]).strip()
                if "summary" in data and data["summary"] is not None:
                    r["summary"] = str(data["summary"]).strip()
                if "findings" in data and data["findings"] is not None:
                    r["findings"] = list(data["findings"])
                if "sources" in data and data["sources"] is not None:
                    r["sources"] = list(data["sources"])
                if "confidence" in data and data["confidence"] is not None:
                    r["confidence"] = str(data["confidence"]).strip()
                if "depth" in data and data["depth"] is not None:
                    r["depth"] = str(data["depth"]).strip()
                if "tags" in data and data["tags"] is not None:
                    r["tags"] = _parse_tags_list(_format_tags_str(data["tags"]))
                r["updated_at"] = self._to_iso(now)
                return dict(r)
        return None

    async def delete_report(self, user_id: str, report_id: str) -> bool:
        """Delete a research report, returning True if deleted and False if not found/unowned."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = delete(ResearchReport).where(
                        ResearchReport.id == report_id,
                        ResearchReport.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    await session.commit()
                    row_count = int(getattr(res, "rowcount", 0) or 0)
                    return row_count > 0
            except Exception as exc:
                log.warning("research_repo.delete_db_fallback", error=str(exc))

        # In-memory fallback
        items = self._mem.get(user_id, [])
        for idx, r in enumerate(items):
            if r.get("id") == report_id:
                items.pop(idx)
                return True
        return False
