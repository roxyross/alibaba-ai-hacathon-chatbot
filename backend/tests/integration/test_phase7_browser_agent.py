"""Integration tests for Phase 7: Autonomous Browser Agent & Web Automation Studio.

Verifies:
1. Headless browser navigation & DOM inspection (headings, links, forms, metadata, preview).
2. Structured web data extraction (tables, links, headings, text excerpts).
3. Visual screenshot capture and resolution configuration.
4. Interactive multi-step flow execution (navigate, extract, click, scroll, wait, form fill).
5. Sensitive action confirmation gating for high-risk browser interactions.
6. Browser automation task CRUD lifecycle, search filtering, and persistence via REST API.
7. Strict multi-tenant isolation (User B cannot view, modify, or delete User A's browser tasks).
8. Central ToolRegistry registration and direct execution for all 6 browser tools:
   - browser_navigate
   - browser_extract
   - browser_screenshot
   - browser_execute_flow
   - browser_list_tasks
   - browser_delete_task
9. Agent Planner deterministic intent decomposition and routing to browser tools.
10. Direct REST endpoints: /navigate, /extract, /screenshot, /execute.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient

from app.agent_runtime.planner import AgentPlanner
from app.auth.service import MagicLinkService
from app.browser.repository import clear_in_memory_stores
from app.browser.service import BrowserService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest, ToolSource

MOCK_HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ACME Global Cloud Portal</title>
    <meta name="description" content="Next-generation cloud infrastructure management portal.">
    <meta name="keywords" content="cloud, analytics, serverless, devops">
    <meta property="og:title" content="ACME Global Cloud Portal">
</head>
<body>
    <header>
        <h1>ACME Cloud Operations</h1>
    </header>
    <main>
        <h2>Global Infrastructure Status</h2>
        <p>Real-time telemetry and cluster availability metrics across all deployed regions.</p>

        <h3>Latency Benchmarks</h3>
        <table id="metrics-table">
            <thead>
                <tr>
                    <th>Region</th>
                    <th>Latency (ms)</th>
                    <th>Uptime</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>us-east-1</td>
                    <td>24</td>
                    <td>99.99%</td>
                </tr>
                <tr>
                    <td>eu-west-1</td>
                    <td>38</td>
                    <td>99.95%</td>
                </tr>
                <tr>
                    <td>ap-southeast-1</td>
                    <td>62</td>
                    <td>99.90%</td>
                </tr>
            </tbody>
        </table>

        <div class="navigation-links">
            <a href="/docs/api-reference">API Documentation</a>
            <a href="/console/clusters">Manage Clusters</a>
            <a href="https://external-partner.org/security">Security Whitepaper</a>
        </div>

        <form action="/auth/login" method="POST" id="auth-form">
            <input type="text" name="username" placeholder="Username" />
            <input type="password" name="password" placeholder="Password" />
            <input type="submit" value="Sign In" />
        </form>
    </main>
</body>
</html>
"""


async def _create_second_user_client() -> AsyncClient:
    """Helper to mint a second authenticated client for tenant isolation testing."""
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    service = MagicLinkService()
    test_email = "browser_tenant_b@example.com"
    await service.request_link(test_email)
    user_id = next(
        u.id for email, u in service._mem_users.items() if email == test_email
    )
    token_value = next(
        t for t, row in service._mem_tokens.items() if row.user_id == user_id
    )
    result = await service.verify(token_value)
    if result is None:
        raise RuntimeError("Failed to verify magic-link token for second user")
    _user, jwt, _ttl = result
    client.headers["Authorization"] = f"Bearer {jwt}"
    return client


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    """Ensure clean browser in-memory state before each test."""
    clear_in_memory_stores()


