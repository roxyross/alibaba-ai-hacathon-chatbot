"""Pydantic v2 schemas for Security, Privacy & Action Audit Studio (Phase 19)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ApprovalTier = Literal["T1", "T2", "T3"]
AuditStatusCode = Literal["ok", "caution", "blocked", "error"]
RiskVerdict = Literal["clear", "caution", "block"]


class AuditLogCreate(BaseModel):
    """Payload to log an agent or system action."""

    agent_slug: str = Field(default="coordinator", max_length=64)
    action: str = Field(..., max_length=128)
    skill_slug: str | None = Field(default=None, max_length=64)
    approval_tier: ApprovalTier = Field(default="T1")
    approved_by: str = Field(default="auto", max_length=64)
    model_used: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=64)
    request_query: str | None = Field(default=None)
    response_summary: str | None = Field(default=None, max_length=1000)
    decision: str = Field(default="executed", max_length=128)
    latency_ms: int = Field(default=0, ge=0)
    status_code: AuditStatusCode = Field(default="ok")
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = Field(default=None, max_length=64)


class AuditLogRead(BaseModel):
    """Standard representation of an audit log entry."""

    id: str
    user_id: str
    trace_id: str
    agent_slug: str
    action: str
    skill_slug: str | None = None
    approval_tier: str
    approved_by: str
    model_used: str | None = None
    provider: str | None = None
    request_query: str | None = None
    response_summary: str | None = None
    decision: str
    latency_ms: int
    status_code: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class AuditLogListResponse(BaseModel):
    """Paginated list response of audit log entries."""

    items: list[AuditLogRead]
    total: int
    page: int = 1
    limit: int = 50


class RiskCheckRequest(BaseModel):
    """Request payload to perform a pre-execution risk check (Security & Privacy Agent)."""

    action_type: str = Field(..., min_length=1, max_length=128, description="Action name or command")
    target: str | None = Field(default=None, max_length=256, description="Target recipient, resource, or destination")
    params: dict[str, Any] = Field(default_factory=dict, description="Action arguments and parameters")
    proposed_tier: ApprovalTier | None = Field(default=None, description="Proposed approval tier if specified")
    user_prompt: str | None = Field(default=None, description="Stated user prompt for intent alignment")


class RiskCheckResponse(BaseModel):
    """Structured risk verdict produced by the Security & Privacy Agent."""

    action: str
    risk_verdict: RiskVerdict
    approval_tier: ApprovalTier
    reason: str
    warning_to_user: str
    narrower_alternative: str | None = None
    blast_radius: str = "isolated"
    is_reversible: bool = True
    blocking: bool = False


class AuditStatsResponse(BaseModel):
    """Aggregated security and execution telemetry."""

    total_events: int
    today_events: int
    by_agent: dict[str, int]
    by_status: dict[str, int]
    by_tier: dict[str, int]
    avg_latency_ms: float
    retention_days: int = 365
    last_event_at: str | None = None


class AuditExportResponse(BaseModel):
    """Portable GDPR-compliant export bundle of all user audit log records."""

    user_id: str
    exported_at: str
    total_records: int
    retention_policy: str = "1-Year Immutable Append-Only Log (§10.12)"
    events: list[AuditLogRead]
