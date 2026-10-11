"""FastAPI REST Router for Phase 25: Production Readiness Audit & Final Exit Gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
import structlog

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.production_readiness.exit_gate import FinalExitGate
from app.production_readiness.schemas import (
    ProductionExitCertificate,
    ProductionReadinessReport,
    ZeroMockAuditResult,
)
from app.production_readiness.zero_mock_auditor import ZeroMockAuditor

log = structlog.get_logger()

router = APIRouter(prefix="/production-readiness", tags=["Production Readiness"])


@router.get("/audit", response_model=ProductionReadinessReport)
async def get_readiness_audit(
    current_user: User = Depends(get_current_user),
) -> ProductionReadinessReport:
    """Retrieve the latest production readiness audit report with cryptographic seal."""
    gate = FinalExitGate.get_instance()
    return gate.get_latest_report()


@router.post("/zero-mock-scan", response_model=ZeroMockAuditResult)
async def run_zero_mock_scan(
    current_user: User = Depends(get_current_user),
) -> ZeroMockAuditResult:
    """Execute targeted Zero-Mock compliance scan across all production sources."""
    auditor = ZeroMockAuditor()
    return auditor.scan_directory()


@router.post("/exit-gate/evaluate", response_model=ProductionReadinessReport)
async def evaluate_exit_gate(
    current_user: User = Depends(get_current_user),
) -> ProductionReadinessReport:
    """Re-evaluate the 7-Point Production Readiness Checklist and issue a cryptographic seal."""
    gate = FinalExitGate.get_instance()
    return gate.evaluate_gate()


@router.get("/exit-gate/certificate", response_model=ProductionExitCertificate)
async def get_exit_certificate(
    current_user: User = Depends(get_current_user),
) -> ProductionExitCertificate:
    """Retrieve the cryptographically signed Production Exit Certificate."""
    gate = FinalExitGate.get_instance()
    report = gate.get_latest_report()
    return report.certificate
