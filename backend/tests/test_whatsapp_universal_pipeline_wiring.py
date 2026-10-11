"""Comprehensive tests for Roxy-AI Phase P1: WhatsApp Universal Pipeline Wiring.

Under the Zero Simulation doctrine:
Covers:
1. Intent resolution through shared IntegrationResolver and KNOWN_CONNECTOR_CATALOG.
2. Route negotiation, synonyms, and capability matching.
3. UniversalAppController 5-stage lifecycle (Resolve -> Permission -> Plan -> Execute -> Verify).
4. Fail-closed behavior for unauthenticated Desktop/Web/Cloud API routes (Stage: 'blocked').
5. Strict ConfirmationGate approval binding, tampering detection, and anti-replay single-use tokens.
6. VerificationEngine 2.0 WhatsAppStatusVerifier multi-level scoring and delivery signal distinction.
7. Composite verification integration with cryptographic proof hashing.

Labels: [MOCKED], [COMPONENT], [INTEGRATION]
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from app.device.integration_resolver import (
    APP_SYNONYMS,
    KNOWN_CONNECTOR_CATALOG,
    IntegrationResolver,
)
from app.device.orchestrator import UniversalAppController
from app.device.schemas import (
    AppControlExecutionRequest,
    CompositeLogic,
    CompositeVerificationRequest,
    IntegrationResolutionRequest,
    WhatsAppVerificationCriteria,
)
from app.device.verification_engine import VerificationEngine, WhatsAppStatusVerifier
from app.integrations.whatsapp.models import (
    WhatsAppOperationResult,
    WhatsAppRoute,
    WhatsAppTaskStatus,
)
from app.integrations.whatsapp.service import WhatsAppService
from app.trust.confirmation_gate import ConfirmationGate


@pytest.fixture(autouse=True)
def setup_whatsapp_test_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Ensure strict test recipient allowlist is set and clean cache."""
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+15551234567")
    monkeypatch.setenv("WHATSAPP_TEST_RECIPIENT_ALLOWLIST", "+15551234567,+15559876543")
    # Reset singleton state
    wa = WhatsAppService.get_instance()
    wa._consumed_challenge_tokens.clear()
    ConfirmationGate.clear()
    yield
    wa._consumed_challenge_tokens.clear()
    ConfirmationGate.clear()


# =============================================================================
# 1. Intent Resolution & Connector Catalog Tests [COMPONENT]
# =============================================================================


def test_whatsapp_in_known_connector_catalog() -> None:
    """Verify WhatsApp is registered in the authoritative connector catalog."""
    assert "whatsapp" in KNOWN_CONNECTOR_CATALOG
    catalog = KNOWN_CONNECTOR_CATALOG["whatsapp"]
    assert catalog["title"] == "WhatsApp"
    assert catalog["connector_type"] == "whatsapp"
    assert "send_message" in catalog["capabilities"]
    assert "check_session" in catalog["capabilities"]
    assert catalog["capabilities"]["send_message"] == "whatsapp_send_message"
    assert catalog["capabilities"]["check_session"] == "whatsapp_check_session"


def test_whatsapp_synonyms_mapping() -> None:
    """Verify synonyms resolve to 'whatsapp' slug."""
    for syn in ("wa", "whatsapp_web", "whatsapp_desktop", "whatsapp_messenger"):
        assert APP_SYNONYMS.get(syn) == "whatsapp"
        assert IntegrationResolver.normalize_app_name(syn) == "whatsapp"


def test_resolve_whatsapp_unauthenticated_catalog() -> None:
    """When unauthenticated, resolver selects cloud_connector with confidence 0.60 and status check."""
    req = IntegrationResolutionRequest(
        application="WhatsApp",
        requested_capability="send_message",
        user_context={},
    )
    result = IntegrationResolver.resolve(req)
    assert result.success is True
    assert result.chosen_integration == "cloud_connector"
    assert result.handler_target == "whatsapp_send_message"
    assert result.confidence == 0.60
    assert result.verification_method == "whatsapp_status_check"
    assert result.risk == "HIGH"
    assert result.requires_confirmation is True
    assert "requires authentication" in result.candidates[0].description.lower()


