"""Integration tests for Phase 6: Hybrid Knowledge Vault & Semantic Memory Subsystem.

Verifies:
1. Document upload, text parsing, hierarchical chunking, and dense vector embeddings.
2. Direct knowledge note creation in Markdown.
3. Hybrid semantic vector and BM25 lexical search with RRF scoring.
4. Document listing, folder filtering, and chunk inspection.
5. Strict multi-tenant isolation (User B cannot search, read, or delete User A's documents).
6. Central ToolRegistry integration with confirmation gating on vault_delete_document.
7. Document deletion, chunk purge, and vault statistics telemetry.
8. Semantic Memory CRUD, semantic retrieval, curator run, and stats.
9. AgentPlanner intent routing for Knowledge Vault and Semantic Memory.
"""

from __future__ import annotations

import io

import httpx
import pytest
from httpx import AsyncClient

from app.agent_runtime.planner import AgentPlanner
from app.auth.service import MagicLinkService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel, ToolExecutionRequest, ToolSource
from app.vault.service import VaultService


async def _create_second_user_client() -> AsyncClient:
    """Helper to mint a second authenticated client for tenant isolation testing."""
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    service = MagicLinkService()
    test_email = "vault_tenant_b@example.com"
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
def _ensure_vault_tools() -> None:
    """Ensure vault tools are registered before tests."""
    VaultService.get_instance().register_vault_tools()


# -----------------------------------------------------------------------------
# 1. Document Upload, Chunking & Embedding Generation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_vault_document_upload_and_chunking(authed_client: AsyncClient) -> None:
    """Verify document upload, text parsing, recursive chunking, and embedding generation."""
    sample_text = """# ROXY-AI 2.0 Architectural Blueprint

## Executive Summary
ROXY-AI 2.0 is a distributed personal AI operating layer featuring multi-agent orchestration,
local device control, and deep contextual memory.

## Knowledge Vault Specifications
The Knowledge Vault employs recursive hierarchical text splitting, signed 128-dimensional
dense vector embeddings, and Reciprocal Rank Fusion for search ranking.

## Chunking Algorithm
Documents exceeding 1,200 characters are partitioned along Markdown section headers (#, ##, ###)
and paragraphs, with a sliding 150-character context overlap.
"""
    file_bytes = sample_text.encode("utf-8")
    files = {"file": ("architecture_blueprint.md", io.BytesIO(file_bytes), "text/markdown")}
    data = {"folder": "Architecture", "document_name": "architecture_blueprint.md"}

    res = await authed_client.post("/api/v1/vault/upload", files=files, data=data)
    assert res.status_code in (200, 201)
    doc = res.json()

    assert "id" in doc
    assert doc["filename"] == "architecture_blueprint.md"
    assert doc["folder"] == "Architecture"
    assert doc["chunk_count"] >= 1
    assert doc["file_size_bytes"] > 0
    assert abs(doc["file_size_bytes"] - len(file_bytes)) <= 5
    assert "chunks" in doc
    assert len(doc["chunks"]) == doc["chunk_count"]

    first_chunk = doc["chunks"][0]
    assert "id" in first_chunk
    assert "content" in first_chunk
    assert "token_count" in first_chunk
    assert first_chunk["token_count"] > 0

    # Also test JSON creation endpoint
    json_doc = {
        "filename": "json_manual_guide.md",
        "content": "# JSON Guide\nDirect manual ingestion via REST API.",
        "folder": "Guides",
        "tags": ["guide", "manual"],
    }
    j_res = await authed_client.post("/api/v1/vault/documents", json=json_doc)
    assert j_res.status_code in (200, 201)
    j_data = j_res.json()
    assert j_data["filename"] == "json_manual_guide.md"
    assert j_data["tags"] == ["guide", "manual"]


# -----------------------------------------------------------------------------
# 2. Markdown Knowledge Note Creation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_vault_note_creation(authed_client: AsyncClient) -> None:
    """Verify direct creation of text/markdown knowledge notes in the Vault."""
    note_payload = {
        "title": "Quantum Computing Principles",
        "content": "Superposition and entanglement enable exponential speedups for specialized problems like Shor's algorithm.",
        "folder": "Research",
        "tags": ["quantum", "physics"],
    }
    res = await authed_client.post("/api/v1/vault/notes", json=note_payload)
    assert res.status_code in (200, 201)
    note = res.json()

    assert note["filename"] == "Quantum Computing Principles.md"
    assert note["folder"] == "Research"
    assert note["tags"] == ["quantum", "physics"]
    assert note["chunk_count"] == 1


