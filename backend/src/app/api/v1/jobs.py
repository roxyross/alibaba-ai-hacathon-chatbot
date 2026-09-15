"""Scheduled Jobs API router — schedule tasks, set reminders, voice/text prompts, Active/Pause/Delete."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/jobs", tags=["jobs"])

_JOBS: list[dict[str, Any]] = [
    {
        "id": "job-1",
        "name": "Daily Market & Portfolio Summary",
        "description": "Scrapes market closing indices, summarizes portfolio shifts, and delivers briefing at 09:00 AM.",
        "schedule": "0 9 * * 1-5",
        "timezone": "Asia/Karachi",
        "status": "Active",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "next_run": (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%b %d, %Y %I:%M %p"),
    },
    {
        "id": "job-2",
        "name": "Weekly Cloud & Subscription Expense Audit",
        "description": "Queries Plaid and Raast accounts for recurring billing anomalies and posts audit alert.",
        "schedule": "0 10 * * 1",
        "timezone": "UTC",
        "status": "Active",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=12)).isoformat(),
        "next_run": (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%b %d, %Y %I:%M %p"),
    },
    {
        "id": "job-3",
        "name": "Nightly Git Repo Sync & Backup",
        "description": "Automated snapshot of active repositories to private backup bucket.",
        "schedule": "0 2 * * *",
        "timezone": "America/New_York",
        "status": "Pause",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
        "next_run": "Paused",
    },
]


class JobCreateRequest(BaseModel):
    name: str = Field(..., min_length=2)
    description: str = Field(default="")
    schedule: str = Field(default="Daily")
    timezone: str = Field(default="UTC")
    prompt: str | None = None  # Voice or text prompt that created the job


class JobStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(Active|Pause)$")


@router.get("")
async def list_jobs(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """List all scheduled tasks and reminders."""
    return {"jobs": _JOBS}


@router.post("")
async def create_job(
    req: JobCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Schedule a new task via text or voice prompt."""
    now = datetime.now(timezone.utc)
    new_job = {
        "id": f"job-{uuid.uuid4().hex[:8]}",
        "name": req.name,
        "description": req.description or f"Automated scheduled task created via prompt: '{req.prompt or req.name}'",
        "schedule": req.schedule,
        "timezone": req.timezone,
        "status": "Active",
        "created_at": now.isoformat(),
        "next_run": (now + timedelta(days=1)).strftime("%b %d, %Y %I:%M %p"),
    }
    _JOBS.insert(0, new_job)
    return {"job": new_job, "message": "Task scheduled successfully."}


@router.patch("/{job_id}/status")
async def update_job_status(
    job_id: str,
    req: JobStatusUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Toggle job status between Active and Pause."""
    job = next((j for j in _JOBS if j["id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    job["status"] = req.status
    if req.status == "Pause":
        job["next_run"] = "Paused"
    else:
        job["next_run"] = (datetime.now(timezone.utc) + timedelta(hours=12)).strftime("%b %d, %Y %I:%M %p")

    return {"job": job, "message": f"Job status updated to {req.status}."}


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a scheduled job."""
    global _JOBS
    _JOBS = [j for j in _JOBS if j["id"] != job_id]
    return {"status": "success", "message": "Scheduled job deleted."}
