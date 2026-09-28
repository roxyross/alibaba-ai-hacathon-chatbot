"""Action Center API router for ROXY-AI 2.0.

Provides endpoints for reviewing pending actions, editing parameters, approving,
and rejecting tool executions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.actions.schemas import (
    ActionEditRequest,
    ActionRejectRequest,
    ActionResponse,
)
from app.actions.service import ActionService
from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/actions", tags=["actions"])
_service = ActionService()


@router.get("/pending", response_model=list[ActionResponse])
async def list_pending_actions(
    user: User = Depends(get_current_user),
) -> list[ActionResponse]:
    """Retrieve all pending actions currently awaiting user confirmation."""
    return await _service.list_pending_actions(user_id=user.id)


@router.get("/history", response_model=list[ActionResponse])
async def list_action_history(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
) -> list[ActionResponse]:
    """Retrieve history of past actions and their execution or rejection states."""
    return await _service.list_action_history(user_id=user.id, limit=limit)


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(
    action_id: str,
    user: User = Depends(get_current_user),
) -> ActionResponse:
    """Retrieve details for a specific action."""
    action = await _service.get_action(user_id=user.id, action_id=action_id)
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found.")
    return action


@router.post("/{action_id}/approve", response_model=ActionResponse)
async def approve_action(
    action_id: str,
    user: User = Depends(get_current_user),
) -> ActionResponse:
    """Approve a pending action and execute its associated tool."""
    try:
        return await _service.approve_action(user_id=user.id, action_id=action_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{action_id}/reject", response_model=ActionResponse)
async def reject_action(
    action_id: str,
    reject_in: ActionRejectRequest = ActionRejectRequest(),
    user: User = Depends(get_current_user),
) -> ActionResponse:
    """Reject a pending action, preventing its execution."""
    try:
        return await _service.reject_action(
            user_id=user.id, action_id=action_id, reason=reject_in.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{action_id}/edit", response_model=ActionResponse)
async def edit_action(
    action_id: str,
    edit_in: ActionEditRequest,
    user: User = Depends(get_current_user),
) -> ActionResponse:
    """Edit parameter payload for a pending action prior to approval."""
    try:
        return await _service.edit_action_params(
            user_id=user.id, action_id=action_id, new_params=edit_in.input_parameters
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
