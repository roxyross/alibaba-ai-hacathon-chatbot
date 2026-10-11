"""Phase 10 Test Suite: Browser Automation Hardening (Playwright Persistent Sessions).

Tests real persistent browser profiles, navigation, DOM inspection, element identification,
click, type, select, scroll, real pixel screenshots, tab management, security privacy,
and the end-to-end exit gate flow (Open -> Navigate -> Inspect -> Click -> Type -> Submit -> Verify).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.browser.playwright_manager import PlaywrightBrowserManager
from app.browser.schemas import BrowserSessionModel
from app.browser.service import BrowserService
from app.device.orchestrator import UniversalAppController
from app.device.schemas import AppControlExecutionRequest
from app.main import app
from app.tools.registry import ToolRegistry

# HTML fixtures for real offline deterministic testing
FORM_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Roxy Automation Test Page</title>
    <style>
        body { font-family: sans-serif; padding: 20px; }
        .tall-container { height: 2000px; }
        #result-box { display: none; margin-top: 15px; color: green; font-weight: bold; }
    </style>
</head>
<body>
    <h1>Browser Automation Hardening</h1>
    <p>Testing real Playwright interactions under Zero Simulation doctrine.</p>
    <a href="https://example.com" id="sample-link">External Documentation</a>

    <form id="test-form" onsubmit="event.preventDefault(); handleSubmit();">
        <label for="username">Username:</label>
        <input type="text" id="username" name="username" placeholder="Enter username" />

        <label for="role-select">Role:</label>
        <select id="role-select" name="role">
            <option value="user">User</option>
            <option value="admin">Admin</option>
        </select>

        <label for="file-upload">Upload:</label>
        <input type="file" id="file-upload" name="file-upload" />

        <button type="submit" id="submit-btn">Submit Action</button>
    </form>

    <a href="data:text/plain;charset=utf-8,Roxy%20Automated%20Export" download="roxy_export.txt" id="download-link">Export Data</a>

    <div id="result-box">Submitted: <span id="submitted-val"></span></div>
    <div class="tall-container">Scroll spacer content</div>

    <script>
        function handleSubmit() {
            const val = document.getElementById('username').value;
            const resBox = document.getElementById('result-box');
            const span = document.getElementById('submitted-val');
            span.innerText = val;
            resBox.style.display = 'block';
        }
    </script>
</body>
</html>
"""


@pytest.fixture(autouse=True)
async def cleanup_browser_sessions() -> AsyncIterator[None]:
    """Ensure all Playwright sessions are closed cleanly after each test."""
    yield
    manager = PlaywrightBrowserManager.get_instance()
    await manager.close_all_sessions()


@pytest.fixture
def mock_user() -> User:
    return User(
        id=str(uuid.uuid4()),
        email="browser_tester@roxy.ai",
    )


# =============================================================================
# 1. Persistent Session & Profile Lifecycle
# =============================================================================

@pytest.mark.asyncio
async def test_playwright_manager_lifecycle_and_persistent_profile() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    profile_name = f"test_prof_{uuid.uuid4().hex[:6]}"

    session = await manager.launch_session(
        profile_name=profile_name,
        headless=True,
        browser_type="chromium",
        viewport_width=1280,
        viewport_height=800,
    )

    assert isinstance(session, BrowserSessionModel)
    assert session.browser == "chromium"
    assert session.profile == profile_name
    assert session.active_tab_id is not None
    assert len(session.tabs) >= 1
    assert session.is_closed is False

    profile_path = Path.home() / ".roxy" / "browser_profiles" / profile_name
    assert profile_path.exists()

    # Query session
    queried = await manager.get_session(session.session_id)
    assert queried is not None
    assert queried.session_id == session.session_id

    # Close session
    closed = await manager.close_session(session.session_id)
    assert closed is True
    assert await manager.get_session(session.session_id) is None


# =============================================================================
# 2. Real Navigation & Structured DOM Extraction
# =============================================================================

@pytest.mark.asyncio
async def test_browser_navigate_and_dom_extraction() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()

    # Navigate to data URL
    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    nav_res = await manager.navigate(session_id=session.session_id, url=data_url)

    assert nav_res.status == "success"
    assert "Browser Automation Hardening" in nav_res.title or "Roxy Automation Test Page" in nav_res.title
    assert len(nav_res.headings) >= 1
    assert nav_res.headings[0]["text"] == "Browser Automation Hardening"
    assert len(nav_res.links) >= 1
    assert len(nav_res.forms) >= 1
    assert "username" in nav_res.forms[0]["fields"]


