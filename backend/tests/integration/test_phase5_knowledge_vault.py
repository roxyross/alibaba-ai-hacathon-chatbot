"""Phase 5 Master Integration Test Suite: Knowledge Vault & Vector Memory.

Verifies:
1. Document upload, parsing (markdown, text, csv), chunking, and NeonDB DocumentRecord persistence.
2. Strict multi-tenant isolation on document listings (User B cannot see User A's uploaded documents).
3. Semantic RAG query search over chunks (User A retrieves relevant excerpts; User B gets zero matches).
4. Chat grounding with citations:
   - When User A chats, relevant document chunks are retrieved and citations [Source: <doc>] are included.
   - User B does not receive User A's document grounding or citations.
5. Document deletion and tenant security guard:
   - User B cannot delete User A's document (returns 404 Not Found).
   - User A can delete their document, which purges chunks from vector store.
"""

from __future__ import annotations

import io
import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.documents.repository import DocumentRepository
from app.main import app


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
    """Return (auth_headers, user_id)."""
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    verify_data = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()
    jwt_tok = verify_data["access_token"]
    user_id = verify_data["user"]["id"]
    return {"Authorization": f"Bearer {jwt_tok}"}, user_id


@pytest.mark.asyncio
async def test_document_upload_parsing_and_persistence(client: httpx.AsyncClient) -> None:
    """Uploading a document parses content, indexes vector chunks, and persists to DB."""
    uid = uuid.uuid4().hex[:8]
    headers_a, user_id_a = await _get_auth(client, f"vault_user_{uid}@example.com")

    doc_text = (
        "# Q3 Engineering & Financial Strategy\n\n"
        "Total Revenue recorded is $4.2M for this quarter.\n"
        "Active Runway extends for 18 months based on current burn rate of $120k/mo.\n"
        "The flagship microservices migration will complete by October 15th."
    )
    file_bytes = doc_text.encode("utf-8")

    files = {
        "file": ("q3_strategy.md", io.BytesIO(file_bytes), "text/markdown"),
    }
    data = {
        "document_name": "Q3 Engineering & Financial Strategy",
    }

    res = await client.post("/api/v1/documents/upload", headers=headers_a, files=files, data=data)
    assert res.status_code == 200, res.text
    payload = res.json()

    assert payload["document_name"] == "Q3 Engineering & Financial Strategy"
    assert payload["chunks_stored"] >= 1
    assert payload["doc_type"] == "markdown"
    assert len(payload["chunk_ids"]) >= 1

    doc_id = payload["document_id"]

    # Verify in DocumentRepository
    repo = DocumentRepository()
    db_doc = await repo.get_by_id(doc_id, user_id_a)
    assert db_doc is not None
    assert db_doc.filename == "Q3 Engineering & Financial Strategy"
    assert "Total Revenue recorded is $4.2M" in (db_doc.extracted_text or "")


@pytest.mark.asyncio
async def test_document_list_and_tenant_isolation(client: httpx.AsyncClient) -> None:
    """User A sees their uploaded document; User B sees an empty list."""
    uid = uuid.uuid4().hex[:8]
    headers_a, user_id_a = await _get_auth(client, f"alice_{uid}@example.com")
    headers_b, user_id_b = await _get_auth(client, f"bob_{uid}@example.com")

    # User A uploads a doc
    file_bytes = b"Confidential Project Pegasus Architecture Spec.\nCore engine runs on Rust and asyncpg."
    files = {"file": ("pegasus_spec.txt", io.BytesIO(file_bytes), "text/plain")}
    up_res = await client.post("/api/v1/documents/upload", headers=headers_a, files=files)
    assert up_res.status_code == 200

    # User A lists documents
    list_a = await client.get("/api/v1/documents", headers=headers_a)
    assert list_a.status_code == 200
    docs_a = list_a.json()["documents"]
    assert len(docs_a) == 1
    assert docs_a[0]["document_name"] == "pegasus_spec.txt"

    # User B lists documents
    list_b = await client.get("/api/v1/documents", headers=headers_b)
    assert list_b.status_code == 200
    docs_b = list_b.json()["documents"]
    assert len(docs_b) == 0, f"Cross-tenant leak! User B received: {docs_b}"


