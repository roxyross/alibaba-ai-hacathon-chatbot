"""REST API endpoints for Security, Privacy & Action Audit Studio (Phase 19).

Mounted at /api/v1/audit.
Guarantees append-only immutability and multi-tenant data isolation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditRepository
from app.audit.schemas import (
    AuditExportResponse,
    AuditLogCreate,
    AuditLogListResponse,
    AuditLogRead,
    AuditStatsResponse,
    RiskCheckRequest,
    RiskCheckResponse,
)
from app.audit.service import AuditService
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


def get_audit_service(
    db: Annotated[AsyncSession | None, Depends(get_db)] = None,
) -> AuditService:
    """Dependency provider for AuditService."""
    repo = AuditRepository(session=db)
    return AuditService(repository=repo)


@router.get("", response_model=AuditLogListResponse)
async def list_audit_events(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    agent_slug: str | None = Query(None, description="Filter by executing agent"),
    status_code: str | None = Query(None, description="Filter by status (ok, caution, blocked, error)"),
    approval_tier: str | None = Query(None, description="Filter by approval tier (T1, T2, T3)"),
    search: str | None = Query(None, description="Search across action or query text"),
) -> AuditLogListResponse:
    """List paginated audit events owned by current user."""
    return await service.list_actions(
        user_id=str(current_user.id),
        page=page,
        limit=limit,
        agent_slug=agent_slug,
        status_code=status_code,
        approval_tier=approval_tier,
        search=search,
    )


@router.get("/today", response_model=list[AuditLogRead])
async def get_today_audit_events(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    limit: int = Query(50, ge=1, le=100, description="Max items for today"),
) -> list[AuditLogRead]:
    """Retrieve 'What did Jarvis do today' timeline feed for the current user."""
    return await service.get_today_actions(
        user_id=str(current_user.id),
        limit=limit,
    )


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuditService, Depends(get_audit_service)],
) -> AuditStatsResponse:
    """Retrieve aggregated execution and security telemetry for the current user."""
    return await service.get_stats(user_id=str(current_user.id))


@router.post("/risk-check", response_model=RiskCheckResponse)
async def assess_action_risk(
    _current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    payload: RiskCheckRequest,
) -> RiskCheckResponse:
    """Run pre-execution risk assessment gate (Security & Privacy Agent)."""
    return service.assess_action_risk(payload)


@router.get("/export", response_model=AuditExportResponse)
async def export_audit_logs(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuditService, Depends(get_audit_service)],
) -> AuditExportResponse:
    """Export complete audit log history in portable GDPR Article 20 JSON format."""
    return await service.export_audit_bundle(user_id=str(current_user.id))


@router.post("", response_model=AuditLogRead, status_code=status.HTTP_201_CREATED)
async def record_audit_event(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuditService, Depends(get_audit_service)],
    payload: AuditLogCreate,
) -> AuditLogRead:
    """Record an action event into the append-only audit log."""
    return await service.log_action(
        user_id=str(current_user.id),
        data=payload,
    )


@router.get("/{entry_id}", response_model=AuditLogRead)
async def get_audit_event(
    entry_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[AuditService, Depends(get_audit_service)],
) -> AuditLogRead:
    """Retrieve single audit entry by ID, enforcing multi-tenant 404 security guard."""
    event = await service.get_action(user_id=str(current_user.id), event_id=entry_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log entry '{entry_id}' not found.",
        )
    return event
