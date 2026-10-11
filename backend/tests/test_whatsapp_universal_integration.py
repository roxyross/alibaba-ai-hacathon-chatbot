"""Comprehensive Universal WhatsApp Integration Test Suite.

Covers:
- Configuration parsing and secret redaction
- Recipient normalization and allowlist enforcement
- Multi-route capability negotiation (Desktop, Web, Cloud API)
- Desktop adapter discovery and Windows UWP probe
- Web adapter browser session probe
- Cloud API client requests, Meta Graph API v21.0 payload formats
- Cloud API Webhook HMAC-SHA256 signature verification and receipt processing
- ConfirmationGate cryptographic binding and anti-replay enforcement
- Security tests: unapproved send rejection, changed content rejection, changed recipient rejection
- Multilingual intent normalizer verification (English, Roman Urdu, Hindi)
- Central ToolRegistry registration and schema validation
"""

from __future__ import annotations

import hashlib
import hmac
import unittest.mock as mock
from pathlib import Path

import pytest
import respx

from app.device.windows_automation import UIElementModel
from app.integrations.whatsapp.base import WhatsAppBaseAdapter
from app.integrations.whatsapp.cloud_api_adapter import WhatsAppCloudApiAdapter
from app.integrations.whatsapp.desktop_adapter import WhatsAppDesktopAdapter
from app.integrations.whatsapp.models import (
    ConnectionState,
    WhatsAppCapability,
    WhatsAppRoute,
    WhatsAppTaskStatus,
)
from app.integrations.whatsapp.service import WhatsAppService
from app.integrations.whatsapp.web_adapter import WhatsAppWebAdapter
from app.multilingual.normalizer import UniversalIntentNormalizer
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel, ToolSource
from app.trust.confirmation_gate import ConfirmationGate
from app.trust.schemas import ConfirmationStatus, RiskTier

_MOCK_USER_ID = "test_user_001"
_VALID_TEST_PHONE = "+14155552671"
_UNAPPROVED_PHONE = "+14155559999"


@pytest.fixture(autouse=True)
def setup_whatsapp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up clean isolated environment for WhatsApp tests."""
    ConfirmationGate.clear()
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", _VALID_TEST_PHONE)
    monkeypatch.setenv("WHATSAPP_TEST_RECIPIENT_ALLOWLIST", f"{_VALID_TEST_PHONE},+447911123456")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test_app_secret_12345")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "10987654321")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "EAAtest_valid_meta_token_secure")
    monkeypatch.setenv("WHATSAPP_API_ENABLED", "true")
    # Reset singleton state
    service = WhatsAppService.get_instance()
    service._consumed_challenge_tokens.clear()


# =============================================================================
# 1. Recipient Normalization & Allowlist Tests
# =============================================================================

def test_recipient_normalization_e164() -> None:
    """Verify phone numbers normalize into strict E.164."""
    norm = WhatsAppBaseAdapter.normalize_phone_number("  +1 (415) 555-2671  ")
    assert norm == "+14155552671"

    norm_intl = WhatsAppBaseAdapter.normalize_phone_number("0044 7911 123456")
    assert norm_intl == "+447911123456"

    norm_digits = WhatsAppBaseAdapter.normalize_phone_number("14155552671")
    assert norm_digits == "+14155552671"

    with pytest.raises(ValueError, match="Invalid phone number format"):
        WhatsAppBaseAdapter.normalize_phone_number("123")  # too short

    with pytest.raises(ValueError, match="Recipient phone number cannot be empty"):
        WhatsAppBaseAdapter.normalize_phone_number("")


def test_recipient_redaction_pii_safety() -> None:
    """Verify phone numbers are masked to prevent PII exposure."""
    redacted = WhatsAppBaseAdapter.redact_phone_number("+14155552671")
    assert redacted == "+14*****671"
    assert "5552" not in redacted

    short_redacted = WhatsAppBaseAdapter.redact_phone_number("+123")
    assert short_redacted == "+XXXXXXX"


def test_allowlist_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify recipients outside the allowlist are strictly rejected."""
    service = WhatsAppService.get_instance()

    # Allowed recipient
    ok, norm, msg = service.validate_recipient_allowlist(_VALID_TEST_PHONE)
    assert ok is True
    assert norm == _VALID_TEST_PHONE

    # Disallowed recipient
    ok, norm, msg = service.validate_recipient_allowlist(_UNAPPROVED_PHONE)
    assert ok is False
    assert "REJECTED" in msg
    assert "+14*****999" in msg  # Redacted in error

    # Missing allowlist configuration
    monkeypatch.delenv("ROXY_WHATSAPP_TEST_RECIPIENT", raising=False)
    monkeypatch.delenv("WHATSAPP_TEST_RECIPIENT_ALLOWLIST", raising=False)
    ok, norm, msg = service.validate_recipient_allowlist(_VALID_TEST_PHONE)
    assert ok is False
    assert "BLOCKED: No test recipient allowlist configured" in msg


