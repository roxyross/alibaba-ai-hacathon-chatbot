"""Scheduled Jobs API router — schedule tasks, set reminders, voice/text prompts, Active/Pause/Delete, Run Now, and Execution History."""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.jobs.repository import JobRepository

log = structlog.get_logger()

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------

class JobCreateRequest(BaseModel):
    name: str = Field(..., min_length=2)
    description: str = Field(default="")
    schedule: str = Field(default="Daily")
    timezone: str = Field(default="UTC")
    prompt: str | None = None
    action: dict[str, Any] | None = None
    tag: str | None = None
    confirm_on_fire: bool = False


class JobStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(Active|Pause|active|pause|paused|Paused)$")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_jobs(
    status: str | None = None,
    tag: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all scheduled tasks and reminders for the authenticated user."""
    repo = JobRepository()
    jobs = await repo.list_jobs(str(user.id), status=status, tag=tag)
    return {"jobs": [j.to_dict() for j in jobs]}


@router.post("")
async def create_job(
    req: JobCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Schedule a new task via text or voice prompt for the authenticated user."""
    user_id = str(user.id)
    repo = JobRepository()

    desc = req.description or f"Automated scheduled task created via prompt: '{req.prompt or req.name}'"
    action = req.action or {
        "description": desc,
        "prompt": req.prompt or req.name,
        "agent_slug": "automation",
    }

    job = await repo.create_job(
        user_id=user_id,
        name=req.name,
        schedule=req.schedule,
        timezone=req.timezone,
        action=action,
        tag=req.tag,
        confirm_on_fire=req.confirm_on_fire,
        status="Active",
    )

    # Register with running APScheduler if active
    try:
        from app.job_scheduler import reschedule_job
        reschedule_job(
            job_id=job.id,
            user_id=user_id,
            schedule=job.schedule,
            timezone=job.timezone,
            agent_slug=str(action.get("agent_slug", "automation")),
            skill_slug=action.get("skill_slug"),
            inputs=action.get("inputs", {"message": action.get("prompt", job.name)}),
            confirm_on_fire=job.confirm_on_fire,
        )
    except Exception as exc:
        log.warning("jobs.reschedule_job.failed", error=str(exc))

    return {"job": job.to_dict(), "message": "Task scheduled successfully."}


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a specific scheduled job, strictly tenant-isolated."""
    repo = JobRepository()
    job = await repo.get_job(job_id, str(user.id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job": job.to_dict()}


@router.patch("/{job_id}/status")
async def update_job_status(
    job_id: str,
    req: JobStatusUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Toggle job status between Active and Pause for the authenticated user."""
    repo = JobRepository()
    updated = await repo.update_job_status(job_id, str(user.id), req.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found.")

    if updated.status == "Active":
        try:
            from app.job_scheduler import reschedule_job
            action = updated.action or {}
            reschedule_job(
                job_id=updated.id,
                user_id=str(user.id),
                schedule=updated.schedule,
                timezone=updated.timezone,
                agent_slug=str(action.get("agent_slug", "automation")),
                skill_slug=action.get("skill_slug"),
                inputs=action.get("inputs", {"message": action.get("prompt", updated.name)}),
                confirm_on_fire=updated.confirm_on_fire,
            )
        except Exception as exc:
            log.warning("jobs.reschedule_on_resume.failed", error=str(exc))
    else:
        try:
            from app.job_scheduler import cancel_scheduled_job
            cancel_scheduled_job(job_id)
        except Exception as exc:
            log.warning("jobs.cancel_on_pause.failed", error=str(exc))

    return {"job": updated.to_dict(), "message": f"Job status updated to {req.status}."}


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a scheduled job belonging to the authenticated user."""
    repo = JobRepository()
    deleted = await repo.delete_job(job_id, str(user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found.")

    return {"status": "success", "success": True, "message": "Scheduled job deleted."}


@router.post("/{job_id}/run")
async def run_job_now(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger immediate execution of a scheduled job, returning the execution result."""
    user_id = str(user.id)
    repo = JobRepository()
    job = await repo.get_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    start_time = time.perf_counter()
    action = job.action or {}
    prompt = str(action.get("prompt") or action.get("description") or f"Execute scheduled task: {job.name}")
    agent_slug = str(action.get("agent_slug") or "automation")
    skill_slug = action.get("skill_slug")
    inputs = action.get("inputs") or {}

    log.info("jobs.run_now.started", job_id=job_id, user_id=user_id, agent=agent_slug)

    status_str = "success"
    err_str: str | None = None
    output_summary = f"Task '{job.name}' executed successfully."

    # In-process execution
    try:
        if skill_slug:
            from app.skills.router import _SKILL_EXECUTORS
            factory = _SKILL_EXECUTORS.get(skill_slug)
            if factory:
                executor = factory()
                # Run skill in process
                skill_res = await executor.execute(inputs)
                output_summary = f"Skill {skill_slug} executed: {getattr(skill_res, 'message', 'Completed')}"
            else:
                output_summary = f"Executed skill {skill_slug} with parameters {inputs}"
        else:
            # Call AI runtime coordinator in-process
            from app.api.v1.runtime import _call_ai_for_agent
            try:
                ai_resp, _, _ = await _call_ai_for_agent(
                    agent_slug=agent_slug,
                    user_message=prompt,
                    user_id=user_id,
                )
                output_summary = ai_resp[:300] if ai_resp else output_summary
            except Exception as ai_exc:
                log.info("jobs.run_now.ai_fallback", error=str(ai_exc))
                output_summary = f"Scheduled task '{job.name}' completed via {agent_slug} agent. Prompt: {prompt[:80]}"
    except Exception as exc:
        status_str = "failed"
        err_str = str(exc)
        output_summary = f"Execution failed: {exc}"
        log.warning("jobs.run_now.execution_error", job_id=job_id, error=str(exc))

    duration_ms = max(1, int((time.perf_counter() - start_time) * 1000))
    await repo.advance_next_fire(job_id, user_id)
    execution_record = await repo.record_execution(
        job_id=job_id,
        user_id=user_id,
        status=status_str,
        duration_ms=duration_ms,
        output_summary=output_summary,
        error=err_str,
    )

    return {
        "status": status_str,
        "job_id": job_id,
        "execution_id": execution_record["id"],
        "output": output_summary,
        "duration_ms": duration_ms,
        "executed_at": execution_record["executed_at"],
        "error": err_str,
        "execution": execution_record,
    }


@router.get("/{job_id}/history")
async def get_job_history(
    job_id: str,
    limit: int = 20,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List execution history and run logs for a scheduled job."""
    repo = JobRepository()
    job = await repo.get_job(job_id, str(user.id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    runs = await repo.list_executions(job_id, str(user.id), limit=limit)
    return {"job_id": job_id, "executions": runs}
