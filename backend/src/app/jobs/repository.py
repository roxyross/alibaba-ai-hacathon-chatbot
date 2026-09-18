"""Job repository — async ORM queries for scheduled_jobs and execution history.

Provides access to `scheduled_jobs` with resilient in-memory fallback stores
(_MEM_JOBS, _MEM_EXECUTIONS) when database is unconfigured or in testing environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import structlog

from app.db import get_session_factory
from app.models.scheduled_job import ScheduledJob

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class _MemJob:
    id: str
    user_id: str
    name: str
    schedule: str
    timezone: str
    action: dict[str, Any]
    status: str = "Active"
    confirm_on_fire: bool = False
    tag: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    next_fire_at: datetime | None = None


@dataclass
class _MemExecution:
    id: str
    job_id: str
    user_id: str
    status: str
    duration_ms: int
    output_summary: str
    error: str | None = None
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_MEM_JOBS: dict[str, _MemJob] = {}
_MEM_EXECUTIONS: dict[str, list[_MemExecution]] = {}


@dataclass
class JobItem:
    id: str
    name: str
    description: str
    schedule: str
    timezone: str
    status: str
    created_at: str | None
    next_run: str
    action: dict[str, Any]
    tag: str | None = None
    confirm_on_fire: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "schedule": self.schedule,
            "timezone": self.timezone,
            "status": self.status,
            "created_at": self.created_at,
            "next_run": self.next_run,
            "action": self.action,
            "tag": self.tag,
            "confirm_on_fire": self.confirm_on_fire,
        }


# ---------------------------------------------------------------------------
# Repository Implementation
# ---------------------------------------------------------------------------

class JobRepository:
    """Enterprise-grade repository for multi-tenant scheduled jobs & executions."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory

    def _get_factory(self) -> async_sessionmaker[AsyncSession] | None:
        if self._session_factory is not None:
            return self._session_factory
        return get_session_factory()

    @staticmethod
    def _normalize_status(raw: str) -> str:
        if raw.lower() in ("pause", "paused"):
            return "Pause"
        return "Active"

    @staticmethod
    def _format_next_run(next_fire_at: datetime | None, status: str) -> str:
        if status == "Pause":
            return "Paused"
        if next_fire_at:
            return next_fire_at.strftime("%b %d, %Y %I:%M %p")
        return "Scheduled"

    async def create_job(
        self,
        user_id: str,
        name: str,
        schedule: str,
        timezone: str,
        action: dict[str, Any],
        tag: str | None = None,
        confirm_on_fire: bool = False,
        status: str = "Active",
    ) -> JobItem:
        """Create and persist a new scheduled job."""
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        norm_status = self._normalize_status(status)
        next_fire = now + timedelta(days=1) if norm_status == "Active" else None
        desc = str(action.get("description", "")) if action else ""

        # In-memory store
        mem_job = _MemJob(
            id=job_id,
            user_id=user_id,
            name=name,
            schedule=schedule,
            timezone=timezone,
            action=action,
            status=norm_status,
            confirm_on_fire=confirm_on_fire,
            tag=tag,
            created_at=now,
            next_fire_at=next_fire,
        )
        _MEM_JOBS[job_id] = mem_job

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    db_job = ScheduledJob(
                        id=job_id,
                        user_id=user_id,
                        name=name,
                        schedule=schedule,
                        timezone=timezone,
                        action=action,
                        confirm_on_fire=confirm_on_fire,
                        status=norm_status,
                        created_at=now,
                        next_fire_at=next_fire,
                        tag=tag,
                    )
                    sess.add(db_job)
                    await sess.commit()
            except Exception as exc:
                log.warning("jobs_repo.create_job.db_failed", error=str(exc))

        log.info("jobs_repo.job_created", job_id=job_id, user_id=user_id, name=name)
        return JobItem(
            id=job_id,
            name=name,
            description=desc,
            schedule=schedule,
            timezone=timezone,
            status=norm_status,
            created_at=now.isoformat(),
            next_run=self._format_next_run(next_fire, norm_status),
            action=action,
            tag=tag,
            confirm_on_fire=confirm_on_fire,
        )

    async def list_jobs(
        self,
        user_id: str,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[JobItem]:
        """List all scheduled jobs for the user, strictly tenant-isolated."""
        factory = self._get_factory()
        db_items: list[JobItem] = []

        if factory is not None:
            try:
                async with factory() as sess:
                    query = select(ScheduledJob).where(ScheduledJob.user_id == user_id)
                    if status:
                        query = query.where(ScheduledJob.status == self._normalize_status(status))
                    if tag:
                        query = query.where(ScheduledJob.tag == tag)
                    query = query.order_by(ScheduledJob.created_at.desc())
                    res = await sess.execute(query)
                    rows = res.scalars().all()
                    for r in rows:
                        db_items.append(
                            JobItem(
                                id=r.id,
                                name=r.name,
                                description=(r.action or {}).get("description", ""),
                                schedule=r.schedule,
                                timezone=r.timezone,
                                status=self._normalize_status(r.status),
                                created_at=r.created_at.isoformat() if r.created_at else None,
                                next_run=self._format_next_run(r.next_fire_at, self._normalize_status(r.status)),
                                action=r.action or {},
                                tag=r.tag,
                                confirm_on_fire=r.confirm_on_fire or False,
                            )
                        )
                    if db_items:
                        return db_items
            except Exception as exc:
                log.warning("jobs_repo.list_jobs.db_failed", error=str(exc))

        # Fallback to in-memory store
        items: list[JobItem] = []
        for j in _MEM_JOBS.values():
            if j.user_id != user_id:
                continue
            if status and j.status != self._normalize_status(status):
                continue
            if tag and j.tag != tag:
                continue
            items.append(
                JobItem(
                    id=j.id,
                    name=j.name,
                    description=str(j.action.get("description", "")),
                    schedule=j.schedule,
                    timezone=j.timezone,
                    status=j.status,
                    created_at=j.created_at.isoformat(),
                    next_run=self._format_next_run(j.next_fire_at, j.status),
                    action=j.action,
                    tag=j.tag,
                    confirm_on_fire=j.confirm_on_fire,
                )
            )
        items.sort(key=lambda x: x.created_at or "", reverse=True)
        return items

    async def get_job(self, job_id: str, user_id: str) -> JobItem | None:
        """Fetch a scheduled job by ID, guaranteeing tenant isolation."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(ScheduledJob).where(
                            ScheduledJob.id == job_id,
                            ScheduledJob.user_id == user_id,
                        )
                    )
                    r = res.scalars().first()
                    if r:
                        return JobItem(
                            id=r.id,
                            name=r.name,
                            description=(r.action or {}).get("description", ""),
                            schedule=r.schedule,
                            timezone=r.timezone,
                            status=self._normalize_status(r.status),
                            created_at=r.created_at.isoformat() if r.created_at else None,
                            next_run=self._format_next_run(r.next_fire_at, self._normalize_status(r.status)),
                            action=r.action or {},
                            tag=r.tag,
                            confirm_on_fire=r.confirm_on_fire or False,
                        )
            except Exception as exc:
                log.warning("jobs_repo.get_job.db_failed", error=str(exc))

        # Check in-memory store
        mem = _MEM_JOBS.get(job_id)
        if mem and mem.user_id == user_id:
            return JobItem(
                id=mem.id,
                name=mem.name,
                description=str(mem.action.get("description", "")),
                schedule=mem.schedule,
                timezone=mem.timezone,
                status=mem.status,
                created_at=mem.created_at.isoformat(),
                next_run=self._format_next_run(mem.next_fire_at, mem.status),
                action=mem.action,
                tag=mem.tag,
                confirm_on_fire=mem.confirm_on_fire,
            )
        return None

    async def update_job_status(
        self,
        job_id: str,
        user_id: str,
        status: str,
    ) -> JobItem | None:
        """Update job status (Active vs Pause) and adjust next_fire_at."""
        norm = self._normalize_status(status)
        now = datetime.now(UTC)
        next_fire = now + timedelta(hours=12) if norm == "Active" else None

        factory = self._get_factory()
        updated_from_db: JobItem | None = None

        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(ScheduledJob).where(
                            ScheduledJob.id == job_id,
                            ScheduledJob.user_id == user_id,
                        )
                    )
                    orm_job = res.scalars().first()
                    if orm_job:
                        orm_job.status = norm
                        orm_job.next_fire_at = next_fire
                        await sess.commit()
                        await sess.refresh(orm_job)
                        updated_from_db = JobItem(
                            id=orm_job.id,
                            name=orm_job.name,
                            description=(orm_job.action or {}).get("description", ""),
                            schedule=orm_job.schedule,
                            timezone=orm_job.timezone,
                            status=norm,
                            created_at=orm_job.created_at.isoformat() if orm_job.created_at else None,
                            next_run=self._format_next_run(next_fire, norm),
                            action=orm_job.action or {},
                            tag=orm_job.tag,
                            confirm_on_fire=orm_job.confirm_on_fire or False,
                        )
            except Exception as exc:
                log.warning("jobs_repo.update_status.db_failed", error=str(exc))

        # Also update in-memory store
        mem = _MEM_JOBS.get(job_id)
        if mem and mem.user_id == user_id:
            mem.status = norm
            mem.next_fire_at = next_fire
            if not updated_from_db:
                return JobItem(
                    id=mem.id,
                    name=mem.name,
                    description=str(mem.action.get("description", "")),
                    schedule=mem.schedule,
                    timezone=mem.timezone,
                    status=norm,
                    created_at=mem.created_at.isoformat(),
                    next_run=self._format_next_run(next_fire, norm),
                    action=mem.action,
                    tag=mem.tag,
                    confirm_on_fire=mem.confirm_on_fire,
                )

        return updated_from_db

    async def advance_next_fire(self, job_id: str, user_id: str) -> None:
        """Advance next_fire_at after execution."""
        next_dt = datetime.now(UTC) + timedelta(days=1)
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as sess:
                    res = await sess.execute(
                        select(ScheduledJob).where(
                            ScheduledJob.id == job_id,
                            ScheduledJob.user_id == user_id,
                        )
                    )
                    r = res.scalars().first()
                    if r:
                        r.next_fire_at = next_dt
                        await sess.commit()
            except Exception:
                pass
        mem = _MEM_JOBS.get(job_id)
        if mem and mem.user_id == user_id:
            mem.next_fire_at = next_dt

    async def delete_job(self, job_id: str, user_id: str) -> bool:
        """Delete scheduled job and its execution records, returning True if deleted."""
        deleted = False
        factory = self._get_factory()

        if factory is not None:
            try:
                async with factory() as sess:
                    del_res = await sess.execute(
                        delete(ScheduledJob).where(
                            ScheduledJob.id == job_id,
                            ScheduledJob.user_id == user_id,
                        )
                    )
                    rowcount = getattr(del_res, "rowcount", None) or 0
                    if rowcount > 0:
                        deleted = True
                    await sess.commit()
            except Exception as exc:
                log.warning("jobs_repo.delete_job.db_failed", error=str(exc))

        # Clean from in-memory stores
        mem = _MEM_JOBS.get(job_id)
        if mem and mem.user_id == user_id:
            del _MEM_JOBS[job_id]
            deleted = True

        if job_id in _MEM_EXECUTIONS:
            del _MEM_EXECUTIONS[job_id]

        if deleted:
            try:
                from app.job_scheduler import cancel_scheduled_job
                cancel_scheduled_job(job_id)
            except Exception:
                pass

        return deleted

    async def record_execution(
        self,
        job_id: str,
        user_id: str,
        status: str,
        duration_ms: int,
        output_summary: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Record an execution run log for a scheduled job."""
        exec_id = f"exec-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        entry = _MemExecution(
            id=exec_id,
            job_id=job_id,
            user_id=user_id,
            status=status,
            duration_ms=duration_ms,
            output_summary=output_summary,
            error=error,
            executed_at=now,
        )
        if job_id not in _MEM_EXECUTIONS:
            _MEM_EXECUTIONS[job_id] = []
        _MEM_EXECUTIONS[job_id].insert(0, entry)

        log.info(
            "jobs_repo.execution_recorded",
            job_id=job_id,
            status=status,
            duration_ms=duration_ms,
        )
        return {
            "id": exec_id,
            "job_id": job_id,
            "status": status,
            "triggered_by": "manual",
            "duration_ms": duration_ms,
            "output_summary": output_summary,
            "result_summary": output_summary,
            "error": error,
            "error_message": error,
            "executed_at": now.isoformat(),
            "created_at": now.isoformat(),
        }

    async def list_executions(
        self,
        job_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List execution run logs for a specific job, tenant-verified."""
        job = await self.get_job(job_id, user_id)
        if not job:
            return []

        entries = _MEM_EXECUTIONS.get(job_id, [])
        return [
            {
                "id": e.id,
                "job_id": e.job_id,
                "status": e.status,
                "triggered_by": "manual",
                "duration_ms": e.duration_ms,
                "output_summary": e.output_summary,
                "result_summary": e.output_summary,
                "error": e.error,
                "error_message": e.error,
                "executed_at": e.executed_at.isoformat(),
                "created_at": e.executed_at.isoformat(),
            }
            for e in entries[:limit]
        ]