@pytest.mark.asyncio
async def test_browser_navigation_and_dom_inspection() -> None:
    """Verify headless navigation parses title, headings, links, forms, metadata, and preview."""
    service = BrowserService.get_instance()

    with patch.object(
        service,
        "fetch_html",
        new=AsyncMock(return_value=(MOCK_HTML_PAGE, "https://example.com/portal", 200)),
    ):
        res = await service.navigate_and_inspect("https://example.com/portal")

        assert res["status"] == "success"
        assert res["title"] == "ACME Global Cloud Portal"
        assert res["final_url"] == "https://example.com/portal"

        # Headings
        headings = res["headings"]
        assert len(headings) >= 3
        assert headings[0] == {"level": 1, "text": "ACME Cloud Operations"}
        assert headings[1] == {"level": 2, "text": "Global Infrastructure Status"}
        assert headings[2] == {"level": 3, "text": "Latency Benchmarks"}

        # Links
        links = res["links"]
        assert len(links) >= 3
        assert links[0]["text"] == "API Documentation"
        assert links[0]["href"] == "https://example.com/docs/api-reference"
        assert links[1]["href"] == "https://example.com/console/clusters"
        assert links[2]["href"] == "https://external-partner.org/security"

        # Forms
        forms = res["forms"]
        assert len(forms) >= 1
        assert forms[0]["action"] == "https://example.com/auth/login"
        assert forms[0]["method"] == "POST"
        assert "username" in forms[0]["fields"]
        assert "password" in forms[0]["fields"]

        # Meta
        meta = res["meta"]
        assert "Next-generation cloud infrastructure" in meta.get("description", "")
        assert meta.get("og:title") == "ACME Global Cloud Portal"

        # Content preview
        assert len(res["content_preview"]) > 0
        assert "Global Infrastructure Status" in res["content_preview"]


@pytest.mark.asyncio
async def test_browser_navigation_error_resilience() -> None:
    """Verify navigation handles network timeouts gracefully without raising unhandled exceptions."""
    service = BrowserService.get_instance()

    with patch.object(
        service,
        "fetch_html",
        side_effect=httpx.ConnectError("Connection refused by target host"),
    ):
        res = await service.navigate_and_inspect("https://unreachable-host.example.com")
        assert res["status"] == "error"
        assert "Connection refused" in str(res["error"])
        assert res["headings"] == []
        assert res["links"] == []
        assert res["forms"] == []


@pytest.mark.asyncio
async def test_browser_extract_structured_data() -> None:
    """Verify structured extraction of tables, links, headings, and text excerpts."""
    service = BrowserService.get_instance()

    with patch.object(
        service,
        "fetch_html",
        new=AsyncMock(return_value=(MOCK_HTML_PAGE, "https://example.com/portal", 200)),
    ):
        # 1. Extract all
        res_all = await service.extract_data("https://example.com/portal", extract_type="all")
        assert res_all["status"] == "success"
        assert res_all["title"] == "ACME Global Cloud Portal"

        # Tables
        tables = res_all["tables"]
        assert len(tables) == 1
        table = tables[0]
        assert table["headers"] == ["Region", "Latency (ms)", "Uptime"]
        assert len(table["rows"]) == 3
        assert table["rows"][0] == ["us-east-1", "24", "99.99%"]
        assert table["rows"][1] == ["eu-west-1", "38", "99.95%"]
        assert table["rows"][2] == ["ap-southeast-1", "62", "99.90%"]
        assert table["total_rows"] == 3

        # Links & Headings
        assert len(res_all["links"]) >= 3
        assert len(res_all["headings"]) >= 3
        assert "Real-time telemetry" in res_all["text_excerpt"]

        # 2. Extract tables only
        res_tables = await service.extract_data("https://example.com/portal", extract_type="tables")
        assert len(res_tables["tables"]) == 1
        assert len(res_tables["links"]) == 0
        assert len(res_tables["headings"]) == 0

        # 3. Extract links only
        res_links = await service.extract_data("https://example.com/portal", extract_type="links")
        assert len(res_links["tables"]) == 0
        assert len(res_links["links"]) >= 3
        assert len(res_links["headings"]) == 0