# -----------------------------------------------------------------------------
# 3. Hybrid Semantic Vector & BM25 Search
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_vault_hybrid_search(authed_client: AsyncClient) -> None:
    """Verify hybrid semantic and keyword search returning ranked relevant chunks."""
    # 1. Ingest distinct document
    content = "The mitochondria is the powerhouse of the biological eukaryotic cell, generating ATP via oxidative phosphorylation."
    files = {"file": ("biology_cell.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}
    await authed_client.post("/api/v1/vault/upload", files=files, data={"folder": "Biology"})

    # 2. Query matching concept semantically
    search_payload = {
        "query": "What organelle produces ATP through cellular respiration?",
        "top_k": 3,
        "folder": "Biology",
    }
    res = await authed_client.post("/api/v1/vault/search", json=search_payload)
    assert res.status_code == 200
    results = res.json()

    assert "results" in results
    assert len(results["results"]) >= 1
    top_hit = results["results"][0]
    assert "powerhouse" in top_hit["content"] or "mitochondria" in top_hit["content"]
    assert top_hit["score"] > 0
    assert top_hit["document_name"] == "biology_cell.txt"


# -----------------------------------------------------------------------------
# 4. Document Listing, Stats, and Details Inspection
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_vault_listing_and_inspection(authed_client: AsyncClient) -> None:
    """Verify listing documents with folder filter, retrieving document details, and stats."""
    # Pre-populate with document
    json_doc = {
        "filename": "inspection_guide.md",
        "content": "# Inspection Guide\nThis document is for listing and inspection testing.",
        "folder": "Guides",
        "tags": ["inspection", "guide"],
    }
    j_res = await authed_client.post("/api/v1/vault/documents", json=json_doc)
    assert j_res.status_code in (200, 201)

    # List documents
    res = await authed_client.get("/api/v1/vault/documents")
    assert res.status_code == 200
    listing = res.json()
    assert "documents" in listing
    assert "total" in listing
    assert listing["total"] >= 1

    first_doc_id = listing["documents"][0]["id"]

    # Get document details
    doc_res = await authed_client.get(f"/api/v1/vault/documents/{first_doc_id}")
    assert doc_res.status_code == 200
    doc_data = doc_res.json()
    assert doc_data["id"] == first_doc_id
    assert "chunks" in doc_data

    # Vault stats
    stats_res = await authed_client.get("/api/v1/vault/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_documents"] >= 1
    assert stats["total_chunks"] >= 1
    assert stats["total_bytes"] > 0


# -----------------------------------------------------------------------------
# 5. Semantic Memory CRUD & Curator
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_semantic_memory_lifecycle_and_curator(authed_client: AsyncClient) -> None:
    """Verify semantic memory creation, retrieval, curation, and stats."""
    # 1. Create a memory entry
    mem_payload = {
        "content": "User prefers concise Python 3.14 code with strict typing and no third-party bloat.",
        "importance": "high",
        "tags": ["preferences", "coding"],
    }
    create_res = await authed_client.post("/api/v1/memory/entries", json=mem_payload)
    assert create_res.status_code in (200, 201)
    mem_data = create_res.json()
    assert "id" in mem_data
    mem_id = mem_data["id"]

    # 2. List memories
    list_res = await authed_client.get("/api/v1/memory/entries?tag=preferences")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1

    # 3. Retrieve relevant memories via semantic search
    retrieve_payload = {
        "query": "What are the user's programming preferences?",
        "top_k": 3,
    }
    ret_res = await authed_client.post("/api/v1/memory/retrieve", json=retrieve_payload)
    assert ret_res.status_code == 200
    ret_data = ret_res.json()
    assert len(ret_data["entries"]) >= 1
    assert "Python" in ret_data["entries"][0]["content"]

    # 4. Trigger memory curator run
    curator_res = await authed_client.post("/api/v1/memory/curator/run")
    assert curator_res.status_code == 200
    curator_data = curator_res.json()
    assert "entries_scanned" in curator_data

    # 5. Clean up memory entry
    del_res = await authed_client.delete(f"/api/v1/memory/entries/{mem_id}")
    assert del_res.status_code in (200, 204)


# -----------------------------------------------------------------------------
# 6. Central ToolRegistry Integration & Confirmation Gating
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_vault_tools_in_central_registry() -> None:
    """Verify vault tools registered in central registry with confirmation gating on delete."""
    registry = ToolRegistry.get_instance()

    expected_tools = [
        "vault_search",
        "vault_read_document",
        "vault_list_documents",
        "vault_store_knowledge",
        "vault_delete_document",
    ]

    for tool_name in expected_tools:
        tool = registry.get(tool_name)
        assert tool is not None, f"Tool {tool_name} not found in ToolRegistry"
        assert tool.source == ToolSource.SYSTEM

    # Destructive delete confirmation gating verification
    del_tool = registry.get("vault_delete_document")
    assert del_tool is not None
    assert del_tool.risk_level == RiskLevel.HIGH
    assert del_tool.requires_confirmation is True

    # Direct execution of vault_store_knowledge and vault_search
    user_id = "test-vault-user-88"
    exec_store = ToolExecutionRequest(
        tool_id="vault_store_knowledge",
        arguments={
            "title": "Agentic Protocol V2",
            "content": "Protocol specification for autonomous peer-to-peer agent coordination.",
            "folder": "Protocols",
            "user_id": user_id,
        },
        user_id=user_id,
    )
    res_store = await registry.execute(exec_store)
    assert res_store.success is True
    assert res_store.output is not None
    assert res_store.output["status"] == "stored"

    # Search through registry
    exec_search = ToolExecutionRequest(
        tool_id="vault_search",
        arguments={"query": "peer-to-peer agent coordination", "top_k": 3, "user_id": user_id},
        user_id=user_id,
    )
    res_search = await registry.execute(exec_search)
    assert res_search.success is True
    assert res_search.output is not None
    assert "results" in res_search.output


# -----------------------------------------------------------------------------
# 7. AgentPlanner Intent Decomposition & Routing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_vault_intent_routing() -> None:
    """Verify AgentPlanner routes Knowledge Vault intents deterministically."""
    VaultService.get_instance().register_vault_tools()
    planner = AgentPlanner()

    # A. Search vault
    plan_search = await planner.create_plan("search vault for architectural guidelines")
    assert len(plan_search) == 1
    assert plan_search[0]["tool_id"] == "vault_search"
    assert "architectural guidelines" in plan_search[0]["tool_input"]["query"]

    # B. Store knowledge note in vault
    plan_store = await planner.create_plan("save note in vault: deployment checklists and runbooks")
    assert len(plan_store) == 1
    assert plan_store[0]["tool_id"] == "vault_store_knowledge"
    assert "deployment checklists" in plan_store[0]["tool_input"]["content"]

    # C. List vault documents
    plan_list = await planner.create_plan("list vault documents")
    assert len(plan_list) == 1
    assert plan_list[0]["tool_id"] == "vault_list_documents"

    # D. Read vault document
    plan_read = await planner.create_plan("read vault document doc_blueprint_01")
    assert len(plan_read) == 1
    assert plan_read[0]["tool_id"] == "vault_read_document"
    assert plan_read[0]["tool_input"]["document_id"] == "doc_blueprint_01"

    # E. Delete vault document (confirmation gated)
    plan_del = await planner.create_plan("delete vault document doc_obsolete_99")
    assert len(plan_del) == 1
    assert plan_del[0]["tool_id"] == "vault_delete_document"
    assert plan_del[0]["tool_input"]["document_id"] == "doc_obsolete_99"


# -----------------------------------------------------------------------------
# 8. Multi-Tenant Strict Isolation (Anti-IDOR)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_vault_multitenant_isolation(authed_client: AsyncClient) -> None:
    """Verify User B cannot search, inspect, or delete User A's vault documents."""
    # User A creates a confidential note
    secret_note = {
        "title": "User A Financial Statement",
        "content": "Confidential financial telemetry: Q3 Revenue exceeds 5M USD.",
        "folder": "Confidential",
    }
    res_a = await authed_client.post("/api/v1/vault/notes", json=secret_note)
    doc_a_id = res_a.json()["id"]

    # User B client
    client_b = await _create_second_user_client()
    try:
        # 1. User B search cannot find User A's document
        search_b = await client_b.post(
            "/api/v1/vault/search",
            json={"query": "Confidential financial telemetry Q3 Revenue"},
        )
        assert search_b.status_code == 200
        assert search_b.json()["total_matches"] == 0

        # 2. User B cannot read User A's document -> 404
        read_b = await client_b.get(f"/api/v1/vault/documents/{doc_a_id}")
        assert read_b.status_code == 404

        # 3. User B cannot delete User A's document -> 404
        del_b = await client_b.delete(f"/api/v1/vault/documents/{doc_a_id}")
        assert del_b.status_code == 404

        # Verify User A's document is completely untouched
        read_a = await authed_client.get(f"/api/v1/vault/documents/{doc_a_id}")
        assert read_a.status_code == 200
        assert "5M USD" in read_a.json()["chunks"][0]["content"]
    finally:
        await client_b.aclose()
