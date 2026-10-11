"""Typed models, enums, and structured payloads for Universal WhatsApp Integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class WhatsAppRoute(StrEnum):
    """Supported integration routes."""
    DESKTOP = "desktop"
    WEB = "web"
    CLOUD_API = "cloud_api"
    AUTO = "auto"


class WhatsAppCapability(StrEnum):
    """Fine-grained adapter capabilities."""
    SESSION_DISCOVERY = "session_discovery"
    RECIPIENT_RESOLUTION = "recipient_resolution"
    MESSAGE_DRAFTING = "message_drafting"
    SEND_TEXT = "send_text"
    SEND_TEMPLATE = "send_template"
    DELIVERY_VERIFICATION = "delivery_verification"
    READ_RECEIPT_VERIFICATION = "read_receipt_verification"
    WEBHOOK_STATUS = "webhook_status"
    CANCEL_OPERATION = "cancel_operation"


class ConnectionState(StrEnum):
    """Connection and authentication states."""
    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    NOT_RUNNING = "NOT_RUNNING"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    INACCESSIBLE = "INACCESSIBLE"
    UNKNOWN = "UNKNOWN"


class WhatsAppTaskStatus(StrEnum):
    """Explicit task execution and lifecycle states."""
    DISCOVERING = "DISCOVERING"
    SESSION_CHECK = "SESSION_CHECK"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    READY_TO_SEND = "READY_TO_SEND"
    SENDING = "SENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    # Canonical Gate A3 Truthful Status Equivalents
    BLOCKED_AUTH = "BLOCKED_AUTH"
    BLOCKED_CREDENTIALS = "BLOCKED_CREDENTIALS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    REJECTED = "REJECTED"
    SUBMITTED = "SUBMITTED"


@dataclass
class WhatsAppConnectionReport:
    """Report detailing adapter connection and session availability."""
    route: WhatsAppRoute
    state: ConnectionState
    is_ready: bool
    details: str
    missing_prerequisites: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class WhatsAppOperationResult:
    """Authoritative structured result returned by every WhatsApp operation."""
    operation_id: str
    route: WhatsAppRoute
    status: WhatsAppTaskStatus
    requires_approval: bool = False
    recipient_redacted: str = ""
    recipient_normalized: str = ""
    message_snippet: str = ""
    challenge_id: str | None = None
    provider_message_id: str | None = None
    verification_evidence: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    user_facing_error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def semantic_status(self) -> str:
        """Map repository status and error codes to Section 5 canonical truthful status."""
        if self.status in (WhatsAppTaskStatus.WAITING_FOR_APPROVAL, WhatsAppTaskStatus.AWAITING_CONFIRMATION):
            return "AWAITING_CONFIRMATION"
        if self.status in (WhatsAppTaskStatus.BLOCKED, WhatsAppTaskStatus.BLOCKED_AUTH, WhatsAppTaskStatus.BLOCKED_CREDENTIALS):
            if self.error_code in ("BLOCKED_CREDENTIALS", "MISSING_CREDENTIALS", "NO_CREDENTIALS"):
                return "BLOCKED_CREDENTIALS"
            if self.error_code in ("ALLOWLIST_REJECTED", "APPROVAL_REJECTED", "REJECTED"):
                return "REJECTED"
            return "BLOCKED_AUTH"
        if self.status == WhatsAppTaskStatus.REJECTED:
            return "REJECTED"
        if self.status == WhatsAppTaskStatus.CANCELLED:
            return "CANCELLED"
        if self.status == WhatsAppTaskStatus.FAILED:
            return "FAILED"
        if self.status == WhatsAppTaskStatus.DELIVERED:
            return "DELIVERED"
        if self.status in (WhatsAppTaskStatus.SENT, WhatsAppTaskStatus.SUBMITTED):
            return "SUBMITTED"
        if self.status in (
            WhatsAppTaskStatus.DISCOVERING,
            WhatsAppTaskStatus.SESSION_CHECK,
            WhatsAppTaskStatus.READY_TO_SEND,
            WhatsAppTaskStatus.SENDING,
        ):
            return self.status.value
        return "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for tool response or API delivery."""
        return {
            "operation_id": self.operation_id,
            "route": self.route.value,
            "status": self.status.value,
            "semantic_status": self.semantic_status,
            "requires_approval": self.requires_approval,
            "recipient_redacted": self.recipient_redacted,
            "recipient_normalized": self.recipient_normalized,
            "message_snippet": self.message_snippet,
            "challenge_id": self.challenge_id,
            "provider_message_id": self.provider_message_id,
            "verification_evidence": self.verification_evidence,
            "error_code": self.error_code,
            "user_facing_error": self.user_facing_error,
            "timestamp": self.timestamp,
        }