@pytest.mark.asyncio
async def test_browser_capture_screenshot() -> None:
    """Verify visual preview screenshot generation with resolution parameters."""
    service = BrowserService.get_instance()

    with patch.object(
        service,
        "fetch_html",
        new=AsyncMock(return_value=(MOCK_HTML_PAGE, "https://example.com/dashboard", 200)),
    ):
        res = await service.capture_screenshot(
            "https://example.com/dashboard", width=1920, height=1080
        )

        assert res["status"] == "success"
        assert res["url"] == "https://example.com/dashboard"
        assert res["width"] == 1920
        assert res["height"] == 1080
        assert "image.thum.io" in res["screenshot_url"]
        assert "1920" in res["screenshot_url"]
        assert "1080" in res["screenshot_url"]
        assert res["title"] == "ACME Global Cloud Portal"
        assert res["timestamp"] is not None


@pytest.mark.asyncio
async def test_browser_execute_flow_actions_and_persistence() -> None:
    """Verify multi-step interactive flow execution (navigate, extract, click, scroll, wait) and task persistence."""
    service = BrowserService.get_instance()

    actions: list[dict[str, Any]] = [
        {"type": "navigate"},
        {"type": "extract_table"},
        {"type": "click", "selector": "#metrics-table"},
        {"type": "scroll", "direction": "down", "amount": 600},
        {"type": "wait", "seconds": 0.05},
    ]

    with patch.object(
        service,
        "fetch_html",
        new=AsyncMock(return_value=(MOCK_HTML_PAGE, "https://example.com/app", 200)),
    ):
        res = await service.execute_browser_flow(
            user_id="user_flow_test",
            url="https://example.com/app",
            actions=actions,
            title="Inspect Infrastructure Table",
            save_task=True,
            tags=["monitoring", "infra"],
        )

        assert res["status"] == "completed"
        assert res["url"] == "https://example.com/app"
        assert res["title"] == "Inspect Infrastructure Table"
        assert res["task_id"] is not None

        steps = res["steps_executed"]
        assert len(steps) == 5

        # Step 1: Navigate
        assert steps[0]["action"] == "navigate"
        assert steps[0]["status"] == "success"

        # Step 2: Extract table
        assert steps[1]["action"] == "extract_table"
        assert steps[1]["details"]["tables_found"] == 1

        # Step 3: Interactive click
        assert steps[2]["action"] == "click"
        assert steps[2]["details"]["clicked_selector"] == "#metrics-table"
        assert res["result_data"]["last_clicked"] == "#metrics-table"

        # Step 4: Scroll
        assert steps[3]["action"] == "scroll"
        assert steps[3]["details"]["scrolled_direction"] == "down"
        assert steps[3]["details"]["scrolled_amount"] == 600

        # Step 5: Wait
        assert steps[4]["action"] == "wait"
        assert steps[4]["details"]["slept_seconds"] == 0.05

        # Verify task is persisted in repository
        persisted = await service.repo.get_task(user_id="user_flow_test", task_id=res["task_id"])
        assert persisted is not None
        assert persisted["title"] == "Inspect Infrastructure Table"
        assert persisted["status"] == "completed"
        assert persisted["tags"] == ["monitoring", "infra"]


@pytest.mark.asyncio
async def test_browser_flow_sensitive_confirmation_gate() -> None:
    """Verify that unconfirmed sensitive form actions trigger confirmation_required status."""
    service = BrowserService.get_instance()

    actions: list[dict[str, Any]] = [
        {"type": "navigate"},
        {
            "type": "fill_form",
            "is_sensitive": True,
            "confirm": False,
            "fields": {"#bank_transfer_amount": "50000"},
            "submit": True,
        },
    ]

    with patch.object(
        service,
        "fetch_html",
        new=AsyncMock(return_value=(MOCK_HTML_PAGE, "https://example.com/transfer", 200)),
    ):
        res = await service.execute_browser_flow(
            user_id="user_gate_test",
            url="https://example.com/transfer",
            actions=actions,
            title="Wire Transfer Task",
            save_task=True,
        )

        assert res["status"] == "confirmation_required"
        steps = res["steps_executed"]
        assert len(steps) == 2
        assert steps[1]["status"] == "confirmation_required"
        assert "requires explicit user confirmation" in steps[1]["details"]["message"]


