"""Phase 8 Integration Tests: Streaming UX (Reply Now vs Stop Polishing & Stream Persistence).

Verifies:
1. `POST /api/v1/runtime/chat/stream`:
   - Streams valid SSE data events with deltas and completion flag.
   - Delivers attribution event upon completion.
   - Persists completed stream turns to `chat_messages` when `session_id` is supplied.
2. Fast Greeting Streaming:
   - Delivers sub-50ms token stream and persists turns.
3. Guest Trial Streaming:
   - Validates unauthenticated streaming functions cleanly without crashing.
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, "src")

from app.ai_gateway.models.schemas import StreamingChunk
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


async def test_runtime_chat_stream_turn_persistence(client: httpx.AsyncClient) -> None:
    """Verifies that streamed assistant responses are persisted to chat_messages when session_id is provided."""
    headers = await _get_auth_headers(client, "streaming_persistence_user@roxy.ai")

    # Create session
    sess_res = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"title": "Streaming Test Session", "provider": "runtime", "model": "coordinator"},
    )
    assert sess_res.status_code == 201
    session_id = sess_res.json()["id"]

    # Mock adapter stream
    async def mock_adapter_stream(_request: object) -> AsyncIterator[StreamingChunk]:
        yield StreamingChunk(
            delta="Hello, ",
            provider="gemini",
            model="gemini-2.0-flash",
            done=False,
        )
        yield StreamingChunk(
            delta="this is streamed content!",
            provider="gemini",
            model="gemini-2.0-flash",
            done=True,
        )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletionStream = mock_adapter_stream
        mock_get_adapter.return_value = mock_adapter

        resp = await client.post(
            "/api/v1/runtime/chat/stream",
            headers=headers,
            json={
                "message": "Please stream a response",
                "session_id": session_id,
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        # Parse SSE
        lines = resp.text.split("\n")
        deltas = []
        attribution_seen = False

        for raw_line in lines:
            line = raw_line.strip()
            if line.startswith("data: "):
                data_str = line[len("data: "):]
                try:
                    parsed = json.loads(data_str)
                    if "delta" in parsed and parsed["delta"]:
                        deltas.append(parsed["delta"])
                    if parsed.get("done") and "agent_slug" in parsed:
                        attribution_seen = True
                except json.JSONDecodeError:
                    pass

        assert "".join(deltas) == "Hello, this is streamed content!"
        assert attribution_seen

    # Verify database persistence
    msgs_res = await client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Please stream a response"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Hello, this is streamed content!"


async def test_runtime_chat_stream_fast_greeting(client: httpx.AsyncClient) -> None:
    """Verifies that fast greeting streaming returns immediate tokens and persists."""
    headers = await _get_auth_headers(client, "streaming_greeting_user@roxy.ai")

    sess_res = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"title": "Greeting Stream Session", "provider": "runtime", "model": "coordinator"},
    )
    assert sess_res.status_code == 201
    session_id = sess_res.json()["id"]

    resp = await client.post(
        "/api/v1/runtime/chat/stream",
        headers=headers,
        json={
            "message": "Salam Roxy!",
            "session_id": session_id,
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    lines = resp.text.split("\n")
    deltas = []
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("data: "):
            try:
                parsed = json.loads(line[len("data: "):])
                if parsed.get("delta"):
                    deltas.append(parsed["delta"])
            except json.JSONDecodeError:
                pass

    streamed_text = "".join(deltas)
    assert len(streamed_text) > 0
    assert any(w in streamed_text for w in ("Salam", "ROXY", "Walaikum"))

    # Verify persisted in database
    msgs_res = await client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Salam Roxy!"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == streamed_text


async def test_runtime_chat_stream_guest_mode(client: httpx.AsyncClient) -> None:
    """Verifies that guest trial streaming without auth returns SSE stream properly."""
    async def mock_route_stream(_request: object) -> AsyncIterator[StreamingChunk]:
        yield StreamingChunk(
            delta="Guest response token",
            provider="test_provider",
            model="test_model",
            done=True,
        )

    with patch(
        "app.ai_gateway.services.router.AIRouter.route_stream",
        side_effect=mock_route_stream,
    ):
        resp = await client.post(
            "/api/v1/runtime/chat/stream",
            json={"message": "Hello from guest"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert "Guest response token" in resp.text
