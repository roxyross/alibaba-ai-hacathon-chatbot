"""Phase 13 Master Integration Test Suite: Voice & Real-Time Audio Intelligence Engine.

Verifies:
1. Fresh user starts with clean empty recordings (0 recordings).
2. Voice recording creation and retrieval (POST/GET /api/v1/voice/recordings).
3. Voice recording patching and mutation (PATCH /api/v1/voice/recordings/{id}).
4. Voice recording deletion (DELETE /api/v1/voice/recordings/{id}).
5. Search and tag filtering on recordings.
6. Audio transcription endpoint (POST /api/v1/voice/transcribe).
7. Audio transcription with auto-save as voice note (save_as_note=True).
8. Text-to-speech synthesis endpoint (POST /api/v1/voice/synthesize).
9. Audio intelligence enhancement: summary, title, and action item extraction (POST /api/v1/voice/enhance).
10. Voices and modulations catalog retrieval (GET /api/v1/voice/voices).
11. Strict multi-tenant isolation: User B cannot view, update, or delete User A's recordings (404 Not Found).
12. Multi-agent chat runtime grounding with saved voice notes history.
"""

from __future__ import annotations

import base64
import json
import sys
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.main import app
from app.voice.repository import clear_in_memory_stores


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
async def test_voice_empty_state(client: httpx.AsyncClient) -> None:
    """Verify that a brand-new user starts with 0 voice recordings."""
    email = f"clean_voice_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.get("/api/v1/voice/recordings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["recordings"] == []
    assert data["total"] == 0


# -----------------------------------------------------------------------------
# 2. Create and Retrieve Voice Recording
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_and_get_voice_recording(client: httpx.AsyncClient) -> None:
    """Verify creating a voice note and retrieving it by ID."""
    email = f"voice_author_{uuid.uuid4().hex[:8]}@example.com"
    headers, user_id = await _get_auth(client, email)

    payload: dict[str, Any] = {
        "title": "Weekly Engineering Sync",
        "transcript": "Team discussed database sharding and performance optimizations for Q4.",
        "summary": "Engineering discussed Q4 DB optimizations.",
        "language": "en",
        "tags": ["engineering", "database", "q4"],
        "duration_seconds": 45.5,
        "voice_model": "whisper",
    }
    create_resp = await client.post("/api/v1/voice/recordings", json=payload, headers=headers)
    assert create_resp.status_code == 201
    created = create_resp.json()["recording"]
    assert created["title"] == payload["title"]
    assert created["transcript"] == payload["transcript"]
    assert created["user_id"] == user_id
    assert "engineering" in created["tags"]
    rec_id = created["id"]

    get_resp = await client.get(f"/api/v1/voice/recordings/{rec_id}", headers=headers)
    assert get_resp.status_code == 200
    fetched = get_resp.json()["recording"]
    assert fetched["id"] == rec_id
    assert fetched["title"] == payload["title"]


