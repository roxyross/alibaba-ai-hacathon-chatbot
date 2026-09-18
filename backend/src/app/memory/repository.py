"""Dual-mode persistence repository for Semantic Memory and Curator (Phase 18).

Supports async PostgreSQL ORM with thread-safe in-memory fallback stores
for deterministic testing and offline local execution.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic_memory import CuratorRunReport, SemanticMemory

log = structlog.get_logger()

# In-memory stores for testing / offline execution
_MEM_LOCK = threading.Lock()
_MEM_MEMORIES: dict[str, dict[str, Any]] = {}
_MEM_REPORTS: dict[str, dict[str, Any]] = {}
_MEM_POLICIES: dict[str, dict[str, Any]] = {}


def clear_in_memory_stores() -> None:
    """Clear in-memory stores between test runs."""
    with _MEM_LOCK:
        _MEM_MEMORIES.clear()
        _MEM_REPORTS.clear()
        _MEM_POLICIES.clear()


class MemoryRepository:
    """Repository handling semantic memory storage, retrieval, and curator runs."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self._use_db = session is not None and bool(os.environ.get("DATABASE_URL"))

    # ---------------------------------------------------------------------------
    # Semantic Memories
    # ---------------------------------------------------------------------------

    async def list_memories(
        self,
        user_id: str,
        query: str | None = None,
        tag: str | None = None,
        importance: str | None = None,
        include_soft_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List memories for user with optional tag, importance, search, and soft-delete filters."""
        if self._use_db and self.session:
            stmt = select(SemanticMemory).where(SemanticMemory.user_id == user_id)
            if not include_soft_deleted:
                stmt = stmt.where(SemanticMemory.is_soft_deleted == False)  # noqa: E712
            if importance:
                stmt = stmt.where(SemanticMemory.importance == importance)
            if tag:
                stmt = stmt.where(SemanticMemory.tags.ilike(f"%{tag}%"))
            if query:
                stmt = stmt.where(SemanticMemory.content.ilike(f"%{query}%"))

            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await self.session.execute(count_stmt)).scalar() or 0

            stmt = stmt.order_by(desc(SemanticMemory.created_at)).limit(limit).offset(offset)
            result = await self.session.execute(stmt)
            memories = result.scalars().all()
            return [m.to_dict() for m in memories], total

        with _MEM_LOCK:
            user_items = [
                m for m in _MEM_MEMORIES.values() if m.get("user_id") == user_id
            ]
            if not include_soft_deleted:
                user_items = [m for m in user_items if not m.get("is_soft_deleted")]
            if importance:
                user_items = [m for m in user_items if m.get("importance") == importance]
            if tag:
                tag_lower = tag.lower()
                user_items = [
                    m for m in user_items if any(tag_lower in t.lower() for t in m.get("tags", []))
                ]
            if query:
                q_lower = query.lower()
                user_items = [
                    m for m in user_items if q_lower in m.get("content", "").lower()
                ]

            user_items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            total = len(user_items)
            paged = user_items[offset : offset + limit]
            return [dict(item) for item in paged], total

    async def get_memory(
        self, user_id: str, memory_id: str, include_soft_deleted: bool = False
    ) -> dict[str, Any] | None:
        """Fetch a single memory if owned by user."""
        if self._use_db and self.session:
            stmt = select(SemanticMemory).where(
                SemanticMemory.id == memory_id,
                SemanticMemory.user_id == user_id,
            )
            if not include_soft_deleted:
                stmt = stmt.where(SemanticMemory.is_soft_deleted == False)  # noqa: E712
            result = await self.session.execute(stmt)
            memory = result.scalar_one_or_none()
            return memory.to_dict() if memory else None

        with _MEM_LOCK:
            m = _MEM_MEMORIES.get(memory_id)
            if not m or m.get("user_id") != user_id:
                return None
            if not include_soft_deleted and m.get("is_soft_deleted"):
                return None
            return dict(m)

    async def store_memory(
        self,
        user_id: str,
        content: str,
        importance: str = "normal",
        source: str = "user:explicit",
        tags: list[str] | None = None,
        cluster_id: str | None = None,
        source_entry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Store a new long-term semantic memory."""
        now = datetime.now(UTC)
        tag_str = ", ".join(tags) if tags else None
        source_ids_str = ", ".join(source_entry_ids) if source_entry_ids else None

        if self._use_db and self.session:
            memory = SemanticMemory(
                user_id=user_id,
                content=content,
                importance=importance,
                source=source,
                tags=tag_str,
                cluster_id=cluster_id,
                source_entry_ids=source_ids_str,
                is_soft_deleted=False,
                retrieval_count=0,
                created_at=now,
                updated_at=now,
            )
            self.session.add(memory)
            await self.session.commit()
            await self.session.refresh(memory)
            return memory.to_dict()

        mem_id = str(uuid.uuid4())
        data: dict[str, Any] = {
            "id": mem_id,
            "user_id": user_id,
            "content": content,
            "importance": importance,
            "source": source,
            "tags": tags or [],
            "is_soft_deleted": False,
            "soft_deleted_at": None,
            "soft_delete_reason": None,
            "cluster_id": cluster_id,
            "source_entry_ids": source_entry_ids or [],
            "retrieval_count": 0,
            "last_retrieved_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        with _MEM_LOCK:
            _MEM_MEMORIES[mem_id] = data
        return dict(data)

    async def update_memory(
        self,
        user_id: str,
        memory_id: str,
        content: str | None = None,
        importance: str | None = None,
        tags: list[str] | None = None,
        is_soft_deleted: bool | None = None,
        soft_delete_reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Update memory fields, respecting user ownership."""
        now = datetime.now(UTC)

        if self._use_db and self.session:
            stmt = select(SemanticMemory).where(
                SemanticMemory.id == memory_id,
                SemanticMemory.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            memory = result.scalar_one_or_none()
            if not memory:
                return None

            if content is not None:
                memory.content = content
            if importance is not None:
                memory.importance = importance
            if tags is not None:
                memory.tags = ", ".join(tags) if tags else None
            if is_soft_deleted is not None:
                memory.is_soft_deleted = is_soft_deleted
                if is_soft_deleted:
                    memory.soft_deleted_at = now
                    memory.soft_delete_reason = soft_delete_reason
                else:
                    memory.soft_deleted_at = None
                    memory.soft_delete_reason = None
            memory.updated_at = now
            await self.session.commit()
            await self.session.refresh(memory)
            return memory.to_dict()

        with _MEM_LOCK:
            m = _MEM_MEMORIES.get(memory_id)
            if not m or m.get("user_id") != user_id:
                return None
            if content is not None:
                m["content"] = content
            if importance is not None:
                m["importance"] = importance
            if tags is not None:
                m["tags"] = tags
            if is_soft_deleted is not None:
                m["is_soft_deleted"] = is_soft_deleted
                if is_soft_deleted:
                    m["soft_deleted_at"] = now.isoformat()
                    m["soft_delete_reason"] = soft_delete_reason
                else:
                    m["soft_deleted_at"] = None
                    m["soft_delete_reason"] = None
            m["updated_at"] = now.isoformat()
            return dict(m)

    async def delete_memory(
        self, user_id: str, memory_id: str, permanent: bool = False
    ) -> bool:
        """Delete a memory. If permanent is False, marks as soft-deleted."""
        now = datetime.now(UTC)

        if self._use_db and self.session:
            stmt = select(SemanticMemory).where(
                SemanticMemory.id == memory_id,
                SemanticMemory.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            memory = result.scalar_one_or_none()
            if not memory:
                return False

            if permanent:
                await self.session.delete(memory)
            else:
                memory.is_soft_deleted = True
                memory.soft_deleted_at = now
                memory.soft_delete_reason = "user:manual_delete"
                memory.updated_at = now
            await self.session.commit()
            return True

        with _MEM_LOCK:
            m = _MEM_MEMORIES.get(memory_id)
            if not m or m.get("user_id") != user_id:
                return False

            if permanent:
                del _MEM_MEMORIES[memory_id]
            else:
                m["is_soft_deleted"] = True
                m["soft_deleted_at"] = now.isoformat()
                m["soft_delete_reason"] = "user:manual_delete"
                m["updated_at"] = now.isoformat()
            return True

    async def restore_memory(
        self, user_id: str, memory_id: str
    ) -> dict[str, Any] | None:
        """Restore a soft-deleted memory within the grace period."""
        return await self.update_memory(
            user_id=user_id,
            memory_id=memory_id,
            is_soft_deleted=False,
            soft_delete_reason=None,
        )

    async def record_retrievals(
        self, user_id: str, memory_ids: list[str]
    ) -> None:
        """Increment retrieval counts and update last_retrieved_at."""
        if not memory_ids:
            return
        now = datetime.now(UTC)

        if self._use_db and self.session:
            stmt = select(SemanticMemory).where(
                SemanticMemory.user_id == user_id,
                SemanticMemory.id.in_(memory_ids),
            )
            result = await self.session.execute(stmt)
            memories = result.scalars().all()
            for m in memories:
                m.retrieval_count += 1
                m.last_retrieved_at = now
            await self.session.commit()
            return

        with _MEM_LOCK:
            for mid in memory_ids:
                mem_dict = _MEM_MEMORIES.get(mid)
                if mem_dict and mem_dict.get("user_id") == user_id:
                    mem_dict["retrieval_count"] = mem_dict.get("retrieval_count", 0) + 1
                    mem_dict["last_retrieved_at"] = now.isoformat()

    async def purge_all_memories(self, user_id: str) -> int:
        """Permanently delete all memories for user (GDPR / right to erasure)."""
        if self._use_db and self.session:
            stmt = select(SemanticMemory).where(SemanticMemory.user_id == user_id)
            result = await self.session.execute(stmt)
            memories = result.scalars().all()
            count = len(memories)
            for m in memories:
                await self.session.delete(m)
            await self.session.commit()
            return count

        with _MEM_LOCK:
            keys_to_del = [
                k for k, v in _MEM_MEMORIES.items() if v.get("user_id") == user_id
            ]
            for k in keys_to_del:
                del _MEM_MEMORIES[k]
            return len(keys_to_del)

    # ---------------------------------------------------------------------------
    # Memory Curator Reports & Policies
    # ---------------------------------------------------------------------------

    async def record_curator_report(
        self,
        user_id: str,
        entries_scanned: int,
        summarized_count: int,
        clusters_formed: list[Any] | None,
        soft_deleted_count: int,
        hard_deleted_count: int,
        errors_count: int,
        duration_ms: int,
        status: str,
        diff_summary: str,
    ) -> dict[str, Any]:
        """Save a new curator audit report."""
        now = datetime.now(UTC)
        cluster_str = json.dumps(clusters_formed) if clusters_formed else None

        if self._use_db and self.session:
            report = CuratorRunReport(
                user_id=user_id,
                entries_scanned=entries_scanned,
                summarized_count=summarized_count,
                clusters_formed=cluster_str,
                soft_deleted_count=soft_deleted_count,
                hard_deleted_count=hard_deleted_count,
                errors_count=errors_count,
                duration_ms=duration_ms,
                status=status,
                diff_summary=diff_summary,
                created_at=now,
            )
            self.session.add(report)
            await self.session.commit()
            await self.session.refresh(report)
            return report.to_dict()

        report_id = str(uuid.uuid4())
        data: dict[str, Any] = {
            "id": report_id,
            "user_id": user_id,
            "entries_scanned": entries_scanned,
            "summarized_count": summarized_count,
            "clusters_formed": clusters_formed or [],
            "soft_deleted_count": soft_deleted_count,
            "hard_deleted_count": hard_deleted_count,
            "errors_count": errors_count,
            "duration_ms": duration_ms,
            "status": status,
            "diff_summary": diff_summary,
            "created_at": now.isoformat(),
        }
        with _MEM_LOCK:
            _MEM_REPORTS[report_id] = data
        return dict(data)

    async def list_curator_reports(
        self, user_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """List curator run reports for user."""
        if self._use_db and self.session:
            stmt = (
                select(CuratorRunReport)
                .where(CuratorRunReport.user_id == user_id)
                .order_by(desc(CuratorRunReport.created_at))
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            reports = result.scalars().all()
            return [r.to_dict() for r in reports]

        with _MEM_LOCK:
            mem_reports = [
                dict(r)
                for r in _MEM_REPORTS.values()
                if r.get("user_id") == user_id
            ]
            mem_reports.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            return mem_reports[:limit]

    async def get_policy(self, user_id: str) -> dict[str, Any]:
        """Get curator policy config thresholds for user."""
        default_policy = {
            "summarize_after_days": 30,
            "cluster_min_size": 3,
            "soft_delete_never_retrieved_days": 180,
            "hard_delete_after_days": 30,
            "notify_on_changes": True,
        }
        with _MEM_LOCK:
            return _MEM_POLICIES.get(user_id, default_policy).copy()

    async def save_policy(
        self, user_id: str, policy: dict[str, Any]
    ) -> dict[str, Any]:
        """Save customized curator policy thresholds for user."""
        with _MEM_LOCK:
            current = _MEM_POLICIES.get(user_id, {
                "summarize_after_days": 30,
                "cluster_min_size": 3,
                "soft_delete_never_retrieved_days": 180,
                "hard_delete_after_days": 30,
                "notify_on_changes": True,
            }).copy()
            current.update(policy)
            _MEM_POLICIES[user_id] = current
            return current.copy()

    async def get_stats(self, user_id: str) -> dict[str, Any]:
        """Compute user memory statistics."""
        if self._use_db and self.session:
            total_stmt = select(func.count()).where(SemanticMemory.user_id == user_id)
            total = (await self.session.execute(total_stmt)).scalar() or 0

            active_stmt = select(func.count()).where(
                SemanticMemory.user_id == user_id,
                SemanticMemory.is_soft_deleted == False,  # noqa: E712
            )
            active = (await self.session.execute(active_stmt)).scalar() or 0

            forever_stmt = select(func.count()).where(
                SemanticMemory.user_id == user_id,
                SemanticMemory.is_soft_deleted == False,  # noqa: E712
                SemanticMemory.importance == "forever",
            )
            forever = (await self.session.execute(forever_stmt)).scalar() or 0

            soft_stmt = select(func.count()).where(
                SemanticMemory.user_id == user_id,
                SemanticMemory.is_soft_deleted == True,  # noqa: E712
            )
            soft = (await self.session.execute(soft_stmt)).scalar() or 0

            reports_stmt = select(func.count()).where(CuratorRunReport.user_id == user_id)
            reports_count = (await self.session.execute(reports_stmt)).scalar() or 0

            last_report_stmt = (
                select(CuratorRunReport.created_at)
                .where(CuratorRunReport.user_id == user_id)
                .order_by(desc(CuratorRunReport.created_at))
                .limit(1)
            )
            last_report = (await self.session.execute(last_report_stmt)).scalar_one_or_none()

            return {
                "total_memories": total,
                "active_memories": active,
                "forever_memories": forever,
                "soft_deleted_memories": soft,
                "curator_runs_count": reports_count,
                "last_curated_at": last_report.isoformat() if last_report else None,
            }

        with _MEM_LOCK:
            user_items = [
                m for m in _MEM_MEMORIES.values() if m.get("user_id") == user_id
            ]
            total = len(user_items)
            active = sum(1 for m in user_items if not m.get("is_soft_deleted"))
            forever = sum(
                1
                for m in user_items
                if not m.get("is_soft_deleted") and m.get("importance") == "forever"
            )
            soft = sum(1 for m in user_items if m.get("is_soft_deleted"))

            user_reports = [
                r for r in _MEM_REPORTS.values() if r.get("user_id") == user_id
            ]
            reports_count = len(user_reports)
            last_curated = None
            if user_reports:
                user_reports.sort(key=lambda x: x.get("created_at") or "", reverse=True)
                last_curated = user_reports[0].get("created_at")

            return {
                "total_memories": total,
                "active_memories": active,
                "forever_memories": forever,
                "soft_deleted_memories": soft,
                "curator_runs_count": reports_count,
                "last_curated_at": last_curated,
            }
