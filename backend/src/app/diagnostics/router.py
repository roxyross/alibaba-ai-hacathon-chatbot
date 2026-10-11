"""Roxy Health Center API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.diagnostics.service import DiagnosticsService

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/health-center")
async def get_health_center(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve comprehensive status for all 15 operational subsystems."""
    svc = DiagnosticsService(db)
    return await svc.get_system_health()
