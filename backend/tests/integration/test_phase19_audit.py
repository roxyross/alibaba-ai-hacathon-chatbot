"""Phase 19 Integration Tests: Security, Privacy & Autonomous Action Audit Studio.

Verifies:
1. Clean zero-state for new users (0 audit events, 0 stats).
2. Record and retrieve audit events via POST /api/v1/audit and GET /api/v1/audit/{entry_id}.
3. Strict multi-tenant isolation (404 on unowned audit event access).
4. Audit log immutability (no PUT/PATCH/DELETE allowed on audit records).
5. "What did Jarvis do today" feed via GET /api/v1/audit/today.
6. Filtering audit logs by agent_slug.
7. Filtering audit logs by approval_tier and status_code.
8. Pre-execution risk check: clear verdict (T1 safe read).
9. Pre-execution risk check: caution verdict (T2 external action).
10. Pre-execution risk check: block verdict (T3 destructive / secret exfiltration).
11. Telemetry and stats computation via GET /api/v1/audit/stats.
12. GDPR portable data export via GET /api/v1/audit/export.
13. Chat coordinator audit context grounding for live queries.
14. Authentic offline fallback reporting audit log activity when LLM fails.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, "src")

from app.audit.repository import clear_in_memory_stores
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


@pytest.mark.asyncio
async def test_audit_empty_state(client: httpx.AsyncClient) -> None:
    """A newly registered user has zero audit logs and zero stats."""
    headers, _ = await _get_auth(client, f"audit_new_{uuid.uuid4().hex[:6]}@example.com")

    list_res = await client.get("/api/v1/audit", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 0
    assert data["items"] == []

    today_res = await client.get("/api/v1/audit/today", headers=headers)
    assert today_res.status_code == 200
    assert today_res.json() == []

    stats_res = await client.get("/api/v1/audit/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_events"] == 0
    assert stats["today_events"] == 0


@pytest.mark.asyncio
async def test_record_and_get_audit_event(client: httpx.AsyncClient) -> None:
    """User can record an audit event and fetch it by entry_id."""
    headers, user_id = await _get_auth(client, f"audit_rec_{uuid.uuid4().hex[:6]}@example.com")

    payload = {
        "agent_slug": "coding",
        "action": "execute_code",
        "skill_slug": "python_sandbox",
        "approval_tier": "T2",
        "approved_by": "user_confirm",
        "model_used": "qwen-2.5-coder-32b",
        "provider": "ollama",
        "request_query": "Calculate factorial of 50",
        "response_summary": "Code executed successfully. Output: 304140932...",
        "decision": "approved_and_executed",
        "latency_ms": 142,
        "status_code": "ok",
        "details": {"exit_code": 0, "lines": 5},
    }

    create_res = await client.post("/api/v1/audit", headers=headers, json=payload)
    assert create_res.status_code == 201
    entry = create_res.json()
    assert entry["id"] is not None
    assert entry["user_id"] == user_id
    assert entry["action"] == "execute_code"
    assert entry["approval_tier"] == "T2"
    assert entry["status_code"] == "ok"
    assert entry["details"]["exit_code"] == 0

    get_res = await client.get(f"/api/v1/audit/{entry['id']}", headers=headers)
    assert get_res.status_code == 200
    fetched = get_res.json()
    assert fetched["id"] == entry["id"]
    assert fetched["action"] == "execute_code"


@pytest.mark.asyncio
async def test_audit_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """User B cannot view or access User A's audit log entry (must return 404)."""
    headers_a, _ = await _get_auth(client, f"audit_userA_{uuid.uuid4().hex[:6]}@example.com")
    headers_b, _ = await _get_auth(client, f"audit_userB_{uuid.uuid4().hex[:6]}@example.com")

    # User A records an event
    create_res = await client.post(
        "/api/v1/audit",
        headers=headers_a,
        json={
            "agent_slug": "finance",
            "action": "transfer_funds",
            "approval_tier": "T3",
            "status_code": "ok",
        },
    )
    assert create_res.status_code == 201
    entry_a_id = create_res.json()["id"]

    # User B attempts to access User A's entry -> strictly 404
    b_res = await client.get(f"/api/v1/audit/{entry_a_id}", headers=headers_b)
    assert b_res.status_code == 404
    assert "not found" in b_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_audit_immutability(client: httpx.AsyncClient) -> None:
    """Audit logs are strictly append-only: PUT, PATCH, and DELETE are not allowed."""
    headers, _ = await _get_auth(client, f"audit_imm_{uuid.uuid4().hex[:6]}@example.com")

    create_res = await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "general", "action": "browse_url", "approval_tier": "T1"},
    )
    assert create_res.status_code == 201
    entry_id = create_res.json()["id"]

    # Attempt PUT
    put_res = await client.put(
        f"/api/v1/audit/{entry_id}",
        headers=headers,
        json={"action": "tampered_action"},
    )
    assert put_res.status_code == 405

    # Attempt PATCH
    patch_res = await client.patch(
        f"/api/v1/audit/{entry_id}",
        headers=headers,
        json={"action": "tampered_action"},
    )
    assert patch_res.status_code == 405

    # Attempt DELETE
    del_res = await client.delete(
        f"/api/v1/audit/{entry_id}",
        headers=headers,
    )
    assert del_res.status_code == 405


