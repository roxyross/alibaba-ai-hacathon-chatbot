"""Integration tests for Phase 5: Knowledge Vault & Vector Memory (RAG Engine).

Verifies:
1. Document upload, text parsing, hierarchical chunking, and dense vector embeddings.
2. Direct knowledge note creation in Markdown.
3. Hybrid semantic vector and BM25 lexical search with RRF scoring.
4. Document listing, folder filtering, and chunk inspection.
5. Strict multi-tenant isolation (User B cannot search, read, or delete User A's documents).
6. Central ToolRegistry integration: execution of `vault_search`, `vault_read_document`, `vault_list_documents`.
7. Document deletion, chunk purge, and vault statistics telemetry.
"""

from __future__ import annotations

import io

import httpx
import pytest
from httpx import AsyncClient

from app.auth.service import MagicLinkService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest, ToolSource


async def _create_second_user_client() -> AsyncClient:
    """Helper to mint a second authenticated client for tenant isolation testing."""
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    service = MagicLinkService()
    test_email = "tenant_isolation_b@example.com"
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


@pytest.mark.asyncio
async def test_vault_document_upload_and_chunking(authed_client: AsyncClient) -> None:
    """Verify document upload, text parsing, recursive chunking, and embedding generation."""
    sample_text = """# ROXY-AI 2.0 Architectural Blueprint

## Executive Summary
ROXY-AI 2.0 is a distributed personal AI operating layer featuring multi-agent orchestration,
local device control, and deep contextual memory.

## Knowledge Vault Specifications
The Knowledge Vault employs recursive hierarchical text splitting, signed 128-dimensional
feature-hashed dense vectors, and hybrid BM25 lexical retrieval. All chunks are bounded to
approximately 1200 characters with 150-character contextual overlap.

## Security & Privacy Model
Strict multi-tenant cryptographic partitioning ensures that customer documents are completely
isolated and inaccessible to other users.
"""
    file_bytes = sample_text.encode("utf-8")
    files = {"file": ("architecture_blueprint.md", io.BytesIO(file_bytes), "text/markdown")}
    data = {"document_name": "ROXY Architecture Blueprint", "folder": "Engineering"}

    res = await authed_client.post("/api/v1/vault/upload", files=files, data=data)
    assert res.status_code == 201
    doc = res.json()

    assert "id" in doc
    assert doc["filename"] == "ROXY Architecture Blueprint"
    assert doc["folder"] == "Engineering"
    assert doc["chunk_count"] >= 1
    assert "status" in doc
    assert doc["status"] == "ready"
    assert len(doc["chunks"]) >= 1

    first_chunk = doc["chunks"][0]
    assert "id" in first_chunk
    assert "content" in first_chunk
    assert "token_count" in first_chunk
    assert first_chunk["token_count"] > 0
    assert first_chunk["has_embedding"] is True


@pytest.mark.asyncio
async def test_vault_note_creation(authed_client: AsyncClient) -> None:
    """Verify quick markdown note creation directly into the Knowledge Vault."""
    note_payload = {
        "title": "Weekly Strategy Sync Notes",
        "content": """# Strategy Sync - Q4
Key Priorities:
1. Complete Phase 5 Knowledge Vault rollout with sub-50ms hybrid search.
2. Finalize cloud-native deployment on Alibaba Cloud Serverless Container Instances.
3. Conduct end-to-end stress testing under multi-tenant load.
""",
        "folder": "Strategy",
        "tags": ["strategy", "planning", "q4"],
    }

    res = await authed_client.post("/api/v1/vault/notes", json=note_payload)
    assert res.status_code == 201
    doc = res.json()

    assert doc["filename"] == "Weekly Strategy Sync Notes.md"
    assert doc["folder"] == "Strategy"
    assert doc["mime_type"] == "text/markdown"
    assert "strategy" in doc["tags"]
    assert doc["chunk_count"] >= 1


