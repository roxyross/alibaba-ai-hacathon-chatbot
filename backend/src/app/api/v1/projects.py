"""Workspace Hub Projects and Tasks API router.

Supports multi-tenant project management, task breakdown and status lifecycles,
document attachments from Knowledge Vault, and project summary metrics.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.projects.repository import ProjectRepository

router = APIRouter(prefix="/projects", tags=["projects"])
_repo = ProjectRepository()


# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------

class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    status: str = Field(default="active")


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    status: str = Field(default="todo")  # todo, in_progress, done, blocked
    priority: str = Field(default="medium")  # low, medium, high, urgent
    assigned_agent: str | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assigned_agent: str | None = None


class DocumentLinkRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    file_type: str = Field(default="document")


# -----------------------------------------------------------------------------
# Project Endpoints
# -----------------------------------------------------------------------------

@router.get("")
async def list_projects(
    status: str | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all workspace projects for the authenticated user."""
    user_id = str(user.id)
    projects = await _repo.list_projects(user_id=user_id, status=status)
    return {"projects": projects}


@router.post("")
async def create_project(
    req: ProjectCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new project in Workspace Hub for the authenticated user."""
    user_id = str(user.id)
    new_proj = await _repo.create_project(
        user_id=user_id,
        name=req.name,
        description=req.description,
        status=req.status,
    )
    return {"project": new_proj, "message": "Project created successfully."}


@router.get("/{project_id}")
async def get_project_details(
    project_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get project details including recent tasks and linked documents."""
    user_id = str(user.id)
    proj = await _repo.get_project(user_id=user_id, project_id=project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"project": proj}


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    req: ProjectUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update project status or details for the authenticated user."""
    user_id = str(user.id)
    updated = await _repo.update_project(
        user_id=user_id,
        project_id=project_id,
        name=req.name,
        description=req.description,
        status=req.status,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"project": updated, "message": "Project updated successfully."}


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete project from Workspace Hub belonging to the authenticated user."""
    user_id = str(user.id)
    deleted = await _repo.delete_project(user_id=user_id, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"status": "success", "message": "Project deleted."}


# -----------------------------------------------------------------------------
# Project Tasks Endpoints
# -----------------------------------------------------------------------------

@router.get("/{project_id}/tasks")
async def list_project_tasks(
    project_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List tasks for a specific project."""
    user_id = str(user.id)
    tasks = await _repo.list_tasks(user_id=user_id, project_id=project_id)
    if tasks is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"tasks": tasks}


@router.post("/{project_id}/tasks")
async def create_project_task(
    project_id: str,
    req: TaskCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a task within a workspace project."""
    user_id = str(user.id)
    task = await _repo.create_task(
        user_id=user_id,
        project_id=project_id,
        title=req.title,
        description=req.description,
        status=req.status,
        priority=req.priority,
        assigned_agent=req.assigned_agent,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"task": task, "message": "Task created successfully."}


@router.patch("/{project_id}/tasks/{task_id}")
async def update_project_task(
    project_id: str,
    task_id: str,
    req: TaskUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update task status, priority, or content."""
    user_id = str(user.id)
    task = await _repo.update_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task_id,
        title=req.title,
        description=req.description,
        status=req.status,
        priority=req.priority,
        assigned_agent=req.assigned_agent,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"task": task, "message": "Task updated successfully."}


@router.delete("/{project_id}/tasks/{task_id}")
async def delete_project_task(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a task from a project."""
    user_id = str(user.id)
    deleted = await _repo.delete_task(
        user_id=user_id,
        project_id=project_id,
        task_id=task_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"status": "success", "message": "Task deleted."}


# -----------------------------------------------------------------------------
# Project Documents Endpoints
# -----------------------------------------------------------------------------

@router.get("/{project_id}/documents")
async def list_project_documents(
    project_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List documents linked to a workspace project."""
    user_id = str(user.id)
    docs = await _repo.list_documents(user_id=user_id, project_id=project_id)
    if docs is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"documents": docs}


@router.post("/{project_id}/documents")
async def link_project_document(
    project_id: str,
    req: DocumentLinkRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Link a document to a workspace project."""
    user_id = str(user.id)
    doc = await _repo.link_document(
        user_id=user_id,
        project_id=project_id,
        document_id=req.document_id,
        title=req.title,
        file_type=req.file_type,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"document": doc, "message": "Document linked successfully."}


@router.delete("/{project_id}/documents/{doc_link_id}")
async def unlink_project_document(
    project_id: str,
    doc_link_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Unlink a document from a workspace project."""
    user_id = str(user.id)
    deleted = await _repo.unlink_document(
        user_id=user_id,
        project_id=project_id,
        doc_link_id=doc_link_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Linked document not found.")
    return {"status": "success", "message": "Document unlinked."}