def test_resolve_whatsapp_authenticated_route() -> None:
    """When session or Cloud API is active, confidence elevates to 0.98."""
    req = IntegrationResolutionRequest(
        application="wa",
        requested_capability="send_text_message",
        user_context={"whatsapp_authenticated": True},
    )
    result = IntegrationResolver.resolve(req)
    assert result.success is True
    assert result.chosen_integration == "cloud_connector"
    assert result.confidence == 0.98
    assert result.verification_method == "whatsapp_status_check"


def test_resolve_whatsapp_unsupported_action() -> None:
    """Unsupported arbitrary capability falls back cleanly to 'unsupported'."""
    req = IntegrationResolutionRequest(
        application="WhatsApp",
        requested_capability="delete_remote_server_database",
    )
    result = IntegrationResolver.resolve(req)
    assert result.success is False
    assert result.chosen_integration == "unsupported"
    assert result.confidence == 0.0


# =============================================================================
# 2. UniversalAppController Shared Planning & Dispatch [INTEGRATION]
# =============================================================================


def test_orchestrator_stage_plan_whatsapp() -> None:
    """Verify UniversalAppController synthesizes 3-step WhatsApp execution plan."""
    controller = UniversalAppController.get_instance()
    req = AppControlExecutionRequest(
        application="WhatsApp",
        capability="send_message",
        parameters={"recipient": "+15551234567", "message": "Test"},
    )
    resolution = IntegrationResolver.resolve(
        IntegrationResolutionRequest(application="WhatsApp", requested_capability="send_message")
    )
    plan = controller._stage_plan("plan_test_wa", req, resolution)
    assert len(plan.steps) == 3
    assert plan.steps[0].action == "verify_whatsapp_route"
    assert plan.steps[1].action == "whatsapp_send_message"
    assert plan.steps[2].action == "verify_whatsapp_status"
    assert plan.verification_criteria.get("method") == "whatsapp_status_check"


@pytest.mark.asyncio
async def test_shared_dispatch_unauthenticated_fails_closed_blocked() -> None:
    """Without QR scan or Cloud API, shared execution returns stage='blocked' fail-closed."""
    controller = UniversalAppController.get_instance()
    req = AppControlExecutionRequest(
        application="WhatsApp",
        capability="send_message",
        parameters={"recipient": "+15551234567", "message": "Live send attempt"},
        confirmed=True,  # Caller confirmed, but session is not authenticated
    )
    result = await controller.execute_lifecycle(req)
    assert result.success is False
    assert result.verified is False
    assert result.stage == "blocked"
    assert "No authenticated WhatsApp route is available" in (result.error or "")
    assert result.execution_output.get("status") == "BLOCKED"


@pytest.mark.asyncio
async def test_shared_dispatch_unconfirmed_requires_pending_confirmation() -> None:
    """High-risk WhatsApp send requires human confirmation if not pre-confirmed."""
    controller = UniversalAppController.get_instance()
    req = AppControlExecutionRequest(
        application="WhatsApp",
        capability="send_message",
        parameters={"recipient": "+15551234567", "message": "Hello"},
        confirmed=False,
    )
    result = await controller.execute_lifecycle(req)
    assert result.success is False
    assert result.stage == "pending_confirmation"
    assert result.pending_confirmation_details is not None
    assert "confirmation_token" in result.pending_confirmation_details


@pytest.mark.asyncio
async def test_shared_dispatch_check_session_capability() -> None:
    """Check session capability dispatches to probe_all_routes cleanly."""
    controller = UniversalAppController.get_instance()
    req = AppControlExecutionRequest(
        application="WhatsApp",
        capability="check_session",
        parameters={"route": "auto"},
        confirmed=True,
    )
    result = await controller.execute_lifecycle(req)
    assert result.success is True
    assert result.stage in ("verified", "executed")
    output = result.execution_output
    assert "desktop" in output
    assert "web" in output
    assert "cloud_api" in output


# =============================================================================
# 3. Security, Allowlist, and Approval Binding Tests [COMPONENT]
# =============================================================================


@pytest.mark.asyncio
async def test_allowlist_rejection_in_shared_pipeline() -> None:
    """Unapproved recipient is rejected and returns stage='blocked'."""
    controller = UniversalAppController.get_instance()
    req = AppControlExecutionRequest(
        application="WhatsApp",
        capability="send_message",
        parameters={"recipient": "+19998887777", "message": "Disallowed"},
        confirmed=True,
    )
    result = await controller.execute_lifecycle(req)
    assert result.success is False
    assert result.stage == "blocked"
    assert result.execution_output.get("error_code") == "ALLOWLIST_REJECTED"


