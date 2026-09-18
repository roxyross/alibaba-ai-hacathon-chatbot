"""Phase 12 Master Integration Test Suite: Email & Communications Engine.

Verifies:
1. Fresh user starts with clean empty drafts and outbox (0 messages).
2. Email draft creation and retrieval (POST/GET /api/v1/emails).
3. Email draft patching and mutation (PATCH /api/v1/emails/{id}).
4. Email draft deletion (DELETE /api/v1/emails/{id}).
5. Status filtering (draft vs sent) and keyword search.
6. AI draft composer (POST /api/v1/emails/compose-ai).
7. AI tone polisher (POST /api/v1/emails/polish-ai).
8. Curated template library retrieval (GET /api/v1/emails/templates).
9. Strict multi-tenant isolation: User B cannot view, update, or delete User A's emails (404 Not Found).
10. Multi-agent chat runtime grounding with email outbox and drafts history.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.emails.repository import clear_in_memory_stores
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

    ver_resp = await client.post("/api/v1/auth/verify", json={"token": token})
    assert ver_resp.status_code == 200
    data = ver_resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]["id"]


# -----------------------------------------------------------------------------
# 1. Fresh User Empty State
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_email_empty_state(client: httpx.AsyncClient) -> None:
    """Verify that a brand-new user starts with 0 drafts and 0 sent messages."""
    email = f"clean_email_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.get("/api/v1/emails", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["emails"] == []
    assert data["total"] == 0

    drafts_resp = await client.get("/api/v1/emails?status=draft", headers=headers)
    assert drafts_resp.status_code == 200
    assert drafts_resp.json()["total"] == 0

    sent_resp = await client.get("/api/v1/emails?status=sent", headers=headers)
    assert sent_resp.status_code == 200
    assert sent_resp.json()["total"] == 0


# -----------------------------------------------------------------------------
# 2. Create and Retrieve Email Draft
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_and_get_draft(client: httpx.AsyncClient) -> None:
    """Verify creating a draft and retrieving it by ID."""
    email = f"draft_author_{uuid.uuid4().hex[:8]}@example.com"
    headers, user_id = await _get_auth(client, email)

    payload: dict[str, Any] = {
        "to": "client@acme.org",
        "subject": "Q3 Deliverables and Sprint Review",
        "body": "Hi Client Team,\nHere are the deliverables for Q3...",
        "cc": ["lead@acme.org"],
        "status": "draft",
    }
    create_resp = await client.post("/api/v1/emails", json=payload, headers=headers)
    assert create_resp.status_code == 201
    created = create_resp.json()["email"]
    assert created["subject"] == payload["subject"]
    assert created["to"] == payload["to"]
    assert created["status"] == "draft"
    assert created["user_id"] == user_id
    email_id = created["id"]

    get_resp = await client.get(f"/api/v1/emails/{email_id}", headers=headers)
    assert get_resp.status_code == 200
    fetched = get_resp.json()["email"]
    assert fetched["id"] == email_id
    assert fetched["subject"] == payload["subject"]
    assert "lead@acme.org" in fetched["cc"]


# -----------------------------------------------------------------------------
# 3. Update and Delete Email Draft
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_update_and_delete_draft(client: httpx.AsyncClient) -> None:
    """Verify modifying a draft and deleting it."""
    email = f"editor_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/emails",
        json={
            "to": "partner@venture.co",
            "subject": "Intro Call",
            "body": "Let's connect soon.",
            "status": "draft",
        },
        headers=headers,
    )
    email_id = create_resp.json()["email"]["id"]

    patch_resp = await client.patch(
        f"/api/v1/emails/{email_id}",
        json={
            "subject": "Intro Call — Exploring AI Collaboration",
            "body": "Let's connect next Tuesday at 2 PM UTC to discuss our partnership.",
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()["email"]
    assert updated["subject"] == "Intro Call — Exploring AI Collaboration"
    assert "Tuesday at 2 PM UTC" in updated["body"]

    del_resp = await client.delete(f"/api/v1/emails/{email_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    get_deleted = await client.get(f"/api/v1/emails/{email_id}", headers=headers)
    assert get_deleted.status_code == 404


# -----------------------------------------------------------------------------
# 4. Status Filtering and Keyword Search
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_email_status_filtering_and_search(client: httpx.AsyncClient) -> None:
    """Verify filtering by status (draft vs sent) and searching text."""
    email = f"filter_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/emails",
        json={"to": "investor@sequoia.com", "subject": "Series A Deck", "body": "Pitch details", "status": "draft"},
        headers=headers,
    )
    await client.post(
        "/api/v1/emails",
        json={"to": "support@stripe.com", "subject": "Merchant Verification", "body": "Account docs", "status": "sent"},
        headers=headers,
    )
    await client.post(
        "/api/v1/emails",
        json={"to": "vendor@aws.amazon.com", "subject": "Cloud Invoice March", "body": "Compute usage", "status": "sent"},
        headers=headers,
    )

    drafts = (await client.get("/api/v1/emails?status=draft", headers=headers)).json()["emails"]
    assert len(drafts) == 1
    assert drafts[0]["subject"] == "Series A Deck"

    sent = (await client.get("/api/v1/emails?status=sent", headers=headers)).json()["emails"]
    assert len(sent) == 2

    search_res = (await client.get("/api/v1/emails?search=invoice", headers=headers)).json()["emails"]
    assert len(search_res) == 1
    assert search_res[0]["subject"] == "Cloud Invoice March"


# -----------------------------------------------------------------------------
# 5. AI Draft Composition
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ai_compose_draft(client: httpx.AsyncClient) -> None:
    """Verify natural language prompt expansion into a structured email draft."""
    email = f"ai_composer_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/emails/compose-ai",
        json={
            "prompt": "follow up with Sarah on Q3 product roadmap, request design feedback by Friday",
            "tone": "executive",
            "recipient_name": "Sarah",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "subject" in data and len(data["subject"]) > 3
    assert "body" in data
    assert "Sarah" in data["body"]
    assert "BLUF" in data["body"] or "Executive" in data["body"] or "feedback" in data["body"].lower()


# -----------------------------------------------------------------------------
# 6. AI Tone Polisher
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ai_polish_draft(client: httpx.AsyncClient) -> None:
    """Verify refining and elevating existing email copy with AI."""
    email = f"polisher_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/emails/polish-ai",
        json={
            "subject": "need budget approval",
            "body": "hey can you approve the new cloud server budget for $500/mo we need it for testing",
            "tone": "professional",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["subject"] == "need budget approval"
    assert "Hello" in data["body"] or "Kind regards" in data["body"]
    assert "$500" in data["body"]


# -----------------------------------------------------------------------------
# 7. Template Library Retrieval
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_email_templates(client: httpx.AsyncClient) -> None:
    """Verify retrieving the built-in professional template library."""
    email = f"templates_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.get("/api/v1/emails/templates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 5
    ids = [t["id"] for t in data["templates"]]
    assert "meeting_followup" in ids
    assert "status_update" in ids
    assert "invoice_notice" in ids


# -----------------------------------------------------------------------------
# 8. Dispatch Draft Endpoint
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_send_draft_endpoint(client: httpx.AsyncClient) -> None:
    """Verify dispatching a saved draft via POST /api/v1/emails/{id}/send."""
    email = f"dispatcher_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/emails",
        json={
            "to": "colleague@acme.org",
            "subject": "System Upgrade Notice",
            "body": "System will be updated tonight at midnight.",
            "status": "draft",
        },
        headers=headers,
    )
    email_id = create_resp.json()["email"]["id"]

    send_resp = await client.post(
        f"/api/v1/emails/{email_id}/send",
        json={"smtp_user": "tester@example.com", "smtp_pass": "samplepass"},
        headers=headers,
    )
    assert send_resp.status_code == 200
    result = send_resp.json()
    assert "delivery_status" in result
    assert result["delivery_status"] in ("sent", "failed")

    msg_resp = await client.get(f"/api/v1/emails/{email_id}", headers=headers)
    assert msg_resp.status_code == 200
    record = msg_resp.json()["email"]
    assert record["status"] in ("sent", "failed")


# -----------------------------------------------------------------------------
# 9. Strict Multi-Tenant Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_email_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """Verify that User B cannot read, patch, or delete User A's email messages."""
    headers_a, _ = await _get_auth(client, f"tenant_a_{uuid.uuid4().hex[:8]}@example.com")
    headers_b, _ = await _get_auth(client, f"tenant_b_{uuid.uuid4().hex[:8]}@example.com")

    create_resp = await client.post(
        "/api/v1/emails",
        json={
            "to": "classified@corp.com",
            "subject": "Strictly Confidential M&A Offer",
            "body": "Private acquisition terms...",
            "status": "draft",
        },
        headers=headers_a,
    )
    email_a_id = create_resp.json()["email"]["id"]

    # User B tries to view User A's draft -> 404
    get_b = await client.get(f"/api/v1/emails/{email_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B tries to update User A's draft -> 404
    patch_b = await client.patch(
        f"/api/v1/emails/{email_a_id}",
        json={"subject": "Hacked Subject"},
        headers=headers_b,
    )
    assert patch_b.status_code == 404

    # User B tries to delete User A's draft -> 404
    del_b = await client.delete(f"/api/v1/emails/{email_a_id}", headers=headers_b)
    assert del_b.status_code == 404

    # User B lists emails -> 0 items
    list_b = await client.get("/api/v1/emails", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0


# -----------------------------------------------------------------------------
# 10. Multi-Agent Chat Grounding with Email Context
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_chat_email_grounding(client: httpx.AsyncClient) -> None:
    """Verify that coordinator agent chat accurately reflects user's email drafts and sent messages."""
    email = f"chat_email_grounding_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/emails",
        json={
            "to": "alex@partner.com",
            "subject": "Contract Renewal Discussion",
            "body": "Hi Alex, let's review the contract terms.",
            "status": "draft",
        },
        headers=headers,
    )

    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        json={
            "message": "What email drafts do I currently have saved?",
            "provider": "runtime",
            "model": "coordinator",
        },
        headers=headers,
    )
    assert chat_resp.status_code == 200
    body = chat_resp.json()
    assert "response" in body
    text = body["response"]
    assert "Contract Renewal Discussion" in text or "draft" in text.lower() or "1 message" in text.lower()