@pytest.mark.asyncio
async def test_browser_task_crud_rest_api(authed_client: AsyncClient) -> None:
    """Verify browser automation task lifecycle via REST API (create, list, get, update, delete)."""
    # 1. Create task
    create_payload: dict[str, Any] = {
        "url": "https://example.com/analytics",
        "title": "Daily Telemetry Scraper",
        "action_type": "multi_step",
        "actions": [{"type": "navigate"}, {"type": "extract", "extract_type": "tables"}],
        "result_data": {"cached_rows": 42},
        "status": "pending",
        "tags": ["telemetry", "daily"],
    }
    create_resp = await authed_client.post("/api/v1/browser/tasks", json=create_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    task = created_data["task"]
    task_id = task["id"]
    assert task["title"] == "Daily Telemetry Scraper"
    assert task["url"] == "https://example.com/analytics"
    assert task["tags"] == ["telemetry", "daily"]

    # 2. List tasks
    list_resp = await authed_client.get("/api/v1/browser/tasks")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(t["id"] == task_id for t in list_data["tasks"])

    # 3. Search tasks
    search_resp = await authed_client.get("/api/v1/browser/tasks?search=Telemetry")
    assert search_resp.status_code == 200
    assert len(search_resp.json()["tasks"]) >= 1

    empty_search = await authed_client.get("/api/v1/browser/tasks?search=NonExistentKeywordXYZ")
    assert empty_search.status_code == 200
    assert len(empty_search.json()["tasks"]) == 0

    # 4. Get task by ID
    get_resp = await authed_client.get(f"/api/v1/browser/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["task"]["id"] == task_id

    # 5. Patch task
    patch_payload: dict[str, Any] = {
        "title": "Updated Telemetry Scraper",
        "status": "completed",
        "tags": ["telemetry", "production"],
    }
    patch_resp = await authed_client.patch(f"/api/v1/browser/tasks/{task_id}", json=patch_payload)
    assert patch_resp.status_code == 200
    updated_task = patch_resp.json()["task"]
    assert updated_task["title"] == "Updated Telemetry Scraper"
    assert updated_task["status"] == "completed"
    assert updated_task["tags"] == ["telemetry", "production"]

    # 6. Delete task
    del_resp = await authed_client.delete(f"/api/v1/browser/tasks/{task_id}")
    assert del_resp.status_code == 204

    # 7. Verify 404 after deletion
    after_del = await authed_client.get(f"/api/v1/browser/tasks/{task_id}")
    assert after_del.status_code == 404


@pytest.mark.asyncio
async def test_browser_multi_tenant_isolation(authed_client: AsyncClient) -> None:
    """Verify strict tenant isolation: User B cannot read, modify, or delete User A's browser tasks."""
    # User A creates a browser task
    create_payload: dict[str, Any] = {
        "url": "https://company-private.internal/dashboard",
        "title": "Confidential Executive Telemetry",
        "action_type": "navigate",
        "actions": [{"type": "navigate"}],
        "tags": ["private", "c-level"],
    }
    resp_a = await authed_client.post("/api/v1/browser/tasks", json=create_payload)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["task"]["id"]

    # Mint authenticated client for User B
    client_b = await _create_second_user_client()
    try:
        # User B attempts to access User A's task
        get_b = await client_b.get(f"/api/v1/browser/tasks/{task_a_id}")
        assert get_b.status_code == 404

        # User B attempts to update User A's task
        patch_b = await client_b.patch(
            f"/api/v1/browser/tasks/{task_a_id}",
            json={"title": "Hacked Title Attempt"},
        )
        assert patch_b.status_code == 404

        # User B attempts to delete User A's task
        del_b = await client_b.delete(f"/api/v1/browser/tasks/{task_a_id}")
        assert del_b.status_code == 404

        # User B's task list does not include User A's task
        list_b = await client_b.get("/api/v1/browser/tasks")
        assert list_b.status_code == 200
        assert not any(t["id"] == task_a_id for t in list_b.json()["tasks"])

        # User A can still retrieve the original task intact
        verify_a = await authed_client.get(f"/api/v1/browser/tasks/{task_a_id}")
        assert verify_a.status_code == 200
        assert verify_a.json()["task"]["title"] == "Confidential Executive Telemetry"

    finally:
        await client_b.aclose()


@pytest.mark.asyncio
async def test_browser_tool_registry_registration_and_execution() -> None:
    """Verify all 6 browser tools are registered in Central ToolRegistry and execute successfully."""
    # Ensure tools are registered
    service = BrowserService.get_instance()
    service.register_browser_tools()
    registry = ToolRegistry.get_instance()

    expected_tools = [
        "browser_navigate",
        "browser_extract",
        "browser_screenshot",
        "browser_execute_flow",
        "browser_list_tasks",
        "browser_delete_task",
    ]

    for tool_id in expected_tools:
        tool = registry.get(tool_id)
        assert tool is not None, f"Tool '{tool_id}' not found in registry"
        assert tool.source == ToolSource.SYSTEM
        assert tool.enabled is True
        assert "browser" in tool.capabilities

    # Discovery check
    discovered = registry.discover_for_task("browse website to extract pricing tables")
    discovered_ids = [t.id for t in discovered]
    assert any("browser" in tid for tid in discovered_ids)

    # 1. Execute browser_navigate
    with patch.object(
        service,
        "fetch_html",
        new=AsyncMock(return_value=(MOCK_HTML_PAGE, "https://example.com/test", 200)),
    ):
        req_nav = ToolExecutionRequest(
            tool_id="browser_navigate",
            arguments={"url": "https://example.com/test"},
            user_id="user_reg_test",
        )
        res_nav = await registry.execute(req_nav)
        assert res_nav.success is True
        assert res_nav.output is not None
        assert res_nav.output["title"] == "ACME Global Cloud Portal"

        # 2. Execute browser_extract
        req_ext = ToolExecutionRequest(
            tool_id="browser_extract",
            arguments={"url": "https://example.com/test", "extract_type": "tables"},
            user_id="user_reg_test",
        )
        res_ext = await registry.execute(req_ext)
        assert res_ext.success is True
        assert len(res_ext.output["tables"]) == 1

        # 3. Execute browser_screenshot
        req_shot = ToolExecutionRequest(
            tool_id="browser_screenshot",
            arguments={"url": "https://example.com/test", "width": 1024, "height": 768},
            user_id="user_reg_test",
        )
        res_shot = await registry.execute(req_shot)
        assert res_shot.success is True
        assert "image.thum.io" in res_shot.output["screenshot_url"]

        # 4. Execute browser_execute_flow
        req_flow = ToolExecutionRequest(
            tool_id="browser_execute_flow",
            arguments={
                "url": "https://example.com/test",
                "actions": [{"type": "navigate"}, {"type": "scroll", "direction": "down", "amount": 300}],
                "title": "Registry Flow Execution",
                "save_task": True,
            },
            user_id="user_reg_flow",
        )
        res_flow = await registry.execute(req_flow)
        assert res_flow.success is True
        task_id = res_flow.output["task_id"]
        assert task_id is not None
        assert res_flow.output["status"] == "completed"

        # 5. Execute browser_list_tasks
        req_list = ToolExecutionRequest(
            tool_id="browser_list_tasks",
            arguments={"limit": 10},
            user_id="user_reg_flow",
        )
        res_list = await registry.execute(req_list)
        assert res_list.success is True
        assert res_list.output["total"] >= 1
        assert any(t["id"] == task_id for t in res_list.output["tasks"])

        # 6. Execute browser_delete_task
        req_del = ToolExecutionRequest(
            tool_id="browser_delete_task",
            arguments={"task_id": task_id},
            user_id="user_reg_flow",
        )
        res_del = await registry.execute(req_del)
        assert res_del.success is True
        assert res_del.output["deleted"] is True


@pytest.mark.asyncio
async def test_browser_agent_planner_intent_routing() -> None:
    """Verify AgentPlanner decomposes user queries into appropriate browser tool steps."""
    planner = AgentPlanner()
    service = BrowserService.get_instance()
    service.register_browser_tools()

    # 1. Navigate intent
    plan_nav = planner._deterministic_decomposition("navigate to https://news.ycombinator.com")
    assert plan_nav is not None
    assert len(plan_nav) == 1
    assert plan_nav[0]["tool_id"] == "browser_navigate"
    assert plan_nav[0]["tool_input"]["url"] == "https://news.ycombinator.com"

    # 2. Extract tables intent
    plan_ext = planner._deterministic_decomposition("extract tables from https://example.com/financials")
    assert plan_ext is not None
    assert len(plan_ext) == 1
    assert plan_ext[0]["tool_id"] == "browser_extract"
    assert plan_ext[0]["tool_input"]["extract_type"] == "tables"

    # 3. Screenshot intent
    plan_shot = planner._deterministic_decomposition("take screenshot of https://github.com")
    assert plan_shot is not None
    assert len(plan_shot) == 1
    assert plan_shot[0]["tool_id"] == "browser_screenshot"
    assert plan_shot[0]["tool_input"]["url"] == "https://github.com"

    # 4. Form fill intent
    plan_form = planner._deterministic_decomposition("fill form on https://service.com/login")
    assert plan_form is not None
    assert len(plan_form) == 1
    assert plan_form[0]["tool_id"] == "browser_execute_flow"
    assert plan_form[0]["tool_input"]["url"] == "https://service.com/login"


@pytest.mark.asyncio
async def test_browser_rest_endpoints_direct(authed_client: AsyncClient) -> None:
    """Verify direct REST endpoints: /navigate, /extract, /screenshot, and /execute."""
    with patch.object(
        BrowserService,
        "fetch_html",
        new=AsyncMock(return_value=(MOCK_HTML_PAGE, "https://example.com/portal", 200)),
    ):
        # 1. POST /api/v1/browser/navigate
        nav_res = await authed_client.post(
            "/api/v1/browser/navigate",
            json={"url": "https://example.com/portal", "timeout_seconds": 15},
        )
        assert nav_res.status_code == 200
        nav_data = nav_res.json()
        assert nav_data["title"] == "ACME Global Cloud Portal"
        assert len(nav_data["headings"]) >= 3

        # 2. POST /api/v1/browser/extract
        ext_res = await authed_client.post(
            "/api/v1/browser/extract",
            json={"url": "https://example.com/portal", "extract_type": "all"},
        )
        assert ext_res.status_code == 200
        ext_data = ext_res.json()
        assert len(ext_data["tables"]) == 1
        assert ext_data["tables"][0]["headers"] == ["Region", "Latency (ms)", "Uptime"]

        # 3. POST /api/v1/browser/screenshot
        shot_res = await authed_client.post(
            "/api/v1/browser/screenshot",
            json={"url": "https://example.com/portal", "width": 1280, "height": 800},
        )
        assert shot_res.status_code == 200
        shot_data = shot_res.json()
        assert "image.thum.io" in shot_data["screenshot_url"]
        assert shot_data["width"] == 1280

        # 4. POST /api/v1/browser/execute
        flow_res = await authed_client.post(
            "/api/v1/browser/execute",
            json={
                "url": "https://example.com/portal",
                "actions": [{"type": "navigate"}, {"type": "extract", "extract_type": "tables"}],
                "title": "REST Flow Endpoint Test",
                "save_task": True,
                "tags": ["rest", "integration"],
            },
        )
        assert flow_res.status_code == 200
        flow_data = flow_res.json()
        assert flow_data["status"] == "completed"
        assert flow_data["task_id"] is not None
        assert len(flow_data["steps_executed"]) == 2
