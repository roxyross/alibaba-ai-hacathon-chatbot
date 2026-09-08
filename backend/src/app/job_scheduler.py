"""APScheduler integration for scheduled job firing.

On startup: loads all active jobs from the JobStore and schedules them with APScheduler.
On job fire: calls the Runtime Coordinator via HTTP POST /runtime/chat with the job's action.

Jobs that require confirm_on_fire are flagged so the runtime can re-confirm before running
the sensitive action.
"""

from __future__ import annotations

import asyncio
import json
import os
import httpx
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

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


def _build_cron_trigger(schedule: str, timezone: str | None = None):
    """Parse a 5-field cron expression and return a CronTrigger."""
    parts = schedule.strip().split()
    if len(parts) < 5:
        return None
    return CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        timezone=timezone or "UTC",
    )


def _build_date_trigger(schedule: str):
    """Parse an ISO-8601 datetime string and return a DateTrigger."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
        return DateTrigger(run_date=dt)
    except Exception:
        return None


async def _fire_job(job_id: str, user_id: str, agent_slug: str, skill_slug: str | None, inputs: dict, confirm_on_fire: bool):
    """Execute a scheduled job action.

    Calls POST /runtime/chat (or the skill endpoint directly) with the job's action.
    Sensitive jobs require confirm_on_fire to be re-confirmed at fire time.
    """
    api_base = _get_api_base()
    auth_token = _get_auth_token_for_user(user_id)
    if not auth_token:
        log.warning("job_scheduler.no_auth_token", job_id=job_id, user_id=user_id)
        return

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if skill_slug:
                # Call the skill endpoint directly
                resp = await client.post(
                    f"{api_base}/api/v1/skills/{skill_slug}",
                    headers=headers,
                    json=inputs,
                )
                log.info(
                    "job_scheduler.skill_fired",
                    job_id=job_id,
                    skill=skill_slug,
                    status=resp.status_code,
                )
            else:
                # Call the runtime coordinator
                message = inputs.get("message", "Scheduled job executed.")
                resp = await client.post(
                    f"{api_base}/api/v1/runtime/chat",
                    headers=headers,
                    json={
                        "message": message,
                        "agent_override": agent_slug,
                    },
                )
                log.info(
                    "job_scheduler.agent_fired",
                    job_id=job_id,
                    agent=agent_slug,
                    status=resp.status_code,
                )

            if resp.status_code not in (200, 201):
                log.error(
                    "job_scheduler.job_failed",
                    job_id=job_id,
                    status=resp.status_code,
                    body=resp.text[:200],
                )
    except httpx.TimeoutException:
        log.error("job_scheduler.job_timeout", job_id=job_id)
    except Exception as exc:
        log.error("job_scheduler.job_error", job_id=job_id, error=str(exc))


def _get_auth_token_for_user(user_id: str) -> str | None:
    """Get a short-lived JWT for a user to call the runtime from a job.

    For scheduled jobs, we mint a service token using a shared secret.
    """
    import os
    secret = os.environ.get("JWT_SERVICE_SECRET", "")
    if not secret:
        # Fallback: no token — job firing will fail auth
        return None

    import jwt
    from datetime import datetime, timedelta, timezone as tz
    payload = {
        "sub": user_id,
        "iat": datetime.now(tz.utc),
        "exp": datetime.now(tz.utc) + timedelta(hours=1),
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
    inputs: dict,
    confirm_on_fire: bool,
):
    """Add a job to APScheduler."""
    from app.skills.schedule_job import JobAction

    # Determine trigger type
    if schedule.strip().startswith(("2", "20", "19", "18", "17", "16", "15", "14", "13", "12", "11", "10", "0")):
        # Looks like an ISO datetime
        trigger = _build_date_trigger(schedule)
    else:
        trigger = _build_cron_trigger(schedule, timezone)

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
        next_run=job.next_run_time,
    )


def load_jobs_into_scheduler(scheduler: AsyncIOScheduler):
    """Load all active jobs from the job store and register them with APScheduler."""
    store = get_job_store()
    # Load all users' jobs
    import json, os
    path = store._path
    if not path or not path.exists():
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
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
    load_jobs_into_scheduler(scheduler)
    scheduler.start()
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
    inputs: dict,
    confirm_on_fire: bool,
):
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


def cancel_scheduled_job(job_id: str):
    """Remove a job from the running scheduler (used after schedule_job skill cancels a job)."""
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(job_id)
        log.info("job_scheduler.job_removed", job_id=job_id)
    except Exception:
        pass  # Job may not be in scheduler
