"""Phase 15 Master Integration Test Suite: Autonomous Browser Agent & Web Automation Studio.

Verifies:
1. Fresh user starts with clean empty browser tasks (0 tasks).
2. Browser task creation and retrieval (POST/GET /api/v1/browser/tasks).
3. Browser task patching and mutation (PATCH /api/v1/browser/tasks/{id}).
4. Browser task deletion (DELETE /api/v1/browser/tasks/{id}).
5. Search, status, and action_type filtering on browser tasks.
6. Web page navigation and DOM inspection endpoint (POST /api/v1/browser/navigate).
7. Structured DOM element extraction endpoint (POST /api/v1/browser/extract).
8. Screenshot preview capture endpoint (POST /api/v1/browser/screenshot).
9. Autonomous multi-step browser flow runner (POST /api/v1/browser/execute).
10. Strict multi-tenant isolation: User B cannot view, update, or delete User A's tasks (404 Not Found).
11. Multi-agent chat runtime routing to browser specialist agent.
12. Multi-agent chat offline fallback with authentic browser tasks count.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.browser.repository import clear_in_memory_stores
from app.main import app


@pytest.fixture(autouse=True)
def _reset_stores() -> None:
    clear_in_memory_stores()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Helper to request magic link, verify token, and return auth headers + user_id."""
    req_resp = await client.post("/api/v1/auth/request-link", json={"email": email})
    assert req_resp.status_code == 200
    token = req_resp.json()["dev_token"]

    verify_resp = await client.post("/api/v1/auth/verify", json={"token": token})
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    access_token = data["access_token"]
    user_id = data["user"]["id"]
    return {"Authorization": f"Bearer {access_token}"}, user_id


@pytest.mark.anyio
async def test_browser_empty_state(client: httpx.AsyncClient) -> None:
    """A freshly authenticated user has 0 saved browser tasks and 0 mock cards."""
    email = f"fresh_browser_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.get("/api/v1/browser/tasks", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tasks"] == []
    assert data["total"] == 0


@pytest.mark.anyio
async def test_create_and_get_browser_task(client: httpx.AsyncClient) -> None:
    """Create a browser automation task and verify its retrieval with full schema validation."""
    email = f"browser_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    payload = {
        "url": "https://example.com/pricing",
        "title": "Extract Enterprise SaaS Pricing Matrix",
        "action_type": "extract",
        "actions": [
            {"type": "navigate", "url": "https://example.com/pricing"},
            {"type": "extract", "extract_type": "tables"},
        ],
        "result_data": {
            "tables": [
                {
                    "headers": ["Tier", "Price", "Seats"],
                    "rows": [["Starter", "$10", "5"], ["Enterprise", "$99", "Unlimited"]],
                }
            ]
        },
        "status": "completed",
        "requires_confirmation": False,
        "is_sensitive": False,
        "tags": ["pricing", "competitor", "saas"],
    }

    create_resp = await client.post("/api/v1/browser/tasks", json=payload, headers=headers)
    assert create_resp.status_code == 201
    created = create_resp.json()["task"]
    task_id = created["id"]
    assert created["title"] == "Extract Enterprise SaaS Pricing Matrix"
    assert created["url"] == "https://example.com/pricing"
    assert created["status"] == "completed"
    assert created["action_type"] == "extract"
    assert len(created["actions"]) == 2
    assert created["tags"] == ["pricing", "competitor", "saas"]

    get_resp = await client.get(f"/api/v1/browser/tasks/{task_id}", headers=headers)
    assert get_resp.status_code == 200
    task = get_resp.json()["task"]
    assert task["id"] == task_id
    assert task["url"] == payload["url"]
    assert task["result_data"]["tables"][0]["headers"] == ["Tier", "Price", "Seats"]


