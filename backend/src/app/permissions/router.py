"""Permissions API router for ROXY-AI 2.0.

Provides endpoints for managing target-scoped tool execution permissions,
security policies, and human-readable UX permission checks.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.permissions.schemas import (
    PermissionCheckRequest,
    PermissionCheckResult,
    PermissionGrantCreate,
    PermissionGrantResponse,
)
from app.permissions.service import PermissionService

router = APIRouter(prefix="/permissions", tags=["permissions"])
_service = PermissionService()


class RevokeRequest(BaseModel):
    tool_id: str | None = Field(default=None)
    permission: str | None = Field(default=None)
    grant_id: str | None = Field(default=None)
    target_app: str | None = Field(default=None)
    device_id: str | None = Field(default=None)


@router.get("", response_model=list[PermissionGrantResponse])
async def list_permissions(
    target_app: str | None = Query(default=None, description="Filter by target application"),
    device_id: str | None = Query(default=None, description="Filter by device identifier"),
    active_only: bool = Query(default=False, description="Include only active non-expired grants"),
    user: User = Depends(get_current_user),
) -> list[PermissionGrantResponse]:
    """Retrieve permission policies and grants for the authenticated user."""
    return await _service.list_grants(
        user_id=user.id,
        target_app=target_app,
        device_id=device_id,
        active_only=active_only,
    )


@router.post("/grant", response_model=PermissionGrantResponse)
async def grant_permission(
    grant_in: PermissionGrantCreate,
    user: User = Depends(get_current_user),
) -> PermissionGrantResponse:
    """Grant or update a target-scoped permission policy."""
    return await _service.grant_permission(user_id=user.id, grant_in=grant_in)


@router.post("/revoke")
async def revoke_permission(
    req: RevokeRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Revoke a previously configured permission grant."""
    success = await _service.revoke_permission(
        user_id=user.id,
        tool_id=req.tool_id,
        permission=req.permission,
        grant_id=req.grant_id,
        target_app=req.target_app,
        device_id=req.device_id,
    )
    return {
        "revoked": success,
        "grant_id": req.grant_id,
        "tool_id": req.tool_id,
        "permission": req.permission,
        "target_app": req.target_app,
    }


@router.delete("/grants/{grant_id}")
async def delete_grant(
    grant_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Revoke and delete a specific grant by its unique identifier."""
    success = await _service.revoke_permission(
        user_id=user.id,
        grant_id=grant_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Permission grant '{grant_id}' not found or already revoked.")
    return {"revoked": True, "grant_id": grant_id}


@router.post("/check", response_model=PermissionCheckResult)
async def check_permission(
    req: PermissionCheckRequest,
    user: User = Depends(get_current_user),
) -> PermissionCheckResult:
    """Evaluate whether an action requires explicit user confirmation or is pre-authorized."""
    return await _service.check_permission(
        user_id=user.id,
        tool_id=req.tool_id,
        permission=req.permission,
        target_app=req.target_app,
        capability=req.capability,
        resource=req.resource,
        device_id=req.device_id,
        scope=req.scope,
        parameters=req.parameters,
    )
