"""FastAPI router for Open Work Agent long-running autonomous tasks."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.open_work.schemas import (
    CreateOpenWorkTaskRequest,
    OpenWorkTask,
    TaskControlRequest,
)
from app.open_work.service import OpenWorkAgentService

router = APIRouter(prefix="/open-work/tasks", tags=["open-work"])
_service = OpenWorkAgentService.get_instance()


@router.post("", response_model=OpenWorkTask, status_code=status.HTTP_201_CREATED)
async def create_open_work_task(
    req: CreateOpenWorkTaskRequest,
    user: User = Depends(get_current_user),
) -> OpenWorkTask:
    """Create and optionally start a new autonomous multi-step Open Work task."""
    try:
        return await _service.create_task(user_id=user.id, request=req)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[OpenWorkTask])
async def list_open_work_tasks(
    user: User = Depends(get_current_user),
) -> list[OpenWorkTask]:
    """List all Open Work tasks belonging to the current user."""
    return _service.list_tasks(user_id=user.id)


@router.get("/{task_id}", response_model=OpenWorkTask)
async def get_open_work_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> OpenWorkTask:
    """Fetch task progression, subtask states, and checkpoints."""
    try:
        return _service.get_task(task_id=task_id, user_id=user.id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.post("/{task_id}/pause", response_model=OpenWorkTask)
async def pause_open_work_task(
    task_id: str,
    control: TaskControlRequest | None = None,
    user: User = Depends(get_current_user),
) -> OpenWorkTask:
    """Pause an active task at the current subtask boundary."""
    try:
        return await _service.pause_task(task_id=task_id, user_id=user.id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.post("/{task_id}/resume", response_model=OpenWorkTask)
async def resume_open_work_task(
    task_id: str,
    control: TaskControlRequest | None = None,
    user: User = Depends(get_current_user),
) -> OpenWorkTask:
    """Resume execution of a paused or halted task from its saved checkpoint."""
    try:
        return await _service.resume_task(task_id=task_id, user_id=user.id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.post("/{task_id}/cancel", response_model=OpenWorkTask)
async def cancel_open_work_task(
    task_id: str,
    control: TaskControlRequest | None = None,
    user: User = Depends(get_current_user),
) -> OpenWorkTask:
    """Cancel a running task immediately."""
    try:
        return await _service.cancel_task(task_id=task_id, user_id=user.id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
