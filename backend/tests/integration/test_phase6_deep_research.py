"""Integration tests for Phase 6: Autonomous Deep Research Agent.

Verifies:
1. Multi-strategy query decomposition across diverse topic archetypes.
2. Live web search schema normalization, snippet extraction, and canonical domain parsing.
3. Primary source web page extraction (HTML cleanup, title parsing, script stripping).
4. Autonomous deep research synthesis: structured findings, confidence assessment, and citations.
5. Research report CRUD operations, search filtering, tag queries, and status updates.
6. Strict multi-tenant isolation (User B cannot view, modify, or delete User A's research).
7. Central ToolRegistry integration for research tools:
   - research_deep_investigate
   - research_live_search
   - research_fetch_page
   - research_list_reports
   - research_get_report
   - research_delete_report
   - research_export_to_vault
8. Agent Planner intent decomposition and routing to deep research tools.
9. Cross-grounding: Exporting completed research reports into Knowledge Vault document notes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient

from app.agent_runtime.planner import AgentPlanner
from app.auth.service import MagicLinkService
from app.main import app
from app.research.repository import ResearchRepository, clear_in_memory_stores
from app.research.service import ResearchService
from app.skills.schemas import SearchResult, WebSearchResponse
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest, ToolSource
from app.vault.service import VaultService


async def _create_second_user_client() -> AsyncClient:
    """Helper to mint a second authenticated client for tenant isolation testing."""
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    service = MagicLinkService()
    test_email = "research_tenant_b@example.com"
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
    """Ensure clean research and vault in-memory state before each test."""
    clear_in_memory_stores()
    VaultService.get_instance()._mem_documents.clear()
    VaultService.get_instance()._mem_chunks.clear()


@pytest.mark.asyncio
async def test_research_query_decomposition() -> None:
    """Verify targeted query decomposition across diverse topic patterns."""
    service = ResearchService.get_instance()

    # 1. Comparison query
    comp_queries = service.decompose_query("PyTorch vs JAX for deep learning research")
    assert len(comp_queries) >= 3
    assert any("comparison" in q.lower() or "vs" in q.lower() for q in comp_queries)

    # 2. Guide query
    guide_queries = service.decompose_query("How to build an autonomous agent in python")
    assert len(guide_queries) >= 3
    assert any("guide" in q.lower() or "best practices" in q.lower() for q in guide_queries)

    # 3. News / Trends query
    news_queries = service.decompose_query("Latest developments in quantum computing 2026")
    assert len(news_queries) >= 3
    assert any("latest" in q.lower() or "report" in q.lower() or "developments" in q.lower() for q in news_queries)

    # 4. Standard technical query
    std_queries = service.decompose_query("Alibaba Cloud Model Studio multi-agent orchestration")
    assert len(std_queries) >= 2
    assert "Alibaba Cloud Model Studio multi-agent orchestration" in std_queries[0]


@pytest.mark.asyncio
async def test_research_live_search_normalization() -> None:
    """Verify live web search schema normalization and domain parsing."""
    service = ResearchService.get_instance()

    mock_results = [
        SearchResult(
            title="FastAPI Documentation",
            url="https://fastapi.tiangolo.com/tutorial/first-steps/",
            snippet="FastAPI framework, high performance, easy to learn.",
            source="tavily",
        ),
        SearchResult(
            title="Python AsyncIO Guide",
            url="https://docs.python.org/3/library/asyncio.html",
            snippet="asyncio is a library to write concurrent code using the async/await syntax.",
            source="tavily",
        ),
    ]

    with patch.object(
        service.search_skill,
        "execute",
        new=AsyncMock(return_value=WebSearchResponse(query="FastAPI async", results=mock_results, total_results=2)),
    ):
        items = await service.search_web("FastAPI async", num_results=2)
        assert len(items) == 2

        first = items[0]
        assert first["title"] == "FastAPI Documentation"
        assert first["url"] == "https://fastapi.tiangolo.com/tutorial/first-steps/"
        assert first["domain"] == "fastapi.tiangolo.com"
        assert "FastAPI framework" in first["snippet"]

        second = items[1]
        assert second["domain"] == "docs.python.org"


@pytest.mark.asyncio
async def test_research_fetch_page_content() -> None:
    """Verify web page fetching, script/style stripping, and title extraction."""
    service = ResearchService.get_instance()

    html_content = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Autonomous Systems Report 2026</title>
        <style>body { background: #000; }</style>
        <script>console.log("tracking code");</script>
      </head>
      <body>
        <h1>Executive Overview</h1>
        <p>Autonomous AI agents coordinate multi-turn actions across heterogeneous APIs.</p>
        <script>var x = 123;</script>
      </body>
    </html>
    """

    mock_resp = httpx.Response(
        status_code=200,
        text=html_content,
        request=httpx.Request("GET", "https://example.com/reports/agents-2026"),
    )

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        res = await service.fetch_url("https://example.com/reports/agents-2026", max_chars=1000)
        assert res["status"] == "success"
        assert res["title"] == "Autonomous Systems Report 2026"
        assert res["domain"] == "example.com"
        assert "Autonomous AI agents coordinate" in res["content"]
        assert "console.log" not in res["content"]
        assert "background: #000" not in res["content"]