@pytest.mark.asyncio
async def test_what_did_jarvis_do_today(client: httpx.AsyncClient) -> None:
    """GET /api/v1/audit/today returns all events logged today in chronological order."""
    headers, _ = await _get_auth(client, f"audit_today_{uuid.uuid4().hex[:6]}@example.com")

    # Record 3 events
    actions = ["summarize_document", "schedule_calendar_event", "send_email"]
    for act in actions:
        await client.post(
            "/api/v1/audit",
            headers=headers,
            json={
                "agent_slug": "coordinator",
                "action": act,
                "approval_tier": "T1" if act != "send_email" else "T2",
                "status_code": "ok",
            },
        )

    today_res = await client.get("/api/v1/audit/today", headers=headers)
    assert today_res.status_code == 200
    data = today_res.json()
    assert len(data) == 3
    returned_actions = [item["action"] for item in data]
    assert "send_email" in returned_actions
    assert "schedule_calendar_event" in returned_actions
    assert "summarize_document" in returned_actions


@pytest.mark.asyncio
async def test_filter_audit_logs_by_agent(client: httpx.AsyncClient) -> None:
    """Querying audit logs filtered by agent_slug only returns matching entries."""
    headers, _ = await _get_auth(client, f"audit_agent_{uuid.uuid4().hex[:6]}@example.com")

    # Create 2 coding events and 1 browser event
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "coding", "action": "run_python", "approval_tier": "T1"},
    )
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "coding", "action": "lint_file", "approval_tier": "T1"},
    )
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "browser", "action": "extract_dom", "approval_tier": "T1"},
    )

    coding_res = await client.get("/api/v1/audit?agent_slug=coding", headers=headers)
    assert coding_res.status_code == 200
    c_data = coding_res.json()
    assert c_data["total"] == 2
    for item in c_data["items"]:
        assert item["agent_slug"] == "coding"

    browser_res = await client.get("/api/v1/audit?agent_slug=browser", headers=headers)
    assert browser_res.status_code == 200
    b_data = browser_res.json()
    assert b_data["total"] == 1
    assert b_data["items"][0]["agent_slug"] == "browser"