@pytest.mark.asyncio
async def test_vault_hybrid_semantic_search(authed_client: AsyncClient) -> None:
    """Verify hybrid dense vector + lexical keyword search over indexed documents."""
    # 1. Ingest distinct document for searching
    tech_content = """# Alibaba Cloud GPU Acceleration & Model Serving
This document details high-throughput LLM deployment patterns on Alibaba Cloud PAI-EAS.
Using vLLM with PagedAttention and Tensor Parallelism across 4x NVIDIA A10 GPUs,
inference latency is reduced to 18 milliseconds per token.
"""
    files = {"file": ("alibaba_gpu_guide.txt", io.BytesIO(tech_content.encode("utf-8")), "text/plain")}
    data = {"document_name": "Alibaba GPU Serving Guide", "folder": "Engineering"}
    upload_res = await authed_client.post("/api/v1/vault/upload", files=files, data=data)
    assert upload_res.status_code == 201

    # 2. Search query matching both semantic meaning and exact tokens
    search_payload = {
        "query": "Alibaba Cloud GPU vLLM latency",
        "folder": "Engineering",
        "top_k": 3,
        "hybrid": True,
    }

    search_res = await authed_client.post("/api/v1/vault/search", json=search_payload)
    assert search_res.status_code == 200
    res_data = search_res.json()

    assert "results" in res_data
    assert len(res_data["results"]) >= 1
    top_hit = res_data["results"][0]

    assert "Alibaba" in top_hit["content"] or "GPU" in top_hit["content"]
    assert top_hit["score"] > 0.0
    assert top_hit["dense_score"] >= 0.0
    assert top_hit["lexical_score"] >= 0.0
    assert top_hit["document_name"] == "Alibaba GPU Serving Guide"
    assert res_data["execution_time_ms"] >= 0.0


@pytest.mark.asyncio
async def test_vault_list_and_filter_documents(authed_client: AsyncClient) -> None:
    """Verify document listing with folder and search filtering."""
    # 1. Seed two documents in different folders
    await authed_client.post(
        "/api/v1/vault/notes",
        json={"title": "Doc In Engineering", "content": "Engineering content", "folder": "Engineering"},
    )
    await authed_client.post(
        "/api/v1/vault/notes",
        json={"title": "Doc In Finance", "content": "Finance content", "folder": "Finance"},
    )

    # 2. List all documents
    res_all = await authed_client.get("/api/v1/vault/documents")
    assert res_all.status_code == 200
    all_data = res_all.json()
    assert all_data["total"] >= 2
    assert len(all_data["documents"]) >= 2

    # 3. Filter by folder
    res_folder = await authed_client.get("/api/v1/vault/documents?folder=Engineering")
    assert res_folder.status_code == 200
    folder_data = res_folder.json()
    assert len(folder_data["documents"]) >= 1
    for d in folder_data["documents"]:
        assert d["folder"] == "Engineering"


@pytest.mark.asyncio
async def test_vault_get_document_details(authed_client: AsyncClient) -> None:
    """Verify retrieving single document with its constituent chunks."""
    # 1. Ingest document
    create_res = await authed_client.post(
        "/api/v1/vault/notes",
        json={
            "title": "Quantum Computing Notes",
            "content": "# Quantum Computing\n\nQubits leverage quantum superposition and entanglement.",
            "folder": "Research",
        },
    )
    assert create_res.status_code == 201
    doc_id = create_res.json()["id"]

    # 2. Get document details
    res_detail = await authed_client.get(f"/api/v1/vault/documents/{doc_id}")
    assert res_detail.status_code == 200
    doc = res_detail.json()

    assert doc["id"] == doc_id
    assert doc["folder"] == "Research"
    assert "chunks" in doc
    assert len(doc["chunks"]) == doc["chunk_count"]
    for ch in doc["chunks"]:
        assert ch["document_id"] == doc_id
        assert len(ch["content"]) > 0