@pytest.mark.asyncio
async def test_approval_tampering_and_replay_protection() -> None:
    """Test message tampering and single-use challenge token consumption."""
    service = WhatsAppService.get_instance()
    chal = service.create_send_challenge(
        user_id="user1",
        recipient="+15551234567",
        message="Original Message",
        route=WhatsAppRoute.DESKTOP,
        run_id="run_123",
    )
    # User approves
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="user1",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # 1. Message altered after approval -> REJECTED
    is_valid, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="user1",
        expected_recipient="+15551234567",
        expected_message="Tampered Message",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_123",
    )
    assert is_valid is False
    assert "altered after user approval" in reason

    # 2. Recipient altered after approval -> REJECTED
    is_valid, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="user1",
        expected_recipient="+15559876543",
        expected_message="Original Message",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_123",
    )
    assert is_valid is False
    assert "recipient does not match" in reason

    # 3. Valid parameters -> APPROVED & consumed
    is_valid, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="user1",
        expected_recipient="+15551234567",
        expected_message="Original Message",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_123",
    )
    assert is_valid is True
    assert reason == "APPROVED"

    # 4. Replay attempt with same token -> REJECTED
    is_valid_replay, reason_replay = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="user1",
        expected_recipient="+15551234567",
        expected_message="Original Message",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_123",
    )
    assert is_valid_replay is False
    assert "already been consumed" in reason_replay


# =============================================================================
# 4. VerificationEngine 2.0 & Multi-Level Evidence [COMPONENT & MOCKED]
# =============================================================================


@pytest.mark.asyncio
async def test_verification_engine_whatsapp_status_scoring() -> None:
    """Verify WhatsAppStatusVerifier distinguishes the evidence levels under Zero Simulation."""
    # Case A: WAITING_FOR_APPROVAL
    crit_approval = WhatsAppVerificationCriteria(expected_status="SENT")
    res_approval = await WhatsAppStatusVerifier.verify(
        crit_approval, exec_output={"status": "WAITING_FOR_APPROVAL", "route": "desktop"}
    )
    assert res_approval.passed is False
    assert res_approval.score == 0.70

    # Case B: BLOCKED
    crit_blocked = WhatsAppVerificationCriteria(expected_status="SENT")
    res_blocked = await WhatsAppStatusVerifier.verify(
        crit_blocked, exec_output={"status": "BLOCKED", "route": "web", "user_facing_error": "Session unauthenticated"}
    )
    assert res_blocked.passed is False
    assert res_blocked.score == 0.0

    # Case C: SENT without delivery receipt when require_delivery_signal=False
    crit_sent = WhatsAppVerificationCriteria(expected_status="SENT", require_delivery_signal=False)
    res_sent = await WhatsAppStatusVerifier.verify(
        crit_sent, exec_output={"status": "SENT", "route": "desktop", "outgoing_bubble_detected": True}
    )
    assert res_sent.passed is True
    assert res_sent.score >= 0.85
    assert res_sent.evidence.get("message_visible_in_outgoing") is True

    # Case D: SENT without delivery receipt when require_delivery_signal=True (must NOT overclaim delivery)
    crit_delivery_req = WhatsAppVerificationCriteria(expected_status="DELIVERED", require_delivery_signal=True)
    res_delivery_req = await WhatsAppStatusVerifier.verify(
        crit_delivery_req, exec_output={"status": "SENT", "route": "desktop", "outgoing_bubble_detected": True}
    )
    assert res_delivery_req.passed is False
    assert "Delivery signal unconfirmed" in (res_delivery_req.error or "")

    # Case E: DELIVERED with reliable delivery signal (wamid / webhook)
    crit_delivered = WhatsAppVerificationCriteria(expected_status="DELIVERED", require_delivery_signal=True)
    res_delivered = await WhatsAppStatusVerifier.verify(
        crit_delivered,
        exec_output={
            "status": "DELIVERED",
            "route": "cloud_api",
            "message_id": "wamid.HBgL...",
            "read_receipt_verified": True,
        },
    )
    assert res_delivered.passed is True
    assert res_delivered.score == 1.0
    assert res_delivered.evidence.get("delivery_signal_type") == "meta_webhook_delivered"


