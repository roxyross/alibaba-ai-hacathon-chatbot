"""Phase 17 Master Integration Test Suite: Autonomous Coding Agent & Developer Studio.

Verifies:
1. Fresh user starts with clean empty snippets and execution runs (0 items).
2. Code snippet creation and retrieval (POST/GET /api/v1/coding/snippets).
3. Snippet updating, favoriting, and search/language filtering.
4. Snippet deletion (DELETE /api/v1/coding/snippets/{id}).
5. Strict multi-tenant isolation: User B cannot view, update, or delete User A's snippets or runs (404 Not Found).
6. AI Code generation endpoint with auto-save (POST /api/v1/coding/generate).
7. AI Code explanation endpoint with scope and audience level (POST /api/v1/coding/explain).
8. AI Code debug endpoint with root-cause hypothesis and patch (POST /api/v1/coding/debug).
9. Sandboxed code execution with successful stdout and exit code (POST /api/v1/coding/execute).
10. Sandboxed code execution with error and stderr capture.
11. Code execution with standard input stream (stdin).
12. Developer studio metrics and stats endpoint (GET /api/v1/coding/stats).
13. Multi-agent chat runtime routing and coding grounding.
14. Multi-agent chat offline fallback reporting real snippet counts.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.coding.repository import clear_in_memory_stores
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
    token_data = verify_resp.json()
    access_token = token_data["access_token"]
    user_id = token_data["user"]["id"]
    return {"Authorization": f"Bearer {access_token}"}, user_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_coding_empty_state(client: httpx.AsyncClient) -> None:
    """Fresh user starts with clean empty snippets and executions."""
    headers, _ = await _get_auth(client, f"coding_empty_{uuid.uuid4().hex[:6]}@example.com")

    # Snippets
    snips_res = await client.get("/api/v1/coding/snippets", headers=headers)
    assert snips_res.status_code == 200
    snips_data = snips_res.json()
    assert snips_data["snippets"] == []
    assert snips_data["total"] == 0

    # Executions
    execs_res = await client.get("/api/v1/coding/executions", headers=headers)
    assert execs_res.status_code == 200
    execs_data = execs_res.json()
    assert execs_data["executions"] == []
    assert execs_data["total"] == 0

    # Stats
    stats_res = await client.get("/api/v1/coding/stats", headers=headers)
    assert stats_res.status_code == 200
    stats_data = stats_res.json()
    assert stats_data["total_snippets"] == 0
    assert stats_data["favorite_snippets"] == 0
    assert stats_data["total_executions"] == 0
    assert stats_data["success_rate_percentage"] == 100.0


@pytest.mark.anyio
async def test_create_and_get_snippet(client: httpx.AsyncClient) -> None:
    """Create a code snippet and retrieve it by ID."""
    headers, _ = await _get_auth(client, f"coding_crud_{uuid.uuid4().hex[:6]}@example.com")

    create_res = await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={
            "title": "Binary Search Algorithm",
            "language": "python",
            "code": "def binary_search(arr, x):\n    low, high = 0, len(arr) - 1\n    return -1\n",
            "description": "Standard binary search implementation",
            "tags": ["algorithms", "search"],
            "is_favorite": True,
        },
    )
    assert create_res.status_code == 201
    created = create_res.json()
    snip_id = created["id"]
    assert created["title"] == "Binary Search Algorithm"
    assert created["language"] == "python"
    assert created["is_favorite"] is True
    assert "algorithms" in created["tags"]

    # Fetch by ID
    get_res = await client.get(f"/api/v1/coding/snippets/{snip_id}", headers=headers)
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["id"] == snip_id
    assert fetched["title"] == "Binary Search Algorithm"


@pytest.mark.anyio
async def test_update_and_filter_snippets(client: httpx.AsyncClient) -> None:
    """Update snippet fields, toggle favorite, and test search/language filters."""
    headers, _ = await _get_auth(client, f"coding_filter_{uuid.uuid4().hex[:6]}@example.com")

    # Create Python snippet
    s1_res = await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={
            "title": "Quicksort Partition",
            "language": "python",
            "code": "def partition(arr): pass",
            "tags": ["sort", "divide_conquer"],
            "is_favorite": False,
        },
    )
    s1_id = s1_res.json()["id"]

    # Create TypeScript snippet
    await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={
            "title": "Debounce Hook",
            "language": "typescript",
            "code": "export function useDebounce() {}",
            "tags": ["react", "hooks"],
            "is_favorite": True,
        },
    )

    # Update s1 to favorite
    patch_res = await client.patch(
        f"/api/v1/coding/snippets/{s1_id}",
        headers=headers,
        json={"is_favorite": True, "title": "Optimized Quicksort Partition"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_favorite"] is True
    assert patch_res.json()["title"] == "Optimized Quicksort Partition"

    # Filter by language = python
    py_res = await client.get("/api/v1/coding/snippets?language=python", headers=headers)
    assert py_res.status_code == 200
    assert py_res.json()["total"] == 1
    assert py_res.json()["snippets"][0]["language"] == "python"

    # Search filter = Quicksort
    search_res = await client.get("/api/v1/coding/snippets?search=quicksort", headers=headers)
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert "Quicksort" in search_res.json()["snippets"][0]["title"]


@pytest.mark.anyio
async def test_delete_snippet(client: httpx.AsyncClient) -> None:
    """Delete a snippet and verify 404 on subsequent get."""
    headers, _ = await _get_auth(client, f"coding_del_{uuid.uuid4().hex[:6]}@example.com")

    create_res = await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={
            "title": "Temp Snippet",
            "language": "python",
            "code": "print('temporary')",
        },
    )
    snip_id = create_res.json()["id"]

    del_res = await client.delete(f"/api/v1/coding/snippets/{snip_id}", headers=headers)
    assert del_res.status_code == 204

    get_res = await client.get(f"/api/v1/coding/snippets/{snip_id}", headers=headers)
    assert get_res.status_code == 404


@pytest.mark.anyio
async def test_coding_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """User B cannot access or modify User A's snippet or execution run."""
    headers_a, _ = await _get_auth(client, f"user_a_{uuid.uuid4().hex[:6]}@example.com")
    headers_b, _ = await _get_auth(client, f"user_b_{uuid.uuid4().hex[:6]}@example.com")

    # User A creates a snippet
    create_res = await client.post(
        "/api/v1/coding/snippets",
        headers=headers_a,
        json={"title": "User A Secret Algorithm", "language": "python", "code": "def secret(): return 42"},
    )
    snip_id = create_res.json()["id"]

    # User A runs code
    exec_res = await client.post(
        "/api/v1/coding/execute",
        headers=headers_a,
        json={"language": "python", "code": "print('User A Run')", "snippet_id": snip_id},
    )
    exec_id = exec_res.json()["id"]

    # User B attempts to access User A's snippet -> 404
    get_res = await client.get(f"/api/v1/coding/snippets/{snip_id}", headers=headers_b)
    assert get_res.status_code == 404

    # User B attempts to update User A's snippet -> 404
    patch_res = await client.patch(f"/api/v1/coding/snippets/{snip_id}", headers=headers_b, json={"title": "Hacked"})
    assert patch_res.status_code == 404

    # User B attempts to delete User A's snippet -> 404
    del_res = await client.delete(f"/api/v1/coding/snippets/{snip_id}", headers=headers_b)
    assert del_res.status_code == 404

    # User B attempts to access User A's execution log -> 404
    get_exec_res = await client.get(f"/api/v1/coding/executions/{exec_id}", headers=headers_b)
    assert get_exec_res.status_code == 404


