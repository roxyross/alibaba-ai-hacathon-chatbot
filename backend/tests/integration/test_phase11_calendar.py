"""Phase 11 Master Integration Test Suite: Calendar & Event Scheduling Engine.

Verifies:
1. Fresh user starts with a clean empty calendar (0 events).
2. Event creation, retrieval, and date/category filtering.
3. Event patching and mutation (PATCH /api/v1/calendar/events/{id}).
4. Event deletion (DELETE /api/v1/calendar/events/{id}).
5. Strict multi-tenant isolation: User B cannot view, update, or delete User A's events (404 Not Found).
6. Natural language AI event parser (POST /api/v1/calendar/parse-ai).
7. RFC 5545 iCalendar (.ics) export and import round-trip.
8. Upcoming events query (GET /api/v1/calendar/upcoming).
9. Multi-agent chat runtime grounding with calendar schedule.
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.calendar.repository import clear_in_memory_stores
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
async def test_calendar_empty_state(client: httpx.AsyncClient) -> None:
    """Verify fresh user starts with clean empty schedule."""
    auth, _ = await _get_auth(client, f"cal_fresh_{uuid.uuid4().hex[:6]}@roxy.ai")

    resp = await client.get("/api/v1/calendar/events", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"] == []
    assert data["total"] == 0

    up_resp = await client.get("/api/v1/calendar/upcoming", headers=auth)
    assert up_resp.status_code == 200
    assert up_resp.json()["events"] == []


# -----------------------------------------------------------------------------
# 2. Event Creation & Listing with Filtering
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_and_list_events(client: httpx.AsyncClient) -> None:
    """Create events with dates, categories, locations and verify listing and filtering."""
    auth, user_id = await _get_auth(client, f"cal_create_{uuid.uuid4().hex[:6]}@roxy.ai")

    now = datetime.now(UTC)
    tomorrow = now + timedelta(days=1)
    next_week = now + timedelta(days=7)

    # Event 1: Meeting
    res1 = await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "Alibaba Cloud Architecture Sync",
            "start_time": tomorrow.isoformat(),
            "end_time": (tomorrow + timedelta(hours=1)).isoformat(),
            "description": "Discuss model inference and serverless scaling.",
            "location": "Zoom Meeting",
            "category": "meeting",
        },
    )
    assert res1.status_code == 200
    ev1 = res1.json()["event"]
    assert ev1["title"] == "Alibaba Cloud Architecture Sync"
    assert ev1["category"] == "meeting"
    assert ev1["location"] == "Zoom Meeting"

    # Event 2: Hackathon
    res2 = await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "AI Hackathon Final Submission",
            "start_time": next_week.isoformat(),
            "category": "hackathon",
            "location": "Virtual Portal",
        },
    )
    assert res2.status_code == 200
    ev2 = res2.json()["event"]
    assert ev2["title"] == "AI Hackathon Final Submission"
    assert ev2["category"] == "hackathon"

    # List all
    all_res = await client.get("/api/v1/calendar/events", headers=auth)
    assert all_res.status_code == 200
    events = all_res.json()["events"]
    assert len(events) == 2

    # Filter by category = 'hackathon'
    h_res = await client.get("/api/v1/calendar/events?category=hackathon", headers=auth)
    assert h_res.status_code == 200
    h_events = h_res.json()["events"]
    assert len(h_events) == 1
    assert h_events[0]["title"] == "AI Hackathon Final Submission"


# -----------------------------------------------------------------------------
# 3. Update Event (PATCH)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_update_event(client: httpx.AsyncClient) -> None:
    """Verify modifying event parameters."""
    auth, user_id = await _get_auth(client, f"cal_patch_{uuid.uuid4().hex[:6]}@roxy.ai")

    res = await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "Preliminary Review",
            "start_time": datetime.now(UTC).isoformat(),
            "category": "meeting",
        },
    )
    ev_id = res.json()["event"]["id"]

    # Patch event
    patch_res = await client.patch(
        f"/api/v1/calendar/events/{ev_id}",
        headers=auth,
        json={
            "title": "Final Approved Architecture Review",
            "location": "Google Meet",
            "category": "deadline",
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()["event"]
    assert updated["title"] == "Final Approved Architecture Review"
    assert updated["location"] == "Google Meet"
    assert updated["category"] == "deadline"


# -----------------------------------------------------------------------------
# 4. Delete Event (DELETE)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_delete_event(client: httpx.AsyncClient) -> None:
    """Verify deleting event and confirming absence."""
    auth, user_id = await _get_auth(client, f"cal_del_{uuid.uuid4().hex[:6]}@roxy.ai")

    res = await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "Ephemeral Sync",
            "start_time": datetime.now(UTC).isoformat(),
        },
    )
    ev_id = res.json()["event"]["id"]

    # Delete
    del_res = await client.delete(f"/api/v1/calendar/events/{ev_id}", headers=auth)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Confirm 404
    get_res = await client.get(f"/api/v1/calendar/events/{ev_id}", headers=auth)
    assert get_res.status_code == 404


# -----------------------------------------------------------------------------
# 5. Multi-Tenant Security Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_calendar_multi_tenant_isolation(client: httpx.AsyncClient) -> None:
    """User B cannot view, edit, or delete User A's scheduled events."""
    auth_a, user_a = await _get_auth(client, f"cal_alice_{uuid.uuid4().hex[:6]}@roxy.ai")
    auth_b, user_b = await _get_auth(client, f"cal_bob_{uuid.uuid4().hex[:6]}@roxy.ai")

    # User A creates confidential event
    res_a = await client.post(
        "/api/v1/calendar/events",
        headers=auth_a,
        json={
            "title": "Project Excalibur Closed-Door Board Meeting",
            "start_time": datetime.now(UTC).isoformat(),
            "location": "Penthouse Boardroom",
        },
    )
    ev_a_id = res_a.json()["event"]["id"]

    # User B lists events -> empty
    b_list = await client.get("/api/v1/calendar/events", headers=auth_b)
    assert b_list.status_code == 200
    assert len(b_list.json()["events"]) == 0

    # User B attempts to fetch User A's event -> 404
    b_get = await client.get(f"/api/v1/calendar/events/{ev_a_id}", headers=auth_b)
    assert b_get.status_code == 404

    # User B attempts to patch User A's event -> 404
    b_patch = await client.patch(
        f"/api/v1/calendar/events/{ev_a_id}",
        headers=auth_b,
        json={"title": "Hacked Title"},
    )
    assert b_patch.status_code == 404

    # User B attempts to delete User A's event -> 404
    b_del = await client.delete(f"/api/v1/calendar/events/{ev_a_id}", headers=auth_b)
    assert b_del.status_code == 404

    # Verify User A's event is intact
    a_get = await client.get(f"/api/v1/calendar/events/{ev_a_id}", headers=auth_a)
    assert a_get.status_code == 200
    assert a_get.json()["event"]["title"] == "Project Excalibur Closed-Door Board Meeting"


