"""SQLAlchemy ORM models for ROXY Trust, Control, Recovery & Reliability Layer.

Fulfills requirements for:
- Trust Events & Action Verification Audit
- Undo & Recovery Jobs (with Idempotency & Safe Retry)
- Personalization Proposals & User Approval
- User Data Export Jobs
- AI Evaluation Records
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TrustEvent(Base):
    """Immutable audit record for user and agent actions with verification and rollback metadata."""

    __tablename__ = "trust_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    risk_level: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    permission_policy: Mapped[str] = mapped_column(String(32), default="allow_automatically", nullable=False)
    confirmation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    execution_status: Mapped[str] = mapped_column(String(32), default="requested", nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False, index=True)

    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    rollback_supported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rollback_status: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    rollback_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    data_accessed: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    external_service: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_trust_events_user_status", "user_id", "execution_status"),
        Index("idx_trust_events_user_verification", "user_id", "verification_status"),
    )

    def get_metadata(self) -> dict[str, Any]:
        try:
            return json.loads(self.metadata_json) if self.metadata_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_metadata(self, data: dict[str, Any]) -> None:
        self.metadata_json = json.dumps(data)

    def get_data_accessed(self) -> list[str]:
        try:
            return json.loads(self.data_accessed) if self.data_accessed else []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_data_accessed(self, items: list[str]) -> None:
        self.data_accessed = json.dumps(items)

    def get_rollback_payload(self) -> dict[str, Any]:
        try:
            return json.loads(self.rollback_payload_json) if self.rollback_payload_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_rollback_payload(self, data: dict[str, Any]) -> None:
        self.rollback_payload_json = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "action_name": self.action_name,
            "tool_id": self.tool_id,
            "risk_level": self.risk_level,
            "permission_policy": self.permission_policy,
            "confirmation_id": self.confirmation_id,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
            "success": self.success,
            "failure_code": self.failure_code,
            "failure_reason": self.failure_reason,
            "rollback_supported": self.rollback_supported,
            "rollback_status": self.rollback_status,
            "rollback_strategy": self.rollback_strategy,
            "data_accessed": self.get_data_accessed(),
            "external_service": self.external_service,
            "external_reference": self.external_reference,
            "metadata": self.get_metadata(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }


class RecoveryJob(Base):
    """Track resilient recovery, offline queuing, and safe retries with idempotency keys."""

    __tablename__ = "recovery_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    trust_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    failure_category: Mapped[str] = mapped_column(String(64), nullable=False)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )

    def get_payload(self) -> dict[str, Any]:
        try:
            return json.loads(self.payload_json) if self.payload_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "trust_event_id": self.trust_event_id,
            "action_type": self.action_type,
            "tool_id": self.tool_id,
            "payload": self.get_payload(),
            "failure_category": self.failure_category,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "last_error": self.last_error,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PersonalizationProposal(Base):
    """User-approved personalization preferences."""

    __tablename__ = "personalization_proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    proposed_value: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_pers_user_status", "user_id", "status"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category,
            "key": self.key,
            "proposed_value": self.proposed_value,
            "rationale": self.rationale,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class DataExportJob(Base):
    """User data export requests and download tokens."""

    __tablename__ = "data_export_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="requested", nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    export_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "status": self.status,
            "file_path": self.file_path,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class EvaluationRecord(Base):
    """Results from automated continuous AI evaluation runs."""

    __tablename__ = "evaluation_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def get_details(self) -> dict[str, Any]:
        """Deserialize evaluation details safely."""
        try:
            raw = str(self.details_json) if self.details_json else "{}"
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_details(self, data: dict[str, Any]) -> None:
        """Serialize evaluation details safely."""
        self.details_json = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "test_case_id": self.test_case_id,
            "category": self.category,
            "passed": self.passed,
            "score": self.score,
            "details": self.get_details(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
