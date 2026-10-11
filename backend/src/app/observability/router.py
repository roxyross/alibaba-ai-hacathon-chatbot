"""FastAPI REST router for Phase 22 Audit & Observability."""

from __future__ import annotations

from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.correlation import TraceCollector, TraceRecord
from app.observability.ledger import (
    AuditRecord,
    HashChainVerificationResult,
    ImmutableLedger,
)
from app.observability.masking import ZeroLeakageMasker

router = APIRouter(prefix="/observability", tags=["observability"])


class ExportRequest(BaseModel):
    format: Literal["json", "csv"] = "json"


class LeakProbeRequest(BaseModel):
    test_text: str | None = None
    test_payload: dict[str, Any] = Field(default_factory=dict)


class LeakProbeResponse(BaseModel):
    sanitized_text: str | None
    sanitized_payload: dict[str, Any]
    recorded_audit_id: str
    secrets_intercepted: int


# -----------------------------------------------------------------------------
# 1. Distributed Tracing Endpoints
# -----------------------------------------------------------------------------


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve full distributed trace and hierarchical waterfall spans."""
    collector = TraceCollector.get_instance()
    trace = collector.get_trace(trace_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace with ID '{trace_id}' was not found.",
        )
    return {
        "trace_id": trace.trace_id,
        "correlation_id": trace.correlation_id,
        "root_span_name": trace.root_span_name,
        "duration_ms": trace.duration_ms,
        "status": trace.status,
        "attributes": trace.attributes,
        "created_at": trace.created_at.isoformat(),
        "spans": trace.to_waterfall(),
    }


@router.get("/traces")
async def list_recent_traces(
    limit: int = Query(default=25, ge=1, le=100),
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List recent distributed traces with duration and span count."""
    collector = TraceCollector.get_instance()
    traces = collector.list_recent_traces(limit=limit)
    return [
        {
            "trace_id": t.trace_id,
            "correlation_id": t.correlation_id,
            "root_span_name": t.root_span_name,
            "duration_ms": t.duration_ms,
            "status": t.status,
            "span_count": len(t.spans),
            "created_at": t.created_at.isoformat(),
        }
        for t in traces
    ]


# -----------------------------------------------------------------------------
# 2. Immutable Ledger Endpoints
# -----------------------------------------------------------------------------


@router.get("/audit/ledger", response_model=list[AuditRecord])
async def query_audit_ledger(
    action_type: str | None = None,
    actor_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    correlation_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
) -> list[AuditRecord]:
    """Query immutable audit records with sequence hashes and zero-leakage payloads."""
    ledger = ImmutableLedger.get_instance()
    return ledger.query(
        action_type=action_type,
        actor_id=actor_id,
        status=status_filter,
        correlation_id=correlation_id,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/verify", response_model=HashChainVerificationResult)
async def verify_audit_hash_chain(
    _user: User = Depends(get_current_user),
) -> HashChainVerificationResult:
    """Cryptographically verify the SHA-256 hash chain from genesis to head."""
    ledger = ImmutableLedger.get_instance()
    return ledger.verify_integrity()


@router.post("/audit/export")
async def export_audit_ledger(
    req: ExportRequest,
    _user: User = Depends(get_current_user),
) -> Any:
    """Export cryptographically verified audit records in JSON or CSV format."""
    ledger = ImmutableLedger.get_instance()
    return ledger.export_ledger(export_format=req.format)


# -----------------------------------------------------------------------------
# 3. Observability Metrics & Zero-Leakage Probing
# -----------------------------------------------------------------------------


@router.get("/metrics")
async def get_observability_metrics(
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Aggregate metrics for system health, audit records, and DLP secret masking."""
    ledger = ImmutableLedger.get_instance()
    collector = TraceCollector.get_instance()
    verif = ledger.verify_integrity()

    records = ledger.query(limit=500)
    status_counts: dict[str, int] = {}
    tier_counts: dict[str, int] = {}
    total_duration = 0.0

    for r in records:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        tier_counts[r.risk_tier] = tier_counts.get(r.risk_tier, 0) + 1
        total_duration += r.duration_ms

    avg_duration = round(total_duration / len(records), 2) if records else 0.0

    return {
        "total_audit_events": ledger.count(),
        "ledger_head_hash": verif.head_hash,
        "hash_chain_valid": verif.is_valid,
        "active_traces_in_memory": len(collector.list_recent_traces(limit=1000)),
        "zero_leakage_redactions": ZeroLeakageMasker.get_metrics(),
        "actions_by_status": status_counts,
        "actions_by_tier": tier_counts,
        "avg_action_latency_ms": avg_duration,
    }


@router.post("/test-leak-probe", response_model=LeakProbeResponse)
async def test_security_leak_probe(
    req: LeakProbeRequest,
    user: User = Depends(get_current_user),
) -> LeakProbeResponse:
    """Verify that sensitive secrets are sanitized before storage in the immutable ledger."""
    initial_metrics = ZeroLeakageMasker.get_metrics()["total"]

    sanitized_text = ZeroLeakageMasker.mask_string(req.test_text or "") if req.test_text else None
    sanitized_payload = ZeroLeakageMasker.mask_dict(req.test_payload)

    # Record in immutable ledger
    record = ImmutableLedger.get_instance().record_action(
        actor_id=str(user.id),
        action_type="security_leak_probe",
        category="security_test",
        status="success",
        risk_tier="low",
        payload={
            "raw_sanitized_text": sanitized_text,
            "structured_payload": sanitized_payload,
        },
    )

    final_metrics = ZeroLeakageMasker.get_metrics()["total"]

    return LeakProbeResponse(
        sanitized_text=sanitized_text,
        sanitized_payload=sanitized_payload,
        recorded_audit_id=record.record_id,
        secrets_intercepted=max(0, final_metrics - initial_metrics),
    )