@pytest.mark.asyncio
async def test_filter_audit_logs_by_tier_and_status(client: httpx.AsyncClient) -> None:
    """Querying audit logs filtered by approval_tier and status_code returns exact matches."""
    headers, _ = await _get_auth(client, f"audit_tier_{uuid.uuid4().hex[:6]}@example.com")

    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "coordinator", "action": "safe_read", "approval_tier": "T1", "status_code": "ok"},
    )
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "finance", "action": "payout", "approval_tier": "T3", "status_code": "caution"},
    )
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "system", "action": "kill_process", "approval_tier": "T3", "status_code": "error"},
    )

    # Filter T3
    t3_res = await client.get("/api/v1/audit?approval_tier=T3", headers=headers)
    assert t3_res.status_code == 200
    assert t3_res.json()["total"] == 2

    # Filter T3 and error
    err_res = await client.get("/api/v1/audit?approval_tier=T3&status_code=error", headers=headers)
    assert err_res.status_code == 200
    assert err_res.json()["total"] == 1
    assert err_res.json()["items"][0]["action"] == "kill_process"


@pytest.mark.asyncio
async def test_risk_check_clear(client: httpx.AsyncClient) -> None:
    """Pre-execution risk check on safe read-only queries returns clear verdict (T1)."""
    headers, _ = await _get_auth(client, f"risk_clear_{uuid.uuid4().hex[:6]}@example.com")

    req_payload = {
        "action_type": "web_search",
        "target": "OpenAI news",
        "params": {"query": "OpenAI news"},
        "user_prompt": "What are the latest AI news today?",
    }
    risk_res = await client.post("/api/v1/audit/risk-check", headers=headers, json=req_payload)
    assert risk_res.status_code == 200
    data = risk_res.json()
    assert data["risk_verdict"] == "clear"
    assert data["approval_tier"] == "T1"
    assert data["blocking"] is False


@pytest.mark.asyncio
async def test_risk_check_caution(client: httpx.AsyncClient) -> None:
    """Pre-execution risk check on external side-effects returns caution verdict (T2)."""
    headers, _ = await _get_auth(client, f"risk_caution_{uuid.uuid4().hex[:6]}@example.com")

    req_payload = {
        "action_type": "send_email",
        "target": "client@example.com",
        "params": {"subject": "Project Proposal", "body": "Attached is the proposal."},
        "user_prompt": "Send the proposal email to the client.",
    }
    risk_res = await client.post("/api/v1/audit/risk-check", headers=headers, json=req_payload)
    assert risk_res.status_code == 200
    data = risk_res.json()
    assert data["risk_verdict"] == "caution"
    assert data["approval_tier"] == "T2"
    assert data["blocking"] is False
    assert "confirm" in data["warning_to_user"].lower() or "irreversible" in data["warning_to_user"].lower() or "caution" in data["warning_to_user"].lower()


@pytest.mark.asyncio
async def test_risk_check_block(client: httpx.AsyncClient) -> None:
    """Pre-execution risk check on destructive commands or credential exposure returns block verdict (T3)."""
    headers, _ = await _get_auth(client, f"risk_block_{uuid.uuid4().hex[:6]}@example.com")

    # Destructive SQL statement
    req_payload = {
        "action_type": "execute_query",
        "target": "PostgreSQL production",
        "params": {"sql": "DROP TABLE users CASCADE;"},
        "user_prompt": "Drop all user tables now.",
    }
    risk_res = await client.post("/api/v1/audit/risk-check", headers=headers, json=req_payload)
    assert risk_res.status_code == 200
    data = risk_res.json()
    assert data["risk_verdict"] == "block"
    assert data["approval_tier"] == "T3"
    assert data["blocking"] is True
    assert "destructive" in data["reason"].lower() or "drop" in data["reason"].lower()


