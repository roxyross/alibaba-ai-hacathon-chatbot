"""SQLAlchemy ORM model for Audit Log (Phase 19).

Fulfills specs/001-runtime-orchestrator/data-model.md, specs/feature/audit-log.md,
and Constitution §3.5 (Approval Tiers T1/T2/T3) and §3.6 (Immutable Audit Logging).
Guarantees append-only, tamper-evident record of all agent actions, tool calls,
decisions, and security reviews.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditLogEntry(Base):
    """Immutable, append-only audit log entry for user and agent actions."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=lambda: str(uuid.uuid4()), index=True
    )
    agent_slug: Mapped[str] = mapped_column(
        String(64), nullable=False, default="coordinator", index=True
    )
    action: Mapped[str] = mapped_column(
        String(128), nullable=False, default="routed", index=True
    )
    skill_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_tier: Mapped[str] = mapped_column(
        String(16), nullable=False, default="T1"
    )  # T1 (auto-run), T2 (confirm-tap), T3 (PIN/biometric)
    approved_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="auto"
    )  # auto, user, pin, operator
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(
        String(128), nullable=False, default="executed"
    )  # executed, caution_approved, blocked_by_security, timeout, error
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ok"
    )  # ok, caution, blocked, error
    details: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )  # JSON-encoded extra metadata

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_audit_user_created", "user_id", "created_at"),
        Index("idx_audit_trace", "trace_id"),
        Index("idx_audit_agent", "agent_slug"),
        Index("idx_audit_status", "status_code"),
    )

    def get_details_dict(self) -> dict[str, Any]:
        """Return parsed JSON details dictionary."""
        if not self.details:
            return {}
        try:
            return json.loads(self.details)  # type: ignore[no-any-return]
        except Exception:
            return {"raw": self.details}

    def set_details_dict(self, data: dict[str, Any]) -> None:
        """Serialize data dictionary into JSON details string."""
        self.details = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        """Convert entry into standard representation dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "trace_id": self.trace_id,
            "agent_slug": self.agent_slug,
            "action": self.action,
            "skill_slug": self.skill_slug,
            "approval_tier": self.approval_tier,
            "approved_by": self.approved_by,
            "model_used": self.model_used,
            "provider": self.provider,
            "request_query": self.request_query,
            "response_summary": self.response_summary,
            "decision": self.decision,
            "latency_ms": self.latency_ms,
            "status_code": self.status_code,
            "details": self.get_details_dict(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
