"""Personalization API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_db
from app.personalization.service import PersonalizationService

router = APIRouter(prefix="/personalization", tags=["personalization"])


class ProposePreferenceRequest(BaseModel):
    category: str = Field(..., examples=["language"])
    key: str = Field(..., examples=["preferred_language"])
    proposed_value: str = Field(..., examples=["ur"])
    rationale: str = Field(..., examples=["User frequently communicates in Roman Urdu/Urdu."])


class ResolveProposalRequest(BaseModel):
    approve: bool


@router.get("/proposals")
async def list_proposals(
    status: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List pending or resolved preference proposals."""
    svc = PersonalizationService(db)
    items = await svc.list_proposals(user_id=str(user.id), status=status)
    return [p.to_dict() for p in items]


@router.post("/proposals")
async def create_proposal(
    body: ProposePreferenceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new preference proposal."""
    svc = PersonalizationService(db)
    item = await svc.propose_preference(
        user_id=str(user.id),
        category=body.category,
        key=body.key,
        proposed_value=body.proposed_value,
        rationale=body.rationale,
    )
    return item.to_dict()


@router.post("/proposals/{proposal_id}/resolve")
async def resolve_proposal(
    proposal_id: str,
    body: ResolveProposalRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve or decline a preference proposal."""
    svc = PersonalizationService(db)
    result = await svc.resolve_proposal(
        proposal_id=proposal_id, user_id=str(user.id), approve=body.approve
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=result.get("reason")
        )
    return result


@router.post("/reset")
async def reset_personalization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reset all learned personalization to default settings."""
    svc = PersonalizationService(db)
    return await svc.reset_personalization(user_id=str(user.id))