@pytest.mark.asyncio
async def test_autonomous_deep_research_synthesis_and_citations() -> None:
    """Verify autonomous deep research synthesis produces structured findings and citations."""
    service = ResearchService.get_instance()

    mock_sources = [
        {
            "title": "Alibaba Cloud Model Studio Deep Dive",
            "url": "https://alibabacloud.com/model-studio",
            "snippet": "Model Studio enables enterprise multi-agent workflows and customized model fine-tuning.",
            "domain": "alibabacloud.com",
            "published_date": None,
        },
        {
            "title": "Agentic Reasoning Architecture",
            "url": "https://research.org/agents-architecture",
            "snippet": "Coordinated planner and executor cycles provide verifiable audit trails.",
            "domain": "research.org",
            "published_date": None,
        },
        {
            "title": "Vector Retrieval Standards",
            "url": "https://standards.org/rag-vector-memory",
            "snippet": "Hybrid retrieval combining dense vectors and BM25 achieves optimal precision.",
            "domain": "standards.org",
            "published_date": None,
        },
    ]

    with patch.object(service, "search_web", new=AsyncMock(return_value=mock_sources)):
        res = await service.synthesize_research(
            topic="Alibaba Cloud Model Studio agentic capabilities",
            depth="deep",
            save_report=False,
        )

        assert res["topic"] == "Alibaba Cloud Model Studio agentic capabilities"
        assert len(res["summary"]) > 50
        assert len(res["findings"]) >= 2
        for f in res["findings"]:
            assert "theme" in f
            assert "claim" in f
            assert "confidence" in f
            assert "source_indices" in f
            assert len(f["source_indices"]) > 0

        assert len(res["citations"]) == 3
        assert "[1]" in res["citations"][0]
        assert "alibabacloud.com" in res["citations"][0]
        assert res["confidence"] == "high"
        assert len(res["next_actions"]) >= 2


