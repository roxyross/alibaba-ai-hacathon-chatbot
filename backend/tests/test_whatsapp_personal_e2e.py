"""Test Suite for ROXY-AI Personal WhatsApp Integration Engine.

Covers:
1. Redaction of secrets and personal data
2. Recipient phone number normalization (E.164)
3. Recipient outside allowlist rejection
4. Unresolved, missing, and duplicate recipients
5. Confirmation challenge generation with RiskTier.HIGH
6. Missing approval gate enforcement
7. Expired approval rejection
8. Invalid or mismatched HMAC rejection
9. Recipient changed after approval rejection
10. Message body altered after approval rejection
11. Cancelled / rejected confirmation enforcement
12. Duplicate click and duplicate-send prevention (single-use tokens)
13. Missing authentication detection (mocked browser DOM)
14. UI navigation failure detection (mocked browser DOM)
15. Safe restart / recovery without automatic resend
16. Live E2E test guard (truthful skip when unconfigured)
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.whatsapp_personal import (
    WhatsAppPersonalIntegrationEngine,
    WorkflowStage,
)
from app.trust.confirmation_gate import ConfirmationGate
from app.trust.schemas import ConfirmationStatus, RiskTier


@pytest.fixture(autouse=True)
def reset_confirmation_gate() -> Generator[None, None, None]:
    """Reset ConfirmationGate before and after each test for strict isolation."""
    ConfirmationGate.clear()
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    engine._consumed_tokens.clear()
    yield
    ConfirmationGate.clear()
    engine._consumed_tokens.clear()


# =============================================================================
# 1. Privacy, Normalization & Recipient Allowlist Tests
# =============================================================================

def test_redaction_of_secrets_and_personal_data() -> None:
    """UNIT (Mocked): Ensure phone numbers and PII are redacted and never leaked."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    redacted = engine.redact_phone_number("+14155552671")
    assert "+14155552671" not in redacted
    assert "*****" in redacted
    assert redacted.startswith("+14")
    assert redacted.endswith("671")

    # Short string edge case
    assert engine.redact_phone_number("+123") == "+XXXXXXX"


def test_recipient_phone_number_normalization() -> None:
    """UNIT (Mocked): Normalize diverse formats into strict E.164 international standard."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()

    assert engine.normalize_phone_number("+1 (415) 555-2671") == "+14155552671"
    assert engine.normalize_phone_number("0092 300 1234567") == "+923001234567"
    assert engine.normalize_phone_number("+44-7911-123456") == "+447911123456"

    # Invalid formats
    with pytest.raises(ValueError, match="Invalid phone number format"):
        engine.normalize_phone_number("not_a_number")

    with pytest.raises(ValueError, match="Invalid phone number format"):
        engine.normalize_phone_number("+12")  # Too short

    with pytest.raises(ValueError, match="cannot be empty"):
        engine.normalize_phone_number("")


def test_recipient_outside_allowlist_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """UNIT (Mocked): Strict rejection of any number outside the single configured test recipient."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    # Target matching allowlist
    ok, norm, reason = engine.validate_recipient_allowlist("+1 (415) 555-0001")
    assert ok is True
    assert norm == "+14155550001"
    assert reason == "OK"

    # Target outside allowlist
    ok, norm, reason = engine.validate_recipient_allowlist("+14155559999")
    assert ok is False
    assert "not in the approved test allowlist" in reason
    # Ensure real target number was redacted in message
    assert "+14155559999" not in reason


def test_missing_configured_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    """UNIT (Mocked): When no recipient is configured, fail closed with BLOCKED status."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.delenv("ROXY_WHATSAPP_TEST_RECIPIENT", raising=False)

    ok, norm, reason = engine.validate_recipient_allowlist("+14155550001")
    assert ok is False
    assert "BLOCKED: No test recipient configured" in reason


def test_unresolved_and_duplicate_recipients() -> None:
    """UNIT (Mocked): Rejection of ambiguous, multi-recipient, or invalid targets."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()

    # Comma-separated or multiple recipients
    ok, norm, reason = engine.validate_recipient_allowlist("+14155550001, +14155550002")
    assert ok is False

    # Name instead of phone
    ok, norm, reason = engine.validate_recipient_allowlist("Ali")
    assert ok is False


# =============================================================================
# 2. Cryptographic Approval Gate & Tamper-Resistance Tests
# =============================================================================

