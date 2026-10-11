"""Tests for Phase 18: Recovery & Self-Correction Engine.

Verifies:
1. ErrorClassifier taxonomy, transience detection, and recommended tier escalation.
2. SelfCorrectionEngine empirical hint generation (window focus, timing delay, selector fallback).
3. Primary Tier 1 API execution success without fallback (SUCCEEDED_PRIMARY).
4. API Auth / 401 failure fast failover to Tier 2 Browser (RECOVERED_BROWSER).
5. API 500 failure -> Browser CAPTCHA block -> fast failover to Tier 3 Desktop (RECOVERED_DESKTOP).
6. Postcondition verification gate catching execution failure and driving self-correction.
7. Exhaustion of all ladder tiers generating comprehensive Root Cause Analysis (FAILED_ALL_TIERS).
8. Deterministic SHA-256 cryptographic proof hash generation and audit integrity.
9. DeviceService ToolRegistry dynamic agent recovery tools registration and execution.
10. FastAPI REST endpoints under /api/v1/devices/{device_id}/recovery/.

Conforms strictly to the Zero Simulation Doctrine.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.recovery_engine import (
    ErrorClassifier,
    RecoveryEngine,
    RecoveryPlaybooks,
    SelfCorrectionEngine,
    get_recovery_engine,
)
from app.device.schemas import (
    APIRouteConfig,
    BrowserRouteConfig,
    CompositeLogic,
    CompositeVerificationRequest,
    DesktopRouteConfig,
    DOMStateVerificationCriteria,
    ErrorCategory,
    ExecuteRecoveryRequest,
    ExecutionTier,
    RecoveryAttemptRecord,
    RecoveryPolicy,
    RecoveryStatus,
    SingleCheckResult,
    VerificationModality,
    VerificationOperator,
)
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_recovery_state() -> Generator[None, None, None]:
    """Ensure in-memory recovery history and tools are reset between test runs."""
    engine = get_recovery_engine()
    engine.clear_history()
    svc = DeviceService.get_instance()
    svc.clear_in_memory_state()
    yield
    engine.clear_history()


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    """Provide authenticated FastAPI TestClient."""
    fake_user = User(
        id="usr_recovery_test",
        email="operator@roxy.ai",
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 1. Error Classifier & Root Cause Taxonomy
# -----------------------------------------------------------------------------


def test_error_classifier_taxonomies() -> None:
    """Verify error classifier maps diverse runtime signals into canonical ErrorCategory."""
    # 1. Auth failure (401 / 403)
    c_401 = ErrorClassifier.classify("Token expired", status_code=401, current_tier=ExecutionTier.API)
    assert c_401.category == ErrorCategory.AUTH_CREDENTIAL_ERROR
    assert c_401.is_transient is False
    assert c_401.recommended_tier == ExecutionTier.BROWSER

    # 2. Rate limit (429)
    c_429 = ErrorClassifier.classify("Too Many Requests", status_code=429, current_tier=ExecutionTier.API)
    assert c_429.category == ErrorCategory.RATE_LIMIT_EXCEEDED
    assert c_429.is_transient is True

    # 3. Not Found (404)
    c_404 = ErrorClassifier.classify("Endpoint gone", status_code=404, current_tier=ExecutionTier.API)
    assert c_404.category == ErrorCategory.RESOURCE_NOT_FOUND
    assert c_404.is_transient is False

    # 4. Server fault (500)
    c_500 = ErrorClassifier.classify("Internal Server Error", status_code=500, current_tier=ExecutionTier.API)
    assert c_500.category == ErrorCategory.SERVER_FAULT
    assert c_500.is_transient is True

    # 5. CAPTCHA / Cloudflare Turnstile in Web Page
    html_captcha = "<html><body><div class='cf-browser-verification'>Please verify you are human</div></body></html>"
    c_captcha = ErrorClassifier.classify("Failed navigation", page_content=html_captcha, current_tier=ExecutionTier.BROWSER)
    assert c_captcha.category == ErrorCategory.CAPTCHA_CHALLENGE
    assert c_captcha.is_transient is False
    assert c_captcha.recommended_tier == ExecutionTier.DESKTOP

    # 6. DOM Element Not Found
    c_dom = ErrorClassifier.classify("Selector '#submit-button' not matched in DOM", current_tier=ExecutionTier.BROWSER)
    assert c_dom.category == ErrorCategory.DOM_ELEMENT_NOT_FOUND
    assert c_dom.is_transient is False
    assert c_dom.recommended_tier == ExecutionTier.DESKTOP

    # 7. Window Not Found
    c_win = ErrorClassifier.classify("Window_not_found: App HWND is 0", current_tier=ExecutionTier.DESKTOP)
    assert c_win.category == ErrorCategory.WINDOW_NOT_FOUND
    assert c_win.is_transient is False

    # 8. Network unreachable
    c_net = ErrorClassifier.classify("Connection refused by remote host", current_tier=ExecutionTier.API)
    assert c_net.category == ErrorCategory.NETWORK_UNREACHABLE
    assert c_net.is_transient is True

    # 9. Window Minimized (Phase 3 Playbook)
    c_min = ErrorClassifier.classify("Window is minimized", current_tier=ExecutionTier.DESKTOP)
    assert c_min.category == ErrorCategory.WINDOW_MINIMIZED
    assert c_min.is_transient is True
    assert c_min.recommended_action is not None and "SW_RESTORE" in c_min.recommended_action

    # 10. Process Unresponsive / Hung (Phase 3 Playbook)
    c_hung = ErrorClassifier.classify("Process is not responding / hung", current_tier=ExecutionTier.DESKTOP)
    assert c_hung.category == ErrorCategory.PROCESS_UNRESPONSIVE
    assert c_hung.is_transient is True


# -----------------------------------------------------------------------------
# 2. Self-Correction Engine Empirical Hint Generation
# -----------------------------------------------------------------------------


def test_self_correction_engine_hints() -> None:
    """Verify concrete parameter and strategy adjustments based on empirical check results."""
    # Case 1: Desktop target window was not in foreground
    chk_foreground = SingleCheckResult(
        modality=VerificationModality.WINDOW_STATE,
        criterion_name="window_state:active",
        passed=False,
        operator_used=VerificationOperator.EXISTS,
        evidence={"is_foreground": False, "target_window": "Spotify"},
        error="Window was backgrounded",
    )
    res_fg = SelfCorrectionEngine.generate_hints(
        failed_tier=ExecutionTier.DESKTOP,
        error_message="Window was backgrounded",
        verification_check=chk_foreground,
    )
    assert res_fg.can_retry_current_tier is True
    assert any(h.suggested_action == "focus_window" for h in res_fg.hints)
    assert res_fg.hints[0].parameter_adjustments.get("force_foreground") is True

    # Case 2: Desktop window non-existent -> hint launch_process
    chk_missing = SingleCheckResult(
        modality=VerificationModality.WINDOW_STATE,
        criterion_name="window_state:target",
        passed=False,
        operator_used=VerificationOperator.EXISTS,
        actual_value="NON_EXISTENT",
        evidence={"target_window": "Calculator"},
        error="Window not found",
    )
    res_launch = SelfCorrectionEngine.generate_hints(
        failed_tier=ExecutionTier.DESKTOP,
        error_message="Window not found",
        verification_check=chk_missing,
    )
    assert res_launch.can_retry_current_tier is True
    assert any(h.suggested_action == "launch_process" for h in res_launch.hints)

    # Case 3: Browser DOM selector missing -> hint use_text_matching
    res_dom = SelfCorrectionEngine.generate_hints(
        failed_tier=ExecutionTier.BROWSER,
        error_message="CSS selector '#btn-send' not found",
    )
    assert any(h.suggested_action == "use_text_matching" for h in res_dom.hints)
    assert res_dom.hints[0].parameter_adjustments.get("fallback_to_inner_text") is True

    # Case 4: Browser CAPTCHA -> escalate directly to desktop
    res_cap = SelfCorrectionEngine.generate_hints(
        failed_tier=ExecutionTier.BROWSER,
        error_message="CAPTCHA challenge detected",
    )
    assert res_cap.can_retry_current_tier is False
    assert res_cap.escalate_to_next_tier is True
    assert any(h.suggested_action == "escalate_desktop" for h in res_cap.hints)

    # Case 5: Desktop window minimized -> hint restore_window with sw_restore
    chk_min = SingleCheckResult(
        modality=VerificationModality.WINDOW_STATE,
        criterion_name="window_state:active",
        passed=False,
        operator_used=VerificationOperator.EXISTS,
        evidence={"is_minimized": True, "target_window": "Calculator"},
        error="Target window is minimized",
    )
    res_min = SelfCorrectionEngine.generate_hints(
        failed_tier=ExecutionTier.DESKTOP,
        error_message="Target window is minimized",
        verification_check=chk_min,
    )
    assert res_min.can_retry_current_tier is True
    assert any(h.suggested_action == "restore_window" for h in res_min.hints)
    assert any(h.parameter_adjustments.get("sw_restore") is True for h in res_min.hints)

    # Case 6: Target process hung/unresponsive -> hint restart_process
    res_hung = SelfCorrectionEngine.generate_hints(
        failed_tier=ExecutionTier.DESKTOP,
        error_message="Process is hung and not responding",
    )
    assert res_hung.can_retry_current_tier is True
    assert any(h.suggested_action == "restart_process" for h in res_hung.hints)
    assert any(h.parameter_adjustments.get("graceful_restart") is True for h in res_hung.hints)

    # Case 7: Desktop UIA resolution failed -> hint ensure_interactive_desktop
    res_uia = SelfCorrectionEngine.generate_hints(
        failed_tier=ExecutionTier.DESKTOP,
        error_message="UIA desktop resolution failed with timeout",
    )
    assert res_uia.can_retry_current_tier is True
    assert any(h.suggested_action == "ensure_interactive_desktop" for h in res_uia.hints)
    assert any(h.parameter_adjustments.get("rebind_desktop") is True for h in res_uia.hints)


# -----------------------------------------------------------------------------
# 2.5 Automated Recovery Playbooks (Phase 3 Hardening)
# -----------------------------------------------------------------------------


def test_automated_recovery_playbooks() -> None:
    """Verify Phase 3 automated recovery playbooks dispatch and execution."""
    # 1. Window restoration playbook (SW_RESTORE)
    with patch("app.device.desktop_automation.DesktopAutomationEngine.restore_window", return_value={"restored": True, "hwnd": 12345}):
        res_win = RecoveryPlaybooks.playbook_restore_minimized_window("Calculator")
        assert res_win["playbook"] == "restore_minimized_window"
        assert res_win["status"] == "restored"
        assert res_win["details"]["hwnd"] == 12345

    # 2. UIA desktop recovery playbook
    with patch("app.device.windows_automation.WindowsUIAutomationEngine.ensure_interactive_desktop", return_value=True):
        res_uia = RecoveryPlaybooks.playbook_recover_uia_desktop()
        assert res_uia["playbook"] == "recover_uia_desktop"
        assert res_uia["reattached"] is True

    # 3. Process restart playbook
    with patch("app.device.process_controller.ProcessLifecycleController.restart", return_value=9999):
        res_proc = RecoveryPlaybooks.playbook_restart_unresponsive_process("notepad.exe")
        assert res_proc["playbook"] == "restart_unresponsive_process"
        assert res_proc["status"] == "restarted"
        assert res_proc["new_pid"] == 9999

    # 4. Dispatch via execute_playbook aliases
    with patch("app.device.desktop_automation.DesktopAutomationEngine.restore_window", return_value={"restored": True}):
        res_disp = RecoveryPlaybooks.execute_playbook("sw_restore", target="Spotify")
        assert res_disp["playbook"] == "restore_minimized_window"

    with patch("app.device.windows_automation.WindowsUIAutomationEngine.ensure_interactive_desktop", return_value=True):
        res_disp_uia = RecoveryPlaybooks.execute_playbook("ensure_interactive_desktop")
        assert res_disp_uia["playbook"] == "recover_uia_desktop"

    # 5. Dispatch via RecoveryEngine instance
    with patch("app.device.windows_automation.WindowsUIAutomationEngine.ensure_interactive_desktop", return_value=True):
        engine = get_recovery_engine()
        res_eng = engine.execute_playbook("recover_uia_desktop")
        assert res_eng["playbook"] == "recover_uia_desktop"

    # 6. Unknown playbook raises ValueError
    with pytest.raises(ValueError, match="Unknown recovery playbook"):
        RecoveryPlaybooks.execute_playbook("non_existent_playbook")


# -----------------------------------------------------------------------------
# 3. Tier 1 API Success (No Fallback Needed)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier1_api_success_no_fallback() -> None:
    """Verify fast path: Tier 1 Direct API succeeds on first attempt."""
    engine = get_recovery_engine()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "created", "id": "job_99"}, headers={"Content-Type": "application/json"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        req = ExecuteRecoveryRequest(
            action_name="create_remote_job",
            api_route=APIRouteConfig(
                endpoint_url="https://api.internal/v1/jobs",
                method="POST",
                body={"name": "test_job"},
                expected_status_code=200,
            ),
            browser_route=BrowserRouteConfig(
                target_url="https://app.internal/jobs/new",
            ),
            desktop_route=DesktopRouteConfig(
                app_name="JobClient",
            ),
        )

        res = await engine.execute_recovery(req, custom_client=client)
        assert res.passed is True
        assert res.status == RecoveryStatus.SUCCEEDED_PRIMARY
        assert res.resolved_tier == ExecutionTier.API
        assert res.total_attempts == 1
        assert len(res.tier_attempts) == 1
        assert res.tier_attempts[0].passed is True
        assert len(res.recovery_proof_hash) == 64


# -----------------------------------------------------------------------------
# 4. API 401 Auth Failure -> Fast Failover to Tier 2 Browser
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier1_api_failover_to_tier2_browser() -> None:
    """Verify Tier 1 API 401 Auth error triggers immediate failover to Tier 2 Browser route."""
    engine = get_recovery_engine()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "api.internal" in url_str:
            # API endpoint rejects expired token
            return httpx.Response(401, json={"error": "Unauthorized: Token Expired"})
        elif "web.internal" in url_str:
            # Web portal loads successfully with user session
            return httpx.Response(
                200,
                text="<html><body><h1>Dashboard</h1><div id='job-status'>Job Created Successfully</div></body></html>",
                headers={"Content-Type": "text/html"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        req = ExecuteRecoveryRequest(
            action_name="submit_report",
            api_route=APIRouteConfig(
                endpoint_url="https://api.internal/submit",
                method="POST",
                expected_status_code=200,
            ),
            browser_route=BrowserRouteConfig(
                target_url="https://web.internal/submit",
                expected_success_text="Job Created Successfully",
            ),
            desktop_route=DesktopRouteConfig(
                app_name="ReportDesktopApp",
            ),
            policy=RecoveryPolicy(
                fast_failover_on_auth_error=True,
                max_retries_per_tier=1,
            ),
        )

        res = await engine.execute_recovery(req, custom_client=client)
        assert res.passed is True
        assert res.status == RecoveryStatus.RECOVERED_BROWSER
        assert res.resolved_tier == ExecutionTier.BROWSER
        assert res.total_attempts == 2
        # Attempt 1: API failed with AUTH_CREDENTIAL_ERROR
        assert res.tier_attempts[0].tier == ExecutionTier.API
        assert res.tier_attempts[0].passed is False
        assert res.tier_attempts[0].error_category == ErrorCategory.AUTH_CREDENTIAL_ERROR
        # Attempt 2: Browser passed
        assert res.tier_attempts[1].tier == ExecutionTier.BROWSER
        assert res.tier_attempts[1].passed is True


# -----------------------------------------------------------------------------
# 5. API Failure -> Browser CAPTCHA -> Failover to Tier 3 Desktop
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier1_api_fail_tier2_captcha_failover_to_tier3_desktop() -> None:
    """Verify deep fallback: API 500 + Browser CAPTCHA -> Native Desktop Automation executes successfully."""
    engine = get_recovery_engine()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "api.service" in url_str:
            return httpx.Response(500, text="Internal Server Error")
        elif "web.service" in url_str:
            # Cloudflare bot challenge page
            return httpx.Response(
                403,
                text="<html><body><div class='cf-browser-verification'>Security Check: Please verify you are human</div></body></html>",
                headers={"Content-Type": "text/html"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        req = ExecuteRecoveryRequest(
            action_name="send_instant_message",
            api_route=APIRouteConfig(
                endpoint_url="https://api.service/messages/send",
                expected_status_code=200,
            ),
            browser_route=BrowserRouteConfig(
                target_url="https://web.service/chat",
            ),
            desktop_route=DesktopRouteConfig(
                app_name="Slack",
                target_window="Slack - Workspace",
                focus_window=True,
                ui_actions=[
                    {"action": "click", "name": "Message Input"},
                    {"action": "type", "text": "Deployment complete!"},
                    {"action": "hotkey", "hotkey": "enter"},
                ],
            ),
            policy=RecoveryPolicy(
                fast_failover_on_captcha=True,
                max_retries_per_tier=0,
            ),
        )

        with (
            patch("app.device.desktop_automation.DesktopAutomationEngine.click_element", return_value={"clicked": True}),
            patch("app.device.desktop_automation.DesktopAutomationEngine.type_text", return_value={"typed": True}),
            patch("app.device.desktop_automation.DesktopAutomationEngine.send_hotkey", return_value={"hotkey": True}),
            patch("app.device.process_controller.ProcessLifecycleController.focus", return_value=True),
        ):
            res = await engine.execute_recovery(req, custom_client=client)

        assert res.passed is True
        assert res.status == RecoveryStatus.RECOVERED_DESKTOP
        assert res.resolved_tier == ExecutionTier.DESKTOP
        assert res.total_attempts == 3

        # Attempt 1: API 500 Server Fault
        assert res.tier_attempts[0].tier == ExecutionTier.API
        assert res.tier_attempts[0].passed is False
        assert res.tier_attempts[0].error_category == ErrorCategory.SERVER_FAULT

        # Attempt 2: Browser CAPTCHA challenge
        assert res.tier_attempts[1].tier == ExecutionTier.BROWSER
        assert res.tier_attempts[1].passed is False
        assert res.tier_attempts[1].error_category == ErrorCategory.CAPTCHA_CHALLENGE

        # Attempt 3: Desktop automation succeeded
        assert res.tier_attempts[2].tier == ExecutionTier.DESKTOP
        assert res.tier_attempts[2].passed is True


# -----------------------------------------------------------------------------
# 6. Postcondition Verification Gate & Self-Correction Loop
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_with_verification_gate_and_self_correction() -> None:
    """Verify execution succeeds but postcondition verification fails, triggering self-correction to next tier."""
    engine = get_recovery_engine()
    browser_navigated = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal browser_navigated
        url_str = str(request.url)
        if "api.service/start" in url_str:
            # API returns 200 OK, but silent backend failure (task didn't start)
            return httpx.Response(200, json={"ack": True})
        elif "web.service/trigger" in url_str:
            # Browser route navigates to trigger url
            browser_navigated = True
            return httpx.Response(200, text="<html><body>Task Triggered</body></html>", headers={"Content-Type": "text/html"})
        elif "web.service/status" in url_str:
            if not browser_navigated:
                return httpx.Response(
                    200,
                    text='<html><body><div id="task-badge">Task Active: False</div></body></html>',
                    headers={"Content-Type": "text/html"},
                )
            else:
                return httpx.Response(
                    200,
                    text='<html><body><div id="task-badge">Task Active: True</div></body></html>',
                    headers={"Content-Type": "text/html"},
                )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # Verification criteria: DOM element must contain 'Task Active: True'
        verif_req = CompositeVerificationRequest(
            action_name="verify_active_task",
            logic=CompositeLogic.ALL_OF,
            timeout_sec=0.2,
            poll_interval_sec=0.05,
            dom_criteria=[
                DOMStateVerificationCriteria(
                    page_url_pattern="https://web.service/status",
                    selector="task-badge",
                    expected_text="Task Active: True",
                )
            ],
        )

        req = ExecuteRecoveryRequest(
            action_name="start_task",
            api_route=APIRouteConfig(
                endpoint_url="https://api.service/start",
                expected_status_code=200,
            ),
            browser_route=BrowserRouteConfig(
                target_url="https://web.service/trigger",
                expected_success_text="Task Triggered",
            ),
            policy=RecoveryPolicy(
                fallback_ladder=[ExecutionTier.API, ExecutionTier.BROWSER],
                max_retries_per_tier=0,
                require_postcondition_verification=True,
            ),
            verification_criteria=verif_req,
        )

        # In this scenario, API executes OK but postcondition is verified against web.service (fails) -> recovers on Browser!
        res = await engine.execute_recovery(req, custom_client=client)
        assert res.passed is True
        assert res.status == RecoveryStatus.RECOVERED_BROWSER
        assert res.resolved_tier == ExecutionTier.BROWSER
        assert res.total_attempts == 2
        assert res.tier_attempts[0].passed is False
        assert res.tier_attempts[0].error_category == ErrorCategory.POSTCONDITION_FAILED
        assert res.tier_attempts[1].passed is True
        assert res.verification_result is not None
        assert res.verification_result.passed is True


# -----------------------------------------------------------------------------
# 7. Exhaustion of All Tiers Produces Comprehensive RCA
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_failed_all_tiers_rca() -> None:
    """Verify that when all tiers fail, FAILED_ALL_TIERS status and comprehensive RCA are generated."""
    engine = get_recovery_engine()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "api.fail" in url_str:
            return httpx.Response(500, text="Internal DB Crash")
        elif "web.fail" in url_str:
            return httpx.Response(404, text="Page Not Found")
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        req = ExecuteRecoveryRequest(
            action_name="unachievable_goal",
            api_route=APIRouteConfig(endpoint_url="https://api.fail/act"),
            browser_route=BrowserRouteConfig(target_url="https://web.fail/act"),
            desktop_route=DesktopRouteConfig(
                app_name="NonExistentApp",
                target_window="NonExistentWindow",
                ui_actions=[{"action": "click", "name": "MissingButton"}],
            ),
            policy=RecoveryPolicy(
                fallback_ladder=[ExecutionTier.API, ExecutionTier.BROWSER, ExecutionTier.DESKTOP],
                max_retries_per_tier=0,
            ),
        )

        with patch("app.device.desktop_automation.DesktopAutomationEngine.click_element", side_effect=RuntimeError("Desktop control failed")):
            res = await engine.execute_recovery(req, custom_client=client)

        assert res.passed is False
        assert res.status == RecoveryStatus.FAILED_ALL_TIERS
        assert res.resolved_tier is None
        assert res.total_attempts == 3
        assert res.root_cause_analysis is not None
        assert "[API]" in res.root_cause_analysis
        assert "[BROWSER]" in res.root_cause_analysis
        assert "[DESKTOP]" in res.root_cause_analysis


# -----------------------------------------------------------------------------
# 8. Cryptographic Proof Hash Integrity & Tamper Evidence
# -----------------------------------------------------------------------------


def test_cryptographic_proof_hash_integrity() -> None:
    """Verify cryptographic proof hash is deterministic and tamper-evident."""
    attempt = RecoveryAttemptRecord(
        attempt_number=1,
        tier=ExecutionTier.API,
        passed=True,
        error_category=None,
        error_message=None,
        latency_ms=45.2,
        correction_applied=None,
        evidence={"status": 200},
        timestamp="2026-10-04T12:00:00Z",
    )

    hash1 = RecoveryEngine._generate_proof_hash(
        recovery_id="rec_101",
        action_name="post_status",
        status=RecoveryStatus.SUCCEEDED_PRIMARY,
        resolved_tier=ExecutionTier.API,
        completed_at="2026-10-04T12:00:01Z",
        attempts=[attempt],
    )
    hash2 = RecoveryEngine._generate_proof_hash(
        recovery_id="rec_101",
        action_name="post_status",
        status=RecoveryStatus.SUCCEEDED_PRIMARY,
        resolved_tier=ExecutionTier.API,
        completed_at="2026-10-04T12:00:01Z",
        attempts=[attempt],
    )
    assert hash1 == hash2
    assert len(hash1) == 64

    # Tampered status alters hash
    hash_tampered = RecoveryEngine._generate_proof_hash(
        recovery_id="rec_101",
        action_name="post_status",
        status=RecoveryStatus.FAILED_ALL_TIERS,
        resolved_tier=None,
        completed_at="2026-10-04T12:00:01Z",
        attempts=[attempt],
    )
    assert hash1 != hash_tampered


# -----------------------------------------------------------------------------
# 9. DeviceService ToolRegistry Dynamic Recovery Tools Execution
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_device_service_recovery_tools() -> None:
    """Verify all 4 Phase 18 recovery agent tools in ToolRegistry."""
    registry = ToolRegistry.get_instance()

    # Tool 1: recovery_classify_error
    handler_cls = registry.get_handler("recovery_classify_error")
    assert handler_cls is not None
    res_cls = await handler_cls(error_message="Unauthorized access", status_code=401)
    assert res_cls["category"] == "auth_credential_error"
    assert res_cls["is_transient"] is False

    # Tool 2: recovery_suggest_correction
    handler_sug = registry.get_handler("recovery_suggest_correction")
    assert handler_sug is not None
    res_sug = await handler_sug(failed_tier="desktop", error_message="Window was backgrounded")
    assert "hints" in res_sug
    assert len(res_sug["hints"]) >= 1

    # Tool 3: recovery_execute_with_fallback
    handler_exec = registry.get_handler("recovery_execute_with_fallback")
    assert handler_exec is not None
    res_exec = await handler_exec(
        action_name="test_tool_action",
        desktop_route={"app_name": "TestApp", "ui_actions": []},
    )
    assert "status" in res_exec
    assert "recovery_proof_hash" in res_exec

    # Tool 4: recovery_get_history
    handler_hist = registry.get_handler("recovery_get_history")
    assert handler_hist is not None
    res_hist = await handler_hist(limit=10)
    assert res_hist["total_records"] >= 1


# -----------------------------------------------------------------------------
# 10. FastAPI Recovery REST Endpoints
# -----------------------------------------------------------------------------


def test_api_recovery_endpoints(auth_client: TestClient) -> None:
    """Verify all FastAPI REST endpoints under /api/v1/devices/{device_id}/recovery/."""
    device_id = "dev_rec_p18"

    # 1. POST /classify
    resp_cls = auth_client.post(
        f"/api/v1/devices/{device_id}/recovery/classify",
        json={"error_message": "Rate limit exceeded (429)", "status_code": 429},
    )
    assert resp_cls.status_code == 200
    assert resp_cls.json()["category"] == "rate_limit_exceeded"
    assert resp_cls.json()["is_transient"] is True

    # 2. POST /self-correct
    resp_sug = auth_client.post(
        f"/api/v1/devices/{device_id}/recovery/self-correct",
        json={"failed_tier": "browser", "error_message": "CSS selector '#missing' not found"},
    )
    assert resp_sug.status_code == 200
    assert len(resp_sug.json()["hints"]) >= 1

    # 3. POST /execute
    resp_exec = auth_client.post(
        f"/api/v1/devices/{device_id}/recovery/execute",
        json={
            "action_name": "rest_recovery_test",
            "desktop_route": {"app_name": "Calculator", "ui_actions": []},
            "policy": {"fallback_ladder": ["desktop"]},
        },
    )
    assert resp_exec.status_code == 200
    exec_data = resp_exec.json()
    assert exec_data["passed"] is True
    assert exec_data["status"] == "recovered_desktop"
    assert "recovery_proof_hash" in exec_data

    # 4. GET /history
    resp_hist = auth_client.get(f"/api/v1/devices/{device_id}/recovery/history")
    assert resp_hist.status_code == 200
    hist_data = resp_hist.json()
    assert hist_data["total_records"] >= 1
    assert any(r["recovery_id"] == exec_data["recovery_id"] for r in hist_data["records"])
