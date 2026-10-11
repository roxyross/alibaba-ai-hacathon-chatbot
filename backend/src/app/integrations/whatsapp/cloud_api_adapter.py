"""Official Meta WhatsApp Business Cloud API Adapter (Graph API v21.0)."""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from typing import Any

import httpx
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

log = structlog.get_logger()

_GRAPH_API_VERSION = "v21.0"
_GRAPH_API_BASE = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"


class WhatsAppCloudApiAdapter(WhatsAppBaseAdapter):
    """Server-side client for official WhatsApp Business Platform Cloud API."""

    def __init__(self) -> None:
        self._active_operations: dict[str, WhatsAppOperationResult] = {}
        self._status_by_wamid: dict[str, str] = {}

    @property
    def route(self) -> WhatsAppRoute:
        return WhatsAppRoute.CLOUD_API

    def get_capabilities(self) -> list[WhatsAppCapability]:
        return [
            WhatsAppCapability.SESSION_DISCOVERY,
            WhatsAppCapability.RECIPIENT_RESOLUTION,
            WhatsAppCapability.MESSAGE_DRAFTING,
            WhatsAppCapability.SEND_TEXT,
            WhatsAppCapability.SEND_TEMPLATE,
            WhatsAppCapability.DELIVERY_VERIFICATION,
            WhatsAppCapability.READ_RECEIPT_VERIFICATION,
            WhatsAppCapability.WEBHOOK_STATUS,
        ]

    # -------------------------------------------------------------------------
    # Configuration Management
    # -------------------------------------------------------------------------

    @classmethod
    def get_config(cls) -> dict[str, Any]:
        """Fetch and validate environment configuration for WhatsApp Cloud API."""
        return {
            "enabled": os.environ.get("WHATSAPP_API_ENABLED", "").lower() in ("true", "1", "yes"),
            "phone_number_id": os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            "business_account_id": os.environ.get("WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip(),
            "access_token": os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip(),
            "webhook_verify_token": os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip(),
            "app_secret": os.environ.get("WHATSAPP_APP_SECRET", "").strip(),
            "test_mode": os.environ.get("WHATSAPP_TEST_MODE", "true").lower() in ("true", "1", "yes"),
        }

    @classmethod
    def validate_credentials(cls, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform offline format and completeness validation for Meta Cloud API configuration."""
        cfg = config or cls.get_config()
        errors: list[str] = []
        warnings: list[str] = []

        phone_id = str(cfg.get("phone_number_id") or "").strip()
        access_token = str(cfg.get("access_token") or "").strip()
        b_acc_id = str(cfg.get("business_account_id") or "").strip()
        secret = str(cfg.get("app_secret") or "").strip()

        if not phone_id:
            errors.append("WHATSAPP_PHONE_NUMBER_ID is missing or empty.")
        elif not phone_id.isdigit():
            errors.append(f"WHATSAPP_PHONE_NUMBER_ID must be numeric, got: '{phone_id}'.")

        if not access_token:
            errors.append("WHATSAPP_ACCESS_TOKEN is missing or empty.")
        elif len(access_token) < 20:
            errors.append("WHATSAPP_ACCESS_TOKEN appears truncated or invalid (minimum 20 characters expected).")
        elif not access_token.startswith("EA"):
            warnings.append("Meta System User tokens typically start with 'EA'. Verify token prefix.")

        if b_acc_id and not b_acc_id.isdigit():
            warnings.append(f"WHATSAPP_BUSINESS_ACCOUNT_ID is typically numeric, got: '{b_acc_id}'.")

        if not secret:
            warnings.append("WHATSAPP_APP_SECRET is not configured; incoming webhook HMAC signatures cannot be verified.")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "configured_phone_number_id": phone_id if phone_id else None,
            "is_enabled": bool(cfg.get("enabled")),
        }

    async def get_connection_status(self) -> WhatsAppConnectionReport:
        """Validate Meta API credentials and probe endpoint connection."""
        cfg = self.get_config()
        missing = []
        if not cfg["phone_number_id"]:
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if not cfg["access_token"]:
            missing.append("WHATSAPP_ACCESS_TOKEN")

        if missing:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.NOT_CONFIGURED,
                is_ready=False,
                details=f"Missing required Cloud API configuration: {', '.join(missing)}.",
                missing_prerequisites=missing,
            )

        if not cfg["enabled"]:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.NOT_CONFIGURED,
                is_ready=False,
                details="WhatsApp Cloud API is disabled (set WHATSAPP_API_ENABLED=true).",
                missing_prerequisites=["WHATSAPP_API_ENABLED=true"],
            )

        # Optional online validation of phone_number_id against Meta Graph API
        phone_id = cfg["phone_number_id"]
        token = cfg["access_token"]
        url = f"{_GRAPH_API_BASE}/{phone_id}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                if resp.status_code == 200:
                    data = resp.json()
                    return WhatsAppConnectionReport(
                        route=self.route,
                        state=ConnectionState.AUTHENTICATED,
                        is_ready=True,
                        details=f"Connected to Meta Cloud API (Verified Name: {data.get('verified_name', 'Active')}).",
                        metadata={"phone_number_id": phone_id, "display_phone_number": data.get("display_phone_number")},
                    )
                else:
                    return WhatsAppConnectionReport(
                        route=self.route,
                        state=ConnectionState.UNAUTHENTICATED,
                        is_ready=False,
                        details=f"Meta Cloud API rejected credentials: HTTP {resp.status_code}.",
                        missing_prerequisites=["Provide valid WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID"],
                        metadata={"http_status": resp.status_code},
                    )
        except Exception as exc:
            return WhatsAppConnectionReport(
                route=self.route,
                state=ConnectionState.UNKNOWN,
                is_ready=False,
                details=f"Network error probing Meta Cloud API: {exc}",
                metadata={"error": str(exc)},
            )

    # -------------------------------------------------------------------------
    # Webhook Signature Verification
    # -------------------------------------------------------------------------

    @classmethod
    def verify_webhook_signature(cls, payload_bytes: bytes, signature_header: str) -> bool:
        """Verify X-Hub-Signature-256 header against WHATSAPP_APP_SECRET using HMAC-SHA256."""
        secret = os.environ.get("WHATSAPP_APP_SECRET", "").strip()
        if not secret:
            log.warning("whatsapp_cloud_api.verify_signature_missing_app_secret")
            return False

        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected_sig = signature_header[7:]
        computed_sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, computed_sig)

    def process_webhook_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract delivery and read receipts from incoming Meta webhook event."""
        updates: list[dict[str, Any]] = []
        try:
            entries = payload.get("entry", [])
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    statuses = value.get("statuses", [])
                    for st in statuses:
                        wamid = st.get("id")
                        status = st.get("status")  # sent, delivered, read, failed
                        recipient_id = st.get("recipient_id")
                        timestamp = st.get("timestamp")
                        if wamid and status:
                            self._status_by_wamid[wamid] = status
                            updates.append({
                                "wamid": wamid,
                                "status": status,
                                "recipient_id": recipient_id,
                                "timestamp": timestamp,
                            })
                            log.info("whatsapp_cloud_api.webhook_status_update", wamid=wamid, status=status)
        except Exception as exc:
            log.error("whatsapp_cloud_api.webhook_parse_error", error=str(exc))
        return updates

    # -------------------------------------------------------------------------
    # Outbound Message Sending
    # -------------------------------------------------------------------------

    async def send_message(
        self,
        user_id: str,
        recipient: str,
        message: str,
        challenge_id: str,
        run_id: str,
    ) -> WhatsAppOperationResult:
        """Send message via official Meta Graph API v21.0 endpoint."""
        active_op_id = run_id or f"op_api_{uuid.uuid4().hex[:8]}"
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

        cfg = self.get_config()
        if not cfg["phone_number_id"] or not cfg["access_token"]:
            res = WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.BLOCKED,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code="CREDENTIALS_MISSING",
                user_facing_error="BLOCKED: Official WhatsApp Business Cloud API credentials are not configured.",
                verification_evidence={"config_missing": ["WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN"]},
            )
            self._active_operations[active_op_id] = res
            return res

        # Strip '+' from E.164 for Meta 'to' field
        clean_digits = norm_recipient.replace("+", "")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_digits,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message,
            },
        }

        endpoint = f"{_GRAPH_API_BASE}/{cfg['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {cfg['access_token']}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                resp_json = resp.json()

                if resp.status_code in (200, 201):
                    messages = resp_json.get("messages", [])
                    wamid = messages[0].get("id") if messages else None
                    evidence = {
                        "provider": "Meta Graph API v21.0",
                        "status_code": resp.status_code,
                        "wamid": wamid,
                    }
                    res = WhatsAppOperationResult(
                        operation_id=active_op_id,
                        route=self.route,
                        status=WhatsAppTaskStatus.SENT,
                        recipient_redacted=redacted,
                        recipient_normalized=norm_recipient,
                        message_snippet=message[:40],
                        challenge_id=challenge_id,
                        provider_message_id=wamid,
                        verification_evidence=evidence,
                    )
                    self._active_operations[active_op_id] = res
                    return res
                else:
                    error_detail = resp_json.get("error", {})
                    err_msg = error_detail.get("message", f"HTTP {resp.status_code}")
                    res = WhatsAppOperationResult(
                        operation_id=active_op_id,
                        route=self.route,
                        status=WhatsAppTaskStatus.FAILED,
                        recipient_redacted=redacted,
                        recipient_normalized=norm_recipient,
                        message_snippet=message[:40],
                        challenge_id=challenge_id,
                        error_code=f"META_API_ERROR_{error_detail.get('code', resp.status_code)}",
                        user_facing_error=f"WhatsApp Cloud API rejected request: {err_msg}",
                        verification_evidence={"error": error_detail},
                    )
                    self._active_operations[active_op_id] = res
                    return res
        except Exception as exc:
            log.error("whatsapp_cloud_api.request_exception", error=str(exc))
            res = WhatsAppOperationResult(
                operation_id=active_op_id,
                route=self.route,
                status=WhatsAppTaskStatus.FAILED,
                recipient_redacted=redacted,
                recipient_normalized=norm_recipient,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                error_code="NETWORK_OR_TIMEOUT",
                user_facing_error=f"Cloud API network error: {exc}",
            )
            self._active_operations[active_op_id] = res
            return res

    async def get_message_status(self, operation_id: str) -> WhatsAppOperationResult:
        if operation_id in self._active_operations:
            op = self._active_operations[operation_id]
            if op.provider_message_id and op.provider_message_id in self._status_by_wamid:
                st = self._status_by_wamid[op.provider_message_id]
                if st == "delivered":
                    op.status = WhatsAppTaskStatus.DELIVERED
                elif st == "read":
                    op.status = WhatsAppTaskStatus.READ
                elif st == "failed":
                    op.status = WhatsAppTaskStatus.FAILED
            return op
        return WhatsAppOperationResult(
            operation_id=operation_id,
            route=self.route,
            status=WhatsAppTaskStatus.UNKNOWN,
            error_code="OPERATION_NOT_FOUND",
            user_facing_error="Operation record not found.",
        )

    async def cancel_operation(self, operation_id: str) -> bool:
        # API messages once dispatched cannot be canceled over Graph API
        return False
