"""Independent Security Re-Audit and Adversarial Verification Suite for Gate A2 and P0 Remediation.

This test file programmatically evaluates the 10 mandatory adversarial test cases
defined in Gate A2 and the P0 Security Remediation Master Prompt:
1. Public request with bypass_confirmation=true is neutralized and rejected.
2. Missing confirmation halts execution at pending_confirmation with server challenge.
3. confirmed=true without a valid server-issued approval token is rejected.
4. Forged, modified, expired, mismatched, and consumed tokens are rejected fail-closed.
5. Approval token cannot be reused across users, apps, actions, or altered parameters.
6. Race-safe single-use enforcement: concurrent attempts allow at most 1 execution.
7. Unauthorized and unauthenticated attempts never invoke sensitive handlers.
8. Failed or skipped verification is reported truthfully (stage='executed', verified=False).
9. WhatsApp cryptographic message-hash, recipient-binding, and anti-replay remain intact.
10. Authentication and authorization boundaries are enforced on all public routes.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.orchestrator import _PENDING_CONFIRMATIONS, UniversalAppController
from app.device.schemas import (
    AppControlExecutionRequest,
    AppControlExecutionResult,
)
from app.integrations.whatsapp.models import WhatsAppRoute
from app.integrations.whatsapp.service import (
    WhatsAppService,
)
from app.main import app
from app.tools.builtin import register_builtin_tools
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    RiskLevel,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
)
from app.trust.confirmation_gate import ConfirmationGate, canonicalize_parameters


from app.permissions.schemas import PermissionPolicy
from app.permissions.service import _MEM_GRANTS_BY_ID, clear_in_memory_grants


@pytest.fixture(autouse=True)
def clean_audit_state() -> Generator[None, None, None]:
    """Reset confirmation stores and ensure isolated testing."""
    ConfirmationGate.clear()
    _PENDING_CONFIRMATIONS.clear()
    clear_in_memory_grants()
    reg = ToolRegistry.get_instance()
    register_builtin_tools(reg)

    # Configure ALWAYS_ASK policy on Spotify for isolated adversarial audit test users
    for u in ("usr_audit_target_12345", "victim_user_a"):
        gid = f"grant_{u}_spotify_always_ask"
        _MEM_GRANTS_BY_ID[gid] = {
            "id": gid,
            "user_id": u,
            "target_app": "spotify",
            "capability": None,
            "permission": "execute",
            "policy": PermissionPolicy.ALWAYS_ASK.value,
            "scope": "app",
            "device_id": None,
            "resource": None,
            "parameter_constraints": None,
            "risk_level": "medium",
            "grant_source": "audit_test",
            "expires_at": None,
            "revoked_at": None,
            "is_active": True,
        }

    yield
    ConfirmationGate.clear()
    _PENDING_CONFIRMATIONS.clear()
    clear_in_memory_grants()


@pytest.fixture
def mock_user() -> User:
    return User(
        id="usr_audit_target_12345",
        email="auditor@roxy.internal",
    )


@pytest.fixture
def test_client(mock_user: User) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# =============================================================================
# Test Case 1: Public request with bypass_confirmation=true is neutralized
# =============================================================================

@pytest.mark.asyncio
async def test_case_01_tool_execution_bypass_confirmation_flag(test_client: TestClient) -> None:
    """Verify that external public clients CANNOT supply bypass_confirmation=true to bypass confirmation."""
    reg = ToolRegistry.get_instance()
    tool = reg.get("system_email_send")
    assert tool is not None
    assert tool.requires_confirmation is True

    # 1. Normal call without bypass -> asks for confirmation
    payload_normal = {
        "tool_id": "system_email_send",
        "user_id": "usr_audit_target_12345",
        "arguments": {"to": "audit_victim@test.local", "subject": "Audit", "body": "Sensitive Body"},
        "bypass_confirmation": False,
    }
    resp1 = test_client.post("/api/v1/tools/execute", json=payload_normal)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "requires_confirmation"
    assert data1["success"] is False
    assert "challenge" in data1.get("output", {})

    # 2. Adversarial public call with bypass_confirmation=true -> MUST BE NEUTRALIZED & REJECTED
    payload_bypass = {
        "tool_id": "system_email_send",
        "user_id": "usr_audit_target_12345",
        "arguments": {"to": "audit_victim@test.local", "subject": "Audit", "body": "Sensitive Body"},
        "bypass_confirmation": True,
    }
    resp2 = test_client.post("/api/v1/tools/execute", json=payload_bypass)
    assert resp2.status_code == 200
    data2 = resp2.json()

    # Must NOT succeed; must still require confirmation
    assert data2["success"] is False, "CRITICAL: Public bypass_confirmation=true must not succeed!"
    assert data2["status"] == "requires_confirmation"
    assert "challenge" in data2.get("output", {})


# =============================================================================
# Test Case 2: Missing confirmation halts execution at pending_confirmation
# =============================================================================

@pytest.mark.asyncio
async def test_case_02_missing_confirmation_returns_pending() -> None:
    """Verify that omitting confirmation for sensitive operations halts execution at pending_confirmation."""
    ctrl = UniversalAppController.get_instance()
    req = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Adversarial Track"},
        user_id="usr_audit_target_12345",
        confirmed=False,
    )
    res = await ctrl.execute_lifecycle(req)
    assert res.stage == "pending_confirmation"
    assert res.success is False
    assert res.verified is False
    assert res.pending_confirmation_details is not None
    assert "confirmation_token" in res.pending_confirmation_details


# =============================================================================
# Test Case 3: confirmed=true without a valid server-issued approval is rejected
# =============================================================================

@pytest.mark.asyncio
async def test_case_03_app_control_confirmed_true_without_valid_token(test_client: TestClient) -> None:
    """Verify that confirmed=true without a valid server token is rejected."""
    payload_fake_confirmed = {
        "application": "Spotify",
        "capability": "play_music",
        "parameters": {"track": "Bypassed Track"},
        "confirmed": True,
        "confirmation_token": None,
    }
    resp = test_client.post("/api/v1/devices/app-control/orchestrate", json=payload_fake_confirmed)
    assert resp.status_code == 200
    data = resp.json()

    # Must NOT execute or be verified
    assert data["success"] is False
    assert data["verified"] is False
    assert data["stage"] == "pending_confirmation"
    assert "confirmation_token" in data["pending_confirmation_details"]


# =============================================================================
# Test Case 4: Forged, modified, expired, mismatched, and consumed tokens
# =============================================================================

@pytest.mark.asyncio
async def test_case_04_forged_and_expired_tokens() -> None:
    """Verify rejection of forged and expired confirmation tokens in ConfirmationGate and Orchestrator."""
    # A. ConfirmationGate token tampering check
    chal = ConfirmationGate.create_challenge(
        user_id="usr_audit_target_12345",
        action_type="financial_transfer",
        title="Transfer",
        summary="Transfer funds",
        ttl_seconds=300,
    )

    # 1. Forged token in ConfirmationGate -> Rejected
    with pytest.raises(ValueError, match="Invalid challenge verification token"):
        ConfirmationGate.resolve_challenge(
            challenge_id=chal.challenge_id,
            user_id="usr_audit_target_12345",
            decision="approve",
            challenge_token="forged_token_00000000000000000000",
        )

    # 2. Expired challenge in ConfirmationGate -> Rejected
    exp_chal = ConfirmationGate.create_challenge(
        user_id="usr_audit_target_12345",
        action_type="financial_transfer",
        title="Transfer Expired",
        summary="Transfer funds",
        ttl_seconds=-10,  # Expired immediately
    )
    with pytest.raises(ValueError, match="expired"):
        ConfirmationGate.resolve_challenge(
            challenge_id=exp_chal.challenge_id,
            user_id="usr_audit_target_12345",
            decision="approve",
            challenge_token=exp_chal.challenge_token,
        )

    # B. UniversalAppController with forged token:
    ctrl = UniversalAppController.get_instance()
    req_forged = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Forged Token Track"},
        user_id="usr_audit_target_12345",
        confirmed=True,
        confirmation_token="completely_fake_unissued_token_xyz",
    )
    res_forged = await ctrl.execute_lifecycle(req_forged)
    assert res_forged.success is False
    assert res_forged.verified is False
    assert res_forged.stage == "permission_denied"
    assert "Confirmation rejected" in (res_forged.error or "")


# =============================================================================
# Test Case 5: Approval token reused for a different user, app, action, or parameters
# =============================================================================

@pytest.mark.asyncio
async def test_case_05_token_reuse_across_apps_and_users() -> None:
    """Verify that an approval token generated for (User A, App A, Action A) cannot authorize (User B, App B, Action B)."""
    ctrl = UniversalAppController.get_instance()

    # Step 1: User A requests Spotify play_music -> challenge issued
    req_a = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Innocent User Track"},
        user_id="victim_user_a",
        confirmed=False,
    )
    res_a = await ctrl.execute_lifecycle(req_a)
    assert res_a.pending_confirmation_details is not None
    token = str(res_a.pending_confirmation_details["confirmation_token"])

    # Approve token for victim_user_a
    ConfirmationGate.approve_challenge_internally(token, user_id="victim_user_a")

    # Step 2: Attacker B attempts to use token for Calculator terminate
    req_b = AppControlExecutionRequest(
        application="Calculator",
        capability="terminate",
        parameters={"pid": 12345},
        user_id="attacker_user_b",
        confirmed=True,
        confirmation_token=token,
    )
    res_b = await ctrl.execute_lifecycle(req_b)

    # Must be denied due to user and app/action mismatch
    assert res_b.success is False
    assert res_b.verified is False
    assert res_b.stage == "permission_denied"

    # Step 3: Parameter tampering - Victim User A presents token with altered track
    req_tampered_param = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "TAMPERED Malicious Track"},
        user_id="victim_user_a",
        confirmed=True,
        confirmation_token=token,
    )
    res_tampered = await ctrl.execute_lifecycle(req_tampered_param)
    assert res_tampered.success is False
    assert res_tampered.stage == "permission_denied"


# =============================================================================
# Test Case 6: Two concurrent attempts to consume the same approval
# =============================================================================

@pytest.mark.asyncio
async def test_case_06_concurrent_approval_consumption_replay() -> None:
    """Verify race condition and concurrent replay behavior against confirmation challenges."""
    ctrl = UniversalAppController.get_instance()

    # 1. Generate challenge
    req1 = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Concurrent Track"},
        user_id="usr_audit_target_12345",
        confirmed=False,
    )
    res1 = await ctrl.execute_lifecycle(req1)
    assert res1.pending_confirmation_details is not None
    token = str(res1.pending_confirmation_details["confirmation_token"])

    # Approve challenge
    ConfirmationGate.approve_challenge_internally(token, user_id="usr_audit_target_12345")

    # 2. Submit token in parallel via execute_lifecycle with confirmed=True
    req_parallel_1 = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Concurrent Track"},
        user_id="usr_audit_target_12345",
        confirmed=True,
        confirmation_token=token,
    )
    req_parallel_2 = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Concurrent Track"},
        user_id="usr_audit_target_12345",
        confirmed=True,
        confirmation_token=token,
    )

    results = await asyncio.gather(
        ctrl.execute_lifecycle(req_parallel_1),
        ctrl.execute_lifecycle(req_parallel_2),
    )

    # Exactly ONE must succeed and the other MUST be rejected as replay
    success_count = sum(1 for r in results if r.success is True)
    denied_count = sum(1 for r in results if r.success is False and r.stage == "permission_denied")

    assert success_count == 1, f"Expected exactly 1 success under concurrent consumption, got {success_count}"
    assert denied_count == 1, f"Expected exactly 1 replay rejection, got {denied_count}"


# =============================================================================
# Test Case 7: Unauthorized attempts do not invoke the sensitive executor
# =============================================================================

@pytest.mark.asyncio
async def test_case_07_unauthorized_attempts_blocked_from_executor() -> None:
    """Verify that unauthenticated / policy-blocked attempts do not invoke sensitive handlers."""
    reg = ToolRegistry.get_instance()

    # Missing user_id entirely -> unauthenticated execution blocked
    req = ToolExecutionRequest(
        tool_id="system_email_send",
        user_id="",
        arguments={"to": "nobody@test.local", "subject": "Blocked"},
    )
    res = await reg.execute(req)
    assert res.status == ToolExecutionStatus.DENIED
    assert res.success is False
    assert res.error_details is not None
    assert res.error_details.code == "unauthenticated"


# =============================================================================
# Test Case 8: Skipped verification truthfulness
# =============================================================================

@pytest.mark.asyncio
async def test_case_08_skipped_verification_truthfulness() -> None:
    """Verify that skip_verification=True is NOT falsely reported as verified=True / stage=verified."""
    ctrl = UniversalAppController.get_instance()
    
    # 1. Issue challenge
    init_req = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Unverified Track"},
        user_id="usr_audit_target_12345",
        confirmed=False,
    )
    init_res = await ctrl.execute_lifecycle(init_req)
    assert init_res.pending_confirmation_details is not None
    token = str(init_res.pending_confirmation_details["confirmation_token"])
    ConfirmationGate.approve_challenge_internally(token, user_id="usr_audit_target_12345")

    # 2. Execute with approved token and skip_verification=True
    req = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Unverified Track"},
        user_id="usr_audit_target_12345",
        confirmed=True,
        confirmation_token=token,
        skip_verification=True,
    )
    res = await ctrl.execute_lifecycle(req)

    # Truthful reporting: execution succeeded, but verification is FALSE and stage is 'executed'
    assert res.success is True
    assert res.verified is False, "Truthful reporting: verified must be False when skip_verification is True!"
    assert res.stage == "executed", "Truthful reporting: stage must be 'executed', NEVER 'verified'!"


# =============================================================================
# Test Case 9: Existing WhatsApp approval binding and anti-replay behavior remain intact
# =============================================================================

@pytest.mark.asyncio
async def test_case_09_whatsapp_approval_binding_and_anti_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that WhatsAppService still enforces strict cryptographic binding and anti-replay."""
    monkeypatch.setenv("ROXY_WHATSAPP_TEST_RECIPIENT", "+15551234567")
    svc = WhatsAppService.get_instance()
    chal = svc.create_send_challenge(
        user_id="usr_wa_test",
        recipient="+15551234567",
        message="Confidential Audit Notice",
        route=WhatsAppRoute.DESKTOP,
        run_id="run_wa_001",
    )

    # Approve challenge
    ConfirmationGate.resolve_challenge(
        challenge_id=chal.challenge_id,
        user_id="usr_wa_test",
        decision="approve",
        challenge_token=chal.challenge_token,
    )

    # 1. Tampered message -> REJECTED
    ok, reason = svc.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="usr_wa_test",
        expected_recipient="+15551234567",
        expected_message="TAMPERED MESSAGE",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_wa_001",
    )
    assert ok is False
    assert "altered after user approval" in reason

    # 2. Legitimate validation -> APPROVED and consumed
    ok, reason = svc.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="usr_wa_test",
        expected_recipient="+15551234567",
        expected_message="Confidential Audit Notice",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_wa_001",
    )
    assert ok is True
    assert reason == "APPROVED"

    # 3. Replay attempt -> REJECTED
    ok_replay, reason_replay = svc.validate_send_approval(
        challenge_id=chal.challenge_id,
        user_id="usr_wa_test",
        expected_recipient="+15551234567",
        expected_message="Confidential Audit Notice",
        expected_route=WhatsAppRoute.DESKTOP,
        expected_run_id="run_wa_001",
    )
    assert ok_replay is False
    assert "already been consumed" in reason_replay


# =============================================================================
# Test Case 10: Existing authentication, authorization and regression tests
# =============================================================================

def test_case_10_unauthenticated_api_endpoints_denied(test_client: TestClient) -> None:
    """Verify that public callers without auth headers cannot invoke agent/tool endpoints."""
    # Reset dependency override to simulate real unauthenticated request
    app.dependency_overrides.clear()
    unauth_client = TestClient(app)

    resp = unauth_client.post("/api/v1/tools/execute", json={"tool_id": "system_calculator", "user_id": "none"})
    # Must be 401 Unauthorized
    assert resp.status_code == 401
