"""Permissions API router for ROXY-AI 2.0.

Provides endpoints for managing tool execution permissions and security policies.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
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
    tool_id: str = Field(..., min_length=1)
    permission: str = Field(..., min_length=1)


@router.get("", response_model=list[PermissionGrantResponse])
async def list_permissions(
    user: User = Depends(get_current_user),
) -> list[PermissionGrantResponse]:
    """Retrieve all permission policies and grants for the authenticated user."""
    return await _service.list_grants(user_id=user.id)


@router.post("/grant", response_model=PermissionGrantResponse)
async def grant_permission(
    grant_in: PermissionGrantCreate,
    user: User = Depends(get_current_user),
) -> PermissionGrantResponse:
    """Grant or update a permission policy for a specific tool and capability."""
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
    )
    return {"revoked": success, "tool_id": req.tool_id, "permission": req.permission}


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
        scope=req.scope,
    )
