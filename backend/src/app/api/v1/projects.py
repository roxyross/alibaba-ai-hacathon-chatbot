"""Workspace Hub Projects API router — projects list, status, last updated date, and quick actions."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/projects", tags=["projects"])

# Mock/in-memory store with realistic default projects
_PROJECTS: list[dict[str, Any]] = [
    {
        "id": "proj-1",
        "name": "Personal AI Assistant Orchestration",
        "description": "Multi-agent runtime for automated schedule management, finance tracking, and document indexing.",
        "status": "active",
        "last_updated": (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%b %d, %Y"),
        "tasks_count": 14,
        "completed_count": 11,
    },
    {
        "id": "proj-2",
        "name": "Q3 Financial Modeling & Expense Automation",
        "description": "Plaid and Raast integration pipelines with automated anomaly alerts and budget triggers.",
        "status": "in_progress",
        "last_updated": (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%b %d, %Y"),
        "tasks_count": 8,
        "completed_count": 5,
    },
    {
        "id": "proj-3",
        "name": "Enterprise Document Vector Vault",
        "description": "OCR, chunking, and semantic vector embeddings for technical documentation and whitepapers.",
        "status": "active",
        "last_updated": (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%b %d, %Y"),
        "tasks_count": 22,
        "completed_count": 20,
    },
]


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    status: str = Field(default="active")


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


@router.get("")
async def list_projects(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """List all workspace projects."""
    return {"projects": _PROJECTS}


@router.post("")
async def create_project(
    req: ProjectCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new project in Workspace Hub."""
    now = datetime.now(timezone.utc)
    new_proj = {
        "id": f"proj-{uuid.uuid4().hex[:8]}",
        "name": req.name,
        "description": req.description,
        "status": req.status,
        "last_updated": now.strftime("%b %d, %Y"),
        "tasks_count": 0,
        "completed_count": 0,
    }
    _PROJECTS.insert(0, new_proj)
    return {"project": new_proj, "message": "Project created successfully."}


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    req: ProjectUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update project status or details."""
    proj = next((p for p in _PROJECTS if p["id"] == project_id), None)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")

    if req.name is not None:
        proj["name"] = req.name
    if req.description is not None:
        proj["description"] = req.description
    if req.status is not None:
        proj["status"] = req.status
    proj["last_updated"] = datetime.now(timezone.utc).strftime("%b %d, %Y")

    return {"project": proj, "message": "Project updated successfully."}


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete project from Workspace Hub."""
    global _PROJECTS
    _PROJECTS = [p for p in _PROJECTS if p["id"] != project_id]
    return {"status": "success", "message": "Project deleted."}
