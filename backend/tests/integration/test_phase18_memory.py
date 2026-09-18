"""Phase 18 Integration Tests: Autonomous Semantic Memory & Memory Curator Studio.

Verifies:
1. Clean zero-state for new users (0 memories, 0 reports).
2. Semantic memory CRUD (store, get, update, soft-delete, restore, permanent purge).
3. Strict multi-tenant isolation (404 on unowned memory access or mutation).
4. Tag and importance filtering.
5. Scored semantic and keyword retrieval endpoint.
6. Autonomous Memory Curator run execution, diff report generation, and history logs.
7. Curator policy configuration update.
8. Telemetry and stats computation.
9. GDPR portable data export.
10. Complete memory purge ("right to be forgotten").
11. Chat coordinator semantic memory grounding.
12. Authentic offline fallback reporting memory statistics.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, "src")

from app.main import app
from app.memory.repository import clear_in_memory_stores


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

@pytest.mark.asyncio
async def test_memory_empty_state(client: httpx.AsyncClient) -> None:
    """Fresh account has zero memories and zero curator reports."""
    headers, _ = await _get_auth(client, f"mem_empty_{uuid.uuid4().hex[:6]}@example.com")

    res = await client.get("/api/v1/memory/entries", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["entries"] == []
    assert data["total"] == 0

    stats_res = await client.get("/api/v1/memory/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_memories"] == 0
    assert stats["active_memories"] == 0
    assert stats["forever_memories"] == 0
    assert stats["soft_deleted_memories"] == 0
    assert stats["curator_runs_count"] == 0


@pytest.mark.asyncio
async def test_store_and_get_memory(client: httpx.AsyncClient) -> None:
    """User can store a new long-term semantic memory and retrieve it by ID."""
    headers, _ = await _get_auth(client, f"mem_store_{uuid.uuid4().hex[:6]}@example.com")

    payload = {
        "content": "User prefers concise responses with bullet points.",
        "importance": "high",
        "source": "user:explicit",
        "tags": ["preferences", "formatting"],
    }
    res = await client.post("/api/v1/memory/entries", headers=headers, json=payload)
    assert res.status_code == 201
    mem = res.json()
    assert mem["id"] is not None
    assert mem["content"] == payload["content"]
    assert mem["importance"] == "high"
    assert "preferences" in mem["tags"]
    assert mem["is_soft_deleted"] is False

    # Retrieve by ID
    get_res = await client.get(f"/api/v1/memory/entries/{mem['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == mem["id"]


@pytest.mark.asyncio
async def test_update_and_filter_memories(client: httpx.AsyncClient) -> None:
    """Update memory and test filtering by tag and importance."""
    headers, _ = await _get_auth(client, f"mem_filter_{uuid.uuid4().hex[:6]}@example.com")

    # Create 2 memories
    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={
            "content": "My native language is Urdu.",
            "importance": "forever",
            "tags": ["language", "identity"],
        },
    )
    m2_res = await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={
            "content": "I am working on Project Alpha.",
            "importance": "normal",
            "tags": ["work", "project"],
        },
    )
    m2 = m2_res.json()

    # Update m2
    patch_res = await client.patch(
        f"/api/v1/memory/entries/{m2['id']}",
        headers=headers,
        json={"importance": "high", "tags": ["work", "project", "active"]},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["importance"] == "high"
    assert "active" in patch_res.json()["tags"]

    # Filter by tag
    list_tag = await client.get("/api/v1/memory/entries?tag=language", headers=headers)
    assert list_tag.status_code == 200
    assert list_tag.json()["total"] == 1
    assert "Urdu" in list_tag.json()["entries"][0]["content"]

    # Filter by importance
    list_imp = await client.get("/api/v1/memory/entries?importance=forever", headers=headers)
    assert list_imp.status_code == 200
    assert list_imp.json()["total"] == 1


@pytest.mark.asyncio
async def test_soft_delete_and_restore_memory(client: httpx.AsyncClient) -> None:
    """Soft-deleted memory is hidden from active list but can be restored within grace period."""
    headers, _ = await _get_auth(client, f"mem_softdel_{uuid.uuid4().hex[:6]}@example.com")

    create_res = await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Temporary scratchpad note.", "importance": "low"},
    )
    mem_id = create_res.json()["id"]

    # Soft delete
    del_res = await client.delete(f"/api/v1/memory/entries/{mem_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify not in default active list
    active_list = await client.get("/api/v1/memory/entries", headers=headers)
    assert active_list.json()["total"] == 0

    # Verify present when include_soft_deleted=true
    all_list = await client.get("/api/v1/memory/entries?include_soft_deleted=true", headers=headers)
    assert all_list.json()["total"] == 1
    assert all_list.json()["entries"][0]["is_soft_deleted"] is True

    # Restore
    restore_res = await client.post(f"/api/v1/memory/entries/{mem_id}/restore", headers=headers)
    assert restore_res.status_code == 200
    assert restore_res.json()["is_soft_deleted"] is False

    # Now appears in default active list again
    active_list2 = await client.get("/api/v1/memory/entries", headers=headers)
    assert active_list2.json()["total"] == 1


@pytest.mark.asyncio
async def test_permanent_delete_memory(client: httpx.AsyncClient) -> None:
    """Permanent delete completely purges the memory."""
    headers, _ = await _get_auth(client, f"mem_permdel_{uuid.uuid4().hex[:6]}@example.com")

    create_res = await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Sensitive secret to purge immediately.", "importance": "high"},
    )
    mem_id = create_res.json()["id"]

    del_res = await client.delete(
        f"/api/v1/memory/entries/{mem_id}?permanent=true", headers=headers
    )
    assert del_res.status_code == 204

    # GET should return 404
    get_res = await client.get(f"/api/v1/memory/entries/{mem_id}", headers=headers)
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_memory_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """User B cannot read, update, or delete User A's memory (returns 404)."""
    headers_a, _ = await _get_auth(client, f"user_a_{uuid.uuid4().hex[:6]}@example.com")
    headers_b, _ = await _get_auth(client, f"user_b_{uuid.uuid4().hex[:6]}@example.com")

    create_res = await client.post(
        "/api/v1/memory/entries",
        headers=headers_a,
        json={"content": "User A secret banking preference.", "importance": "high"},
    )
    mem_id = create_res.json()["id"]

    # User B attempts read -> 404
    get_b = await client.get(f"/api/v1/memory/entries/{mem_id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B attempts update -> 404
    patch_b = await client.patch(
        f"/api/v1/memory/entries/{mem_id}",
        headers=headers_b,
        json={"content": "Hacked content"},
    )
    assert patch_b.status_code == 404

    # User B attempts delete -> 404
    del_b = await client.delete(f"/api/v1/memory/entries/{mem_id}", headers=headers_b)
    assert del_b.status_code == 404


@pytest.mark.asyncio
async def test_retrieve_memory_endpoint(client: httpx.AsyncClient) -> None:
    """Semantic/keyword retrieval matches relevant memories and increments retrieval_count."""
    headers, _ = await _get_auth(client, f"mem_retrieve_{uuid.uuid4().hex[:6]}@example.com")

    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={
            "content": "User prefers dark mode and high contrast themes.",
            "importance": "high",
            "tags": ["theme", "ui"],
        },
    )
    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={
            "content": "User lives in Islamabad, Pakistan.",
            "importance": "forever",
            "tags": ["location"],
        },
    )

    query_payload = {
        "query": "what theme or dark mode does the user like?",
        "top_k": 5,
    }
    res = await client.post("/api/v1/memory/retrieve", headers=headers, json=query_payload)
    assert res.status_code == 200
    data = res.json()
    assert len(data["entries"]) >= 1
    top_match = data["entries"][0]
    assert "dark mode" in top_match["content"]
    assert top_match["score"] > 0.0

    # Check that retrieval_count was incremented
    mem_check = await client.get(f"/api/v1/memory/entries/{top_match['entry_id']}", headers=headers)
    assert mem_check.json()["retrieval_count"] >= 1


