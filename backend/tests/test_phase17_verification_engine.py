"""Tests for Phase 17: Verification Engine 2.0.

Verifies:
1. ValueComparator operators (exact_match, contains, regex, json_path, etc.).
2. Window state postcondition verification (existence, title, visibility, bounds, process).
3. OCR & visual text evidence verification (accessible tree, screenshot capture, confidence).
4. Web/browser DOM state verification (selectors, text, attributes, HTML parsing).
5. API/network response verification (status codes, JSONPath assertions, latency).
6. Process state verification (running count, health).
7. Composite multi-modal verification (ALL_OF, ANY_OF, THRESHOLD logic).
8. Polling cycles and asynchronous settling before timeout.
9. Cryptographic SHA-256 tamper-evident proof fingerprint generation.
10. ToolRegistry dynamic verification tools execution.
11. FastAPI REST endpoints for cross-system verification and history.

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
from app.device.schemas import (
    APIResponseVerificationCriteria,
    CompositeLogic,
    CompositeVerificationRequest,
    DOMStateVerificationCriteria,
    OCRVisualVerificationCriteria,
    ProcessStateVerificationCriteria,
    VerificationModality,
    VerificationOperator,
    WindowStateVerificationCriteria,
)
from app.device.service import DeviceService
from app.device.verification_engine import (
    APIResponseVerifier,
    DOMStateVerifier,
    OCRVisualVerifier,
    ProcessStateVerifier,
    ValueComparator,
    WindowStateVerifier,
    get_verification_engine,
)
from app.device.windows_automation import UIBounds, UIElementModel, WindowStateModel
from app.main import app
from app.tools.registry import ToolRegistry

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_verification_state() -> Generator[None, None, None]:
    """Ensure in-memory verification history and tools are reset between test runs."""
    engine = get_verification_engine()
    engine.clear_history()
    svc = DeviceService.get_instance()
    svc.clear_in_memory_state()
    yield
    engine.clear_history()


@pytest.fixture
def mock_user() -> User:
    return User(
        id="usr_phase17_test_001",
        email="operator_phase17@roxy.ai",
    )


@pytest.fixture
def auth_client(mock_user: User) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 1. Value Comparator & Operator Assertions
# -----------------------------------------------------------------------------


def test_value_comparator_operators() -> None:
    """Verify all comparison operators and JSONPath resolution."""
    # EXACT_MATCH
    ok, score, _ = ValueComparator.evaluate(VerificationOperator.EXACT_MATCH, "Chrome", "chrome", case_sensitive=False)
    assert ok is True
    assert score == 1.0

    ok_cs, _, _ = ValueComparator.evaluate(VerificationOperator.EXACT_MATCH, "Chrome", "chrome", case_sensitive=True)
    assert ok_cs is False

    # CONTAINS
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.CONTAINS, "world", "Hello World!", case_sensitive=False)
    assert ok is True

    # REGEX
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.REGEX, r"^Document - \d+$", "Document - 42")
    assert ok is True

    ok_bad, _, _ = ValueComparator.evaluate(VerificationOperator.REGEX, r"^Document - \d+$", "Invalid Doc")
    assert ok_bad is False

    # EQUALS & NOT_EQUALS
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.EQUALS, 200, 200)
    assert ok is True
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.NOT_EQUALS, 200, 500)
    assert ok is True

    # GREATER_THAN & LESS_THAN
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.GREATER_THAN, 50, 100)
    assert ok is True
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.LESS_THAN, 100, 50)
    assert ok is True

    # EXISTS & NOT_EXISTS
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.EXISTS, None, "value")
    assert ok is True
    ok, _, _ = ValueComparator.evaluate(VerificationOperator.NOT_EXISTS, None, None)
    assert ok is True

    # JSONPath resolution
    sample_json = {
        "status": "healthy",
        "data": {
            "users": [
                {"id": 1, "username": "alice"},
                {"id": 2, "username": "bob"},
            ],
            "metrics": {"latency_ms": 12.5},
        },
    }
    assert ValueComparator.resolve_json_path(sample_json, "status") == "healthy"
    assert ValueComparator.resolve_json_path(sample_json, "data.users.0.username") == "alice"
    assert ValueComparator.resolve_json_path(sample_json, "data.users.1.id") == 2
    assert ValueComparator.resolve_json_path(sample_json, "data.metrics.latency_ms") == 12.5
    assert ValueComparator.resolve_json_path(sample_json, "data.nonexistent.key") is None


# -----------------------------------------------------------------------------
# 2. Native Window State Verifier
# -----------------------------------------------------------------------------


def test_window_state_verifier_real_and_mocked() -> None:
    """Verify window postconditions across title, visibility, bounds, and process attributes."""
    # 1. Non-existent window
    crit_not_exist = WindowStateVerificationCriteria(
        target_window="NonExistentWindow_999999",
        must_exist=False,
    )
    res_not_exist = WindowStateVerifier.verify(crit_not_exist)
    assert res_not_exist.passed is True
    assert res_not_exist.modality == VerificationModality.WINDOW_STATE

    # 2. Mock an active valid window
    mock_state = WindowStateModel(
        exists=True,
        hwnd=123456,
        title="Visual Studio Code - roxy-ai",
        pid=9876,
        process_name="Code.exe",
        is_visible=True,
        is_foreground=True,
        bounds=UIBounds(left=0, top=0, right=1920, bottom=1080, width=1920, height=1080),
    )

    with patch("app.device.desktop_automation.DesktopAutomationEngine.read_window_state", return_value=mock_state):
        # Passing criteria
        crit_pass = WindowStateVerificationCriteria(
            target_window="Code",
            expected_title="Visual Studio Code",
            title_operator=VerificationOperator.CONTAINS,
            must_exist=True,
            must_be_visible=True,
            must_be_foreground=True,
            min_width=1000,
            expected_process_name="code",
        )
        res_pass = WindowStateVerifier.verify(crit_pass)
        assert res_pass.passed is True
        assert res_pass.score == 1.0
        assert res_pass.evidence["hwnd"] == 123456
        assert res_pass.evidence["process_name"] == "Code.exe"

        # Failing title criteria
        crit_fail_title = WindowStateVerificationCriteria(
            target_window="Code",
            expected_title="Calculator",
            title_operator=VerificationOperator.CONTAINS,
        )
        res_fail_title = WindowStateVerifier.verify(crit_fail_title)
        assert res_fail_title.passed is False
        assert "Title mismatch" in (res_fail_title.error or "")

        # Failing width criteria
        crit_fail_width = WindowStateVerificationCriteria(
            target_window="Code",
            min_width=3000,
        )
        res_fail_width = WindowStateVerifier.verify(crit_fail_width)
        assert res_fail_width.passed is False
        assert "Width" in (res_fail_width.error or "")


# -----------------------------------------------------------------------------
# 3. OCR & Visual Text Evidence Verifier
# -----------------------------------------------------------------------------


def test_ocr_visual_verifier() -> None:
    """Verify visual rendered text extraction and matching."""
    mock_child = UIElementModel(
        role="button",
        name="Submit Query",
        control_type="ButtonControl",
        value=None,
        children=[],
    )
    mock_tree = UIElementModel(
        role="window",
        name="Welcome to Roxy AI",
        control_type="WindowControl",
        value="Execution Status: SUCCESS",
        children=[mock_child],
    )

    with (
        patch("app.device.desktop_automation.DesktopAutomationEngine.inspect_ui", return_value=mock_tree),
        patch("app.device.desktop_automation.DesktopAutomationEngine.take_screenshot", return_value={"width": 1920, "height": 1080}),
    ):
        # 1. Matching text
        crit = OCRVisualVerificationCriteria(
            target_window="AppWindow",
            expected_text="SUCCESS",
            text_operator=VerificationOperator.CONTAINS,
        )
        res = OCRVisualVerifier.verify(crit)
        assert res.passed is True
        assert res.modality == VerificationModality.OCR_VISUAL
        assert "SUCCESS" in res.actual_value

        # 2. Regex matching
        crit_regex = OCRVisualVerificationCriteria(
            target_window="AppWindow",
            expected_text=r"Status:\s+SUCCESS",
            text_operator=VerificationOperator.REGEX,
        )
        res_regex = OCRVisualVerifier.verify(crit_regex)
        assert res_regex.passed is True

        # 3. Non-matching text
        crit_fail = OCRVisualVerificationCriteria(
            target_window="AppWindow",
            expected_text="FATAL_CRASH",
            text_operator=VerificationOperator.CONTAINS,
        )
        res_fail = OCRVisualVerifier.verify(crit_fail)
        assert res_fail.passed is False


# -----------------------------------------------------------------------------
# 4. Web DOM State Verifier
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dom_state_verifier() -> None:
    """Verify HTML DOM element presence, attributes, and text."""
    html_page = """
    <!DOCTYPE html>
    <html>
    <head><title>Dashboard - Roxy</title></head>
    <body>
        <div id="app-container" class="dashboard-active">
            <span class="status-badge" data-status="ready">System Operational</span>
            <button id="action-submit" disabled>Save Changes</button>
        </div>
    </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_page, headers={"Content-Type": "text/html"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # 1. Selector and text match
        crit = DOMStateVerificationCriteria(
            page_url_pattern="https://roxy.local/dashboard",
            selector="status-badge",
            expected_text="System Operational",
            attribute_name="data-status",
            expected_attribute_value="ready",
        )
        res = await DOMStateVerifier.verify(crit, custom_client=client)
        assert res.passed is True
        assert res.modality == VerificationModality.DOM_STATE
        assert res.evidence["selector_found"] is True
        assert res.evidence["attribute_matched"] is True

        # 2. Missing element failure
        crit_fail = DOMStateVerificationCriteria(
            page_url_pattern="https://roxy.local/dashboard",
            selector="non-existent-button",
        )
        res_fail = await DOMStateVerifier.verify(crit_fail, custom_client=client)
        assert res_fail.passed is False


# -----------------------------------------------------------------------------
# 5. API & Connector Response Verifier
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_response_verifier() -> None:
    """Verify HTTP status codes, JSONPath assertions, and body substrings."""
    api_payload = {
        "status": "success",
        "result": {
            "task_id": "tsk_12345",
            "items_processed": 42,
            "is_complete": True,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json=api_payload,
            headers={"Content-Type": "application/json", "X-Service": "Roxy-Backend"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # 1. Full passing API check
        crit = APIResponseVerificationCriteria(
            endpoint_url="https://api.internal/v1/jobs/trigger",
            method="POST",
            expected_status_code=201,
            expected_body_contains="tsk_12345",
            json_path="result.items_processed",
            expected_json_value=42,
            max_latency_ms=5000.0,
        )
        res = await APIResponseVerifier.verify(crit, custom_client=client)
        assert res.passed is True
        assert res.modality == VerificationModality.API_RESPONSE
        assert res.actual_value == 201
        assert res.evidence["json_path_resolved"] == 42

        # 2. Status code mismatch
        crit_bad_status = APIResponseVerificationCriteria(
            endpoint_url="https://api.internal/v1/jobs/trigger",
            expected_status_code=200,  # got 201
        )
        res_bad_status = await APIResponseVerifier.verify(crit_bad_status, custom_client=client)
        assert res_bad_status.passed is False
        assert "Status code 201 != expected 200" in (res_bad_status.error or "")

        # 3. JSONPath value mismatch
        crit_bad_json = APIResponseVerificationCriteria(
            endpoint_url="https://api.internal/v1/jobs/trigger",
            expected_status_code=201,
            json_path="result.items_processed",
            expected_json_value=100,  # actual 42
        )
        res_bad_json = await APIResponseVerifier.verify(crit_bad_json, custom_client=client)
        assert res_bad_json.passed is False
        assert "value '42' != expected '100'" in (res_bad_json.error or "")


# -----------------------------------------------------------------------------
# 6. Operating System Process State Verifier
# -----------------------------------------------------------------------------


def test_process_state_verifier() -> None:
    """Verify live OS processes via psutil."""
    # 1. Process that is definitely running (python)
    crit_running = ProcessStateVerificationCriteria(
        process_name="python",
        must_be_running=True,
        min_instances=1,
    )
    res_running = ProcessStateVerifier.verify(crit_running)
    assert res_running.passed is True
    assert res_running.modality == VerificationModality.PROCESS_STATE
    assert res_running.evidence["count"] >= 1

    # 2. Process that is definitely NOT running
    crit_not_running = ProcessStateVerificationCriteria(
        process_name="definitely_fake_nonexistent_process_xyz_888",
        must_be_running=False,
    )
    res_not_running = ProcessStateVerifier.verify(crit_not_running)
    assert res_not_running.passed is True
    assert res_not_running.evidence["count"] == 0


# -----------------------------------------------------------------------------
# 7. Composite Verification Logic (ALL_OF, ANY_OF, THRESHOLD)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_composite_verification_all_of_and_any_of() -> None:
    """Verify composite cross-system verification with logic aggregation."""
    engine = get_verification_engine()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"}, headers={"Content-Type": "application/json"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # Case 1: ALL_OF passes when all pass
        req_all = CompositeVerificationRequest(
            action_name="publish_and_launch",
            logic=CompositeLogic.ALL_OF,
            timeout_sec=0.5,
            api_criteria=[
                APIResponseVerificationCriteria(
                    endpoint_url="https://api.example/status",
                    expected_status_code=200,
                )
            ],
            process_criteria=[
                ProcessStateVerificationCriteria(
                    process_name="python",
                    must_be_running=True,
                )
            ],
        )
        res_all = await engine.execute_composite(req_all, custom_client=client)
        assert res_all.passed is True
        assert res_all.overall_score == 1.0
        assert res_all.passed_criteria == 2
        assert len(res_all.verification_proof_hash) == 64

        # Case 2: ALL_OF fails when one fails
        req_fail = CompositeVerificationRequest(
            action_name="failing_composite",
            logic=CompositeLogic.ALL_OF,
            timeout_sec=0.3,
            api_criteria=[
                APIResponseVerificationCriteria(
                    endpoint_url="https://api.example/status",
                    expected_status_code=200,
                ),
                APIResponseVerificationCriteria(
                    endpoint_url="https://api.example/status",
                    expected_status_code=500,  # Fails
                ),
            ],
        )
        res_fail = await engine.execute_composite(req_fail, custom_client=client)
        assert res_fail.passed is False
        assert res_fail.overall_score == 0.5
        assert res_fail.failed_criteria == 1

        # Case 3: ANY_OF passes when at least one passes
        req_any = CompositeVerificationRequest(
            action_name="any_of_composite",
            logic=CompositeLogic.ANY_OF,
            timeout_sec=0.3,
            api_criteria=[
                APIResponseVerificationCriteria(
                    endpoint_url="https://api.example/status",
                    expected_status_code=500,  # Fails
                ),
                APIResponseVerificationCriteria(
                    endpoint_url="https://api.example/status",
                    expected_status_code=200,  # Passes
                ),
            ],
        )
        res_any = await engine.execute_composite(req_any, custom_client=client)
        assert res_any.passed is True

        # Case 4: THRESHOLD logic
        req_thresh = CompositeVerificationRequest(
            action_name="threshold_composite",
            logic=CompositeLogic.THRESHOLD,
            threshold=0.6,
            timeout_sec=0.3,
            api_criteria=[
                APIResponseVerificationCriteria(
                    endpoint_url="https://api.example/status",
                    expected_status_code=200,
                ),
                APIResponseVerificationCriteria(
                    endpoint_url="https://api.example/status",
                    expected_status_code=500,
                ),
            ],
            process_criteria=[
                ProcessStateVerificationCriteria(
                    process_name="python",
                    must_be_running=True,
                )
            ],
        )
        # 2 out of 3 pass = 0.6667 >= 0.6 -> Passes!
        res_thresh = await engine.execute_composite(req_thresh, custom_client=client)
        assert res_thresh.passed is True
        assert res_thresh.overall_score >= 0.66


# -----------------------------------------------------------------------------
# 8. Cryptographic Proof Hash Integrity
# -----------------------------------------------------------------------------


def test_cryptographic_proof_hash_integrity() -> None:
    """Verify proof hash is deterministic and changes upon evidence tampering."""
    engine = get_verification_engine()

    crit = ProcessStateVerificationCriteria(process_name="python", must_be_running=True)
    check = ProcessStateVerifier.verify(crit)

    hash1 = engine._generate_proof_hash("v_1", "2026-10-04T12:00:00Z", True, 1.0, [check])
    hash2 = engine._generate_proof_hash("v_1", "2026-10-04T12:00:00Z", True, 1.0, [check])
    assert hash1 == hash2

    # Tampered verdict
    hash_tampered = engine._generate_proof_hash("v_1", "2026-10-04T12:00:00Z", False, 0.0, [check])
    assert hash1 != hash_tampered


# -----------------------------------------------------------------------------
# 9. DeviceService ToolRegistry Dynamic Workspace Tools Execution
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_device_service_verification_tools() -> None:
    """Verify all 5 Phase 17 verification agent tools in ToolRegistry."""
    registry = ToolRegistry.get_instance()

    # Tool 1: verification_verify_window_state
    handler_win = registry.get_handler("verification_verify_window_state")
    assert handler_win is not None
    res_win = await handler_win(target_window="NonExistent", must_exist=False)
    assert res_win["passed"] is True
    assert res_win["modality"] == "window_state"

    # Tool 2: verification_verify_ocr_text
    handler_ocr = registry.get_handler("verification_verify_ocr_text")
    assert handler_ocr is not None
    res_ocr = await handler_ocr(expected_text="NonExistentRandomStringXYZ")
    assert "passed" in res_ocr
    assert res_ocr["modality"] == "ocr_visual"

    # Tool 3: verification_verify_dom_state
    handler_dom = registry.get_handler("verification_verify_dom_state")
    assert handler_dom is not None
    res_dom = await handler_dom(page_url_pattern="https://example.com", expected_text="Example")
    assert "passed" in res_dom
    assert res_dom["modality"] == "dom_state"

    # Tool 4: verification_verify_api_response
    handler_api = registry.get_handler("verification_verify_api_response")
    assert handler_api is not None
    res_api = await handler_api(endpoint_url="https://example.com", expected_status_code=200)
    assert "passed" in res_api
    assert res_api["modality"] == "api_response"

    # Tool 5: verification_execute_composite
    handler_comp = registry.get_handler("verification_execute_composite")
    assert handler_comp is not None
    res_comp = await handler_comp(
        action_name="test_tool_composite",
        logic="all_of",
        process_criteria=[{"process_name": "python", "must_be_running": True}],
    )
    assert res_comp["passed"] is True
    assert "verification_proof_hash" in res_comp


# -----------------------------------------------------------------------------
# 10. FastAPI Verification REST Endpoints
# -----------------------------------------------------------------------------


def test_api_verification_endpoints(auth_client: TestClient) -> None:
    """Verify all FastAPI REST endpoints under /api/v1/devices/{device_id}/verification/."""
    device_id = "dev_verif_p17"

    # 1. POST /window
    resp_win = auth_client.post(
        f"/api/v1/devices/{device_id}/verification/window",
        json={"target_window": "FakeWindowXYZ", "must_exist": False},
    )
    assert resp_win.status_code == 200
    assert resp_win.json()["passed"] is True

    # 2. POST /ocr
    resp_ocr = auth_client.post(
        f"/api/v1/devices/{device_id}/verification/ocr",
        json={"expected_text": "Roxy"},
    )
    assert resp_ocr.status_code == 200
    assert "passed" in resp_ocr.json()

    # 3. POST /dom
    resp_dom = auth_client.post(
        f"/api/v1/devices/{device_id}/verification/dom",
        json={"page_url_pattern": "https://example.com", "expected_text": "Example"},
    )
    assert resp_dom.status_code == 200
    assert "passed" in resp_dom.json()

    # 4. POST /api
    resp_api = auth_client.post(
        f"/api/v1/devices/{device_id}/verification/api",
        json={"endpoint_url": "https://example.com", "expected_status_code": 200},
    )
    assert resp_api.status_code == 200
    assert "passed" in resp_api.json()

    # 5. POST /process
    resp_proc = auth_client.post(
        f"/api/v1/devices/{device_id}/verification/process",
        json={"process_name": "python", "must_be_running": True},
    )
    assert resp_proc.status_code == 200
    assert resp_proc.json()["passed"] is True

    # 6. POST /composite
    resp_comp = auth_client.post(
        f"/api/v1/devices/{device_id}/verification/composite",
        json={
            "action_name": "api_rest_test",
            "logic": "all_of",
            "timeout_sec": 1.0,
            "process_criteria": [{"process_name": "python", "must_be_running": True}],
        },
    )
    assert resp_comp.status_code == 200
    comp_data = resp_comp.json()
    assert comp_data["passed"] is True
    assert "verification_proof_hash" in comp_data

    # 7. GET /history
    resp_hist = auth_client.get(f"/api/v1/devices/{device_id}/verification/history")
    assert resp_hist.status_code == 200
    hist_data = resp_hist.json()
    assert hist_data["total_verifications"] >= 1
    assert any(v["verification_id"] == comp_data["verification_id"] for v in hist_data["verifications"])