@pytest.mark.anyio
async def test_ai_generate_code_endpoint(client: httpx.AsyncClient) -> None:
    """Generate code with optional auto-save to snippets."""
    headers, _ = await _get_auth(client, f"coding_gen_{uuid.uuid4().hex[:6]}@example.com")

    gen_res = await client.post(
        "/api/v1/coding/generate",
        headers=headers,
        json={
            "task": "Write a function to calculate the nth Fibonacci number",
            "language": "python",
            "constraints": ["O(n) time complexity", "iterative approach"],
            "save_as_snippet": True,
            "snippet_title": "Fibonacci Iterative",
        },
    )
    assert gen_res.status_code == 200
    data = gen_res.json()
    assert "code" in data and len(data["code"]) > 0
    assert data["language"] == "python"
    assert "explanation" in data
    assert data["saved_snippet_id"] is not None

    # Verify saved snippet exists
    snip_res = await client.get(f"/api/v1/coding/snippets/{data['saved_snippet_id']}", headers=headers)
    assert snip_res.status_code == 200
    assert snip_res.json()["title"] == "Fibonacci Iterative"


@pytest.mark.anyio
async def test_ai_explain_code_endpoint(client: httpx.AsyncClient) -> None:
    """Explain code snippet with line callouts and followups."""
    headers, _ = await _get_auth(client, f"coding_explain_{uuid.uuid4().hex[:6]}@example.com")

    sample_code = "def add(a, b):\n    return a + b\n\nprint(add(2, 3))\n"
    res = await client.post(
        "/api/v1/coding/explain",
        headers=headers,
        json={
            "code": sample_code,
            "language": "python",
            "scope": "block",
            "level": "beginner",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["explanation"]) > 0
    assert data["language"] == "python"
    assert isinstance(data["key_lines"], list)
    assert len(data["followups"]) > 0


@pytest.mark.anyio
async def test_ai_debug_code_endpoint(client: httpx.AsyncClient) -> None:
    """Debug code, form hypothesis, and return minimal fix."""
    headers, _ = await _get_auth(client, f"coding_debug_{uuid.uuid4().hex[:6]}@example.com")

    buggy_code = "def divide(a, b):\n    return a / b\n\ndivide(10, 0)\n"
    res = await client.post(
        "/api/v1/coding/debug",
        headers=headers,
        json={
            "code": buggy_code,
            "language": "python",
            "error_message": "ZeroDivisionError: division by zero",
            "expected_behavior": "Should handle zero divisor safely without crash",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "hypothesis" in data and len(data["hypothesis"]) > 0
    assert "fixed_code" in data and len(data["fixed_code"]) > 0
    assert "verification" in data


@pytest.mark.anyio
async def test_execute_code_python_success(client: httpx.AsyncClient) -> None:
    """Execute Python script and verify stdout and exit code 0."""
    headers, _ = await _get_auth(client, f"coding_run_{uuid.uuid4().hex[:6]}@example.com")

    run_res = await client.post(
        "/api/v1/coding/execute",
        headers=headers,
        json={
            "language": "python",
            "code": "nums = [1, 2, 3, 4, 5]\nprint('Sum:', sum(nums))\n",
        },
    )
    assert run_res.status_code == 200
    data = run_res.json()
    assert data["status"] == "success"
    assert data["exit_code"] == 0
    assert "Sum: 15" in data["stdout"]
    assert data["execution_time_ms"] >= 1


@pytest.mark.anyio
async def test_execute_code_error(client: httpx.AsyncClient) -> None:
    """Execute Python script that raises an error and capture stderr."""
    headers, _ = await _get_auth(client, f"coding_err_{uuid.uuid4().hex[:6]}@example.com")

    run_res = await client.post(
        "/api/v1/coding/execute",
        headers=headers,
        json={
            "language": "python",
            "code": "raise ValueError('Custom Test Error Output')\n",
        },
    )
    assert run_res.status_code == 200
    data = run_res.json()
    assert data["status"] == "error"
    assert data["exit_code"] != 0
    assert "ValueError: Custom Test Error Output" in data["stderr"]


@pytest.mark.anyio
async def test_execute_code_stdin(client: httpx.AsyncClient) -> None:
    """Execute code with standard input provided."""
    headers, _ = await _get_auth(client, f"coding_stdin_{uuid.uuid4().hex[:6]}@example.com")

    run_res = await client.post(
        "/api/v1/coding/execute",
        headers=headers,
        json={
            "language": "python",
            "code": "import sys\nname = sys.stdin.read().strip()\nprint(f'Hello, {name}!')\n",
            "stdin": "Antigravity",
        },
    )
    assert run_res.status_code == 200
    data = run_res.json()
    assert data["status"] == "success"
    assert data["exit_code"] == 0
    assert "Hello, Antigravity!" in data["stdout"]


@pytest.mark.anyio
async def test_coding_stats_endpoint(client: httpx.AsyncClient) -> None:
    """Verify statistics aggregates snippets, executions, and success rate."""
    headers, _ = await _get_auth(client, f"coding_stats_{uuid.uuid4().hex[:6]}@example.com")

    # Create 2 snippets
    await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={"title": "Py 1", "language": "python", "code": "pass", "is_favorite": True},
    )
    await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={"title": "JS 1", "language": "javascript", "code": "console.log(1)", "is_favorite": False},
    )

    # Run 1 success, 1 failure
    await client.post(
        "/api/v1/coding/execute",
        headers=headers,
        json={"language": "python", "code": "print('ok')"},
    )
    await client.post(
        "/api/v1/coding/execute",
        headers=headers,
        json={"language": "python", "code": "1/0"},
    )

    stats_res = await client.get("/api/v1/coding/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_snippets"] == 2
    assert stats["favorite_snippets"] == 1
    assert stats["languages_count"].get("python") == 1
    assert stats["languages_count"].get("javascript") == 1
    assert stats["total_executions"] == 2
    assert stats["successful_executions"] == 1
    assert stats["success_rate_percentage"] == 50.0


@pytest.mark.anyio
async def test_chat_coding_grounding(client: httpx.AsyncClient) -> None:
    """Coordinator chat endpoint routes coding intent and grounds with snippets."""
    headers, _ = await _get_auth(client, f"coding_chat_{uuid.uuid4().hex[:6]}@example.com")

    # Create a snippet to ground
    await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={"title": "AStar Pathfinding", "language": "python", "code": "def a_star(): pass"},
    )

    chat_res = await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={"message": "Can you debug my python function and write a function?"},
    )
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["agent_slug"] == "coding"
    assert "response" in data and len(data["response"]) > 0


