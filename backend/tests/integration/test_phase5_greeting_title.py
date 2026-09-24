"""Phase 5 Integration Tests: Greeting Detection & Smart Conversation Titling.

Verifies:
1. `is_greeting`: Deterministically identifies pure greetings in English, Urdu, Arabic, Hindi, Spanish, French.
   Returns False for queries containing substantive instructions or questions.
2. `generate_smart_title`: Extracts clean 2–7 word concise titles, stripping prompt filler prefixes.
3. `POST /api/v1/runtime/chat`:
   - A greeting like "Hi" or "Salam" keeps/sets the title to "New Conversation" instead of "Hi".
   - A subsequent substantive turn automatically updates the title to a smart title (e.g. "Photosynthesis").
4. `POST /api/v1/ai/chat`:
   - Greeting keeps "New Conversation".
   - Substantive query automatically smart-titles the session.
5. Manual rename protection:
   - If a user manually renames a session, future messages NEVER overwrite the user's custom title.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, "src")

from app.ai_gateway.models.schemas import AIResponse
from app.api.v1.greeting import generate_smart_title, is_greeting
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


def test_is_greeting_classification() -> None:
    # Pure greetings across multiple languages -> True
    greetings = [
        "hi",
        "Hi!",
        "HELLO",
        "hey there",
        "good morning",
        "good evening!",
        "salam",
        "assalamu alaikum",
        "assalam o alaikum",
        "salam roxy",
        "hola",
        "bonjour",
        "namaste",
        "howdy",
        "whats up",
    ]
    for g in greetings:
        assert is_greeting(g) is True, f"Expected '{g}' to be classified as a greeting"

    # Substantive queries (even if starting with 'hi') -> False
    non_greetings = [
        "What is the capital of France?",
        "Hi, what is the capital of France?",
        "write a python script to parse CSV files",
        "Hello, can you help me calculate monthly compound interest?",
        "Salam, how do I link my bank account to the financial ledger?",
        "explain the difference between tcp and udp",
        "Zanjeerein episode 21 summary",
    ]
    for ng in non_greetings:
        assert is_greeting(ng) is False, f"Expected '{ng}' NOT to be classified as a pure greeting"


def test_generate_smart_title() -> None:
    assert generate_smart_title("What is the capital of France?") == "Capital of France"
    assert generate_smart_title("write a python script to parse CSV files") in ("Parse CSV Files", "CSV Files")
    assert "Photosynthesis" in generate_smart_title("can you please explain how photosynthesis works?")
    assert "Zanjeerein" in generate_smart_title("Zanjeerein episode 21 review and cast")
    assert generate_smart_title("") == "New Conversation"


async def test_runtime_chat_greeting_and_smart_title_transition(
    client: httpx.AsyncClient,
) -> None:
    headers = await _get_auth_headers(client, "greeting_runtime_user@roxy.ai")

    # 1. Create session with default title "New chat"
    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "runtime", "model": "coordinator", "title": "New chat"},
    )
    assert sess_resp.status_code == 201
    sess_id = sess_resp.json()["id"]

    mock_resp_1 = AIResponse(
        content="Hello! How can I assist you today?",
        provider="gemini",
        model="gemini-2.0-flash",
        agent_id="general",
        input_tokens=5,
        output_tokens=10,
        cost_usd=0.00001,
        latency_ms=80,
        request_id=uuid.uuid4(),
    )
    mock_resp_2 = AIResponse(
        content="Photosynthesis is the process by which plants use sunlight to synthesize nutrients.",
        provider="gemini",
        model="gemini-2.0-flash",
        agent_id="general",
        input_tokens=15,
        output_tokens=30,
        cost_usd=0.00003,
        latency_ms=100,
        request_id=uuid.uuid4(),
    )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletion = AsyncMock(side_effect=[mock_resp_1, mock_resp_2])
        mock_get_adapter.return_value = mock_adapter

        # 2. User sends pure greeting "Hi!"
        chat_resp = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={"message": "Hi!", "session_id": sess_id},
        )
        assert chat_resp.status_code == 200

        # 3. Verify session title was NOT renamed to "Hi", but transitioned to "New Conversation"
        sess_after_greeting = (
            await client.get(f"/api/v1/sessions/{sess_id}", headers=headers)
        ).json()
        assert sess_after_greeting["title"] == "New Conversation"
        assert sess_after_greeting["title"] != "Hi!"
        assert sess_after_greeting["title"] != "Hi"

        # 4. In the same session, user now asks a substantive question
        substantive_resp = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={
                "message": "can you explain how photosynthesis works in green plants?",
                "session_id": sess_id,
            },
        )
        assert substantive_resp.status_code == 200

    # 5. Verify session title has been smart-updated to reflect the topic!
    sess_after_query = (
        await client.get(f"/api/v1/sessions/{sess_id}", headers=headers)
    ).json()
    assert sess_after_query["title"] != "New Conversation"
    assert "Photosynthesis" in sess_after_query["title"]


async def test_ai_gateway_greeting_and_subsequent_smart_title(
    client: httpx.AsyncClient,
) -> None:
    headers = await _get_auth_headers(client, "greeting_gateway_user@roxy.ai")

    # 1. Create session
    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "gemini", "model": "gemini-2.0-flash", "title": "New chat"},
    )
    assert sess_resp.status_code == 201
    sess_id = sess_resp.json()["id"]

    # 2. Send greeting "Salam Roxy"
    mock_resp_1 = AIResponse(
        content="Walaikum assalam! How can I assist you today?",
        provider="gemini",
        model="gemini-2.0-flash",
        agent_id="test_agent",
        input_tokens=5,
        output_tokens=10,
        cost_usd=0.00001,
        latency_ms=80,
        request_id=uuid.uuid4(),
    )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletion.return_value = mock_resp_1
        mock_get_adapter.return_value = mock_adapter

        chat_resp = await client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={
                "messages": [{"role": "user", "content": "Salam Roxy"}],
                "provider": "gemini",
                "session_id": sess_id,
            },
        )
        assert chat_resp.status_code == 200

    # Title must remain "New Conversation"
    sess_1 = (await client.get(f"/api/v1/sessions/{sess_id}", headers=headers)).json()
    assert sess_1["title"] == "New Conversation"
    assert "Salam" not in sess_1["title"]

    # 3. Substantive turn
    mock_resp_2 = AIResponse(
        content="Paris is the capital of France.",
        provider="gemini",
        model="gemini-2.0-flash",
        agent_id="test_agent",
        input_tokens=10,
        output_tokens=15,
        cost_usd=0.00002,
        latency_ms=90,
        request_id=uuid.uuid4(),
    )

    with patch("app.ai_gateway.services.router._get_adapter") as mock_get_adapter:
        mock_adapter = AsyncMock()
        mock_adapter.chatCompletion.return_value = mock_resp_2
        mock_get_adapter.return_value = mock_adapter

        chat_resp_2 = await client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={
                "messages": [{"role": "user", "content": "What is the capital of France?"}],
                "provider": "gemini",
                "session_id": sess_id,
            },
        )
        assert chat_resp_2.status_code == 200

    # Title must now be smart-titled
    sess_2 = (await client.get(f"/api/v1/sessions/{sess_id}", headers=headers)).json()
    assert sess_2["title"] == "Capital of France"


async def test_manual_user_rename_is_never_overwritten(
    client: httpx.AsyncClient,
) -> None:
    headers = await _get_auth_headers(client, "greeting_manual_rename@roxy.ai")

    # 1. Create session
    sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "runtime", "model": "coordinator", "title": "New chat"},
    )
    sess_id = sess_resp.json()["id"]

    # 2. User manually renames the session via 3-dots
    rename_resp = await client.patch(
        f"/api/v1/sessions/{sess_id}",
        headers=headers,
        json={"title": "Q3 Financial Strategic Audit"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["title"] == "Q3 Financial Strategic Audit"

    # 3. User sends a message that would normally trigger smart titling
    mock_resp = AIResponse(
        content="Machine learning transformers use multi-head self-attention.",
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
        mock_adapter.chatCompletion = AsyncMock(return_value=mock_resp)
        mock_get_adapter.return_value = mock_adapter

        chat_resp = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={
                "message": "can you explain how machine learning transformers work?",
                "session_id": sess_id,
            },
        )
        assert chat_resp.status_code == 200

    # 4. Verify the manual title was preserved untouched
    sess_final = (await client.get(f"/api/v1/sessions/{sess_id}", headers=headers)).json()
    assert sess_final["title"] == "Q3 Financial Strategic Audit"