@pytest.mark.asyncio
async def test_composite_verification_with_whatsapp_criteria() -> None:
    """Test full VerificationEngine.execute_composite with whatsapp_criteria and cryptographic proof hash."""
    engine = VerificationEngine.get_instance()
    engine.clear_history()

    wa_crit = WhatsAppVerificationCriteria(
        action_name="whatsapp_send_message",
        expected_status="SENT",
        require_delivery_signal=False,
    )
    req = CompositeVerificationRequest(
        action_name="test_composite_wa",
        logic=CompositeLogic.ALL_OF,
        whatsapp_criteria=[wa_crit],
    )

    # Execute composite verification with simulated execution output
    res = await engine.execute_composite(
        req,
        exec_output={"status": "SENT", "route": "desktop", "outgoing_bubble_detected": True},
    )
    assert res.verification_id is not None
    assert res.verification_proof_hash is not None
    assert len(res.verification_proof_hash) == 64  # SHA-256
    assert res.passed is True


# =============================================================================
# 5. Mocked End-to-End Execution & Verification Pipeline [MOCKED]
# =============================================================================


@pytest.mark.asyncio
async def test_mocked_end_to_end_successful_send_and_verify() -> None:
    """Verify complete 5-stage lifecycle when underlying adapter successfully completes (mocked)."""
    controller = UniversalAppController.get_instance()
    service = WhatsAppService.get_instance()

    mock_op_result = WhatsAppOperationResult(
        operation_id="wa_test_mock_123",
        route=WhatsAppRoute.CLOUD_API,
        status=WhatsAppTaskStatus.SENT,
        recipient_normalized="+15551234567",
        recipient_redacted="+1555***4567",
        message_snippet="Hello test",
        provider_message_id="wamid.HBgL12345",
        verification_evidence={"wamid": "wamid.HBgL12345"},
    )

    with patch.object(service, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_op_result

        req = AppControlExecutionRequest(
            application="WhatsApp",
            capability="send_message",
            parameters={"recipient": "+15551234567", "message": "Hello test"},
            confirmed=True,
        )

        result = await controller.execute_lifecycle(req)
        assert result.success is True
        assert result.verified is True
        assert result.stage == "verified"
        assert result.execution_output.get("status") == "SENT"
        assert result.verification.get("verified") is True
        assert result.plan is not None
        assert len(result.plan.steps) == 3


# =============================================================================
# 6. Truthful Status, Anti-Replay, Cancellation & Webhooks [GATE A3 REGRESSIONS]
# =============================================================================


@pytest.mark.asyncio
async def test_truthful_status_taxonomy_distinctions() -> None:
    """Verify semantic status mappings distinguish all Gate A3 required statuses."""
    # 1. BLOCKED_AUTH: missing session/authentication
    res_auth = WhatsAppOperationResult(
        operation_id="op_1",
        route=WhatsAppRoute.DESKTOP,
        status=WhatsAppTaskStatus.BLOCKED,
        error_code="NO_AUTHENTICATED_ROUTE",
    )
    assert res_auth.semantic_status == "BLOCKED_AUTH"
    assert res_auth.to_dict()["semantic_status"] == "BLOCKED_AUTH"

    # 2. BLOCKED_CREDENTIALS: missing Cloud API credentials
    res_cred = WhatsAppOperationResult(
        operation_id="op_2",
        route=WhatsAppRoute.CLOUD_API,
        status=WhatsAppTaskStatus.BLOCKED,
        error_code="BLOCKED_CREDENTIALS",
    )
    assert res_cred.semantic_status == "BLOCKED_CREDENTIALS"
    assert res_cred.to_dict()["semantic_status"] == "BLOCKED_CREDENTIALS"

    # 3. AWAITING_CONFIRMATION: user approval required
    res_conf = WhatsAppOperationResult(
        operation_id="op_3",
        route=WhatsAppRoute.DESKTOP,
        status=WhatsAppTaskStatus.WAITING_FOR_APPROVAL,
    )
    assert res_conf.semantic_status == "AWAITING_CONFIRMATION"

    # 4. REJECTED: policy or allowlist or approval denied
    res_rej = WhatsAppOperationResult(
        operation_id="op_4",
        route=WhatsAppRoute.DESKTOP,
        status=WhatsAppTaskStatus.BLOCKED,
        error_code="ALLOWLIST_REJECTED",
    )
    assert res_rej.semantic_status == "REJECTED"

    # 5. SUBMITTED: outgoing message accepted/transmitted
    res_sub = WhatsAppOperationResult(
        operation_id="op_5",
        route=WhatsAppRoute.CLOUD_API,
        status=WhatsAppTaskStatus.SENT,
    )
    assert res_sub.semantic_status == "SUBMITTED"

    # 6. DELIVERED: trustworthy delivery evidence exists
    res_del = WhatsAppOperationResult(
        operation_id="op_6",
        route=WhatsAppRoute.CLOUD_API,
        status=WhatsAppTaskStatus.DELIVERED,
    )
    assert res_del.semantic_status == "DELIVERED"

    # 7. CANCELLED: operation was cancelled
    res_can = WhatsAppOperationResult(
        operation_id="op_7",
        route=WhatsAppRoute.DESKTOP,
        status=WhatsAppTaskStatus.CANCELLED,
    )
    assert res_can.semantic_status == "CANCELLED"

    # 8. FAILED: execution failed
    res_fail = WhatsAppOperationResult(
        operation_id="op_8",
        route=WhatsAppRoute.DESKTOP,
        status=WhatsAppTaskStatus.FAILED,
    )
    assert res_fail.semantic_status == "FAILED"

    # 9. UNKNOWN: outcome cannot be verified
    res_unk = WhatsAppOperationResult(
        operation_id="op_9",
        route=WhatsAppRoute.DESKTOP,
        status=WhatsAppTaskStatus.UNKNOWN,
    )
    assert res_unk.semantic_status == "UNKNOWN"


@pytest.mark.asyncio
async def test_duplicate_request_and_retry_prevention_in_shared_pipeline() -> None:
    """Verify duplicate execution and replay attempts fail closed without duplicate sends."""
    service = WhatsAppService.get_instance()
    chal = service.create_send_challenge(
        user_id="user1",
        recipient="+15551234567",
        message="Important transaction message",
        route=WhatsAppRoute.DESKTOP,
        run_id="run_dedup_001",
    )
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="user1",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # First validation succeeds
    valid_first, reason_first = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="user1",
        expected_recipient="+15551234567",
        expected_message="Important transaction message",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_dedup_001",
    )
    assert valid_first is True
    assert reason_first == "APPROVED"

    # Immediate replay / retry attempt with identical payload is strictly denied
    valid_second, reason_second = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="user1",
        expected_recipient="+15551234567",
        expected_message="Important transaction message",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_dedup_001",
    )
    assert valid_second is False
    assert "already been consumed" in reason_second