# -----------------------------------------------------------------------------
# 6. Natural Language AI Event Parser
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ai_event_prompt_parser(client: httpx.AsyncClient) -> None:
    """Verify natural language prompt parser returns structured draft event fields."""
    auth, user_id = await _get_auth(client, f"cal_ai_{uuid.uuid4().hex[:6]}@roxy.ai")

    prompt = "Schedule team sprint sync tomorrow at 3pm for 45 minutes on Zoom"
    res = await client.post(
        "/api/v1/calendar/parse-ai",
        headers=auth,
        json={"prompt": prompt},
    )
    assert res.status_code == 200
    draft = res.json()["draft_event"]
    assert "Sprint Sync" in draft["title"] or "Team" in draft["title"]
    assert draft["location"] == "Zoom Meeting"
    assert draft["category"] == "meeting"
    assert "start_time" in draft
    assert "end_time" in draft


# -----------------------------------------------------------------------------
# 7. RFC 5545 iCalendar (.ics) Export and Import
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ics_export_and_import(client: httpx.AsyncClient) -> None:
    """Export schedule as standard .ics and import it back."""
    auth, user_id = await _get_auth(client, f"cal_ics_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create event
    await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "AI Product Demo",
            "start_time": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "location": "Auditorium A",
            "description": "Presenting ROXY-AI multimodal features.",
            "category": "meeting",
        },
    )

    # Export ICS
    export_res = await client.get("/api/v1/calendar/export/ics", headers=auth)
    assert export_res.status_code == 200
    assert "text/calendar" in export_res.headers.get("content-type", "")
    ics_text = export_res.text
    assert "BEGIN:VCALENDAR" in ics_text
    assert "SUMMARY:AI Product Demo" in ics_text
    assert "LOCATION:Auditorium A" in ics_text
    assert "END:VCALENDAR" in ics_text

    # Fresh user B imports this ICS
    auth_b, user_b = await _get_auth(client, f"cal_importer_{uuid.uuid4().hex[:6]}@roxy.ai")
    files = {"file": ("demo.ics", io.BytesIO(ics_text.encode("utf-8")), "text/calendar")}

    import_res = await client.post("/api/v1/calendar/import/ics", headers=auth_b, files=files)
    assert import_res.status_code == 200
    import_data = import_res.json()
    assert import_data["imported_count"] >= 1

    # Verify User B now has the event
    b_events = (await client.get("/api/v1/calendar/events", headers=auth_b)).json()["events"]
    assert any("AI Product Demo" in e["title"] for e in b_events)


