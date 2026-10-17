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

    # Phase A Normalized audit & trust attributes
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="agent", nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skill_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    connector_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    plugin_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)

    risk_level: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    permission_policy: Mapped[str] = mapped_column(String(32), default="allow_automatically", nullable=False)
    permission_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permission_status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    confirmation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confirmation_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmation_status: Mapped[str] = mapped_column(String(32), default="none", nullable=False)

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
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "task_id": self.task_id,
            "action_id": self.action_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "action_type": self.action_type,
            "action_name": self.action_name,
            "tool_id": self.tool_id,
            "skill_id": self.skill_id,
            "connector_id": self.connector_id,
            "plugin_id": self.plugin_id,
            "device_id": self.device_id,
            "target": self.target,
            "risk_level": self.risk_level,
            "permission_policy": self.permission_policy,
            "permission_required": self.permission_required,
            "permission_status": self.permission_status,
            "confirmation_id": self.confirmation_id,
            "confirmation_required": self.confirmation_required,
            "confirmation_status": self.confirmation_status,
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
            # Phase A normalized aliases
            "userId": self.user_id,
            "workspaceId": self.workspace_id,
            "sessionId": self.session_id,
            "correlationId": self.correlation_id,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "actorType": self.actor_type,
            "actorId": self.actor_id,
            "actionType": self.action_type,
            "actionName": self.action_name,
            "toolId": self.tool_id,
            "skillId": self.skill_id,
            "connectorId": self.connector_id,
            "pluginId": self.plugin_id,
            "deviceId": self.device_id,
            "riskLevel": self.risk_level,
            "permissionRequired": self.permission_required,
            "permissionStatus": self.permission_status,
            "confirmationRequired": self.confirmation_required,
            "confirmationStatus": self.confirmation_status,
            "executionStatus": self.execution_status,
            "verificationStatus": self.verification_status,
            "rollbackSupported": self.rollback_supported,
            "rollbackStatus": self.rollback_status,
            "errorCode": self.failure_code,
        }


class RollbackAction(Base):
    """Reusable rollback abstraction declaring strategy, time window, requirements, and execution state."""

    __tablename__ = "rollback_actions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    action_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    trust_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    rollback_window_seconds: Mapped[int] = mapped_column(Integer, default=86400, nullable=False)
    requirements_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="available", nullable=False, index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def get_requirements(self) -> dict[str, Any]:
        try:
            return json.loads(self.requirements_json) if self.requirements_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_requirements(self, data: dict[str, Any]) -> None:
        self.requirements_json = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "actionId": self.action_id,
            "trust_event_id": self.trust_event_id,
            "user_id": self.user_id,
            "supported": self.supported,
            "strategy": self.strategy,
            "rollback_window_seconds": self.rollback_window_seconds,
            "rollbackWindow": self.rollback_window_seconds,
            "requirements": self.get_requirements(),
            "status": self.status,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "executedAt": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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


class ConfirmationChallengeModel(Base):
    """Durable confirmation challenge record supporting cross-worker single-use atomic consumption."""

    __tablename__ = "confirmation_challenges"

    challenge_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    risk_tier: Mapped[str] = mapped_column(String(32), default="HIGH", nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    challenge_token: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    step_up_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    step_up_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step_up_hint: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_conf_challenges_user_status", "user_id", "status"),
        Index("idx_conf_challenges_token", "challenge_token"),
    )

    def get_details(self) -> dict[str, Any]:
        try:
            return json.loads(self.details_json) if self.details_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_details(self, data: dict[str, Any]) -> None:
        self.details_json = json.dumps(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "title": self.title,
            "summary": self.summary,
            "details": self.get_details(),
            "risk_tier": self.risk_tier,
            "risk_score": self.risk_score,
            "challenge_token": self.challenge_token,
            "step_up_required": self.step_up_required,
            "step_up_code": self.step_up_code,
            "step_up_hint": self.step_up_hint,
            "status": self.status,
            "attempts": self.attempts,
            "decision": self.decision,
            "comment": self.comment,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "resolved_at": self.resolved_at,
            "consumed_at": self.consumed_at,
        }