@pytest.mark.asyncio
async def test_curator_run_and_report(client: httpx.AsyncClient) -> None:
    """Triggering curator pass executes without errors and records audit report."""
    headers, _ = await _get_auth(client, f"mem_curator_{uuid.uuid4().hex[:6]}@example.com")

    # Create memories
    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Memory entry 1", "importance": "normal", "tags": ["test"]},
    )
    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Memory entry 2", "importance": "forever", "tags": ["test"]},
    )

    run_res = await client.post("/api/v1/memory/curator/run", headers=headers)
    assert run_res.status_code == 200
    report = run_res.json()
    assert report["status"] == "completed"
    assert report["entries_scanned"] == 2
    assert report["diff_summary"] is not None

    # Verify report in history list
    reports_res = await client.get("/api/v1/memory/curator/reports", headers=headers)
    assert reports_res.status_code == 200
    assert len(reports_res.json()) >= 1
    assert reports_res.json()[0]["id"] == report["id"]


@pytest.mark.asyncio
async def test_curator_policy_get_and_update(client: httpx.AsyncClient) -> None:
    """Verify curator pruning policy configuration read and update."""
    headers, _ = await _get_auth(client, f"mem_policy_{uuid.uuid4().hex[:6]}@example.com")

    get_res = await client.get("/api/v1/memory/curator/policy", headers=headers)
    assert get_res.status_code == 200
    policy = get_res.json()
    assert policy["summarize_after_days"] == 30

    # Update policy
    put_res = await client.put(
        "/api/v1/memory/curator/policy",
        headers=headers,
        json={
            "summarize_after_days": 45,
            "cluster_min_size": 4,
            "soft_delete_never_retrieved_days": 120,
            "hard_delete_after_days": 60,
            "notify_on_changes": True,
        },
    )
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["summarize_after_days"] == 45
    assert updated["cluster_min_size"] == 4