# -----------------------------------------------------------------------------
# 8. Upcoming Events Query
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_upcoming_events(client: httpx.AsyncClient) -> None:
    """Verify upcoming events filters to the next 7 days."""
    auth, user_id = await _get_auth(client, f"cal_up_{uuid.uuid4().hex[:6]}@roxy.ai")

    now = datetime.now(UTC)
    # In 2 days (upcoming)
    await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={"title": "Upcoming Meeting", "start_time": (now + timedelta(days=2)).isoformat()},
    )
    # In 20 days (not in 7-day upcoming)
    await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={"title": "Far Future Summit", "start_time": (now + timedelta(days=20)).isoformat()},
    )

    up_res = await client.get("/api/v1/calendar/upcoming", headers=auth)
    assert up_res.status_code == 200
    up_events = up_res.json()["events"]
    assert len(up_events) == 1
    assert up_events[0]["title"] == "Upcoming Meeting"


# -----------------------------------------------------------------------------
# 9. Multi-Agent Chat Grounding
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_calendar_chat_grounding(client: httpx.AsyncClient) -> None:
    """Verify calendar schedule is grounded into multi-agent chat conversation."""
    auth, user_id = await _get_auth(client, f"cal_chat_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create scheduled event
    await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "Quantum Robotics Demonstration",
            "start_time": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
            "location": "Virtual Lab",
            "category": "hackathon",
        },
    )

    # Query chat asking about schedule
    chat_res = await client.post(
        "/api/v1/runtime/chat",
        headers=auth,
        json={
            "message": "What is on my calendar schedule today?",
            "agent_override": "calendar",
        },
    )
    assert chat_res.status_code == 200
    res_text = chat_res.json()["response"]
    assert "Quantum Robotics Demonstration" in res_text


@pytest.mark.anyio
async def test_calendar_streaming_chat_grounding(client: httpx.AsyncClient) -> None:
    """Verify calendar schedule is grounded into streaming multi-agent chat."""
    auth, user_id = await _get_auth(client, f"cal_chat_str_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create scheduled event
    await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "Autonomous Agent Keynote Presentation",
            "start_time": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "location": "Main Stage",
            "category": "hackathon",
        },
    )

    # Query streaming chat asking about schedule
    stream_res = await client.post(
        "/api/v1/runtime/chat/stream",
        headers=auth,
        json={
            "message": "What is on my calendar schedule today?",
            "agent_override": "calendar",
        },
    )
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers.get("content-type", "")

    full_text = ""
    for raw_line in stream_res.text.splitlines():
        line = raw_line.strip()
        if line.startswith("data:"):
            payload_str = line[len("data:"):].strip()
            if payload_str:
                chunk = json.loads(payload_str)
                full_text += chunk.get("delta", "")

    assert "Autonomous Agent Keynote Presentation" in full_text


@pytest.mark.anyio
async def test_calendar_chat_grounding_without_override(client: httpx.AsyncClient) -> None:
    """Verify calendar schedule inquiry automatically routes and grounds without explicit agent override."""
    auth, user_id = await _get_auth(client, f"cal_auto_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create scheduled event
    await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "Global Hackathon Demo Day",
            "start_time": (datetime.now(UTC) + timedelta(hours=5)).isoformat(),
            "location": "Innovation Auditorium",
            "category": "hackathon",
        },
    )

    mock_response = AsyncMock()
    mock_response.content = "You have the Global Hackathon Demo Day scheduled in the Innovation Auditorium."
    mock_response.provider = "mock_provider"
    mock_response.model = "mock_model"

    with patch("app.api.v1.runtime.AIRouter.route", return_value=mock_response) as mock_route:
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "What is on my calendar schedule today?"},
        )
        assert chat_res.status_code == 200
        assert mock_route.called
        call_request = mock_route.call_args[0][0]
        system_msgs = [m.content for m in call_request.messages if m.role.value == "system"]
        cal_grounded = any("CALENDAR CONTEXT" in sm for sm in system_msgs)
        assert cal_grounded is True
        assert any("Global Hackathon Demo Day" in sm for sm in system_msgs)


@pytest.mark.anyio
async def test_calendar_chat_offline_fallback(client: httpx.AsyncClient) -> None:
    """When router fails, runtime chat returns authentic offline fallback with calendar events."""
    auth, user_id = await _get_auth(client, f"cal_off_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create scheduled event
    await client.post(
        "/api/v1/calendar/events",
        headers=auth,
        json={
            "title": "Deep Learning Architecture Review",
            "start_time": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
            "location": "Conference Room B",
            "category": "meeting",
        },
    )

    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Model stream unreachable")):
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "What is on my calendar schedule today?"},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["agent_slug"] == "calendar"
        assert "Deep Learning Architecture Review" in data["response"]
        assert "event(s) on your calendar" in data["response"]


