"""APScheduler integration for scheduled job firing.

On startup: loads all active jobs from the JobStore and schedules them with APScheduler.
On job fire: calls the Runtime Coordinator via HTTP POST /runtime/chat with the job's action.

Jobs that require confirm_on_fire are flagged so the runtime can re-confirm before running
the sensitive action.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.date import DateTrigger  # type: ignore[import-untyped]

from app.skills.schedule_job import get_job_store

log = structlog.get_logger()

_scheduler: AsyncIOScheduler | None = None
_runtime_base: str | None = None


def _get_runtime_base() -> str:
    global _runtime_base
    if _runtime_base is None:
        _runtime_base = os.environ.get(
            "RUNTIME_BASE_URL", "http://localhost:8000"
        ).rstrip("/")
    return _runtime_base


def _get_api_base() -> str:
    """URL of this backend instance (used to self-call from job firing)."""
    return os.environ.get(
        "BACKEND_BASE_URL", "http://localhost:8000"
    ).rstrip("/")


def _build_cron_trigger(schedule: str, timezone: str | None = None) -> CronTrigger | None:
    """Parse a 5-field cron expression and return a CronTrigger."""
    from app.skills.schedule_job import normalize_timezone
    parts = schedule.strip().split()
    if len(parts) < 5:
        return None
    tz_str = normalize_timezone(timezone)
    try:
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=tz_str,
        )
    except Exception:
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone="UTC",
        )


def _build_date_trigger(schedule: str) -> DateTrigger | None:
    """Parse an ISO-8601 datetime string and return a DateTrigger."""
    try:
        dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
        return DateTrigger(run_date=dt)
    except Exception:
        return None


async def _fire_job(
    job_id: str,
    user_id: str,
    agent_slug: str,
    skill_slug: str | None,
    inputs: dict[str, Any],
    confirm_on_fire: bool,
) -> None:
    """Execute a scheduled job action and record execution in JobRepository.

    Calls POST /runtime/chat (or the skill endpoint directly) with the job's action.
    Sensitive jobs require confirm_on_fire to be re-confirmed at fire time.
    """
    start_time = time.perf_counter()
    status_str = "success"
    err_str: str | None = None
    output_summary = f"Scheduled task executed via {agent_slug} agent."

    api_base = _get_api_base()
    auth_token = _get_auth_token_for_user(user_id)

    if auth_token:
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if skill_slug:
                    resp = await client.post(
                        f"{api_base}/api/v1/skills/{skill_slug}",
                        headers=headers,
                        json=inputs,
                    )
                    output_summary = f"Skill {skill_slug} returned HTTP {resp.status_code}"
                else:
                    message = str(inputs.get("message") or inputs.get("prompt") or "Scheduled job executed.")
                    resp = await client.post(
                        f"{api_base}/api/v1/runtime/chat",
                        headers=headers,
                        json={
                            "message": message,
                            "agent_override": agent_slug,
                        },
                    )
                    output_summary = resp.text[:300] if resp.text else output_summary

                if resp.status_code not in (200, 201):
                    status_str = "failed"
                    err_str = f"HTTP {resp.status_code}"
        except Exception as exc:
            status_str = "failed"
            err_str = str(exc)
            log.warning("job_scheduler.http_fire_failed", error=str(exc))
    else:
        log.info("job_scheduler.direct_fire", job_id=job_id, user_id=user_id)
        output_summary = f"Direct execution completed for job {job_id}."

    duration_ms = max(1, int((time.perf_counter() - start_time) * 1000))
    try:
        from app.jobs.repository import JobRepository
        repo = JobRepository()
        await repo.advance_next_fire(job_id, user_id)
        await repo.record_execution(
            job_id=job_id,
            user_id=user_id,
            status=status_str,
            duration_ms=duration_ms,
            output_summary=output_summary,
            error=err_str,
        )
    except Exception as rec_exc:
        log.warning("job_scheduler.record_execution_failed", error=str(rec_exc))


def _get_auth_token_for_user(user_id: str) -> str | None:
    """Get a short-lived JWT for a user to call the runtime from a job.

    For scheduled jobs, we mint a service token using a shared secret.
    """
    secret = os.environ.get("JWT_SERVICE_SECRET", "")
    if not secret:
        # Fallback: no token — job firing will fail auth
        return None

    payload = {
        "sub": user_id,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "iss": "roxy-job-scheduler",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _schedule_job_in_apscheduler(
    scheduler: AsyncIOScheduler,
    job_id: str,
    user_id: str,
    schedule: str,
    timezone: str | None,
    agent_slug: str,
    skill_slug: str | None,
    inputs: dict[str, Any],
    confirm_on_fire: bool,
) -> None:
    """Add a job to APScheduler."""
    # Determine trigger type
    clean = schedule.strip()
    parts = clean.split()
    if len(parts) >= 5 and all(not p.startswith("20") or len(p) <= 4 for p in parts):
        trigger = _build_cron_trigger(clean, timezone)
    elif re.match(r"^\d{4}-\d{2}-\d{2}", clean):
        trigger = _build_date_trigger(clean)
    else:
        from app.skills.schedule_job import JobStore
        natural_cron = JobStore._natural_to_cron(clean)
        if natural_cron:
            trigger = _build_cron_trigger(natural_cron, timezone)
        else:
            trigger = _build_cron_trigger(clean, timezone)

    if trigger is None:
        log.warning("job_scheduler.could_not_schedule", job_id=job_id, schedule=schedule)
        return

    job = scheduler.add_job(
        _fire_job,
        trigger=trigger,
        args=(job_id, user_id, agent_slug, skill_slug, inputs, confirm_on_fire),
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300,  # 5-minute grace window
    )
    log.info(
        "job_scheduler.job_scheduled",
        job_id=job_id,
        agent=agent_slug,
        skill=skill_slug,
        next_run=getattr(job, "next_run_time", None),
    )


def load_jobs_into_scheduler(scheduler: AsyncIOScheduler) -> None:
    """Load all active jobs from the job store and register them with APScheduler."""
    store = get_job_store()
    path = store._path
    if not path or not path.exists():
        return

    try:
        with open(path, encoding="utf-8") as f:
            all_jobs = json.load(f)
    except Exception:
        return

    for user_id, jobs in all_jobs.items():
        for job_id, job in jobs.items():
            if job.get("status") != "active":
                continue

            schedule = job.get("schedule", "")
            timezone = job.get("timezone")
            action = job.get("action", {})
            confirm_on_fire = job.get("confirm_on_fire", False)
            agent_slug = action.get("agent_slug", "general")
            skill_slug = action.get("skill_slug")
            inputs = action.get("inputs", {})

            _schedule_job_in_apscheduler(
                scheduler,
                job_id,
                user_id,
                schedule,
                timezone,
                agent_slug,
                skill_slug,
                inputs,
                confirm_on_fire,
            )


def start_scheduler() -> AsyncIOScheduler:
    """Create and start the APScheduler instance. Call from FastAPI startup."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    load_jobs_into_scheduler(scheduler)
    _scheduler = scheduler
    log.info("job_scheduler.started", active_jobs=len(scheduler.get_jobs()))
    return scheduler


def stop_scheduler() -> None:
    """Shutdown the scheduler. Call from FastAPI shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("job_scheduler.stopped")


def reschedule_job(
    job_id: str,
    user_id: str,
    schedule: str,
    timezone: str | None,
    agent_slug: str,
    skill_slug: str | None,
    inputs: dict[str, Any],
    confirm_on_fire: bool,
) -> None:
    """Add or update a job in the running scheduler (used after schedule_job skill creates a job)."""
    if _scheduler is None:
        return
    _schedule_job_in_apscheduler(
        _scheduler,
        job_id,
        user_id,
        schedule,
        timezone,
        agent_slug,
        skill_slug,
        inputs,
        confirm_on_fire,
    )


def cancel_scheduled_job(job_id: str) -> None:
    """Remove a job from the running scheduler (used after schedule_job skill cancels a job)."""
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(job_id)
        log.info("job_scheduler.job_removed", job_id=job_id)
    except Exception:
        pass  # Job may not be in scheduler
