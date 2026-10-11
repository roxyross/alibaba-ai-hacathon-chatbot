"""ROXY-AI Personal WhatsApp Integration Engine (Windows 11 UI Automation).

Implements official WhatsApp Web browser UI automation with:
1. Strict recipient allowlist validation (single user-configured test recipient).
2. Explicit, tamper-resistant HMAC send confirmation via ConfirmationGate.
3. Dedicated local Playwright browser profile (~/.roxy/browser_profiles/whatsapp_personal).
4. Single-use send token and duplicate-send prevention.
5. 12-stage end-to-end workflow under the Zero Simulation Doctrine.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from app.browser.playwright_manager import PlaywrightBrowserManager
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource
from app.trust.confirmation_gate import ConfirmationGate
from app.trust.schemas import ConfirmationChallengeResponse, ConfirmationStatus, RiskTier

log = structlog.get_logger()

# Dedicated profile path for WhatsApp testing
_WHATSAPP_PROFILE_NAME = "whatsapp_personal"
_PROFILE_BASE_DIR = Path.home() / ".roxy" / "browser_profiles" / _WHATSAPP_PROFILE_NAME


class WorkflowStage(StrEnum):
    """Controlled 12-stage WhatsApp execution workflow."""
    PREFLIGHT = "PREFLIGHT"
    AUTH_CHECK = "AUTH_CHECK"
    RECIPIENT_RESOLUTION = "RECIPIENT_RESOLUTION"
    MESSAGE_PREVIEW = "MESSAGE_PREVIEW"
    AWAITING_USER_APPROVAL = "AWAITING_USER_APPROVAL"
    APPROVAL_VALIDATION = "APPROVAL_VALIDATION"
    SENDING = "SENDING"
    SEND_ACCEPTANCE_CHECK = "SEND_ACCEPTANCE_CHECK"
    DELIVERY_PENDING = "DELIVERY_PENDING"
    AWAITING_RECIPIENT_VERIFICATION = "AWAITING_RECIPIENT_VERIFICATION"
    DELIVERED_VERIFIED = "DELIVERED_VERIFIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class WhatsAppExecutionResult:
    """Detailed telemetry and audit record of a WhatsApp execution."""
    stage: WorkflowStage
    status: str
    run_id: str
    recipient_redacted: str
    message_snippet: str
    challenge_id: str | None = None
    verification_hash: str | None = None
    delivery_signal: str | None = None
    error: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class WhatsAppPersonalIntegrationEngine:
    """Authoritative personal WhatsApp automation engine for ROXY-AI."""

    _instance: WhatsAppPersonalIntegrationEngine | None = None

    def __init__(self) -> None:
        self.profile_dir = _PROFILE_BASE_DIR
        self._consumed_tokens: set[str] = set()

    @classmethod
    def get_instance(cls) -> WhatsAppPersonalIntegrationEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -------------------------------------------------------------------------
    # Recipient Normalization & Allowlist Enforcement
    # -------------------------------------------------------------------------

    @staticmethod
    def normalize_phone_number(raw_number: str) -> str:
        """Normalize a phone number into strict E.164 format (+[country][national])."""
        if not raw_number:
            raise ValueError("Recipient phone number cannot be empty.")

        clean = re.sub(r"[\s\-\(\)\.]+", "", raw_number.strip())
        if clean.startswith("00"):
            clean = "+" + clean[2:]
        elif not clean.startswith("+"):
            clean = "+" + clean

        # Validate E.164: + followed by 7 to 15 digits
        if not re.match(r"^\+[1-9]\d{6,14}$", clean):
            raise ValueError(
                f"Invalid phone number format '{clean[:4]}...'. Must follow international E.164 (+country_code and number)."
            )
        return clean

    @classmethod
    def get_configured_test_recipient(cls) -> str | None:
        """Fetch the single user-configured test recipient from local environment."""
        raw = os.environ.get("ROXY_WHATSAPP_TEST_RECIPIENT", "").strip()
        if not raw:
            return None
        try:
            return cls.normalize_phone_number(raw)
        except ValueError:
            return None

    @classmethod
    def redact_phone_number(cls, phone_number: str) -> str:
        """Mask a phone number for safe logging and report inclusion without leaking PII."""
        clean = phone_number.strip()
        if len(clean) <= 6:
            return "+XXXXXXX"
        prefix = clean[:3]
        suffix = clean[-3:]
        return f"{prefix}*****{suffix}"

    @classmethod
    def validate_recipient_allowlist(cls, target_number: str) -> tuple[bool, str, str]:
        """Verify that target_number strictly matches the single user-configured test recipient.

        Returns (is_valid, normalized_number, reason_or_error)
        """
        try:
            norm = cls.normalize_phone_number(target_number)
        except ValueError as err:
            return False, "", str(err)

        allowed = cls.get_configured_test_recipient()
        if not allowed:
            return False, norm, "BLOCKED: No test recipient configured. Set ROXY_WHATSAPP_TEST_RECIPIENT in environment."

        if norm != allowed:
            return (
                False,
                norm,
                f"REJECTED: Recipient {cls.redact_phone_number(norm)} is not in the approved test allowlist. Only the configured second device is permitted.",
            )

        return True, norm, "OK"

    # -------------------------------------------------------------------------
    # Confirmation Gate & Tamper-Resistant Approval
    # -------------------------------------------------------------------------

    @classmethod
    def create_send_challenge(
        cls,
        user_id: str,
        recipient: str,
        message: str,
        run_id: str,
        ttl_seconds: int = 180,
    ) -> ConfirmationChallengeResponse:
        """Create a cryptographic ConfirmationGate challenge for outbound WhatsApp sending."""
        is_valid, norm_recipient, err = cls.validate_recipient_allowlist(recipient)
        if not is_valid:
            raise ValueError(f"Cannot create send challenge: {err}")

        # Compute message digest for binding
        msg_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        redacted = cls.redact_phone_number(norm_recipient)

        details: dict[str, Any] = {
            "app": "WhatsApp",
            "action": "send_text_message",
            "recipient_normalized": norm_recipient,
            "recipient_redacted": redacted,
            "message_text": message,
            "message_hash": msg_hash,
            "run_id": run_id,
            "attachments": [],  # Attachments rejected
        }

        challenge = ConfirmationGate.create_challenge(
            user_id=user_id,
            action_type="whatsapp_send_message",
            title="Approve Outbound WhatsApp Message",
            summary=f"Send 1 verified WhatsApp text message to {redacted}",
            details=details,
            risk_tier=RiskTier.HIGH,
            risk_score=80,
            requires_2fa=False,
            ttl_seconds=ttl_seconds,
        )

        log.info(
            "whatsapp_personal.challenge_created",
            challenge_id=challenge.challenge_id,
            recipient=redacted,
            run_id=run_id,
        )
        return challenge

    def validate_send_approval(
        self,
        challenge_id: str,
        user_id: str,
        expected_recipient: str,
        expected_message: str,
        expected_run_id: str,
    ) -> tuple[bool, str]:
        """Revalidate server-side approval immediately prior to UI dispatch and enforce single-use.

        Returns (is_approved, reason)
        """
        if challenge_id in self._consumed_tokens:
            return False, "REJECTED: Send challenge token has already been consumed (replay / duplicate send prevented)."

        challenge = ConfirmationGate.get_challenge(challenge_id, user_id=user_id)
        if not challenge:
            return False, f"REJECTED: Confirmation challenge {challenge_id} not found."

        if challenge.get("status") != ConfirmationStatus.APPROVED:
            return False, f"REJECTED: Challenge status is '{challenge.get('status')}', expected 'approved'."

        details = challenge.get("details", {})
        if details.get("run_id") != expected_run_id:
            return False, "REJECTED: Action run_id does not match approved challenge."

        if details.get("recipient_normalized") != expected_recipient:
            return False, "REJECTED: Target recipient does not match approved challenge."

        expected_hash = hashlib.sha256(expected_message.encode("utf-8")).hexdigest()
        if details.get("message_hash") != expected_hash:
            return False, "REJECTED: Outbound message text was altered after user approval."

        # Mark single-use token as consumed
        self._consumed_tokens.add(challenge_id)
        log.info("whatsapp_personal.approval_validated", challenge_id=challenge_id, run_id=expected_run_id)
        return True, "APPROVED"

    # -------------------------------------------------------------------------
    # 12-Stage Controlled Workflow Execution
    # -------------------------------------------------------------------------

    async def execute_one_message_workflow(
        self,
        user_id: str,
        recipient: str,
        message: str,
        challenge_id: str | None = None,
        run_id: str | None = None,
        interactive: bool = True,
        timeout_seconds: float = 60.0,
    ) -> WhatsAppExecutionResult:
        """Execute the tightly controlled 12-stage WhatsApp send workflow under Zero Simulation."""
        active_run_id = run_id or f"wa_{uuid.uuid4().hex[:10]}"
        redacted_rcpt = self.redact_phone_number(recipient)

        # STAGE 1: PREFLIGHT
        preflight_ok, norm_recipient, reason = self.validate_recipient_allowlist(recipient)
        if not preflight_ok:
            return WhatsAppExecutionResult(
                stage=WorkflowStage.BLOCKED,
                status="BLOCKED",
                run_id=active_run_id,
                recipient_redacted=redacted_rcpt,
                message_snippet=message[:40],
                error=reason,
                evidence={"preflight_error": reason},
            )

        # Ensure browser profile directory exists
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        pw_manager = PlaywrightBrowserManager.get_instance()

        # STAGE 2: AUTH_CHECK & BROWSER CONNECTION
        session_id = f"wa_sess_{active_run_id}"
        page = None
        try:
            # Launch persistent browser context (visible if interactive)
            headless_mode = not interactive
            try:
                launch_res = await pw_manager.launch_session(
                    session_id=session_id,
                    profile_name=_WHATSAPP_PROFILE_NAME,
                    headless=headless_mode,
                )
            except Exception as launch_err:
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.FAILED,
                    status="FAILED",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    error=f"Browser session launch failed: {launch_err}",
                )

            if launch_res is None or getattr(launch_res, "is_closed", False) is True:
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.FAILED,
                    status="FAILED",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    error="Browser session was terminated immediately upon launch",
                )

            page = pw_manager._sessions[session_id].get_active_page()
            if not page:
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.FAILED,
                    status="FAILED",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    error="Active browser page could not be initialized",
                )

            # Navigate to official WhatsApp Web
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=30000)

            # Inspect DOM to check authentication state
            # Wait up to 12s for either chat list (logged in) or QR code (logged out)
            try:
                auth_selector = await page.wait_for_selector(
                    "div[data-testid='chat-list'], #pane-side, canvas[aria-label='Scan me!'], div[data-testid='qrcode']",
                    timeout=12000,
                )
            except Exception:
                auth_selector = None

            is_authenticated = False
            if auth_selector:
                # Check if it was chat list
                chat_list = await page.query_selector("div[data-testid='chat-list'], #pane-side")
                if chat_list:
                    is_authenticated = True

            if not is_authenticated:
                # User has not logged in or session expired
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.BLOCKED,
                    status="BLOCKED",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    error=(
                        "BLOCKED — INTERACTIVE AUTHENTICATION REQUIRED: "
                        "The official WhatsApp Web session is not signed in. "
                        "Please open WhatsApp Web in the dedicated browser profile and scan the QR code manually. "
                        "Roxy will never automate QR scanning or extract session credentials."
                    ),
                    evidence={"auth_state": "QR_CODE_OR_LOGIN_PROMPT_DETECTED"},
                )

            # STAGE 3: RECIPIENT_RESOLUTION
            # Open direct conversation via official web URL
            encoded_text = urllib.parse.quote(message)
            phone_digits = norm_recipient.replace("+", "")
            target_url = f"https://web.whatsapp.com/send?phone={phone_digits}&text={encoded_text}"
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for message compose input or invalid phone number popup
            try:
                compose_elem = await page.wait_for_selector(
                    "div[contenteditable='true'][data-tab='10'], div[data-testid='conversation-compose-box-input']",
                    timeout=15000,
                )
            except Exception:
                compose_elem = None

            if not compose_elem:
                # Check for "Phone number shared via url is invalid" popup
                popup = await page.query_selector("div[data-testid='popup-contents']")
                popup_text = await popup.inner_text() if popup else "Conversation could not be opened"
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.FAILED,
                    status="FAILED",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    error=f"Recipient conversation resolution failed: {popup_text}",
                    evidence={"ui_state": "CONVERSATION_OPEN_FAILED", "popup": popup_text},
                )

            # STAGE 4: MESSAGE_PREVIEW
            # Message is prepared with unique run ID
            log.info("whatsapp_personal.message_preview_ready", run_id=active_run_id, recipient=redacted_rcpt)

            # STAGE 5 & 6: AWAITING_USER_APPROVAL & APPROVAL_VALIDATION
            if not challenge_id:
                # Create challenge if not already provided
                chal = self.create_send_challenge(
                    user_id=user_id,
                    recipient=norm_recipient,
                    message=message,
                    run_id=active_run_id,
                )
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.AWAITING_USER_APPROVAL,
                    status="PENDING_APPROVAL",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    challenge_id=chal.challenge_id,
                    evidence={"challenge": chal.model_dump()},
                )

            # Validate the provided approval challenge
            is_approved, apprv_reason = self.validate_send_approval(
                challenge_id=challenge_id,
                user_id=user_id,
                expected_recipient=norm_recipient,
                expected_message=message,
                expected_run_id=active_run_id,
            )
            if not is_approved:
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.BLOCKED,
                    status="BLOCKED",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    challenge_id=challenge_id,
                    error=f"Approval validation failed: {apprv_reason}",
                    evidence={"approval_error": apprv_reason},
                )

            # STAGE 7: SENDING (Single physical UI interaction)
            send_btn = await page.query_selector("button[data-testid='compose-btn-send'], span[data-testid='send']")
            if send_btn:
                await send_btn.click()
            else:
                await page.keyboard.press("Enter")

            await asyncio.sleep(2.0)

            # STAGE 8: SEND_ACCEPTANCE_CHECK
            # Inspect active chat conversation for outgoing message bubble
            outgoing_bubbles = await page.query_selector_all(
                "div.message-out, div[data-testid='msg-container']"
            )
            found_bubble = False
            for bubble in outgoing_bubbles[-5:]:  # Check last 5 messages
                text = await bubble.inner_text()
                if active_run_id in text or message[:20] in text:
                    found_bubble = True
                    break

            if not found_bubble:
                return WhatsAppExecutionResult(
                    stage=WorkflowStage.UNKNOWN,
                    status="UNKNOWN",
                    run_id=active_run_id,
                    recipient_redacted=redacted_rcpt,
                    message_snippet=message[:40],
                    challenge_id=challenge_id,
                    error="Outgoing message bubble could not be verified in the active conversation UI.",
                    evidence={"send_status": "UNCONFIRMED_BUBBLE"},
                )

            # STAGE 9: DELIVERY_PENDING
            # Check for checkmark status
            single_check = await page.query_selector("span[data-testid='msg-check']")
            double_check = await page.query_selector("span[data-testid='msg-dblcheck'], span[data-testid='msg-dblcheck-ack']")

            signal = "DOUBLE_CHECK_DELIVERED" if double_check else ("SINGLE_CHECK_SENT_SERVER" if single_check else "OUTGOING_BUBBLE_CONFIRMED")

            # STAGE 10: AWAITING_RECIPIENT_VERIFICATION
            return WhatsAppExecutionResult(
                stage=WorkflowStage.AWAITING_RECIPIENT_VERIFICATION,
                status="SENT_PENDING_RECEIPT_VERIFICATION",
                run_id=active_run_id,
                recipient_redacted=redacted_rcpt,
                message_snippet=message[:40],
                challenge_id=challenge_id,
                delivery_signal=signal,
                evidence={
                    "outgoing_bubble_found": True,
                    "delivery_signal": signal,
                    "recipient_verified_on_device": False,
                },
            )

        except Exception as exc:
            import traceback
            log.error("whatsapp_personal.workflow_failed", error=str(exc))
            return WhatsAppExecutionResult(
                stage=WorkflowStage.FAILED,
                status="FAILED",
                run_id=active_run_id,
                recipient_redacted=redacted_rcpt,
                message_snippet=message[:40],
                error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )
        finally:
            # We preserve the browser context open if interactive so user can see what happened
            pass

    # -------------------------------------------------------------------------
    # Tool Registration
    # -------------------------------------------------------------------------

    def register_tool(self) -> None:
        """Register the personal WhatsApp send tool in the Central ToolRegistry."""
        reg = ToolRegistry.get_instance()

        async def _tool_whatsapp_send(
            recipient: str,
            message: str,
            challenge_id: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            res = await self.execute_one_message_workflow(
                user_id=uid,
                recipient=recipient,
                message=message,
                challenge_id=challenge_id,
            )
            return {
                "stage": res.stage.value,
                "status": res.status,
                "run_id": res.run_id,
                "recipient_redacted": res.recipient_redacted,
                "challenge_id": res.challenge_id,
                "delivery_signal": res.delivery_signal,
                "error": res.error,
                "evidence": res.evidence,
            }

        reg.register(
            AgentTool(
                id="whatsapp_send_message",
                name="whatsapp_send_message",
                description="Send a single strictly approved personal WhatsApp text message to the verified second device.",
                source=ToolSource.CONNECTOR,
                capabilities=["messaging", "whatsapp", "communication"],
                permissions=["messaging:whatsapp:send"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "recipient": {
                            "type": "string",
                            "description": "Phone number of recipient in international E.164 format (+country and digits)",
                        },
                        "message": {
                            "type": "string",
                            "description": "Harmless text message content to transmit",
                        },
                        "challenge_id": {
                            "type": "string",
                            "description": "Cryptographic confirmation challenge ID obtained after human-in-the-loop approval",
                        },
                    },
                    "required": ["recipient", "message"],
                },
            ),
            _tool_whatsapp_send,
        )
        log.info("whatsapp_personal.tool_registered")
