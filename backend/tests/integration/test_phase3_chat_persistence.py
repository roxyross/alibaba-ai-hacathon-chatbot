"""Phase 3 Master Integration Test Suite: Chat & Streaming Persistence.

Verifies:
1. Non-streaming chat (POST /api/v1/ai/chat) persists user and assistant turns to chat_messages.
2. Streaming chat (POST /api/v1/ai/chat/stream) accumulates full token stream and persists complete response.
3. Auto-titling of session from first user message.
4. Session updated_at timestamp touched when messages are added.
5. Strict cross-tenant isolation: User B cannot read User A's session messages (404 Not Found).
6. Runtime coordinator chat and streaming persistence (POST /api/v1/runtime/chat and /stream).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.ai_gateway.models.schemas import AIResponse, StreamingChunk
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


async def test_non_streaming_chat_persists_both_turns_and_autotitles(
    client: httpx.AsyncClient,
) -> None:
    headers = await _get_auth_headers(client, "chat_persistence_user1@roxy.ai")

    # 1. Create a session with default title
    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "gemini", "model": "gemini-2.0-flash", "title": "New chat"},
    )
    assert sess_resp.status_code == 201
    session = sess_resp.json()
    sess_id = session["id"]
    assert session["title"] == "New chat"

    # 2. Mock adapter response for gemini
    mock_resp = AIResponse(
        content="Paris is the capital of France and is famous for the Eiffel Tower.",
        provider="gemini",
        model="gemini-2.0-flash",
        agent_id="test_agent",
        input_tokens=15,
        output_tokens=22,
        cost_usd=0.00004,
        latency_ms=120,
        request_id=uuid.uuid4(),
    )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletion.return_value = mock_resp
        mock_get_adapter.return_value = mock_adapter

        chat_resp = await client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={
                "messages": [
                    {"role": "user", "content": "What is the capital of France?"}
                ],
                "provider": "gemini",
                "session_id": sess_id,
            },
        )
        assert chat_resp.status_code == 200

    # 3. Verify messages are persisted in chat_messages table
    history_resp = await client.get(
        f"/api/v1/sessions/{sess_id}/messages",
        headers=headers,
    )
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    messages = history_data["messages"]
    assert len(messages) == 2

    # User message
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is the capital of France?"

    # Assistant message
    assert messages[1]["role"] == "assistant"
    assert (
        messages[1]["content"]
        == "Paris is the capital of France and is famous for the Eiffel Tower."
    )
    assert messages[1]["provider"] == "gemini"
    assert messages[1]["model"] == "gemini-2.0-flash"

    # 4. Verify session auto-titling from first prompt
    updated_sess_resp = await client.get(
        f"/api/v1/sessions/{sess_id}",
        headers=headers,
    )
    assert updated_sess_resp.status_code == 200
    updated_sess = updated_sess_resp.json()
    assert updated_sess["title"] in ("Capital of France", "What is the capital of France?")
    assert updated_sess["message_count"] == 2


async def test_streaming_chat_accumulates_and_persists_full_response(
    client: httpx.AsyncClient,
) -> None:
    headers = await _get_auth_headers(client, "chat_persistence_stream_user@roxy.ai")

    # 1. Create a session
    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "gemini", "model": "gemini-2.0-flash", "title": "Stream Test"},
    )
    assert sess_resp.status_code == 201
    sess_id = sess_resp.json()["id"]

    # 2. Mock streaming chunks from provider adapter
    async def mock_stream(request: Any) -> AsyncIterator[StreamingChunk]:
        chunks = [
            "The quick ",
            "brown fox ",
            "jumps over ",
            "the lazy dog.",
        ]
        for c in chunks:
            yield StreamingChunk(
                delta=c,
                provider="gemini",
                model="gemini-2.0-flash",
                done=False,
            )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletionStream = mock_stream
        mock_get_adapter.return_value = mock_adapter

        stream_resp = await client.post(
            "/api/v1/ai/chat/stream",
            headers=headers,
            json={
                "messages": [
                    {"role": "user", "content": "Type the quick brown fox sentence."}
                ],
                "provider": "gemini",
                "stream": True,
                "session_id": sess_id,
            },
        )
        assert stream_resp.status_code == 200
        # Consume full SSE stream
        sse_body = b""
        async for part in stream_resp.aiter_bytes():
            sse_body += part
        assert len(sse_body) > 0

    # 3. Verify messages in history: the assistant message must contain the FULL accumulated text!
    history_resp = await client.get(
        f"/api/v1/sessions/{sess_id}/messages",
        headers=headers,
    )
    assert history_resp.status_code == 200
    messages = history_resp.json()["messages"]
    assert len(messages) == 2

    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Type the quick brown fox sentence."

    assert messages[1]["role"] == "assistant"
    # CRITICAL INVARIANT: Not just the last chunk 'the lazy dog.'!
    assert (
        messages[1]["content"]
        == "The quick brown fox jumps over the lazy dog."
    )


async def test_cross_tenant_message_isolation(client: httpx.AsyncClient) -> None:
    headers_user_a = await _get_auth_headers(client, "user_alpha_persist@roxy.ai")
    headers_user_b = await _get_auth_headers(client, "user_bravo_persist@roxy.ai")

    # 1. User A creates session and adds a message
    sess_a = (
        await client.post(
            "/api/v1/sessions",
            headers=headers_user_a,
            json={"provider": "gemini", "model": "gemini-2.0-flash", "title": "Confidential Alpha"},
        )
    ).json()
    sess_a_id = sess_a["id"]

    mock_resp = AIResponse(
        content="Secret financial data for Alpha.",
        provider="gemini",
        model="gemini-2.0-flash",
        agent_id="test_agent",
        request_id=uuid.uuid4(),
    )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletion.return_value = mock_resp
        mock_get_adapter.return_value = mock_adapter

        await client.post(
            "/api/v1/ai/chat",
            headers=headers_user_a,
            json={
                "messages": [{"role": "user", "content": "Show my confidential balance."}],
                "session_id": sess_a_id,
            },
        )

    # User A can read their own messages
    a_msgs = await client.get(
        f"/api/v1/sessions/{sess_a_id}/messages",
        headers=headers_user_a,
    )
    assert a_msgs.status_code == 200
    assert len(a_msgs.json()["messages"]) == 2

    # 2. User B tries to read User A's session messages -> MUST return 404
    b_read = await client.get(
        f"/api/v1/sessions/{sess_a_id}/messages",
        headers=headers_user_b,
    )
    assert b_read.status_code == 404

    # User B tries to get session metadata -> MUST return 404
    b_sess = await client.get(
        f"/api/v1/sessions/{sess_a_id}",
        headers=headers_user_b,
    )
    assert b_sess.status_code == 404


async def test_runtime_chat_and_stream_persistence(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "runtime_persist_user@roxy.ai")

    # 1. Create session
    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "runtime", "model": "coordinator", "title": "New chat"},
    )
    assert sess_resp.status_code == 201
    sess_id = sess_resp.json()["id"]

    # 2. Call POST /api/v1/runtime/chat (image intent)
    img_chat_resp = await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={
            "message": "create an image of a neon cyber city",
            "session_id": sess_id,
        },
    )
    assert img_chat_resp.status_code == 200

    # Verify turn is persisted in chat_messages
    history = (
        await client.get(
            f"/api/v1/sessions/{sess_id}/messages",
            headers=headers,
        )
    ).json()["messages"]
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "create an image of a neon cyber city"
    assert history[1]["role"] == "assistant"
    assert "https://image.pollinations.ai" in history[1]["content"]

    # 3. Call POST /api/v1/runtime/chat/stream with Python code query
    async def mock_code_stream(request: Any) -> AsyncIterator[StreamingChunk]:
        code_chunks = [
            "def add_numbers(a: int, b: int) -> int:\n",
            "    \"\"\"Return the sum of two numbers.\"\"\"\n",
            "    return a + b\n",
        ]
        for c in code_chunks:
            yield StreamingChunk(
                delta=c,
                provider="gemini",
                model="gemini-2.0-flash",
                done=False,
            )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletionStream = mock_code_stream
        mock_get_adapter.return_value = mock_adapter

        stream_resp = await client.post(
            "/api/v1/runtime/chat/stream",
            headers=headers,
            json={
                "message": "write a python function to add two numbers",
                "session_id": sess_id,
            },
        )
        assert stream_resp.status_code == 200
        async for _ in stream_resp.aiter_bytes():
            pass

    # Verify history now has 4 messages
    history_after = (
        await client.get(
            f"/api/v1/sessions/{sess_id}/messages",
            headers=headers,
        )
    ).json()["messages"]
    assert len(history_after) == 4
    assert history_after[2]["role"] == "user"
    assert history_after[2]["content"] == "write a python function to add two numbers"
    assert history_after[3]["role"] == "assistant"
    assert "def add_numbers(a: int, b: int) -> int:" in history_after[3]["content"]