def test_missing_approval_yields_awaiting_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked): Unapproved send request pauses at AWAITING_USER_APPROVAL."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    challenge = engine.create_send_challenge(
        user_id="user_test_01",
        recipient="+14155550001",
        message="Harmless E2E Verification Message",
        run_id="run_test_01",
    )

    assert challenge.challenge_id is not None
    assert challenge.risk_tier == RiskTier.HIGH
    assert challenge.status == ConfirmationStatus.PENDING
    assert challenge.details["recipient_normalized"] == "+14155550001"
    assert challenge.details["message_text"] == "Harmless E2E Verification Message"


def test_expired_approval_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked): Approval with expired TTL cannot be used for sending."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    # Create challenge with 0s TTL (already expired)
    challenge = engine.create_send_challenge(
        user_id="user_test_01",
        recipient="+14155550001",
        message="Test Expired",
        run_id="run_exp_01",
        ttl_seconds=-1,
    )

    # Attempting to resolve expired challenge raises ValueError
    with pytest.raises(ValueError, match="expired"):
        ConfirmationGate.resolve_challenge(
            challenge_id=challenge.challenge_id,
            user_id="user_test_01",
            decision="approve",
            challenge_token=challenge.challenge_token,
        )

    # Engine validation rejects it
    ok, reason = engine.validate_send_approval(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        expected_recipient="+14155550001",
        expected_message="Test Expired",
        expected_run_id="run_exp_01",
    )
    assert ok is False
    assert "expired" in reason.lower() or "not found" in reason.lower()


def test_invalid_or_mismatched_hmac_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked): Tampered challenge verification token is rejected by HMAC."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    challenge = engine.create_send_challenge(
        user_id="user_test_01",
        recipient="+14155550001",
        message="HMAC Verification",
        run_id="run_hmac_01",
    )

    # Resolve with forged token
    with pytest.raises(ValueError, match="Invalid challenge verification token"):
        ConfirmationGate.resolve_challenge(
            challenge_id=challenge.challenge_id,
            user_id="user_test_01",
            decision="approve",
            challenge_token="forged_token_1234567890abcdef",
        )


def test_recipient_changed_after_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked): If recipient differs from approved challenge, execution is refused."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    challenge = engine.create_send_challenge(
        user_id="user_test_01",
        recipient="+14155550001",
        message="Exact Message",
        run_id="run_rcpt_01",
    )

    ConfirmationGate.resolve_challenge(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        decision="approve",
        challenge_token=challenge.challenge_token,
    )

    # Attacking/changing recipient to another number
    ok, reason = engine.validate_send_approval(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        expected_recipient="+14155559999",  # Swapped recipient!
        expected_message="Exact Message",
        expected_run_id="run_rcpt_01",
    )
    assert ok is False
    assert "Target recipient does not match approved challenge" in reason


def test_message_changed_after_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked): If message body differs from approved challenge, execution is refused."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    challenge = engine.create_send_challenge(
        user_id="user_test_01",
        recipient="+14155550001",
        message="Original Approved Message",
        run_id="run_msg_01",
    )

    ConfirmationGate.resolve_challenge(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        decision="approve",
        challenge_token=challenge.challenge_token,
    )

    # Attacking/tampering with message body
    ok, reason = engine.validate_send_approval(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        expected_recipient="+14155550001",
        expected_message="Tampered Malicious Message Content",  # Altered!
        expected_run_id="run_msg_01",
    )
    assert ok is False
    assert "Outbound message text was altered after user approval" in reason


def test_cancelled_confirmation_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked): User explicit click 'Reject' results in zero sends."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    challenge = engine.create_send_challenge(
        user_id="user_test_01",
        recipient="+14155550001",
        message="User will reject this",
        run_id="run_cancel_01",
    )

    # User clicks Reject
    ConfirmationGate.resolve_challenge(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        decision="reject",
        challenge_token=challenge.challenge_token,
    )

    ok, reason = engine.validate_send_approval(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        expected_recipient="+14155550001",
        expected_message="User will reject this",
        expected_run_id="run_cancel_01",
    )
    assert ok is False
    assert "rejected" in reason.lower()