@pytest.mark.anyio
async def test_update_browser_task(client: httpx.AsyncClient) -> None:
    """Patch and mutate an existing browser automation task."""
    email = f"patch_browser_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/browser/tasks",
        json={
            "url": "https://news.ycombinator.com",
            "title": "Hacker News Top Stories",
            "status": "pending",
            "action_type": "extract",
            "tags": ["tech", "news"],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    tid = create_resp.json()["task"]["id"]

    patch_resp = await client.patch(
        f"/api/v1/browser/tasks/{tid}",
        json={
            "title": "Hacker News Top Stories (Updated)",
            "status": "completed",
            "result_data": {"stories_count": 30, "top_story": "Show HN: ROXY Personal AI"},
            "tags": ["tech", "news", "frontpage"],
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()["task"]
    assert updated["title"] == "Hacker News Top Stories (Updated)"
    assert updated["status"] == "completed"
    assert updated["result_data"]["stories_count"] == 30
    assert "frontpage" in updated["tags"]


@pytest.mark.anyio
async def test_delete_browser_task(client: httpx.AsyncClient) -> None:
    """Delete an existing browser task and verify it is permanently removed."""
    email = f"del_browser_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/browser/tasks",
        json={"url": "https://delete-me.org", "title": "Temporary Task"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    tid = create_resp.json()["task"]["id"]

    del_resp = await client.delete(f"/api/v1/browser/tasks/{tid}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/browser/tasks/{tid}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.anyio
async def test_browser_search_and_status_filtering(client: httpx.AsyncClient) -> None:
    """Filter browser tasks by search term, lifecycle status, and action_type."""
    email = f"filter_browser_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/browser/tasks",
        json={
            "url": "https://github.com/trending",
            "title": "GitHub Trending Repositories",
            "status": "completed",
            "action_type": "extract",
            "tags": ["developer", "github"],
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/browser/tasks",
        json={
            "url": "https://stripe.com/checkout",
            "title": "Payment Checkout Verification",
            "status": "pending",
            "action_type": "fill_form",
            "tags": ["finance", "checkout"],
        },
        headers=headers,
    )

    # Search for GitHub
    search_resp = await client.get("/api/v1/browser/tasks?search=GitHub", headers=headers)
    assert search_resp.status_code == 200
    assert len(search_resp.json()["tasks"]) == 1
    assert "GitHub" in search_resp.json()["tasks"][0]["title"]

    # Filter by status=completed
    status_resp = await client.get("/api/v1/browser/tasks?status=completed", headers=headers)
    assert status_resp.status_code == 200
    assert len(status_resp.json()["tasks"]) == 1
    assert status_resp.json()["tasks"][0]["status"] == "completed"

    # Filter by action_type=fill_form
    type_resp = await client.get("/api/v1/browser/tasks?action_type=fill_form", headers=headers)
    assert type_resp.status_code == 200
    assert len(type_resp.json()["tasks"]) == 1
    assert type_resp.json()["tasks"][0]["action_type"] == "fill_form"


@pytest.mark.anyio
async def test_browser_navigate_inspect_endpoint(client: httpx.AsyncClient) -> None:
    """Navigate to target URL, inspect DOM structure, and return semantic components."""
    email = f"nav_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/browser/navigate",
        json={"url": "https://example.com", "timeout_seconds": 15},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "example.com" in data["url"]
    assert data["status"] in ("success", "error")
    assert isinstance(data["headings"], list)
    assert isinstance(data["links"], list)
    assert isinstance(data["forms"], list)
    assert isinstance(data["meta"], dict)


@pytest.mark.anyio
async def test_browser_extract_tables_and_links(client: httpx.AsyncClient) -> None:
    """Extract structured elements (tables, links, headings, text) from a web page."""
    email = f"extract_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/browser/extract",
        json={"url": "https://example.com", "extract_type": "all", "max_items": 20},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "example.com" in data["url"]
    assert isinstance(data["tables"], list)
    assert isinstance(data["links"], list)
    assert isinstance(data["headings"], list)
    assert isinstance(data["text_excerpt"], str)


@pytest.mark.anyio
async def test_browser_screenshot_endpoint(client: httpx.AsyncClient) -> None:
    """Capture a visual snapshot representation of a target webpage."""
    email = f"shot_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/browser/screenshot",
        json={"url": "https://example.com", "width": 1280, "height": 800},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "example.com" in data["url"]
    assert "screenshot_url" in data
    assert data["width"] == 1280
    assert data["height"] == 800
    assert data["status"] == "success"
    assert "timestamp" in data


@pytest.mark.anyio
async def test_browser_execute_flow(client: httpx.AsyncClient) -> None:
    """Execute an autonomous multi-step browser automation workflow and verify auto-save."""
    email = f"flow_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    flow_payload = {
        "url": "https://example.com",
        "title": "Example Domain Autonomous Inspection",
        "actions": [
            {"type": "navigate"},
            {"type": "extract", "extract_type": "all"},
            {"type": "wait", "seconds": 0.1},
        ],
        "save_task": True,
        "tags": ["autonomous", "inspection"],
    }

    resp = await client.post("/api/v1/browser/execute", json=flow_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("completed", "confirmation_required")
    assert len(data["steps_executed"]) >= 2
    assert data["task_id"] is not None

    # Verify task was saved in user's library
    task_resp = await client.get(f"/api/v1/browser/tasks/{data['task_id']}", headers=headers)
    assert task_resp.status_code == 200
    saved_task = task_resp.json()["task"]
    assert saved_task["id"] == data["task_id"]
    assert saved_task["title"] == "Example Domain Autonomous Inspection"


@pytest.mark.anyio
async def test_browser_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """User B cannot access, update, or delete User A's browser task (404 Not Found)."""
    headers_a, _ = await _get_auth(client, f"tenant_a_browser_{uuid.uuid4().hex[:8]}@example.com")
    headers_b, _ = await _get_auth(client, f"tenant_b_browser_{uuid.uuid4().hex[:8]}@example.com")

    # Tenant A creates a browser task
    create_resp = await client.post(
        "/api/v1/browser/tasks",
        json={
            "url": "https://tenant-a-private.internal/dashboard",
            "title": "Tenant A Private Metric Scrape",
            "tags": ["confidential"],
        },
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    task_a_id = create_resp.json()["task"]["id"]

    # Tenant B tries to get Tenant A's task -> 404
    get_b_resp = await client.get(f"/api/v1/browser/tasks/{task_a_id}", headers=headers_b)
    assert get_b_resp.status_code == 404

    # Tenant B tries to patch Tenant A's task -> 404
    patch_b_resp = await client.patch(
        f"/api/v1/browser/tasks/{task_a_id}",
        json={"title": "Hacked Title"},
        headers=headers_b,
    )
    assert patch_b_resp.status_code == 404

    # Tenant B tries to delete Tenant A's task -> 404
    del_b_resp = await client.delete(f"/api/v1/browser/tasks/{task_a_id}", headers=headers_b)
    assert del_b_resp.status_code == 404

    # Tenant A can still fetch their own task
    get_a_resp = await client.get(f"/api/v1/browser/tasks/{task_a_id}", headers=headers_a)
    assert get_a_resp.status_code == 200
    assert get_a_resp.json()["task"]["title"] == "Tenant A Private Metric Scrape"


@pytest.mark.anyio
async def test_chat_browser_grounding(client: httpx.AsyncClient) -> None:
    """Chat Coordinator routes browser queries to 'browser' agent."""
    email = f"chat_browser_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        json={"message": "Please browse website https://example.com and inspect dom elements for me."},
        headers=headers,
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert data["agent_slug"] == "browser"
    assert len(data["response"]) > 10


@pytest.mark.anyio
async def test_chat_browser_offline_tasks_count(client: httpx.AsyncClient) -> None:
    """Chat coordinator offline fallback reports authentic count of user's browser tasks."""
    email = f"offline_browser_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    # 1. Ask before saving any task -> 0 tasks message
    resp_empty = await client.post(
        "/api/v1/runtime/chat",
        json={"message": "What browser tasks do I have in my library?", "provider": "offline"},
        headers=headers,
    )
    assert resp_empty.status_code == 200
    assert "no saved browser automation tasks" in resp_empty.json()["response"].lower()

    # 2. Save a task
    await client.post(
        "/api/v1/browser/tasks",
        json={
            "url": "https://news.ycombinator.com",
            "title": "Hacker News Scrape",
            "action_type": "extract",
            "status": "completed",
        },
        headers=headers,
    )

    # 3. Ask again -> confirms 1 browser task
    resp_one = await client.post(
        "/api/v1/runtime/chat",
        json={"message": "List my browser tasks in my library", "provider": "offline"},
        headers=headers,
    )
    assert resp_one.status_code == 200
    res_text = resp_one.json()["response"]
    assert "1 browser automation task" in res_text
    assert "Hacker News Scrape" in res_text