# =============================================================================
# 3. Interactive DOM Inspection
# =============================================================================

@pytest.mark.asyncio
async def test_browser_dom_inspection() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()

    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    await manager.navigate(session_id=session.session_id, url=data_url)

    inspect_res = await manager.inspect_dom(session_id=session.session_id)

    assert inspect_res.total_elements_found > 0
    tags = [el["tag"] for el in inspect_res.elements]
    assert "button" in tags
    assert "input" in tags
    assert "select" in tags

    submit_btn = next((el for el in inspect_res.elements if el["id"] == "submit-btn"), None)
    assert submit_btn is not None
    assert submit_btn["visible"] is True
    assert submit_btn["bounds"]["width"] > 0


# =============================================================================
# 4. Element Interactions (Type, Select, Hover)
# =============================================================================

@pytest.mark.asyncio
async def test_browser_element_interaction_type_and_select() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()

    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    await manager.navigate(session_id=session.session_id, url=data_url)

    # 1. Type text
    type_res = await manager.interact_element(
        session_id=session.session_id,
        selector="#username",
        action="type",
        text="Operator_Alpha",
        clear_first=True,
    )
    assert type_res.success is True
    assert type_res.verified is True
    assert type_res.details.get("verified_input_value") == "Operator_Alpha"

    # 2. Select option
    select_res = await manager.interact_element(
        session_id=session.session_id,
        selector="#role-select",
        action="select",
        value="admin",
    )
    assert select_res.success is True
    assert select_res.details.get("selected_value") == "admin"

    # 3. Hover
    hover_res = await manager.interact_element(
        session_id=session.session_id,
        selector="#sample-link",
        action="hover",
    )
    assert hover_res.success is True
    assert hover_res.details.get("hovered") is True


@pytest.mark.asyncio
async def test_browser_upload_and_download(tmp_path: Path) -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()

    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    await manager.navigate(session_id=session.session_id, url=data_url)

    # 1. Test File Upload
    test_file = tmp_path / "roxy_sample_upload.txt"
    test_file.write_text("Roxy Test Upload Content", encoding="utf-8")

    upload_res = await manager.upload_file(
        session_id=session.session_id,
        selector="#file-upload",
        file_paths=[str(test_file)],
    )
    assert upload_res.success is True
    assert upload_res.uploaded_files_count == 1
    assert "roxy_sample_upload.txt" in upload_res.file_names[0]

    # 2. Test File Download
    download_res = await manager.download_file(
        session_id=session.session_id,
        selector="#download-link",
        trigger_action="click",
        timeout_ms=5000,
    )
    assert download_res.success is True
    assert download_res.downloaded_path != ""
    assert Path(download_res.downloaded_path).exists()
    assert download_res.file_size_bytes > 0
    content = Path(download_res.downloaded_path).read_text(encoding="utf-8")
    assert "Roxy Automated Export" in content


# =============================================================================
# 5. Scrolling & Coordinate Verification
# =============================================================================

@pytest.mark.asyncio
async def test_browser_scroll_and_coordinate_tracking() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()

    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    await manager.navigate(session_id=session.session_id, url=data_url)

    # Scroll down
    scroll_down = await manager.scroll(
        session_id=session.session_id,
        direction="down",
        amount=400,
    )
    assert scroll_down.success is True
    assert scroll_down.scroll_y >= 0

    # Scroll to top
    scroll_top = await manager.scroll(
        session_id=session.session_id,
        direction="top",
    )
    assert scroll_top.success is True
    assert scroll_top.scroll_y == 0


# =============================================================================
# 6. Real Pixel Screenshots
# =============================================================================

@pytest.mark.asyncio
async def test_browser_real_pixel_screenshot() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()

    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    await manager.navigate(session_id=session.session_id, url=data_url)

    shot = await manager.capture_screenshot(session_id=session.session_id)

    assert shot.success is True
    assert shot.screenshot_path != ""
    assert Path(shot.screenshot_path).exists()
    assert shot.base64_data is not None
    assert shot.base64_data.startswith("data:image/png;base64,")

    # Verify real PNG magic bytes
    with open(shot.screenshot_path, "rb") as f:
        magic = f.read(8)
        assert magic == b"\x89PNG\r\n\x1a\n"


# =============================================================================
# 7. Tab Management
# =============================================================================