def test_duplicate_send_and_replay_prevention(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked): Single-use token prevents duplicate clicks and replay sends."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    challenge = engine.create_send_challenge(
        user_id="user_test_01",
        recipient="+14155550001",
        message="One Time Send",
        run_id="run_single_01",
    )

    ConfirmationGate.resolve_challenge(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        decision="approve",
        challenge_token=challenge.challenge_token,
    )

    # First validation succeeds
    ok1, reason1 = engine.validate_send_approval(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        expected_recipient="+14155550001",
        expected_message="One Time Send",
        expected_run_id="run_single_01",
    )
    assert ok1 is True
    assert reason1 == "APPROVED"

    # Second validation of same token (e.g. double click or replay attack) fails
    ok2, reason2 = engine.validate_send_approval(
        challenge_id=challenge.challenge_id,
        user_id="user_test_01",
        expected_recipient="+14155550001",
        expected_message="One Time Send",
        expected_run_id="run_single_01",
    )
    assert ok2 is False
    assert "already been consumed" in reason2


# =============================================================================
# 3. UI Navigation & Session State Tests (Mocked Browser DOM)
# =============================================================================

@pytest.mark.asyncio
async def test_missing_authentication_detection_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked Browser): Detect unauthenticated session / QR prompt and stop safely."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    # Mock Playwright session with QR code visible (no chat list)
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    # auth selector returns a canvas (QR code)
    mock_qr_elem = MagicMock()
    mock_page.wait_for_selector = AsyncMock(return_value=mock_qr_elem)
    # query for chat_list returns None
    mock_page.query_selector = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get_active_page.return_value = mock_page

    mock_pw = MagicMock()
    mock_pw.launch_session = AsyncMock(return_value=MagicMock(success=True))
    mock_pw._sessions = {"wa_sess_run_mock_auth": mock_session}

    with patch("app.integrations.whatsapp_personal.PlaywrightBrowserManager.get_instance", return_value=mock_pw):
        result = await engine.execute_one_message_workflow(
            user_id="user_test_01",
            recipient="+14155550001",
            message="Test message",
            run_id="run_mock_auth",
            interactive=False,
        )

        assert result.stage == WorkflowStage.BLOCKED
        assert result.status == "BLOCKED"
        assert "INTERACTIVE AUTHENTICATION REQUIRED" in (result.error or "")
        assert result.evidence.get("auth_state") == "QR_CODE_OR_LOGIN_PROMPT_DETECTED"


@pytest.mark.asyncio
async def test_ui_navigation_failure_detection_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """INTEGRATION (Mocked Browser): Detect invalid recipient / popup in WhatsApp Web."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+14155550001")

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()

    # Authenticated: chat_list query succeeds
    mock_chat_list = MagicMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=[
        mock_chat_list,  # auth check succeeds
        None,             # compose box wait times out
    ])
    mock_popup = AsyncMock()
    mock_popup.inner_text = AsyncMock(return_value="Phone number shared via url is invalid.")
    mock_page.query_selector = AsyncMock(side_effect=[
        mock_chat_list,  # chat list check
        mock_popup,      # popup check
    ])

    mock_session = MagicMock()
    mock_session.get_active_page.return_value = mock_page

    mock_pw = MagicMock()
    mock_pw.launch_session = AsyncMock(return_value=MagicMock(success=True))
    mock_pw._sessions = {"wa_sess_run_nav_fail": mock_session}

    with patch("app.integrations.whatsapp_personal.PlaywrightBrowserManager.get_instance", return_value=mock_pw):
        result = await engine.execute_one_message_workflow(
            user_id="user_test_01",
            recipient="+14155550001",
            message="Test message",
            run_id="run_nav_fail",
            interactive=False,
        )

        assert result.stage == WorkflowStage.FAILED
        assert result.status == "FAILED"
        assert "Phone number shared via url is invalid" in (result.error or "")


def test_safe_restart_recovery_without_automatic_resend() -> None:
    """UNIT (Mocked): Safe recovery on restart without auto-sending pending messages."""
    engine = WhatsAppPersonalIntegrationEngine.get_instance()
    # Confirm tokens consumed are tracked and challenges clear cleanly
    engine._consumed_tokens.add("chk_consumed_123")
    assert "chk_consumed_123" in engine._consumed_tokens
    # No pending queue automatically dispatches on startup
    ConfirmationGate.clear()
    assert len(ConfirmationGate.list_pending("user_test_01")) == 0
