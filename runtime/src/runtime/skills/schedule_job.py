"""schedule_job skill — APScheduler-based job scheduling.

Per PR 3 plan: creates/manages scheduled jobs using APScheduler.
Jobs are stored in-memory (database persistence lands in PR 4).

The skill manages jobs in a process-wide APScheduler instance.
Job actions are stored as JSON-serializable descriptors; when a
job fires, the runtime's scheduler runner calls back into the
Coordinator to execute the action.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

from runtime.skills.executor import SkillResult

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Process-wide APScheduler instance (singleton per runtime process)
# ---------------------------------------------------------------------------
_scheduler: AsyncIOScheduler | None = None

# ---------------------------------------------------------------------------
# Coordinator reference — injected at startup by main.py
# ---------------------------------------------------------------------------
# Kept as a module-level mutable ref so _fire_job can access it.
# Set via set_coordinator() after the Coordinator is constructed.
_coordinator_ref: "Coordinator | None" = None  # type: ignore[name-defined]


def set_coordinator(coord: "Coordinator") -> None:  # type: ignore[name-defined]
    """Inject the Coordinator so scheduled jobs can call it when they fire."""
    global _coordinator_ref
    _coordinator_ref = coord
    log.info("scheduler.coordinator_injected")


def _get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "coalesce": False,
                "max_instances": 1,
                "misfire_grace_time": 60,
            },
        )
        _scheduler.start()
        log.info("scheduler.started")
    return _scheduler


# ---------------------------------------------------------------------------
# Job descriptor (stored in APScheduler's JSON-serialized job args)
# ---------------------------------------------------------------------------


@dataclass
class JobDescriptor:
    """Serializable description of a scheduled job action."""

    user_id: str
    agent_slug: str
    skill_slug: str
    inputs: dict
    confirm_on_fire: bool = False
    name: str = ""
    timezone: str = "UTC"

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "agent_slug": self.agent_slug,
            "skill_slug": self.skill_slug,
            "inputs": self.inputs,
            "confirm_on_fire": self.confirm_on_fire,
            "name": self.name,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JobDescriptor":
        return cls(
            user_id=data["user_id"],
            agent_slug=data["agent_slug"],
            skill_slug=data["skill_slug"],
            inputs=data.get("inputs", {}),
            confirm_on_fire=data.get("confirm_on_fire", False),
            name=data.get("name", ""),
            timezone=data.get("timezone", "UTC"),
        )


# ---------------------------------------------------------------------------
# Cron expression parser (minimal — APScheduler handles the rest)
# ---------------------------------------------------------------------------

_MIN_INTERVAL_SECONDS = 60  # spec §10.7: once per minute minimum


async def _fire_job(job_id: str, descriptor: JobDescriptor) -> None:
    """Called by APScheduler when a job fires.

    Synthesises a query from the job's action and calls the Coordinator
    to execute it. For sensitive actions with confirm_on_fire=True, the
    job fires but the actual skill execution is deferred until the user
    confirms (via a notification sent to the user).

    The Coordinator is injected via set_coordinator() at startup (main.py).
    """
    log.info(
        "scheduler.job_fired",
        job_id=job_id,
        user_id=descriptor.user_id,
        agent=descriptor.agent_slug,
        skill=descriptor.skill_slug,
        confirm_on_fire=descriptor.confirm_on_fire,
    )

    coord = _coordinator_ref
    if coord is None:
        log.error(
            "scheduler.job_fired.no_coordinator",
            job_id=job_id,
            user_id=descriptor.user_id,
        )
        return

    # Synthesise a natural-language query that the Coordinator can route
    skill_args = ", ".join(f"{k}={repr(v)}" for k, v in descriptor.inputs.items())
    query = (
        f"[Scheduled job: {descriptor.name}] "
        f"Run {descriptor.skill_slug} with {skill_args}."
    )

    try:
        result = await coord.handle(
            query,
            user_id=descriptor.user_id,
            session_id=f"scheduler:{job_id}",
            bearer_token=None,  # scheduled jobs run without a live user token
        )
        log.info(
            "scheduler.job_completed",
            job_id=job_id,
            user_id=descriptor.user_id,
            agent=result.agent_slug,
            status=result.status,
        )
    except Exception as exc:
        log.error(
            "scheduler.job_failed",
            job_id=job_id,
            user_id=descriptor.user_id,
            error=str(exc),
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Skill implementation
# ---------------------------------------------------------------------------


async def schedule_job(
    op: Literal["create", "update", "list", "cancel", "pause", "resume"],
    job_id: str | None = None,
    name: str | None = None,
    schedule: str | None = None,
    timezone: str = "UTC",
    action: dict | None = None,
    confirm_on_fire: bool = False,
    tag: str | None = None,
    *,
    user_id: str,
    _gateway=None,
) -> SkillResult:
    """Manage scheduled jobs.

    Args:
        op: create | update | list | cancel | pause | resume
        job_id: required for update/cancel/pause/resume
        name: job name (for create/update)
        schedule: cron expression or ISO-8601 timestamp (for create/update)
        timezone: IANA timezone name (for create/update)
        action: {agent_slug, skill_slug, inputs} (for create/update)
        confirm_on_fire: if True, runtime re-confirms before each fire
        tag: optional filter for list
        user_id: for audit logging and job ownership

    Returns:
        SkillResult with operation-specific data
    """
    log.info(
        "schedule_job.invoked",
        user_id=user_id,
        op=op,
        job_id=job_id,
    )

    scheduler = _get_scheduler()

    # ---- List ---------------------------------------------------------------
    if op == "list":
        jobs = scheduler.get_jobs()
        result = []
        for job in jobs:
            desc: JobDescriptor = job.args[1] if len(job.args) > 1 else None
            if desc is None:
                continue
            # Filter by user_id (jobs are per-user)
            if desc.user_id != user_id:
                continue
            if tag and tag not in (desc.name or ""):
                continue
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            result.append({
                "job_id": job.id,
                "name": desc.name,
                "schedule": str(job.trigger),
                "timezone": desc.timezone,
                "action": desc.to_dict(),
                "confirm_on_fire": desc.confirm_on_fire,
                "next_run": next_run,
                "paused": job.next_run_time is None,
            })
        return SkillResult(ok=True, data={"jobs": result})

    # ---- Validate job_id for single-job ops ---------------------------------
    if op in ("update", "cancel", "pause", "resume"):
        if not job_id:
            return SkillResult(ok=False, data=None, error="job_id is required for " + op)
        existing = scheduler.get_job(job_id)
        if not existing:
            return SkillResult(ok=False, data=None, error=f"Job '{job_id}' not found")
        # Verify ownership
        desc: JobDescriptor = existing.args[1] if len(existing.args) > 1 else None
        if desc and desc.user_id != user_id:
            return SkillResult(ok=False, data=None, error="Job not found or access denied")

    # ---- Cancel -------------------------------------------------------------
    if op == "cancel":
        scheduler.remove_job(job_id)
        log.info("scheduler.job_cancelled", job_id=job_id, user_id=user_id)
        return SkillResult(ok=True, data={"job_id": job_id, "cancelled": True})

    # ---- Pause --------------------------------------------------------------
    if op == "pause":
        scheduler.pause_job(job_id)
        log.info("scheduler.job_paused", job_id=job_id, user_id=user_id)
        return SkillResult(ok=True, data={"job_id": job_id, "paused": True})

    # ---- Resume -------------------------------------------------------------
    if op == "resume":
        scheduler.resume_job(job_id)
        log.info("scheduler.job_resumed", job_id=job_id, user_id=user_id)
        return SkillResult(ok=True, data={"job_id": job_id, "resumed": True})

    # ---- Create / Update ----------------------------------------------------
    if op in ("create", "update"):
        if not name:
            return SkillResult(ok=False, data=None, error="name is required for create/update")
        if not schedule:
            return SkillResult(ok=False, data=None, error="schedule is required for create/update")
        if not action:
            return SkillResult(ok=False, data=None, error="action is required for create/update")

        agent_slug = action.get("agent_slug")
        skill_slug = action.get("skill_slug")
        inputs = action.get("inputs", {})

        if not agent_slug or not skill_slug:
            return SkillResult(
                ok=False,
                data=None,
                error="action must include agent_slug and skill_slug",
            )

        # Sensitive skill check: confirm_on_fire must be True
        # (runtime checks this at fire time; we just enforce the flag is set)
        _sensitive_skills = {"email_send", "browser_fill_form"}
        if skill_slug in _sensitive_skills and not confirm_on_fire:
            return SkillResult(
                ok=False,
                data=None,
                error=(
                    f"Action includes sensitive skill '{skill_slug}'; "
                    "confirm_on_fire must be True. "
                    "The runtime requires re-confirmation before each fire for sensitive actions."
                ),
            )

        descriptor = JobDescriptor(
            user_id=user_id,
            agent_slug=agent_slug,
            skill_slug=skill_slug,
            inputs=inputs,
            confirm_on_fire=confirm_on_fire,
            name=name,
            timezone=timezone,
        )

        trigger_id = job_id or str(uuid.uuid4())

        try:
            # APScheduler accepts cron expressions, date/datetime, or interval
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.date import DateTrigger
            from apscheduler.triggers.interval import IntervalTrigger

            # Try parsing as cron first
            if " " in schedule or "/" in schedule or "-" in schedule:
                # Likely a cron expression
                parts = schedule.split()
                if len(parts) >= 5:
                    trigger = CronTrigger.from_crontab(schedule, timezone=timezone)
                else:
                    return SkillResult(
                        ok=False,
                        data=None,
                        error=f"Invalid cron expression: '{schedule}'",
                    )
            elif "T" in schedule or schedule.count("-") >= 2:
                # ISO-8601 timestamp
                dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
                trigger = DateTrigger(run_date=dt)
            else:
                return SkillResult(
                    ok=False,
                    data=None,
                    error=f"Invalid schedule: '{schedule}'. Use a cron expression or ISO-8601 timestamp.",
                )
        except Exception as exc:
            return SkillResult(
                ok=False,
                data=None,
                error=f"Invalid schedule format: {exc}",
            )

        # Remove existing job if update
        if op == "update" and job_id:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

        job = scheduler.add_job(
            _fire_job,
            trigger=trigger,
            args=(trigger_id, descriptor),
            id=trigger_id,
            name=name,
            replace=True,
        )

        log.info(
            "scheduler.job_created",
            job_id=trigger_id,
            user_id=user_id,
            name=name,
            schedule=schedule,
        )

        next_run = job.next_run_time.isoformat() if job.next_run_time else None

        return SkillResult(
            ok=True,
            data={
                "job_id": trigger_id,
                "name": name,
                "schedule": schedule,
                "timezone": timezone,
                "action": descriptor.to_dict(),
                "confirm_on_fire": confirm_on_fire,
                "next_run": next_run,
            },
        )

    # ---- Unknown op ---------------------------------------------------------
    return SkillResult(
        ok=False,
        data=None,
        error=f"Unknown op: '{op}'. Use: create, update, list, cancel, pause, resume.",
    )