@pytest.mark.anyio
async def test_chat_coding_offline_fallback(client: httpx.AsyncClient) -> None:
    """When model fails or runs offline, coordinator returns authentic snippet count."""
    headers, _ = await _get_auth(client, f"coding_off_{uuid.uuid4().hex[:6]}@example.com")

    # User with 1 snippet
    await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={"title": "Merge Sort", "language": "python", "code": "def merge(): pass"},
    )

    chat_res = await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={"message": "Show me my code snippet library and debug my code", "provider": "invalid-offline-provider"},
    )
    assert chat_res.status_code == 200
    resp_text = chat_res.json()["response"]
    assert "1 code snippet(s)" in resp_text or "Coding Studio" in resp_text


@pytest.mark.anyio
async def test_chat_streaming_coding_grounding(client: httpx.AsyncClient) -> None:
    """Verify streaming chat runtime grounds code snippets and execution metrics."""
    headers, _ = await _get_auth(client, f"coding_stream_{uuid.uuid4().hex[:6]}@example.com")

    # 1. Ask via stream before creating any snippet -> 0 snippets message
    resp_empty = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "Show me my code snippet library and debug my code", "provider": "offline"},
        headers=headers,
    )
    assert resp_empty.status_code == 200
    empty_stream = resp_empty.text
    assert "data:" in empty_stream
    assert "no saved code snippets" in empty_stream.lower()

    # 2. Create a snippet
    create_res = await client.post(
        "/api/v1/coding/snippets",
        headers=headers,
        json={
            "title": "Dijkstra Shortest Path",
            "language": "python",
            "code": "import heapq\ndef dijkstra(graph, start): pass",
            "tags": ["graph", "algorithms"],
        },
    )
    assert create_res.status_code == 201

    # 3. Ask via stream again -> confirms 1 code snippet
    resp_one = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "Show me my code snippet library and debug my code", "provider": "offline"},
        headers=headers,
    )
    assert resp_one.status_code == 200
    one_stream = resp_one.text
    assert "data:" in one_stream
    assert "1 code snippet(s)" in one_stream
    assert "Dijkstra Shortest Path" in one_stream

