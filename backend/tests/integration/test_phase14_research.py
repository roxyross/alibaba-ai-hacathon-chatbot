"""Phase 14 Master Integration Test Suite: Autonomous Web Research & Real-Time Information Retrieval Engine.

Verifies:
1. Fresh user starts with clean empty research reports (0 reports).
2. Research report creation and retrieval (POST/GET /api/v1/research/reports).
3. Research report patching and mutation (PATCH /api/v1/research/{id}).
4. Research report deletion (DELETE /api/v1/research/{id}).
5. Search and tag filtering on research reports.
6. One-shot live web search endpoint (POST /api/v1/research/search).
7. Autonomous deep research workflow with citations and auto-save (POST /api/v1/research/deep-research).
8. Web URL primary text extraction endpoint (POST /api/v1/research/fetch-url).
9. Strict multi-tenant isolation: User B cannot view, update, or delete User A's reports (404 Not Found).
10. Multi-agent chat runtime grounding with live web search and citations.
11. Multi-agent chat offline fallback with authentic research reports library count.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.main import app
from app.research.repository import clear_in_memory_stores


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
async def test_research_empty_state(client: httpx.AsyncClient) -> None:
    """A freshly authenticated user has 0 saved research reports and 0 mock cards."""
    email = f"fresh_research_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.get("/api/v1/research", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reports"] == []
    assert data["total"] == 0


@pytest.mark.anyio
async def test_create_and_get_research_report(client: httpx.AsyncClient) -> None:
    """Create a research report and verify its retrieval with full schema validation."""
    email = f"researcher_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    payload = {
        "title": "Quantum Computing State of the Art",
        "query": "Quantum computing fault tolerance and error correction in 2026",
        "summary": "Recent advances in neutral atom and superconducting qubits demonstrate logical qubits with lower error rates.",
        "findings": [
            {
                "theme": "Error Correction",
                "claim": "Logical qubits have demonstrated threshold error rates below 0.1%.",
                "source_indices": [1],
                "confidence": "high",
            }
        ],
        "sources": [
            {
                "title": "Quantum Computing Review 2026",
                "url": "https://nature.com/articles/quantum-2026",
                "snippet": "Logical qubit error suppression demonstrated.",
                "domain": "nature.com",
            }
        ],
        "confidence": "high",
        "depth": "deep",
        "tags": ["quantum", "physics", "hardware"],
    }

    create_resp = await client.post("/api/v1/research", json=payload, headers=headers)
    assert create_resp.status_code == 201
    created = create_resp.json()["report"]
    report_id = created["id"]
    assert created["title"] == "Quantum Computing State of the Art"
    assert created["confidence"] == "high"
    assert created["tags"] == ["quantum", "physics", "hardware"]

    get_resp = await client.get(f"/api/v1/research/{report_id}", headers=headers)
    assert get_resp.status_code == 200
    report = get_resp.json()["report"]
    assert report["id"] == report_id
    assert report["query"] == payload["query"]
    assert len(report["findings"]) == 1
    assert len(report["sources"]) == 1


@pytest.mark.anyio
async def test_update_research_report(client: httpx.AsyncClient) -> None:
    """Patch and mutate an existing research report."""
    email = f"patch_research_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/research",
        json={
            "query": "Solid state batteries electric vehicles",
            "summary": "Solid state batteries offer higher energy density.",
            "confidence": "medium",
            "tags": ["battery", "ev"],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    rid = create_resp.json()["report"]["id"]

    patch_resp = await client.patch(
        f"/api/v1/research/{rid}",
        json={
            "title": "Solid-State Battery Breakthroughs (Updated)",
            "confidence": "high",
            "tags": ["battery", "ev", "materials"],
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()["report"]
    assert updated["title"] == "Solid-State Battery Breakthroughs (Updated)"
    assert updated["confidence"] == "high"
    assert "materials" in updated["tags"]


@pytest.mark.anyio
async def test_delete_research_report(client: httpx.AsyncClient) -> None:
    """Delete a research report and verify 404 on subsequent lookups."""
    email = f"del_research_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/research",
        json={
            "query": "Temporary topic to be deleted",
            "summary": "This report will be deleted immediately.",
        },
        headers=headers,
    )
    rid = create_resp.json()["report"]["id"]

    del_resp = await client.delete(f"/api/v1/research/{rid}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/research/{rid}", headers=headers)
    assert get_resp.status_code == 404


@pytest.mark.anyio
async def test_research_search_and_tag_filtering(client: httpx.AsyncClient) -> None:
    """Filter research reports by text search query and categorical tags."""
    email = f"filter_research_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/research",
        json={
            "title": "CRISPR Therapeutics Oncology Pipeline",
            "query": "CRISPR gene editing oncology clinical trials",
            "summary": "Gene editing trials show promising remission rates in hematologic malignancies.",
            "tags": ["biotech", "genetics"],
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/research",
        json={
            "title": "Autonomous Drone Fleet Telemetry",
            "query": "Drone mesh networks communication protocols",
            "summary": "Distributed ad-hoc networks maintain routing stability under packet loss.",
            "tags": ["robotics", "iot"],
        },
        headers=headers,
    )

    # Search for CRISPR
    search_resp = await client.get("/api/v1/research?search=CRISPR", headers=headers)
    assert search_resp.status_code == 200
    assert len(search_resp.json()["reports"]) == 1
    assert "CRISPR" in search_resp.json()["reports"][0]["title"]

    # Tag filter for robotics
    tag_resp = await client.get("/api/v1/research?tag=robotics", headers=headers)
    assert tag_resp.status_code == 200
    assert len(tag_resp.json()["reports"]) == 1
    assert "Drone" in tag_resp.json()["reports"][0]["title"]


@pytest.mark.anyio
async def test_live_web_search_endpoint(client: httpx.AsyncClient) -> None:
    """Execute live web search endpoint and verify schema."""
    email = f"search_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/research/search",
        json={"query": "fastapi python async framework", "num_results": 4},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "fastapi python async framework"
    assert isinstance(data["results"], list)


@pytest.mark.anyio
async def test_deep_research_synthesis_and_save(client: httpx.AsyncClient) -> None:
    """Execute autonomous deep research pipeline and verify report auto-saving."""
    email = f"deep_researcher_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/research/deep-research",
        json={
            "query": "Comparison of PostgreSQL vs Redis for high throughput session storage",
            "depth": "deep",
            "save_report": True,
            "title": "PostgreSQL vs Redis Session Benchmarks",
            "tags": ["database", "benchmark", "architecture"],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "PostgreSQL vs Redis" in data["title"]
    assert len(data["sub_queries"]) >= 2
    assert len(data["findings"]) >= 1
    assert len(data["sources"]) >= 1
    assert len(data["citations"]) >= 1
    assert data["confidence"] in ("high", "medium", "low")
    assert data["report_id"] is not None

    # Verify report was persisted in the repository
    rep_resp = await client.get(f"/api/v1/research/{data['report_id']}", headers=headers)
    assert rep_resp.status_code == 200
    saved = rep_resp.json()["report"]
    assert saved["id"] == data["report_id"]
    assert saved["title"] == "PostgreSQL vs Redis Session Benchmarks"


@pytest.mark.anyio
async def test_fetch_url_endpoint(client: httpx.AsyncClient) -> None:
    """Test web page content extraction endpoint."""
    email = f"fetch_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/research/fetch-url",
        json={"url": "https://example.com", "max_chars": 2000},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://example.com"
    assert "example.com" in data["domain"]
    assert isinstance(data["title"], str)


@pytest.mark.anyio
async def test_research_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """User B cannot access, update, or delete User A's research report (404 Not Found)."""
    headers_a, _ = await _get_auth(client, f"tenant_a_{uuid.uuid4().hex[:8]}@example.com")
    headers_b, _ = await _get_auth(client, f"tenant_b_{uuid.uuid4().hex[:8]}@example.com")

    # Tenant A creates a research report
    create_resp = await client.post(
        "/api/v1/research",
        json={
            "title": "Tenant A Confidential Market Analysis",
            "query": "Proprietary market expansion strategies 2026",
            "summary": "Internal projections and competitor analysis for market entry.",
            "tags": ["confidential"],
        },
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    report_a_id = create_resp.json()["report"]["id"]

    # Tenant B tries to get Tenant A's report -> 404
    get_b_resp = await client.get(f"/api/v1/research/{report_a_id}", headers=headers_b)
    assert get_b_resp.status_code == 404

    # Tenant B tries to patch Tenant A's report -> 404
    patch_b_resp = await client.patch(
        f"/api/v1/research/{report_a_id}",
        json={"title": "Hacked Title"},
        headers=headers_b,
    )
    assert patch_b_resp.status_code == 404

    # Tenant B tries to delete Tenant A's report -> 404
    del_b_resp = await client.delete(f"/api/v1/research/{report_a_id}", headers=headers_b)
    assert del_b_resp.status_code == 404

    # Tenant A can still fetch their own report
    get_a_resp = await client.get(f"/api/v1/research/{report_a_id}", headers=headers_a)
    assert get_a_resp.status_code == 200
    assert get_a_resp.json()["report"]["title"] == "Tenant A Confidential Market Analysis"


@pytest.mark.anyio
async def test_chat_research_grounding(client: httpx.AsyncClient) -> None:
    """Chat Coordinator routes research queries to 'research' agent with live sources context."""
    email = f"chat_researcher_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        json={"message": "What is the latest status of deepseek r1 reasoning model and benchmarks?"},
        headers=headers,
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert data["agent_slug"] == "research"
    assert len(data["response"]) > 20


@pytest.mark.anyio
async def test_chat_research_offline_reports_count(client: httpx.AsyncClient) -> None:
    """Chat coordinator offline fallback reports authentic count of user's saved research reports."""
    email = f"offline_research_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    # 1. Ask before saving any report -> 0 reports message
    resp_empty = await client.post(
        "/api/v1/runtime/chat",
        json={"message": "Do I have any saved research reports or investigations in my library?", "provider": "offline"},
        headers=headers,
    )
    assert resp_empty.status_code == 200
    assert "no saved research reports" in resp_empty.json()["response"].lower()

    # 2. Save a report
    await client.post(
        "/api/v1/research",
        json={
            "title": "Synthetic Biology Roadmap",
            "query": "DNA synthesis throughput and enzymatic methods",
            "summary": "Enzymatic DNA synthesis eliminates toxic organic reagents and extends length limits.",
        },
        headers=headers,
    )

    # 3. Ask again -> confirms 1 saved research report
    resp_one = await client.post(
        "/api/v1/runtime/chat",
        json={"message": "Show me my saved research reports in my library", "provider": "offline"},
        headers=headers,
    )
    assert resp_one.status_code == 200
    res_text = resp_one.json()["response"]
    assert "1 saved research report" in res_text
    assert "Synthetic Biology Roadmap" in res_text


@pytest.mark.anyio
async def test_chat_streaming_research_grounding(client: httpx.AsyncClient) -> None:
    """Verify streaming chat runtime grounds research queries and saved reports library."""
    email = f"stream_researcher_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    # 1. Ask via stream before saving any report -> 0 reports message
    resp_empty = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "Do I have any saved research reports in my library?", "provider": "offline"},
        headers=headers,
    )
    assert resp_empty.status_code == 200
    empty_stream = resp_empty.text
    assert "data:" in empty_stream
    assert "no saved research reports" in empty_stream.lower()

    # 2. Save a report
    create_resp = await client.post(
        "/api/v1/research",
        json={
            "title": "Autonomous AI Agents in Healthcare",
            "query": "Clinical agentic workflows FDA clearance",
            "summary": "Agentic workflows demonstrate superior triage accuracy in multi-center trials.",
            "confidence": "high",
            "tags": ["healthcare", "agents"],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201

    # 3. Ask via stream again -> confirms 1 saved research report
    resp_one = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "Show me my saved research reports in my library", "provider": "offline"},
        headers=headers,
    )
    assert resp_one.status_code == 200
    one_stream = resp_one.text
    assert "data:" in one_stream
    assert "1 saved research report" in one_stream
    assert "Autonomous AI Agents in Healthcare" in one_stream