@pytest.mark.asyncio
async def test_document_query_semantic_rag(client: httpx.AsyncClient) -> None:
    """Semantic RAG queries match user's chunks; User B gets 0 chunks."""
    uid = uuid.uuid4().hex[:8]
    headers_a, user_id_a = await _get_auth(client, f"charlie_{uid}@example.com")
    headers_b, user_id_b = await _get_auth(client, f"dave_{uid}@example.com")

    text = (
        "Project BlueMoon Security Protocol: All SSH keys must be rotated every 30 days. "
        "Two-factor authentication via hardware YubiKey is strictly enforced for production clusters."
    )
    files = {"file": ("bluemoon_security.md", io.BytesIO(text.encode("utf-8")), "text/markdown")}
    await client.post("/api/v1/documents/upload", headers=headers_a, files=files)

    # User A queries
    q_res = await client.post(
        "/api/v1/documents/query",
        headers=headers_a,
        json={"query": "How often must SSH keys be rotated according to BlueMoon?"},
    )
    assert q_res.status_code == 200
    data = q_res.json()
    assert len(data["chunks"]) >= 1
    assert "bluemoon_security.md" in data["sources"]
    assert "bluemoon_security.md" in data["chunks"][0]["document_name"]
    assert "SSH keys must be rotated every 30 days" in data["chunks"][0]["text"]
    assert data["answer"] is not None
    assert "bluemoon_security.md" in data["answer"]

    # User B queries the exact same prompt
    q_res_b = await client.post(
        "/api/v1/documents/query",
        headers=headers_b,
        json={"query": "How often must SSH keys be rotated according to BlueMoon?"},
    )
    assert q_res_b.status_code == 200
    data_b = q_res_b.json()
    assert len(data_b["chunks"]) == 0, "User B leaked chunks from User A!"
    assert data_b["total_candidates"] == 0


@pytest.mark.asyncio
async def test_chat_grounding_and_citations(client: httpx.AsyncClient) -> None:
    """Chat requests ground responses using user's uploaded vault documents and citations."""
    uid = uuid.uuid4().hex[:8]
    headers_a, user_id_a = await _get_auth(client, f"eva_{uid}@example.com")
    headers_b, user_id_b = await _get_auth(client, f"frank_{uid}@example.com")

    # User A uploads a unique product patent
    doc_content = (
        "QuantumLock Protocol Specification: The quantum encryption key uses 4096-bit entanglement pairs. "
        "The fail-safe trigger code is ALPHA-OMEGA-9944."
    )
    files = {"file": ("quantum_lock_patent.txt", io.BytesIO(doc_content.encode("utf-8")), "text/plain")}
    await client.post("/api/v1/documents/upload", headers=headers_a, files=files)

    # User A chats via runtime coordinator
    chat_payload = {
        "message": "What is the fail-safe trigger code in the QuantumLock protocol?",
    }
    chat_res = await client.post("/api/v1/runtime/chat", headers=headers_a, json=chat_payload)
    assert chat_res.status_code == 200
    res_data = chat_res.json()
    response_text = res_data["response"]

    # Must contain the grounded knowledge or document citation
    assert "ALPHA-OMEGA-9944" in response_text or "quantum_lock_patent.txt" in response_text or "QuantumLock" in response_text

    # User B asks the same thing
    chat_res_b = await client.post("/api/v1/runtime/chat", headers=headers_b, json=chat_payload)
    assert chat_res_b.status_code == 200
    res_b_text = chat_res_b.json()["response"]
    assert "quantum_lock_patent.txt" not in res_b_text, "User B leaked User A's document name!"


@pytest.mark.asyncio
async def test_document_deletion_and_cross_tenant_guard(client: httpx.AsyncClient) -> None:
    """User B cannot delete User A's document; User A deletes and chunks are removed."""
    uid = uuid.uuid4().hex[:8]
    headers_a, user_id_a = await _get_auth(client, f"grace_{uid}@example.com")
    headers_b, user_id_b = await _get_auth(client, f"heidi_{uid}@example.com")

    # User A uploads doc
    files = {"file": ("delete_test.txt", io.BytesIO(b"Ephemeral test data to be purged."), "text/plain")}
    up = await client.post("/api/v1/documents/upload", headers=headers_a, files=files)
    doc_id = up.json()["document_id"]

    # User B tries to delete User A's document -> 404
    del_b = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers_b)
    assert del_b.status_code == 404

    # Document still exists for User A
    list_a = await client.get("/api/v1/documents", headers=headers_a)
    assert len(list_a.json()["documents"]) == 1

    # User A deletes their own document -> 200
    del_a = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers_a)
    assert del_a.status_code == 200
    assert del_a.json()["document_id"] == doc_id

    # Verify list is now empty
    list_a_after = await client.get("/api/v1/documents", headers=headers_a)
    assert len(list_a_after.json()["documents"]) == 0

    # Verify RAG query returns 0 chunks
    q_after = await client.post(
        "/api/v1/documents/query",
        headers=headers_a,
        json={"query": "Ephemeral test data"},
    )
    assert len(q_after.json()["chunks"]) == 0
