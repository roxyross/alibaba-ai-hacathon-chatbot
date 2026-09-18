"""Dual-mode persistence repository for Audit Log (Phase 19).

Supports async PostgreSQL ORM with thread-safe in-memory fallback stores
for deterministic testing and offline local execution.
Guarantees append-only immutability.
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

from app.audit.schemas import AuditLogCreate
from app.models.audit_log import AuditLogEntry

log = structlog.get_logger()

# Thread-safe in-memory stores for testing / offline execution
_MEM_LOCK = threading.Lock()
_MEM_AUDIT_LOGS: list[dict[str, Any]] = []


def clear_in_memory_stores() -> None:
    """Clear in-memory stores between test runs."""
    with _MEM_LOCK:
        _MEM_AUDIT_LOGS.clear()


class AuditRepository:
    """Append-only repository handling audit logging, telemetry, and compliance."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self._use_db = session is not None and bool(os.environ.get("DATABASE_URL"))

    async def record_event(
        self,
        user_id: str,
        data: AuditLogCreate,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Record an immutable action entry to the audit log."""
        event_id = str(uuid.uuid4())
        effective_trace_id = trace_id or data.trace_id or str(uuid.uuid4())
        now = datetime.now(UTC)

        details_json = json.dumps(data.details or {})

        if self._use_db and self.session is not None:
            entry = AuditLogEntry(
                id=event_id,
                user_id=user_id,
                trace_id=effective_trace_id,
                agent_slug=data.agent_slug,
                action=data.action,
                skill_slug=data.skill_slug,
                approval_tier=data.approval_tier,
                approved_by=data.approved_by,
                model_used=data.model_used,
                provider=data.provider,
                request_query=data.request_query,
                response_summary=data.response_summary,
                decision=data.decision,
                latency_ms=data.latency_ms,
                status_code=data.status_code,
                details=details_json,
                created_at=now,
            )
            self.session.add(entry)
            await self.session.commit()
            await self.session.refresh(entry)
            return entry.to_dict()

        # In-memory store
        record = {
            "id": event_id,
            "user_id": user_id,
            "trace_id": effective_trace_id,
            "agent_slug": data.agent_slug,
            "action": data.action,
            "skill_slug": data.skill_slug,
            "approval_tier": data.approval_tier,
            "approved_by": data.approved_by,
            "model_used": data.model_used,
            "provider": data.provider,
            "request_query": data.request_query,
            "response_summary": data.response_summary,
            "decision": data.decision,
            "latency_ms": data.latency_ms,
            "status_code": data.status_code,
            "details": data.details or {},
            "created_at": now.isoformat(),
        }
        with _MEM_LOCK:
            _MEM_AUDIT_LOGS.append(record)
        return record

    async def get_event(self, user_id: str, event_id: str) -> dict[str, Any] | None:
        """Retrieve single audit entry enforcing multi-tenant isolation."""
        if self._use_db and self.session is not None:
            stmt = select(AuditLogEntry).where(
                AuditLogEntry.id == event_id,
                AuditLogEntry.user_id == user_id,
            )
            res = await self.session.execute(stmt)
            entry = res.scalar_one_or_none()
            return entry.to_dict() if entry else None

        with _MEM_LOCK:
            for item in _MEM_AUDIT_LOGS:
                if item["id"] == event_id and item["user_id"] == user_id:
                    return dict(item)
        return None

    async def list_events(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        agent_slug: str | None = None,
        status_code: str | None = None,
        approval_tier: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List audit entries for user with filters and pagination."""
        if self._use_db and self.session is not None:
            stmt = select(AuditLogEntry).where(AuditLogEntry.user_id == user_id)
            count_stmt = select(func.count(AuditLogEntry.id)).where(
                AuditLogEntry.user_id == user_id
            )

            if agent_slug:
                stmt = stmt.where(AuditLogEntry.agent_slug == agent_slug)
                count_stmt = count_stmt.where(AuditLogEntry.agent_slug == agent_slug)
            if status_code:
                stmt = stmt.where(AuditLogEntry.status_code == status_code)
                count_stmt = count_stmt.where(AuditLogEntry.status_code == status_code)
            if approval_tier:
                stmt = stmt.where(AuditLogEntry.approval_tier == approval_tier)
                count_stmt = count_stmt.where(
                    AuditLogEntry.approval_tier == approval_tier
                )
            if search:
                term = f"%{search}%"
                search_filter = (
                    AuditLogEntry.action.ilike(term)
                    | AuditLogEntry.request_query.ilike(term)
                    | AuditLogEntry.response_summary.ilike(term)
                )
                stmt = stmt.where(search_filter)
                count_stmt = count_stmt.where(search_filter)

            total_res = await self.session.execute(count_stmt)
            total = total_res.scalar() or 0

            stmt = stmt.order_by(desc(AuditLogEntry.created_at)).offset(skip).limit(limit)
            items_res = await self.session.execute(stmt)
            entries = items_res.scalars().all()
            return [e.to_dict() for e in entries], total

        # In-memory filtering
        with _MEM_LOCK:
            matching = [e for e in _MEM_AUDIT_LOGS if e["user_id"] == user_id]

        if agent_slug:
            matching = [e for e in matching if e.get("agent_slug") == agent_slug]
        if status_code:
            matching = [e for e in matching if e.get("status_code") == status_code]
        if approval_tier:
            matching = [e for e in matching if e.get("approval_tier") == approval_tier]
        if search:
            q = search.lower()
            matching = [
                e
                for e in matching
                if q in (e.get("action") or "").lower()
                or q in (e.get("request_query") or "").lower()
                or q in (e.get("response_summary") or "").lower()
            ]

        # Reverse chronological sort
        matching.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        total = len(matching)
        sliced = matching[skip : skip + limit]
        return [dict(x) for x in sliced], total

    async def list_today_events(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch today's events for user in reverse chronological order ('What did Jarvis do today')."""
        today_date = datetime.now(UTC).date()

        if self._use_db and self.session is not None:
            # Beginning and end of current UTC day
            start_of_day = datetime.combine(
                today_date, datetime.min.time(), tzinfo=UTC
            )
            stmt = (
                select(AuditLogEntry)
                .where(
                    AuditLogEntry.user_id == user_id,
                    AuditLogEntry.created_at >= start_of_day,
                )
                .order_by(desc(AuditLogEntry.created_at))
                .limit(limit)
            )
            res = await self.session.execute(stmt)
            entries = res.scalars().all()
            return [e.to_dict() for e in entries]

        # In-memory check
        today_iso = today_date.isoformat()
        with _MEM_LOCK:
            today_logs = [
                e
                for e in _MEM_AUDIT_LOGS
                if e["user_id"] == user_id
                and (e.get("created_at") or "").startswith(today_iso)
            ]
        today_logs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return [dict(x) for x in today_logs[:limit]]

    async def get_stats(self, user_id: str) -> dict[str, Any]:
        """Aggregate security and execution telemetry for user."""
        today_date = datetime.now(UTC).date()
        today_iso = today_date.isoformat()

        if self._use_db and self.session is not None:
            start_of_day = datetime.combine(
                today_date, datetime.min.time(), tzinfo=UTC
            )
            total_stmt = select(func.count(AuditLogEntry.id)).where(
                AuditLogEntry.user_id == user_id
            )
            today_stmt = select(func.count(AuditLogEntry.id)).where(
                AuditLogEntry.user_id == user_id,
                AuditLogEntry.created_at >= start_of_day,
            )
            avg_latency_stmt = select(func.avg(AuditLogEntry.latency_ms)).where(
                AuditLogEntry.user_id == user_id
            )
            last_event_stmt = (
                select(AuditLogEntry.created_at)
                .where(AuditLogEntry.user_id == user_id)
                .order_by(desc(AuditLogEntry.created_at))
                .limit(1)
            )

            total_res = await self.session.execute(total_stmt)
            today_res = await self.session.execute(today_stmt)
            avg_res = await self.session.execute(avg_latency_stmt)
            last_res = await self.session.execute(last_event_stmt)

            total_events = total_res.scalar() or 0
            today_events = today_res.scalar() or 0
            avg_latency = float(avg_res.scalar() or 0.0)
            last_event_dt = last_res.scalar()
            last_event_at = last_event_dt.isoformat() if last_event_dt else None

            # Breakdown by agent
            agent_stmt = (
                select(AuditLogEntry.agent_slug, func.count(AuditLogEntry.id))
                .where(AuditLogEntry.user_id == user_id)
                .group_by(AuditLogEntry.agent_slug)
            )
            agent_res = await self.session.execute(agent_stmt)
            by_agent = {row[0]: row[1] for row in agent_res.all()}

            # Breakdown by status
            status_stmt = (
                select(AuditLogEntry.status_code, func.count(AuditLogEntry.id))
                .where(AuditLogEntry.user_id == user_id)
                .group_by(AuditLogEntry.status_code)
            )
            status_res = await self.session.execute(status_stmt)
            by_status = {row[0]: row[1] for row in status_res.all()}

            # Breakdown by tier
            tier_stmt = (
                select(AuditLogEntry.approval_tier, func.count(AuditLogEntry.id))
                .where(AuditLogEntry.user_id == user_id)
                .group_by(AuditLogEntry.approval_tier)
            )
            tier_res = await self.session.execute(tier_stmt)
            by_tier = {row[0]: row[1] for row in tier_res.all()}

            return {
                "total_events": total_events,
                "today_events": today_events,
                "by_agent": by_agent,
                "by_status": by_status,
                "by_tier": by_tier,
                "avg_latency_ms": round(avg_latency, 2),
                "retention_days": 365,
                "last_event_at": last_event_at,
            }

        # In-memory computation
        with _MEM_LOCK:
            user_logs = [e for e in _MEM_AUDIT_LOGS if e["user_id"] == user_id]

        total_events = len(user_logs)
        today_events = sum(
            1 for e in user_logs if (e.get("created_at") or "").startswith(today_iso)
        )
        mem_by_agent: dict[str, int] = {}
        mem_by_status: dict[str, int] = {}
        mem_by_tier: dict[str, int] = {}
        total_latency = 0

        for e in user_logs:
            agent = e.get("agent_slug") or "coordinator"
            mem_by_agent[agent] = mem_by_agent.get(agent, 0) + 1

            status = e.get("status_code") or "ok"
            mem_by_status[status] = mem_by_status.get(status, 0) + 1

            tier = e.get("approval_tier") or "T1"
            mem_by_tier[tier] = mem_by_tier.get(tier, 0) + 1

            total_latency += e.get("latency_ms") or 0

        avg_latency = (total_latency / total_events) if total_events > 0 else 0.0
        last_event_at = user_logs[-1]["created_at"] if user_logs else None

        return {
            "total_events": total_events,
            "today_events": today_events,
            "by_agent": mem_by_agent,
            "by_status": mem_by_status,
            "by_tier": mem_by_tier,
            "avg_latency_ms": round(avg_latency, 2),
            "retention_days": 365,
            "last_event_at": last_event_at,
        }

    async def export_user_logs(self, user_id: str) -> list[dict[str, Any]]:
        """Return all user logs in chronological order for GDPR Article 20 export."""
        if self._use_db and self.session is not None:
            stmt = (
                select(AuditLogEntry)
                .where(AuditLogEntry.user_id == user_id)
                .order_by(AuditLogEntry.created_at)
            )
            res = await self.session.execute(stmt)
            entries = res.scalars().all()
            return [e.to_dict() for e in entries]

        with _MEM_LOCK:
            user_logs = [e for e in _MEM_AUDIT_LOGS if e["user_id"] == user_id]
        user_logs.sort(key=lambda x: x.get("created_at") or "")
        return [dict(x) for x in user_logs]