@pytest.mark.asyncio
async def test_memory_stats_endpoint(client: httpx.AsyncClient) -> None:
    """Verify stats endpoint returns accurate counts of active, forever, and soft-deleted memories."""
    headers, _ = await _get_auth(client, f"mem_stats_{uuid.uuid4().hex[:6]}@example.com")

    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Forever Memory", "importance": "forever"},
    )
    m2 = await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Normal Memory", "importance": "normal"},
    )
    # Soft delete m2
    await client.delete(f"/api/v1/memory/entries/{m2.json()['id']}", headers=headers)

    stats_res = await client.get("/api/v1/memory/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_memories"] == 2
    assert stats["active_memories"] == 1
    assert stats["forever_memories"] == 1
    assert stats["soft_deleted_memories"] == 1


@pytest.mark.asyncio
async def test_export_user_data(client: httpx.AsyncClient) -> None:
    """GDPR portable JSON data export includes all user memories and metadata."""
    headers, uid = await _get_auth(client, f"mem_export_{uuid.uuid4().hex[:6]}@example.com")

    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Exportable knowledge item.", "importance": "high"},
    )

    res = await client.get("/api/v1/memory/export", headers=headers)
    assert res.status_code == 200
    export = res.json()
    assert export["user_id"] == uid
    assert export["total_memories"] == 1
    assert len(export["memories"]) == 1
    assert export["memories"][0]["content"] == "Exportable knowledge item."


@pytest.mark.asyncio
async def test_purge_all_memories(client: httpx.AsyncClient) -> None:
    """Permanent erasure removes all user memories from the database/vault."""
    headers, _ = await _get_auth(client, f"mem_purge_{uuid.uuid4().hex[:6]}@example.com")

    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Memory 1", "importance": "normal"},
    )
    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={"content": "Memory 2", "importance": "high"},
    )

    purge_res = await client.delete("/api/v1/memory/purge-all", headers=headers)
    assert purge_res.status_code == 200
    assert purge_res.json()["purged_count"] == 2

    # Verify completely empty
    list_res = await client.get(
        "/api/v1/memory/entries?include_soft_deleted=true", headers=headers
    )
    assert list_res.json()["total"] == 0


@pytest.mark.asyncio
async def test_chat_memory_grounding(client: httpx.AsyncClient) -> None:
    """Chat coordinator injects semantic memory context when user intent matches memory keywords."""
    headers, _ = await _get_auth(client, f"mem_chatground_{uuid.uuid4().hex[:6]}@example.com")

    # Pre-seed a memory
    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={
            "content": "User prefers all responses to be formatted in markdown tables.",
            "importance": "forever",
            "tags": ["preferences"],
        },
    )

    # Mock AI Router to capture injected system messages
    mock_response = AsyncMock()
    mock_response.content = "I recall that you prefer responses formatted in markdown tables."
    mock_response.provider = "mock_provider"
    mock_response.model = "mock_model"

    with patch("app.api.v1.runtime.AIRouter.route", return_value=mock_response) as mock_route:
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={"message": "What do you remember about my formatting preference?"},
        )
        assert chat_res.status_code == 200
        assert mock_route.called
        call_request = mock_route.call_args[0][0]
        system_msgs = [m.content for m in call_request.messages if m.role.value == "system"]
        memory_grounded = any("SEMANTIC MEMORY CONTEXT" in sm for sm in system_msgs)
        assert memory_grounded is True


@pytest.mark.asyncio
async def test_chat_memory_offline_fallback(client: httpx.AsyncClient) -> None:
    """When LLM router fails, chat coordinator returns authentic offline fallback with memory telemetry."""
    headers, _ = await _get_auth(client, f"mem_chatoffline_{uuid.uuid4().hex[:6]}@example.com")

    # Pre-seed a memory
    await client.post(
        "/api/v1/memory/entries",
        headers=headers,
        json={
            "content": "Preferred editor: VS Code / Neovim.",
            "importance": "forever",
            "tags": ["tools"],
        },
    )

    # Mock AIRouter.route to raise an exception simulating offline failure
    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Gateway unreachable")):
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={"message": "What memories or preferences do you have stored for me?"},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["agent_slug"] == "memory"
        assert "active long-term memories in your semantic vault" in data["response"]
        assert "Preferred editor: VS Code / Neovim" in data["response"]