@pytest.mark.asyncio
async def test_audit_stats_endpoint(client: httpx.AsyncClient) -> None:
    """GET /api/v1/audit/stats computes telemetry breakdown across tiers, statuses, and agents."""
    headers, _ = await _get_auth(client, f"audit_stats_{uuid.uuid4().hex[:6]}@example.com")

    # Record 3 events with different latencies and statuses
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "coding", "action": "compile", "approval_tier": "T1", "status_code": "ok", "latency_ms": 100},
    )
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "finance", "action": "payout", "approval_tier": "T3", "status_code": "caution", "latency_ms": 300},
    )
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "coding", "action": "test", "approval_tier": "T1", "status_code": "ok", "latency_ms": 200},
    )

    stats_res = await client.get("/api/v1/audit/stats", headers=headers)
    assert stats_res.status_code == 200
    st = stats_res.json()
    assert st["total_events"] == 3
    assert st["today_events"] == 3
    assert st["by_agent"].get("coding") == 2
    assert st["by_agent"].get("finance") == 1
    assert st["by_tier"].get("T1") == 2
    assert st["by_tier"].get("T3") == 1
    assert st["by_status"].get("ok") == 2
    assert st["by_status"].get("caution") == 1
    assert st["avg_latency_ms"] == pytest.approx(200.0, rel=1e-2)
    assert st["retention_days"] == 365


@pytest.mark.asyncio
async def test_audit_export_endpoint(client: httpx.AsyncClient) -> None:
    """GET /api/v1/audit/export returns portable GDPR compliant audit archive."""
    headers, user_id = await _get_auth(client, f"audit_export_{uuid.uuid4().hex[:6]}@example.com")

    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={"agent_slug": "browser", "action": "download_pdf", "approval_tier": "T1"},
    )

    export_res = await client.get("/api/v1/audit/export", headers=headers)
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert export_data["user_id"] == user_id
    assert export_data["total_records"] == 1
    assert "1-Year Immutable Append-Only Log" in export_data["retention_policy"]
    assert len(export_data["events"]) == 1
    assert export_data["events"][0]["action"] == "download_pdf"


@pytest.mark.asyncio
async def test_chat_audit_grounding(client: httpx.AsyncClient) -> None:
    """Chat coordinator injects authentic audit log context when user asks about Jarvis's daily actions."""
    headers, _ = await _get_auth(client, f"audit_chatground_{uuid.uuid4().hex[:6]}@example.com")

    # Pre-seed an audit event
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={
            "agent_slug": "browser",
            "action": "book_flight_tickets",
            "approval_tier": "T2",
            "status_code": "ok",
            "response_summary": "Flight tickets reserved for conference trip.",
        },
    )

    # Mock AI Router to capture injected system messages
    mock_response = AsyncMock()
    mock_response.content = "Today I booked your flight tickets for your conference trip."
    mock_response.provider = "mock_provider"
    mock_response.model = "mock_model"

    with patch("app.api.v1.runtime.AIRouter.route", return_value=mock_response) as mock_route:
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={"message": "What did you do today?"},
        )
        assert chat_res.status_code == 200
        assert mock_route.called
        call_request = mock_route.call_args[0][0]
        system_msgs = [m.content for m in call_request.messages if m.role.value == "system"]
        audit_grounded = any("AUDIT CONTEXT — ACTIONS PERFORMED TODAY" in sm for sm in system_msgs)
        assert audit_grounded is True


@pytest.mark.asyncio
async def test_chat_audit_offline_fallback(client: httpx.AsyncClient) -> None:
    """When LLM router fails, chat coordinator returns authentic offline fallback with audit log telemetry."""
    headers, _ = await _get_auth(client, f"audit_chatoffline_{uuid.uuid4().hex[:6]}@example.com")

    # Pre-seed an audit event
    await client.post(
        "/api/v1/audit",
        headers=headers,
        json={
            "agent_slug": "coding",
            "action": "refactor_database_migration",
            "approval_tier": "T1",
            "status_code": "ok",
        },
    )

    # Mock AIRouter.route to raise an exception simulating offline failure
    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Gateway timeout")):
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={"message": "Show me my audit log and what actions Jarvis took today."},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["agent_slug"] == "audit"
        assert "activity and audit summary for today" in data["response"]
        assert "Total Events Recorded:" in data["response"]
        assert "refactor_database_migration" in data["response"]
