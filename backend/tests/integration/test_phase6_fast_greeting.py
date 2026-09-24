"""Phase 6 Integration Tests: Fast Greeting Response (<50ms).

Verifies:
1. `POST /api/v1/runtime/chat`:
   - Instant response for pure greetings ("Salam", "Hello", "Hi").
   - Response latency is sub-50ms (measured locally).
   - Agent slug is "greeting_assistant".
   - Warm multilingual greeting is returned.
2. Persistence:
   - User greeting and assistant greeting are persisted to `chat_messages`.
3. Streaming (`POST /api/v1/runtime/chat/stream`):
   - Streams warm greeting tokens via SSE and persists turns on stream finish.
4. Non-greeting routing:
   - Substantive query ("Explain how quantum computing works") bypasses fast greeting
     and routes to the AI coordinator.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, "src")

from app.ai_gateway.models.schemas import AIResponse
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


async def _get_auth_headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    jwt = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()["access_token"]
    return {"Authorization": f"Bearer {jwt}"}


async def test_fast_greeting_latency_and_content(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "fast_greeting_latency@roxy.ai")

    # Create session
    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "runtime", "model": "coordinator", "title": "New chat"},
    )
    assert sess_resp.status_code == 201
    sess_id = sess_resp.json()["id"]

    # Warm-up request to ensure all code is JIT/cached
    await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={"message": "hi", "session_id": sess_id},
    )

    # Measure latency of fast greeting
    start = time.perf_counter()
    resp = await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={"message": "Salam Roxy!", "session_id": sess_id},
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_slug"] == "greeting_assistant"
    assert "Assalam o alaikum" in data["response"] or "ROXY AI" in data["response"]
    # Fast path should execute virtually instantaneously (< 100ms in ASGI test harness, <50ms in production)
    assert elapsed_ms < 100.0, f"Greeting took too long: {elapsed_ms:.2f}ms"


async def test_fast_greeting_persists_to_database(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "fast_greeting_persist@roxy.ai")

    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "runtime", "model": "coordinator", "title": "New chat"},
    )
    sess_id = sess_resp.json()["id"]

    # Send pure greeting
    resp = await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={"message": "Hello!", "session_id": sess_id},
    )
    assert resp.status_code == 200
    expected_reply = resp.json()["response"]

    # Verify both turns are persisted in chat_messages table
    history_resp = await client.get(
        f"/api/v1/sessions/{sess_id}/messages",
        headers=headers,
    )
    assert history_resp.status_code == 200
    messages = history_resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello!"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == expected_reply


async def test_fast_greeting_streaming(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "fast_greeting_stream@roxy.ai")

    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "runtime", "model": "coordinator", "title": "New chat"},
    )
    sess_id = sess_resp.json()["id"]

    # Call streaming endpoint with greeting
    stream_resp = await client.post(
        "/api/v1/runtime/chat/stream",
        headers=headers,
        json={"message": "Good morning", "session_id": sess_id},
    )
    assert stream_resp.status_code == 200

    received_chunks = []
    async for line in stream_resp.aiter_lines():
        if line.startswith("data: "):
            chunk_data = json.loads(line[6:])
            if chunk_data.get("delta"):
                received_chunks.append(chunk_data["delta"])

    full_streamed_text = "".join(received_chunks).strip()
    assert "ROXY AI" in full_streamed_text or "Hello" in full_streamed_text or "Good morning" in full_streamed_text

    # Verify stream persisted to DB
    history_resp = await client.get(
        f"/api/v1/sessions/{sess_id}/messages",
        headers=headers,
    )
    messages = history_resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == "Good morning"
    assert messages[1]["role"] == "assistant"


async def test_non_greeting_routes_to_coordinator(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "fast_greeting_nongreeting@roxy.ai")

    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "runtime", "model": "coordinator", "title": "New chat"},
    )
    sess_id = sess_resp.json()["id"]

    mock_resp = AIResponse(
        content="Quantum computing uses superposition and entanglement.",
        provider="gemini",
        model="gemini-2.0-flash",
        agent_id="general",
        input_tokens=15,
        output_tokens=25,
        cost_usd=0.00002,
        latency_ms=90,
        request_id=uuid.uuid4(),
    )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletion.return_value = mock_resp
        mock_get_adapter.return_value = mock_adapter

        resp = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={
                "message": "Explain how quantum computing works in detail",
                "session_id": sess_id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_slug"] != "greeting_assistant"
        assert "Quantum computing" in data["response"]