@pytest.mark.asyncio
async def test_research_report_crud_and_persistence(authed_client: AsyncClient) -> None:
    """Verify research report creation, listing, searching, updating, and deletion via REST API."""
    # 1. Create a research report
    create_payload: dict[str, Any] = {
        "query": "Quantum Machine Learning Algorithms",
        "title": "Quantum ML Architectural Review",
        "summary": "Analysis of variational quantum eigensolvers and quantum neural networks.",
        "findings": [
            {
                "theme": "Variational Circuits",
                "claim": "Parameterized quantum circuits optimize loss functions via hybrid classical-quantum loops.",
                "confidence": "high",
                "source_indices": [1],
            }
        ],
        "sources": [
            {
                "title": "Quantum Computing Archive",
                "url": "https://quantum.org/papers/vqe",
                "snippet": "Hybrid quantum-classical optimization.",
                "domain": "quantum.org",
            }
        ],
        "confidence": "high",
        "depth": "deep",
        "tags": ["quantum", "machine_learning", "research"],
    }

    create_res = await authed_client.post("/api/v1/research/reports", json=create_payload)
    assert create_res.status_code == 201
    created = create_res.json()["report"]
    report_id = created["id"]
    assert created["title"] == "Quantum ML Architectural Review"
    assert created["tags"] == ["quantum", "machine_learning", "research"]

    # 2. List reports
    list_res = await authed_client.get("/api/v1/research/reports")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == report_id for r in list_data["reports"])

    # 3. Filter by search query
    search_res = await authed_client.get("/api/v1/research/reports?search=eigensolvers")
    assert search_res.status_code == 200
    assert len(search_res.json()["reports"]) >= 1

    # 4. Filter by tag
    tag_res = await authed_client.get("/api/v1/research/reports?tag=quantum")
    assert tag_res.status_code == 200
    assert len(tag_res.json()["reports"]) >= 1

    # 5. Get report details
    get_res = await authed_client.get(f"/api/v1/research/{report_id}")
    assert get_res.status_code == 200
    assert get_res.json()["report"]["id"] == report_id

    # 6. Update report
    patch_res = await authed_client.patch(
        f"/api/v1/research/{report_id}",
        json={"title": "Updated Quantum ML Review 2026", "confidence": "high"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["report"]["title"] == "Updated Quantum ML Review 2026"

    # 7. Delete report
    del_res = await authed_client.delete(f"/api/v1/research/{report_id}")
    assert del_res.status_code == 204

    # 8. Verify 404 after deletion
    get_after_del = await authed_client.get(f"/api/v1/research/{report_id}")
    assert get_after_del.status_code == 404


@pytest.mark.asyncio
async def test_research_strict_multi_tenant_isolation(authed_client: AsyncClient) -> None:
    """Verify that User B cannot read, search, update, or delete User A's private research reports."""
    user_b_client = await _create_second_user_client()
    try:
        # 1. User A creates a proprietary research report
        payload: dict[str, Any] = {
            "query": "Project Hyperion Dark Matter Detector",
            "title": "CONFIDENTIAL: Project Hyperion Analysis",
            "summary": "Cryptographic encryption keys and zero-knowledge proofs.",
            "findings": [
                {
                    "theme": "Security",
                    "claim": "Key derivation uses 256-bit Argon2id hashes.",
                    "confidence": "high",
                    "source_indices": [1],
                }
            ],
            "sources": [],
            "confidence": "high",
            "depth": "deep",
            "tags": ["hyperion", "confidential"],
        }
        res_a = await authed_client.post("/api/v1/research/reports", json=payload)
        assert res_a.status_code == 201
        report_a_id = res_a.json()["report"]["id"]

        # 2. User B tries to get User A's report directly -> 404
        res_b_get = await user_b_client.get(f"/api/v1/research/{report_a_id}")
        assert res_b_get.status_code == 404

        # 3. User B lists reports with search term -> empty
        res_b_list = await user_b_client.get("/api/v1/research/reports?search=Hyperion")
        assert res_b_list.status_code == 200
        assert len(res_b_list.json()["reports"]) == 0

        # 4. User B attempts to patch User A's report -> 404
        res_b_patch = await user_b_client.patch(
            f"/api/v1/research/{report_a_id}",
            json={"title": "Hacked Title"},
        )
        assert res_b_patch.status_code == 404

        # 5. User B attempts to delete User A's report -> 404
        res_b_del = await user_b_client.delete(f"/api/v1/research/{report_a_id}")
        assert res_b_del.status_code == 404
    finally:
        await user_b_client.aclose()


@pytest.mark.asyncio
async def test_research_tools_in_central_registry_and_execution() -> None:
    """Verify Central ToolRegistry registration and execution for all Deep Research tools."""
    registry = ToolRegistry.get_instance()
    ResearchService.get_instance().register_research_tools()

    # 1. Verify tools exist in Central Tool Registry
    assert registry.get("research_deep_investigate") is not None
    assert registry.get("research_live_search") is not None
    assert registry.get("research_fetch_page") is not None
    assert registry.get("research_list_reports") is not None
    assert registry.get("research_get_report") is not None
    assert registry.get("research_delete_report") is not None
    assert registry.get("research_export_to_vault") is not None

    tool_investigate = registry.get("research_deep_investigate")
    assert tool_investigate is not None
    assert tool_investigate.source == ToolSource.SYSTEM
    assert "query" in tool_investigate.input_schema["properties"]

    # 2. Execute research_live_search via ToolRegistry
    mock_sources = [
        SearchResult(
            title="Registry Test Source",
            url="https://test.local/research",
            snippet="Registry execution verification snippet.",
            source="tavily",
        )
    ]
    with patch.object(
        ResearchService.get_instance().search_skill,
        "execute",
        new=AsyncMock(return_value=WebSearchResponse(query="registry test", results=mock_sources, total_results=1)),
    ):
        search_exec = await registry.execute(
            ToolExecutionRequest(
                tool_id="research_live_search",
                arguments={"query": "registry test", "num_results": 1},
                user_id="research_tester_p6",
            )
        )
        assert search_exec.success is True
        assert search_exec.output["total_results"] == 1

    # 3. Execute research_deep_investigate via ToolRegistry
    with patch.object(
        ResearchService.get_instance(),
        "search_web",
        new=AsyncMock(
            return_value=[
                {
                    "title": "Alibaba AI Hackathon Docs",
                    "url": "https://alibaba.com/hackathon",
                    "snippet": "Full-stack personal AI agent stack.",
                    "domain": "alibaba.com",
                    "published_date": None,
                }
            ]
        ),
    ):
        investigate_exec = await registry.execute(
            ToolExecutionRequest(
                tool_id="research_deep_investigate",
                arguments={
                    "query": "Alibaba AI Hackathon Agentic Architecture",
                    "depth": "deep",
                    "save_report": True,
                },
                user_id="research_tester_p6",
            )
        )
        assert investigate_exec.success is True
        assert investigate_exec.output["topic"] == "Alibaba AI Hackathon Agentic Architecture"
        report_id = investigate_exec.output.get("report_id")
        assert report_id is not None

    # 4. Execute research_get_report via ToolRegistry
    get_exec = await registry.execute(
        ToolExecutionRequest(
            tool_id="research_get_report",
            arguments={"report_id": report_id},
            user_id="research_tester_p6",
        )
    )
    assert get_exec.success is True
    assert get_exec.output["found"] is True

    # 5. Execute research_list_reports via ToolRegistry
    list_exec = await registry.execute(
        ToolExecutionRequest(
            tool_id="research_list_reports",
            arguments={"limit": 10},
            user_id="research_tester_p6",
        )
    )
    assert list_exec.success is True
    assert list_exec.output["total"] >= 1

    # 6. Execute research_delete_report via ToolRegistry
    del_exec = await registry.execute(
        ToolExecutionRequest(
            tool_id="research_delete_report",
            arguments={"report_id": report_id},
            user_id="research_tester_p6",
        )
    )
    assert del_exec.success is True
    assert del_exec.output["deleted"] is True


@pytest.mark.asyncio
async def test_research_planner_intent_routing() -> None:
    """Verify that AgentPlanner routes research intents to research_deep_investigate."""
    ResearchService.get_instance().register_research_tools()
    planner = AgentPlanner()

    # 1. Test "deep research on ..." intent
    plan1 = await planner.create_plan(
        objective="deep research on neural network quantization techniques",
        user_id="planner_tester_p6",
    )
    assert len(plan1) >= 1
    first_step = plan1[0]
    assert first_step["tool_id"] == "research_deep_investigate"
    assert "neural network quantization" in first_step["tool_input"]["query"]

    # 2. Test "conduct research on ..." intent
    plan2 = await planner.create_plan(
        objective="conduct research on renewable energy grid storage solutions",
        user_id="planner_tester_p6",
    )
    assert len(plan2) >= 1
    assert plan2[0]["tool_id"] == "research_deep_investigate"


@pytest.mark.asyncio
async def test_research_export_to_knowledge_vault(authed_client: AsyncClient) -> None:
    """Verify exporting a research report into a Knowledge Vault document note."""
    repo = ResearchRepository()
    service = ResearchService.get_instance()
    vault = VaultService.get_instance()

    # 1. Seed a report
    user_id = "vault_export_tester_p6"
    report_data: dict[str, Any] = {
        "query": "GPU Accelerated Vector Indexing",
        "title": "GPU Vector Acceleration Report",
        "summary": "GPU acceleration improves approximate nearest neighbor search by 10x.",
        "findings": [
            {
                "theme": "Throughput Scaling",
                "claim": "Parallelized kernel executions saturate tensor core capacity.",
                "confidence": "high",
                "source_indices": [1],
            }
        ],
        "sources": [
            {
                "title": "NVIDIA Vector Search",
                "url": "https://nvidia.com/vector-search",
                "snippet": "CUDA-accelerated ANN indexing.",
                "domain": "nvidia.com",
            }
        ],
        "confidence": "high",
        "depth": "deep",
        "tags": ["gpu", "indexing", "vector"],
    }
    saved_report = await repo.create_report(user_id=user_id, data=report_data)
    report_id = saved_report["id"]

    # 2. Export report to Knowledge Vault
    export_result = await service.export_to_vault(user_id=user_id, report_id=report_id, folder="Research")
    assert export_result["success"] is True
    doc_id = export_result["document_id"]
    assert export_result["folder"] == "Research"

    # 3. Verify the document exists in Knowledge Vault
    vault_doc = await vault.get_document(user_id=user_id, document_id=doc_id)
    assert vault_doc is not None
    assert vault_doc.folder == "Research"
    assert "GPU Vector Acceleration Report" in vault_doc.filename

    # 4. Verify the document is searchable in Knowledge Vault
    search_resp = await vault.search(
        user_id=user_id,
        query="tensor core capacity vector indexing",
        folder="Research",
        top_k=3,
    )
    assert search_resp.total_matches >= 1
    top_hit = search_resp.results[0]
    assert "Parallelized kernel executions" in top_hit.content