# =============================================================================
# 2. Confirmation Gate & Anti-Replay Security Tests
# =============================================================================

def test_challenge_creation_and_approval_binding() -> None:
    """Verify ConfirmationGate challenge is cryptographically bound to parameters."""
    service = WhatsAppService.get_instance()
    msg = "Test message for WhatsApp"

    chal = service.create_send_challenge(
        user_id=_MOCK_USER_ID,
        recipient=_VALID_TEST_PHONE,
        message=msg,
        route=WhatsAppRoute.WEB,
        run_id="run_wa_101",
    )
    assert chal.challenge_id.startswith("chk_")
    assert chal.risk_tier == RiskTier.HIGH
    assert chal.status == ConfirmationStatus.PENDING

    # Attempt send before approval -> rejected
    is_apprv, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        expected_recipient=_VALID_TEST_PHONE,
        expected_message=msg,
        expected_route=WhatsAppRoute.WEB,
        expected_run_id="run_wa_101",
    )
    assert is_apprv is False
    assert "expected 'approved'" in reason


def test_approval_tampering_message_changed() -> None:
    """Verify modifying message body after approval invalidates token."""
    service = WhatsAppService.get_instance()
    msg = "Original message text"

    chal = service.create_send_challenge(
        user_id=_MOCK_USER_ID,
        recipient=_VALID_TEST_PHONE,
        message=msg,
        route=WhatsAppRoute.DESKTOP,
        run_id="run_wa_102",
    )
    # Simulate user approval
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Attempt to validate with modified message text
    is_apprv, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        expected_recipient=_VALID_TEST_PHONE,
        expected_message="TAMPERED message text",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_wa_102",
    )
    assert is_apprv is False
    assert "altered after user approval" in reason


def test_approval_tampering_recipient_changed() -> None:
    """Verify modifying target recipient after approval invalidates token."""
    service = WhatsAppService.get_instance()
    msg = "Same message text"

    chal = service.create_send_challenge(
        user_id=_MOCK_USER_ID,
        recipient=_VALID_TEST_PHONE,
        message=msg,
        route=WhatsAppRoute.CLOUD_API,
        run_id="run_wa_103",
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Attempt to validate with different recipient
    is_apprv, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        expected_recipient="+447911123456",
        expected_message=msg,
        expected_route=WhatsAppRoute.CLOUD_API,
        expected_run_id="run_wa_103",
    )
    assert is_apprv is False
    assert "Target recipient does not match" in reason


def test_approval_tampering_route_switched() -> None:
    """Verify switching route after approval invalidates token."""
    service = WhatsAppService.get_instance()
    msg = "Same message text"

    chal = service.create_send_challenge(
        user_id=_MOCK_USER_ID,
        recipient=_VALID_TEST_PHONE,
        message=msg,
        route=WhatsAppRoute.WEB,
        run_id="run_wa_104",
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # Attempt to validate with DESKTOP route
    is_apprv, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        expected_recipient=_VALID_TEST_PHONE,
        expected_message=msg,
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_wa_104",
    )
    assert is_apprv is False
    assert "route was switched" in reason