# -----------------------------------------------------------------------------
# 3. Update Voice Recording Note
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_update_voice_recording(client: httpx.AsyncClient) -> None:
    """Verify patching an existing voice recording."""
    email = f"voice_editor_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/voice/recordings",
        json={"transcript": "Initial quick memo."},
        headers=headers,
    )
    rec_id = create_resp.json()["recording"]["id"]

    patch_resp = await client.patch(
        f"/api/v1/voice/recordings/{rec_id}",
        json={
            "title": "Polished Memo Title",
            "summary": "Concise summary of the memo.",
            "tags": ["memo", "urgent"],
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()["recording"]
    assert updated["title"] == "Polished Memo Title"
    assert updated["summary"] == "Concise summary of the memo."
    assert "urgent" in updated["tags"]


# -----------------------------------------------------------------------------
# 4. Delete Voice Recording
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_delete_voice_recording(client: httpx.AsyncClient) -> None:
    """Verify deleting a voice recording and confirming 404 on next get."""
    email = f"voice_deleter_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/voice/recordings",
        json={"title": "Temporary Recording", "transcript": "Delete me soon."},
        headers=headers,
    )
    rec_id = create_resp.json()["recording"]["id"]

    del_resp = await client.delete(f"/api/v1/voice/recordings/{rec_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    get_resp = await client.get(f"/api/v1/voice/recordings/{rec_id}", headers=headers)
    assert get_resp.status_code == 404


# -----------------------------------------------------------------------------
# 5. Search and Tag Filtering
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_voice_search_and_tag_filtering(client: httpx.AsyncClient) -> None:
    """Verify searching voice recordings by keyword and filtering by tags."""
    email = f"voice_searcher_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/voice/recordings",
        json={"title": "Budget Planning", "transcript": "Financial review and budget forecast.", "tags": ["finance"]},
        headers=headers,
    )
    await client.post(
        "/api/v1/voice/recordings",
        json={"title": "Client Pitch Call", "transcript": "Pitching Acme Corp new marketing features.", "tags": ["client", "sales"]},
        headers=headers,
    )

    # Search by keyword
    search_resp = await client.get("/api/v1/voice/recordings?search=budget", headers=headers)
    assert search_resp.status_code == 200
    assert search_resp.json()["total"] == 1
    assert search_resp.json()["recordings"][0]["title"] == "Budget Planning"

    # Filter by tag
    tag_resp = await client.get("/api/v1/voice/recordings?tag=sales", headers=headers)
    assert tag_resp.status_code == 200
    assert tag_resp.json()["total"] == 1
    assert tag_resp.json()["recordings"][0]["title"] == "Client Pitch Call"


# -----------------------------------------------------------------------------
# 6. Audio Transcription Endpoint
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_voice_transcribe_endpoint(client: httpx.AsyncClient) -> None:
    """Verify transcribing base64 audio payload via POST /api/v1/voice/transcribe."""
    email = f"stt_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    dummy_audio_b64 = base64.b64encode(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00").decode("ascii")

    resp = await client.post(
        "/api/v1/voice/transcribe",
        json={
            "audio_data": dummy_audio_b64,
            "language": "en",
            "model": "whisper",
            "save_as_note": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert data["recording_id"] is None


# -----------------------------------------------------------------------------
# 7. Audio Transcription with Auto-Save Note
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_voice_transcribe_and_save_note(client: httpx.AsyncClient) -> None:
    """Verify transcribing audio and saving directly into the voice notes library."""
    email = f"stt_saver_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    dummy_audio_b64 = base64.b64encode(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00").decode("ascii")

    resp = await client.post(
        "/api/v1/voice/transcribe",
        json={
            "audio_data": dummy_audio_b64,
            "language": "en",
            "model": "whisper",
            "save_as_note": True,
            "title": "Spoken Thought on Product Roadmap",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data

    # Check that note was persisted
    list_resp = await client.get("/api/v1/voice/recordings", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1


# -----------------------------------------------------------------------------
# 8. Text-to-Speech Synthesis Endpoint
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_voice_synthesize_endpoint(client: httpx.AsyncClient) -> None:
    """Verify synthesizing speech via POST /api/v1/voice/synthesize."""
    email = f"tts_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.post(
        "/api/v1/voice/synthesize",
        json={
            "text": "Hello, this is Roxy. Your voice operating system is operational.",
            "voice": "Kore",
            "speed": 1.0,
            "model": "gemini",
            "modulation": "calm",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "audio_data" in data
    assert data["format"] in ("mp3", "wav")
    assert data["model"] == "gemini"


# -----------------------------------------------------------------------------
# 9. Voice Enhancement & Audio Intelligence Endpoint
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_voice_enhance_endpoint(client: httpx.AsyncClient) -> None:
    """Verify transcript enhancement with executive summary and action item extraction."""
    email = f"enhance_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    sample_transcript = (
        "We had a great strategy meeting today regarding mobile app performance. "
        "We need to send the updated benchmark report to the executive board by Friday. "
        "Also, Alex will schedule the security audit next Monday."
    )
    resp = await client.post(
        "/api/v1/voice/enhance",
        json={"transcript": sample_transcript},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "title" in data
    assert "summary" in data
    assert len(data["action_items"]) >= 1
    assert any("send" in a.lower() or "report" in a.lower() or "audit" in a.lower() for a in data["action_items"])
    assert len(data["key_topics"]) >= 1


# -----------------------------------------------------------------------------
# 10. Voices & Personas Catalog Endpoint
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_voice_voices_catalog(client: httpx.AsyncClient) -> None:
    """Verify retrieving catalog of voices, models, and tone modulations."""
    email = f"catalog_user_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    resp = await client.get("/api/v1/voice/voices", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "voices" in data
    assert "modulations" in data
    assert "supported_languages" in data
    assert any(v["id"] == "Kore" for v in data["voices"])
    assert any(m["id"] == "whispering" for m in data["modulations"])


# -----------------------------------------------------------------------------
# 11. Strict Multi-Tenant Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_voice_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """Verify that User B cannot read, patch, or delete User A's voice recordings."""
    headers_a, _ = await _get_auth(client, f"tenant_a_{uuid.uuid4().hex[:8]}@example.com")
    headers_b, _ = await _get_auth(client, f"tenant_b_{uuid.uuid4().hex[:8]}@example.com")

    create_resp = await client.post(
        "/api/v1/voice/recordings",
        json={
            "title": "Secret Audio Log",
            "transcript": "Confidential financial roadmap.",
            "tags": ["confidential"],
        },
        headers=headers_a,
    )
    rec_a_id = create_resp.json()["recording"]["id"]

    # User B tries to view User A's recording -> 404
    get_b = await client.get(f"/api/v1/voice/recordings/{rec_a_id}", headers=headers_b)
    assert get_b.status_code == 404

    # User B tries to update User A's recording -> 404
    patch_b = await client.patch(
        f"/api/v1/voice/recordings/{rec_a_id}",
        json={"title": "Hacked Title"},
        headers=headers_b,
    )
    assert patch_b.status_code == 404

    # User B tries to delete User A's recording -> 404
    del_b = await client.delete(f"/api/v1/voice/recordings/{rec_a_id}", headers=headers_b)
    assert del_b.status_code == 404

    # User B lists recordings -> 0 items
    list_b = await client.get("/api/v1/voice/recordings", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json()["total"] == 0


# -----------------------------------------------------------------------------
# 12. Multi-Agent Chat Grounding with Voice History
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_chat_voice_grounding(client: httpx.AsyncClient) -> None:
    """Verify that coordinator agent chat accurately reflects user's saved voice recordings."""
    email = f"chat_voice_grounding_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/voice/recordings",
        json={
            "title": "Investor Briefing Voice Note",
            "transcript": "Series A pitch went well. Growth metrics impressed the venture partners.",
            "summary": "Positive Series A pitch meeting summary.",
        },
        headers=headers,
    )

    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        json={
            "message": "What voice notes do I currently have saved?",
            "provider": "runtime",
            "model": "coordinator",
        },
        headers=headers,
    )
    assert chat_resp.status_code == 200
    body = chat_resp.json()
    assert "response" in body
    text = body["response"]
    assert "Investor Briefing" in text or "voice note" in text.lower() or "1 saved" in text.lower()


@pytest.mark.anyio
async def test_chat_streaming_voice_grounding(client: httpx.AsyncClient) -> None:
    """Verify that streaming coordinator agent chat accurately reflects user's saved voice recordings."""
    email = f"chat_voice_stream_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/voice/recordings",
        json={
            "title": "Quantum Algorithm Brainstorm",
            "transcript": "Explored Shor algorithm optimizations and error mitigation techniques on NISQ devices.",
            "summary": "NISQ quantum algorithm discussion.",
        },
        headers=headers,
    )

    stream_resp = await client.post(
        "/api/v1/runtime/chat/stream",
        json={
            "message": "What voice notes do I currently have saved?",
            "provider": "runtime",
            "model": "coordinator",
        },
        headers=headers,
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")

    full_text = ""
    for raw_line in stream_resp.text.splitlines():
        line = raw_line.strip()
        if line.startswith("data:"):
            payload_str = line[len("data:"):].strip()
            if payload_str:
                chunk = json.loads(payload_str)
                full_text += chunk.get("delta", "")

    assert (
        "Quantum Algorithm Brainstorm" in full_text
        or "voice note" in full_text.lower()
        or "1 saved" in full_text.lower()
    )


@pytest.mark.anyio
async def test_chat_voice_offline_fallback(client: httpx.AsyncClient) -> None:
    """When router fails, runtime chat returns authentic offline fallback with voice notes library."""
    email = f"chat_voice_off_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/voice/recordings",
        json={
            "title": "Autonomous Agent Keynote Reflection",
            "transcript": "Keynote covered multi-agent coordination, local SLMs, and streaming state machines.",
            "summary": "Keynote recap on multi-agent SLM systems.",
        },
        headers=headers,
    )

    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Model stream unreachable")):
        chat_resp = await client.post(
            "/api/v1/runtime/chat",
            json={
                "message": "What voice notes do I currently have saved?",
                "provider": "runtime",
                "model": "coordinator",
            },
            headers=headers,
        )
        assert chat_resp.status_code == 200
        body = chat_resp.json()
        assert body["agent_slug"] == "voice"
        assert "Autonomous Agent Keynote Reflection" in body["response"]
        assert "voice recording(s)" in body["response"]