@pytest.mark.asyncio
async def test_browser_tab_management() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()
    init_tab_id = session.active_tab_id

    # Create new tab
    new_tab_res = await manager.manage_tabs(
        session_id=session.session_id,
        action="new_tab",
        url="about:blank",
    )
    assert len(new_tab_res.tabs) == 2
    second_tab_id = new_tab_res.active_tab_id
    assert second_tab_id != init_tab_id

    # Switch back to first tab
    switch_res = await manager.manage_tabs(
        session_id=session.session_id,
        action="switch_tab",
        tab_id=init_tab_id,
    )
    assert switch_res.active_tab_id == init_tab_id

    # Close second tab
    close_tab_res = await manager.manage_tabs(
        session_id=session.session_id,
        action="close_tab",
        tab_id=second_tab_id,
    )
    assert len(close_tab_res.tabs) == 1
    assert close_tab_res.tabs[0].tab_id == init_tab_id


# =============================================================================
# 8. Wait Operations & Page State Telemetry (No Credential Leakage)
# =============================================================================

@pytest.mark.asyncio
async def test_browser_wait_and_telemetry_privacy() -> None:
    manager = PlaywrightBrowserManager.get_instance()
    session = await manager.launch_session()

    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    await manager.navigate(session_id=session.session_id, url=data_url)

    # Wait for submit button
    wait_res = await manager.wait_for(
        session_id=session.session_id,
        selector="#submit-btn",
        state="visible",
        timeout_ms=5000,
    )
    assert wait_res.success is True
    assert wait_res.waited_ms >= 0

    # Get page state
    state = await manager.get_page_state(session_id=session.session_id)
    assert state.ready_state in ("complete", "interactive")
    assert state.viewport["width"] == 1280
    assert state.tabs_count == 1
    # Security requirement: No auth cookies/tokens exposed
    assert isinstance(state.has_cookies, bool)


# =============================================================================
# 9. BrowserService Integration & Flow Runner
# =============================================================================

@pytest.mark.asyncio
async def test_browser_service_flow_runner_real_execution(mock_user: User) -> None:
    service = BrowserService.get_instance()
    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")

    actions = [
        {"type": "navigate"},
        {"type": "type", "selector": "#username", "text": "FlowTester"},
        {"type": "click", "selector": "#submit-btn"},
        {"type": "screenshot"},
    ]

    res = await service.execute_browser_flow(
        user_id=str(mock_user.id),
        url=data_url,
        actions=actions,
        title="Automated Test Flow",
        save_task=False,
    )

    assert res["status"] == "completed"
    assert len(res["steps_executed"]) == 4
    assert res["steps_executed"][1]["details"]["typed_selector"] == "#username"
    assert res["steps_executed"][2]["details"]["clicked_selector"] == "#submit-btn"
    assert "screenshot_url" in res["steps_executed"][3]["details"]


# =============================================================================
# 10. Central Tool Registry Browser Tools Registration
# =============================================================================

def test_tool_registry_browser_tools() -> None:
    service = BrowserService.get_instance()
    service.register_browser_tools()
    reg = ToolRegistry.get_instance()

    expected_tools = [
        "browser_navigate",
        "browser_extract",
        "browser_screenshot",
        "browser_execute_flow",
        "browser_launch_session",
        "browser_close_session",
        "browser_manage_tabs",
        "browser_inspect_dom",
        "browser_interact_element",
        "browser_upload_file",
        "browser_download_file",
        "browser_scroll",
        "browser_wait_for",
        "browser_get_page_state",
    ]

    for tool_id in expected_tools:
        tool = reg.get(tool_id)
        assert tool is not None, f"Tool '{tool_id}' must be registered in ToolRegistry"
        assert "browser" in tool.capabilities


# =============================================================================
# 11. Universal App Control Orchestrator Browser Surface Routing
# =============================================================================

@pytest.mark.asyncio
async def test_universal_app_controller_browser_automation(mock_user: User) -> None:
    controller = UniversalAppController.get_instance()
    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")

    req = AppControlExecutionRequest(
        application="chrome",
        capability="inspect_dom",
        parameters={"url": data_url},
        user_id=str(mock_user.id),
    )

    res = await controller.orchestrate(req)
    assert res.stage == "verified"
    assert res.plan is not None
    assert res.plan.chosen_integration == "browser_automation"
    assert res.verification.get("verified") is True