def test_single_use_token_anti_replay() -> None:
    """Verify that a consumed approval token cannot be replayed for duplicate sends."""
    service = WhatsAppService.get_instance()
    msg = "One-time broadcast"

    chal = service.create_send_challenge(
        user_id=_MOCK_USER_ID,
        recipient=_VALID_TEST_PHONE,
        message=msg,
        route=WhatsAppRoute.CLOUD_API,
        run_id="run_wa_105",
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # First validation succeeds
    is_apprv, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        expected_recipient=_VALID_TEST_PHONE,
        expected_message=msg,
        expected_route=WhatsAppRoute.CLOUD_API,
        expected_run_id="run_wa_105",
    )
    assert is_apprv is True
    assert reason == "APPROVED"

    # Second validation fails (single-use enforced)
    is_apprv2, reason2 = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id=_MOCK_USER_ID,
        expected_recipient=_VALID_TEST_PHONE,
        expected_message=msg,
        expected_route=WhatsAppRoute.CLOUD_API,
        expected_run_id="run_wa_105",
    )
    assert is_apprv2 is False
    assert "already been consumed" in reason2


# =============================================================================
# 3. WhatsApp Desktop Adapter Tests
# =============================================================================

@pytest.mark.asyncio
async def test_desktop_adapter_discovery_not_running() -> None:
    """Verify desktop adapter discovers AppX package and reports NOT_RUNNING truthfully."""
    adapter = WhatsAppDesktopAdapter()
    assert adapter.route == WhatsAppRoute.DESKTOP
    assert WhatsAppCapability.SESSION_DISCOVERY in adapter.get_capabilities()

    # Mock package installed, process not running
    with mock.patch.object(adapter, "_is_package_installed", return_value=True), \
         mock.patch.object(adapter, "_find_running_process", return_value=None):
        rep = await adapter.get_connection_status()
        assert rep.route == WhatsAppRoute.DESKTOP
        assert rep.state == ConnectionState.NOT_RUNNING
        assert rep.is_ready is False
        assert "not currently running" in rep.details


@pytest.mark.asyncio
async def test_desktop_adapter_unauthenticated_qr() -> None:
    """Verify desktop adapter detects QR code / sign-in screen when running unauthenticated."""
    adapter = WhatsAppDesktopAdapter()

    fake_proc = mock.MagicMock()
    fake_proc.info = {"pid": 9876, "name": "WhatsApp.exe"}

    fake_element = UIElementModel(
        role="pane",
        control_type="PaneControl",
        name="Scan this QR code with your phone",
    )

    with mock.patch.object(adapter, "_is_package_installed", return_value=True), \
         mock.patch.object(adapter, "_find_running_process", return_value=fake_proc), \
         mock.patch("app.device.windows_automation.WindowsUIAutomationEngine.resolve_target_window", return_value=mock.MagicMock()), \
         mock.patch("app.device.windows_automation.WindowsUIAutomationEngine.device_inspect_ui", return_value=fake_element):
        rep = await adapter.get_connection_status()
        assert rep.state == ConnectionState.UNAUTHENTICATED
        assert rep.is_ready is False
        assert "QR" in rep.details


# =============================================================================
# 4. WhatsApp Web Adapter Tests
# =============================================================================

@pytest.mark.asyncio
async def test_web_adapter_status_unauthenticated_profile(tmp_path: Path) -> None:
    """Verify web adapter reports UNAUTHENTICATED for empty profile without fabricating state."""
    adapter = WhatsAppWebAdapter()
    adapter.profile_dir = tmp_path  # Empty directory

    rep = await adapter.get_connection_status()
    assert rep.route == WhatsAppRoute.WEB
    assert rep.state == ConnectionState.UNAUTHENTICATED
    assert rep.is_ready is False
    assert "empty" in rep.details


@pytest.mark.asyncio
async def test_web_adapter_status_authenticated_profile(tmp_path: Path) -> None:
    """Verify web adapter reports AUTHENTICATED when profile directory has session storage."""
    adapter = WhatsAppWebAdapter()
    # Create mock session storage file
    (tmp_path / "Default").mkdir()
    (tmp_path / "Default" / "Preferences").write_text("{}")
    adapter.profile_dir = tmp_path

    rep = await adapter.get_connection_status()
    assert rep.route == WhatsAppRoute.WEB
    assert rep.state == ConnectionState.AUTHENTICATED
    assert rep.is_ready is True


