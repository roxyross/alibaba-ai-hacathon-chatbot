"""Account Data Control API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.account.service import DataControlService
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_db

router = APIRouter(prefix="/account", tags=["account"])


class DeleteAccountRequest(BaseModel):
    confirmation: str = Field(..., description="Must exactly match 'DELETE MY ACCOUNT'")


@router.post("/export")
async def request_data_export(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Initiate a comprehensive personal data export."""
    svc = DataControlService(db)
    job = await svc.create_export_job(user_id=str(user.id))
    return {
        "job_id": job.id,
        "status": job.status,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "message": "Export prepared successfully. Download is available via job ID.",
    }


@router.get("/export/{job_id}")
async def get_data_export(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Download exported personal data bundle."""
    svc = DataControlService(db)
    export_info = await svc.get_export_job(job_id=job_id, user_id=str(user.id))
    if not export_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found or expired."
        )
    return export_info


@router.post("/delete-data")
async def delete_user_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete all user personal data (sessions, chats, memories, documents)."""
    svc = DataControlService(db)
    return await svc.delete_user_data(user_id=str(user.id))


@router.post("/delete")
async def delete_account(
    body: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Permanently delete user account and all personal assets."""
    svc = DataControlService(db)
    result = await svc.delete_account(
        user_id=str(user.id), confirmation=body.confirmation
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("reason")
        )
    return result