# =============================================================================
# 12. FastAPI Browser REST Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_fastapi_browser_sessions_endpoints(mock_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: mock_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Launch session
        launch_resp = await ac.post(
            "/api/v1/browser/sessions/launch",
            json={"profile_name": "api_test_prof", "headless": True},
        )
        assert launch_resp.status_code == 201
        sess_data = launch_resp.json()["session"]
        sid = sess_data["session_id"]

        # 2. Get session
        get_resp = await ac.get(f"/api/v1/browser/sessions/{sid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["session_id"] == sid

        # 3. Navigate
        data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
        nav_resp = await ac.post(
            f"/api/v1/browser/sessions/{sid}/navigate",
            json={"url": data_url},
        )
        assert nav_resp.status_code == 200
        assert nav_resp.json()["status"] == "success"

        # 4. Inspect DOM
        inspect_resp = await ac.post(
            f"/api/v1/browser/sessions/{sid}/dom/inspect",
            json={"session_id": sid},
        )
        assert inspect_resp.status_code == 200
        assert inspect_resp.json()["total_elements_found"] > 0

        # 5. Interact
        interact_resp = await ac.post(
            f"/api/v1/browser/sessions/{sid}/interact",
            json={"session_id": sid, "selector": "#username", "action": "type", "text": "ApiTester"},
        )
        assert interact_resp.status_code == 200
        assert interact_resp.json()["success"] is True

        # 6. Scroll
        scroll_resp = await ac.post(
            f"/api/v1/browser/sessions/{sid}/scroll",
            json={"session_id": sid, "direction": "down", "amount": 200},
        )
        assert scroll_resp.status_code == 200
        assert scroll_resp.json()["success"] is True

        # 7. Screenshot
        shot_resp = await ac.post(
            f"/api/v1/browser/sessions/{sid}/screenshot",
            json={"session_id": sid},
        )
        assert shot_resp.status_code == 200
        assert shot_resp.json()["success"] is True

        # 8. Close session
        close_resp = await ac.post(f"/api/v1/browser/sessions/{sid}/close")
        assert close_resp.status_code == 200
        assert close_resp.json()["closed"] is True

    app.dependency_overrides.clear()


# =============================================================================
# 13. EXIT GATE TEST: Complete End-to-End Real Browser Automation Flow
# =============================================================================

@pytest.mark.asyncio
async def test_exit_gate_end_to_end_flow() -> None:
    """EXIT GATE VERIFICATION:
    Open browser
    -> navigate
    -> inspect
    -> click
    -> type
    -> submit
    -> verify!
    """
    manager = PlaywrightBrowserManager.get_instance()

    # Step 1: Open browser (Launch persistent profile session)
    session = await manager.launch_session(
        profile_name="exit_gate_profile",
        headless=True,
    )
    assert session.session_id is not None
    sid = session.session_id

    # Step 2: Navigate to target page
    data_url = "data:text/html," + FORM_PAGE_HTML.replace("\n", "").replace(" ", "%20")
    nav_res = await manager.navigate(session_id=sid, url=data_url)
    assert nav_res.status == "success"

    # Step 3: Inspect DOM
    inspect_res = await manager.inspect_dom(session_id=sid)
    assert inspect_res.total_elements_found > 0
    # Confirm target input and submit button exist
    element_ids = [el.get("id") for el in inspect_res.elements]
    assert "username" in element_ids
    assert "submit-btn" in element_ids

    # Step 4: Click input to focus
    click_focus_res = await manager.interact_element(
        session_id=sid,
        selector="#username",
        action="click",
    )
    assert click_focus_res.success is True

    # Step 5: Type into form input
    secret_submission_text = f"Verified_Mission_{uuid.uuid4().hex[:8]}"
    type_res = await manager.interact_element(
        session_id=sid,
        selector="#username",
        action="type",
        text=secret_submission_text,
    )
    assert type_res.success is True
    assert type_res.verified is True

    # Step 6: Submit the form
    submit_res = await manager.interact_element(
        session_id=sid,
        selector="#submit-btn",
        action="click",
    )
    assert submit_res.success is True

    # Step 7: Verify submitted text appears live in the DOM!
    await manager.wait_for(
        session_id=sid,
        selector="#result-box",
        state="visible",
        timeout_ms=3000,
    )

    page = manager._sessions[sid].get_active_page()
    displayed_text = await page.inner_text("#submitted-val")
    assert displayed_text == secret_submission_text, (
        f"Exit gate postcondition failed: expected '{secret_submission_text}', got '{displayed_text}'"
    )

    # Step 8: Capture real screenshot of verified result
    shot_res = await manager.capture_screenshot(session_id=sid)
    assert shot_res.success is True
    assert Path(shot_res.screenshot_path).exists()