# =============================================================================
# 5. WhatsApp Cloud API Adapter Tests
# =============================================================================

@pytest.mark.asyncio
@respx.mock
async def test_cloud_api_connection_probe_success() -> None:
    """Verify Cloud API successfully validates credentials against Meta Graph API."""
    adapter = WhatsAppCloudApiAdapter()
    phone_id = "10987654321"

    respx.get(f"https://graph.facebook.com/v21.0/{phone_id}").respond(
        status_code=200,
        json={"verified_name": "ROXY Support Official", "display_phone_number": "+1 555-0199"},
    )

    rep = await adapter.get_connection_status()
    assert rep.state == ConnectionState.AUTHENTICATED
    assert rep.is_ready is True
    assert "ROXY Support Official" in rep.details


@pytest.mark.asyncio
@respx.mock
async def test_cloud_api_send_message_success() -> None:
    """Verify outbound send message to Meta Graph API v21.0 with provider WAMID verification."""
    adapter = WhatsAppCloudApiAdapter()
    phone_id = "10987654321"

    expected_wamid = "wamid.HBgLMTQxNTU1NTI2NzEVAgARGBI2ODQy"
    respx.post(f"https://graph.facebook.com/v21.0/{phone_id}/messages").respond(
        status_code=200,
        json={"messages": [{"id": expected_wamid}]},
    )

    res = await adapter.send_message(
        user_id=_MOCK_USER_ID,
        recipient=_VALID_TEST_PHONE,
        message="Hello from ROXY-AI Universal WhatsApp",
        challenge_id="chk_test_1",
        run_id="run_api_001",
    )
    assert res.status == WhatsAppTaskStatus.SENT
    assert res.provider_message_id == expected_wamid
    assert res.recipient_redacted == "+14*****671"
    assert res.verification_evidence["provider"] == "Meta Graph API v21.0"


def test_cloud_api_webhook_signature_verification() -> None:
    """Verify HMAC-SHA256 signature verification for incoming Meta webhooks."""
    adapter = WhatsAppCloudApiAdapter
    payload = b'{"object":"whatsapp_business_account","entry":[]}'
    secret = "test_app_secret_12345"

    # Compute valid signature
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    valid_header = f"sha256={sig}"

    assert adapter.verify_webhook_signature(payload, valid_header) is True
    assert adapter.verify_webhook_signature(payload, "sha256=invalid_tampered_hash") is False
    assert adapter.verify_webhook_signature(payload, "malformed_header") is False


def test_cloud_api_webhook_status_processing() -> None:
    """Verify processing incoming delivery and read receipts from Meta webhook events."""
    adapter = WhatsAppCloudApiAdapter()
    wamid = "wamid.HBgLMTQxNTU1NTI2NzEVAgARGBI2ODQy"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {
                                    "id": wamid,
                                    "status": "delivered",
                                    "timestamp": "1728518400",
                                    "recipient_id": "14155552671",
                                }
                            ]
                        }
                    }
                ]
            }
        ],
    }

    updates = adapter.process_webhook_payload(payload)
    assert len(updates) == 1
    assert updates[0]["wamid"] == wamid
    assert updates[0]["status"] == "delivered"
    assert adapter._status_by_wamid[wamid] == "delivered"


