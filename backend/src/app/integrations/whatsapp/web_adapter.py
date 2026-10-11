"""WhatsApp Web Adapter wrapping Playwright browser automation."""

from __future__ import annotations

import uuid

import structlog

from app.integrations.whatsapp.base import WhatsAppBaseAdapter
from app.integrations.whatsapp.models import (
    ConnectionState,
    WhatsAppCapability,
    WhatsAppConnectionReport,
    WhatsAppOperationResult,
    WhatsAppRoute,
    WhatsAppTaskStatus,
)
from app.integrations.whatsapp_personal import (
    _PROFILE_BASE_DIR,
    _WHATSAPP_PROFILE_NAME,
    WhatsAppPersonalIntegrationEngine,
    WorkflowStage,
)

log = structlog.get_logger()


class WhatsAppWebAdapter(WhatsAppBaseAdapter):
    """Adapter for official WhatsApp Web browser interaction via dedicated Playwright profile."""

    def __init__(self) -> None:
        self.profile_dir = _PROFILE_BASE_DIR
        self._engine = WhatsAppPersonalIntegrationEngine.get_instance()
        self._active_operations: dict[str, WhatsAppOperationResult] = {}

    @property
    def route(self) -> WhatsAppRoute:
        return WhatsAppRoute.WEB

    def get_capabilities(self) -> list[WhatsAppCapability]:
        return [
            WhatsAppCapability.SESSION_DISCOVERY,
            WhatsAppCapability.RECIPIENT_RESOLUTION,
            WhatsAppCapability.MESSAGE_DRAFTING,
            WhatsAppCapability.SEND_TEXT,
            WhatsAppCapability.DELIVERY_VERIFICATION,
        ]

    async def get_connection_status(self) -> WhatsAppConnectionReport:
        """Inspect dedicated browser profile to determine session readiness without stealing secrets."""
        if not self.profile_dir.exists():
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.NOT_CONFIGURED,
                is_ready=False,
                details="Dedicated WhatsApp Web browser profile does not exist yet.",
                missing_prerequisites=["Initialize browser profile directory and sign in via QR code"],
                metadata={"profile_dir": str(self.profile_dir)},
            )

        # Inspect if profile directory contains storage files (cookies/leveldb/local storage)
        try:
            profile_items = list(self.profile_dir.iterdir())
        except Exception as exc:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.INACCESSIBLE,
                is_ready=False,
                details=f"Cannot inspect browser profile: {exc}",
                metadata={"error": str(exc)},
            )

        if len(profile_items) == 0:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.UNAUTHENTICATED,
                is_ready=False,
                details="WhatsApp Web browser profile is empty (no saved session).",
                missing_prerequisites=["Scan QR code in official WhatsApp Web inside the dedicated profile"],
                metadata={"profile_name": _WHATSAPP_PROFILE_NAME, "file_count": 0},
            )

        # Profile directory has session artifacts; session is present or active
        return WhatsAppConnectionReport(
            route=self.route,
            state=ConnectionState.AUTHENTICATED,
            is_ready=True,
            details="WhatsApp Web browser profile contains persistent session state.",
            metadata={"profile_name": _WHATSAPP_PROFILE_NAME, "file_count": len(profile_items)},
        )

    async def send_message(
        self,
        user_id: str,
        recipient: str,
        message: str,
        challenge_id: str,
        run_id: str,
    ) -> WhatsAppOperationResult:
        """Execute send operation via the 12-stage Playwright workflow."""
        active_op_id = run_id or f"op_web_{uuid.uuid4().hex[:8]}"
        is_ok, norm_recipient, err = self.resolve_recipient(recipient)
        redacted = self.redact_phone_number(norm_recipient if is_ok else recipient)

        if not is_ok:
            return WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.FAILED,
                recipient_redacted=redacted,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code="INVALID_RECIPIENT",
                user_facing_error=err,
            )

        # Delegate execution to engine
        engine_res = await self._engine.execute_one_message_workflow(
            user_id=user_id,
            recipient=norm_recipient,
            message=message,
            challenge_id=challenge_id,
            run_id=active_op_id,
            interactive=True,
        )

        # Map WorkflowStage to WhatsAppTaskStatus
        status_map: dict[WorkflowStage, WhatsAppTaskStatus] = {
            WorkflowStage.AWAITING_USER_APPROVAL: WhatsAppTaskStatus.WAITING_FOR_APPROVAL,
            WorkflowStage.AWAITING_RECIPIENT_VERIFICATION: WhatsAppTaskStatus.SENT,
            WorkflowStage.DELIVERED_VERIFIED: WhatsAppTaskStatus.DELIVERED,
            WorkflowStage.BLOCKED: WhatsAppTaskStatus.BLOCKED,
            WorkflowStage.FAILED: WhatsAppTaskStatus.FAILED,
            WorkflowStage.UNKNOWN: WhatsAppTaskStatus.UNKNOWN,
        }
        mapped_status = status_map.get(engine_res.stage, WhatsAppTaskStatus.UNKNOWN)

        res = WhatsAppOperationResult(
            operation_id=active_op_id,
            route=self.route,
            status=mapped_status,
            requires_approval=(mapped_status == WhatsAppTaskStatus.WAITING_FOR_APPROVAL),
            recipient_redacted=engine_res.recipient_redacted,
            recipient_normalized=norm_recipient,
            message_snippet=engine_res.message_snippet,
            challenge_id=engine_res.challenge_id,
            verification_evidence={
                "engine_stage": engine_res.stage.value,
                "delivery_signal": engine_res.delivery_signal,
                **engine_res.evidence,
            },
            error_code=None if mapped_status in (WhatsAppTaskStatus.SENT, WhatsAppTaskStatus.DELIVERED) else "ENGINE_BLOCKED_OR_FAILED",
            user_facing_error=engine_res.error,
        )
        self._active_operations[active_op_id] = res
        return res

    async def get_message_status(self, operation_id: str) -> WhatsAppOperationResult:
        if operation_id in self._active_operations:
            return self._active_operations[operation_id]
        return WhatsAppOperationResult(
            operation_id=operation_id,
            route=self.route,
            status=WhatsAppTaskStatus.UNKNOWN,
            error_code="OPERATION_NOT_FOUND",
            user_facing_error="Operation record not found.",
        )

    async def cancel_operation(self, operation_id: str) -> bool:
        if operation_id in self._active_operations:
            op = self._active_operations[operation_id]
            if op.status in (WhatsAppTaskStatus.DISCOVERING, WhatsAppTaskStatus.WAITING_FOR_APPROVAL, WhatsAppTaskStatus.READY_TO_SEND):
                op.status = WhatsAppTaskStatus.CANCELLED
                return True
        return False