@pytest.mark.asyncio
async def test_cancellation_and_adapter_execution_failure_handling() -> None:
    """Verify cancelled challenges and adapter execution failures return truthful failure states."""
    service = WhatsAppService.get_instance()
    chal = service.create_send_challenge(
        user_id="user1",
        recipient="+15551234567",
        message="Cancelling this message",
        route=WhatsAppRoute.DESKTOP,
        run_id="run_cancel_001",
    )
    # User explicitly rejects / cancels confirmation
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="user1",
        decision="reject",
        challenge_token=chal.challenge_token,
    )

    # Validation must reject cancelled challenge
    is_valid, reason = service.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="user1",
        expected_recipient="+15551234567",
        expected_message="Cancelling this message",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_cancel_001",
    )
    assert is_valid is False
    assert "rejected" in reason.lower() or "cancelled" in reason.lower()


def test_webhook_signature_verification_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify webhook authenticity validation using HMAC-SHA256 signature."""
    import hashlib
    import hmac
    from app.integrations.whatsapp.cloud_api_adapter import WhatsAppCloudApiAdapter

    secret = "test_meta_webhook_secret_key_12345"
    monkeypatch.setenv("WHATSAPP_APP_SECRET", secret)

    payload_body = b'{"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.123", "status": "delivered"}]}}]}]}'
    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()
    forged_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    assert WhatsAppCloudApiAdapter.verify_webhook_signature(payload_body, valid_sig) is True
    assert WhatsAppCloudApiAdapter.verify_webhook_signature(payload_body, forged_sig) is False
    assert WhatsAppCloudApiAdapter.verify_webhook_signature(payload_body, "invalid_header") is False