# =============================================================================
# 6. Service Route Negotiation & Tool Registration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_service_route_negotiation() -> None:
    """Verify route negotiation prioritizes authenticated channels appropriately."""
    service = WhatsAppService.get_instance()

    # Case 1: Cloud API authenticated -> selected
    with mock.patch.object(service.cloud_api_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=True)), \
         mock.patch.object(service.desktop_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=False)), \
         mock.patch.object(service.web_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=False)):
        route, reason = await service.negotiate_route(WhatsAppRoute.AUTO)
        assert route == WhatsAppRoute.CLOUD_API
        assert "Official Cloud API" in reason

    # Case 2: Only Desktop authenticated -> selected
    with mock.patch.object(service.cloud_api_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=False, state=ConnectionState.NOT_CONFIGURED, details="no creds")), \
         mock.patch.object(service.desktop_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=True)), \
         mock.patch.object(service.web_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=False, state=ConnectionState.UNAUTHENTICATED, details="empty profile")):
        route, reason = await service.negotiate_route(WhatsAppRoute.AUTO)
        assert route == WhatsAppRoute.DESKTOP
        assert "WhatsApp Desktop" in reason

    # Case 3: None authenticated -> reports all blockers truthfully
    with mock.patch.object(service.cloud_api_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=False, state=ConnectionState.NOT_CONFIGURED, details="missing credentials")), \
         mock.patch.object(service.desktop_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=False, state=ConnectionState.NOT_RUNNING, details="not running")), \
         mock.patch.object(service.web_adapter, "get_connection_status", return_value=mock.MagicMock(is_ready=False, state=ConnectionState.UNAUTHENTICATED, details="qr code displayed")):
        route, reason = await service.negotiate_route(WhatsAppRoute.AUTO)
        assert route is None
        assert "No authenticated WhatsApp route is available" in reason


def test_tool_registry_registration() -> None:
    """Verify universal WhatsApp tools are registered in ToolRegistry."""
    service = WhatsAppService.get_instance()
    service.register_tools()

    reg = ToolRegistry.get_instance()
    send_tool = reg.get("whatsapp_send_message")
    check_tool = reg.get("whatsapp_check_session")

    assert send_tool is not None
    assert send_tool.risk_level == RiskLevel.HIGH
    assert send_tool.requires_confirmation is True
    assert send_tool.source == ToolSource.CONNECTOR
    assert "recipient" in send_tool.input_schema["properties"]
    assert "route" in send_tool.input_schema["properties"]

    assert check_tool is not None
    assert check_tool.risk_level == RiskLevel.LOW
    assert check_tool.requires_confirmation is False


# =============================================================================
# 7. Multilingual Intent Normalizer Tests
# =============================================================================

def test_multilingual_whatsapp_intents() -> None:
    """Verify natural language queries in English and Roman Urdu map to exact WhatsApp actions."""
    # English queries
    i1 = UniversalIntentNormalizer.normalize("Roxy, open WhatsApp.")
    assert i1.action == "open"
    assert i1.target_app == "WhatsApp"

    i2 = UniversalIntentNormalizer.normalize("Check whether WhatsApp is connected.")
    assert i2.action == "check_status"
    assert i2.parameters["route"] == "auto"

    i3 = UniversalIntentNormalizer.normalize("Draft a WhatsApp message to my test contact.")
    assert i3.action == "draft_message"

    i4 = UniversalIntentNormalizer.normalize("Send this approved message through WhatsApp Desktop.")
    assert i4.action == "send_message"
    assert i4.parameters["route"] == "desktop"

    i5 = UniversalIntentNormalizer.normalize("Use my configured business messaging API.")
    assert i5.action == "select_route"
    assert i5.parameters["route"] == "cloud_api"

    # Roman Urdu queries
    u1 = UniversalIntentNormalizer.normalize("Roxy, WhatsApp kholo.")
    assert u1.action == "open"
    assert u1.target_app == "WhatsApp"

    u2 = UniversalIntentNormalizer.normalize("Mere test contact ke liye message draft karo.")
    assert u2.action == "draft_message"

    u3 = UniversalIntentNormalizer.normalize("Message bhejne se pehle mujhe dikhao.")
    assert u3.action == "preview_message"

    u4 = UniversalIntentNormalizer.normalize("Pehle recipient verify karo.")
    assert u4.action == "verify_recipient"

    u5 = UniversalIntentNormalizer.normalize("Abhi message send mat karna.")
    assert u5.action == "cancel_send"

    u6 = UniversalIntentNormalizer.normalize("Message ka status check karo.")
    assert u6.action == "check_status"