@pytest.mark.asyncio
async def test_vault_strict_tenant_isolation(authed_client: AsyncClient) -> None:
    """Verify that User B cannot view, query, or delete User A's private documents."""
    user_b_client = await _create_second_user_client()
    try:
        # 1. User A creates a confidential document
        private_text = "CONFIDENTIAL_PROJECT_OMEGA: Secret cryptographic keys and deployment hashes."
        files = {"file": ("top_secret.txt", io.BytesIO(private_text.encode("utf-8")), "text/plain")}
        res_upload = await authed_client.post(
            "/api/v1/vault/upload", files=files, data={"document_name": "Top Secret Omega"}
        )
        assert res_upload.status_code == 201
        user_a_doc_id = res_upload.json()["id"]

        # 2. User B tries to read User A's document directly -> 404
        res_b_get = await user_b_client.get(f"/api/v1/vault/documents/{user_a_doc_id}")
        assert res_b_get.status_code == 404

        # 3. User B queries for secret term -> 0 matches
        res_b_search = await user_b_client.post(
            "/api/v1/vault/search",
            json={"query": "CONFIDENTIAL_PROJECT_OMEGA Secret keys", "top_k": 5},
        )
        assert res_b_search.status_code == 200
        matches = [
            r for r in res_b_search.json()["results"] if "CONFIDENTIAL_PROJECT_OMEGA" in r["content"]
        ]
        assert len(matches) == 0

        # 4. User B tries to delete User A's document -> 404
        res_b_del = await user_b_client.delete(f"/api/v1/vault/documents/{user_a_doc_id}")
        assert res_b_del.status_code == 404
    finally:
        await user_b_client.aclose()


@pytest.mark.asyncio
async def test_vault_tools_in_central_registry_and_deletion(authed_client: AsyncClient) -> None:
    """Verify ToolRegistry integration for vault tools and document deletion lifecycle."""
    registry = ToolRegistry.get_instance()

    # 1. Verify tools are registered in Central Tool Registry
    assert registry.get("vault_search") is not None
    assert registry.get("vault_read_document") is not None
    assert registry.get("vault_list_documents") is not None
    assert registry.get("vault_store_knowledge") is not None
    assert registry.get("vault_delete_document") is not None

    tool = registry.get("vault_search")
    assert tool.source == ToolSource.SYSTEM
    assert "query" in tool.input_schema["properties"]

    # 2. Execute vault_store_knowledge via registry
    store_exec = await registry.execute(
        ToolExecutionRequest(
            tool_id="vault_store_knowledge",
            arguments={
                "title": "ToolRegistry Knowledge Note",
                "content": "This note was registered through the central ToolRegistry dispatcher.",
                "folder": "IntegrationTests",
            },
            user_id="test_user_p5",
        )
    )
    assert store_exec.success is True
    created_id = store_exec.output["document_id"]

    # 3. Execute vault_search via registry
    search_exec = await registry.execute(
        ToolExecutionRequest(
            tool_id="vault_search",
            arguments={"query": "central ToolRegistry dispatcher", "top_k": 3},
            user_id="test_user_p5",
        )
    )
    assert search_exec.success is True
    assert search_exec.output["matches_count"] >= 1

    # 4. Execute vault_read_document via registry
    read_exec = await registry.execute(
        ToolExecutionRequest(
            tool_id="vault_read_document",
            arguments={"document_id": created_id},
            user_id="test_user_p5",
        )
    )
    assert read_exec.success is True
    assert read_exec.output["found"] is True

    # 5. Check Vault Stats telemetry
    stats_res = await authed_client.get("/api/v1/vault/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert "total_documents" in stats
    assert "total_chunks" in stats
    assert "total_bytes" in stats
    assert "storage_formatted" in stats

    # 6. Delete document via Registry tool and verify cleanup
    del_exec = await registry.execute(
        ToolExecutionRequest(
            tool_id="vault_delete_document",
            arguments={"document_id": created_id},
            user_id="test_user_p5",
        )
    )
    assert del_exec.success is True
    assert del_exec.output["deleted"] is True

    # 7. Also verify document deletion via REST API for authed_client's document
    temp_note = await authed_client.post(
        "/api/v1/vault/notes",
        json={"title": "Temp Note For API Delete", "content": "Delete me", "folder": "Testing"},
    )
    assert temp_note.status_code == 201
    temp_id = temp_note.json()["id"]

    del_res = await authed_client.delete(f"/api/v1/vault/documents/{temp_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

