"""Integration tests for Voice WebSocket and Browser API endpoints.

Per spec §3.6 (Voice) and §3.7 (Browser):
- Voice: WebSocket /api/v1/runtime/voice — auth handshake, session lifecycle
- Browser: POST /api/v1/runtime/browser/run — navigation and form-fill tasks
"""

from __future__ import annotations

import json

import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from runtime.main import create_app

import time
import jwt

from runtime.config import settings

# Valid JWT for auth
_DUMMY_TOKEN = jwt.encode(
    {"sub": "test-user-id", "email": "test@example.com", "exp": int(time.time()) + 3600},
    settings.jwt_secret,
    algorithm=settings.jwt_algorithm,
)
_AUTH_HEADER = {"Authorization": f"Bearer {_DUMMY_TOKEN}"}


# ---- fixtures ---------------------------------------------------------------

@pytest.fixture
def app() -> FastAPI:
    return create_app()


# ---- Voice WebSocket tests --------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_voice_ws_auth_handshake(app: FastAPI) -> None:
    """WebSocket accepts auth message and transitions to idle session."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/runtime/voice") as ws:
            # First message must be auth
            ws.send_json({"type": "auth", "token": _DUMMY_TOKEN})
            data = ws.receive_json()
            assert data["type"] == "state"
            assert data["state"] == "idle"
            assert "session_id" in data


@respx.mock
@pytest.mark.asyncio
async def test_voice_ws_rejects_missing_auth(app: FastAPI) -> None:
    """First message is not auth → server sends error and closes."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/runtime/voice") as ws:
            ws.send_json({"type": "text", "text": "hello"})
            data = ws.receive_json()
            # Server should respond with an error about needing auth first
            assert data["type"] == "error"
            assert "auth" in data["message"].lower()


@respx.mock
@pytest.mark.asyncio
async def test_voice_ws_text_message_returns_transcript(app: FastAPI) -> None:
    """Text message is processed and returns transcript + audio stub."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/runtime/voice") as ws:
            ws.send_json({"type": "auth", "token": _DUMMY_TOKEN})
            ws.receive_json()  # state: idle

            ws.send_json({"type": "text", "text": "What is the weather today?"})
            responses = []
            while True:
                msg = ws.receive_json()
                responses.append(msg)
                # Terminal state is when we receive "idle" state after processing
                if msg["type"] == "state" and msg.get("state") == "idle":
                    break

            types = {r["type"] for r in responses}
            assert "transcript" in types
            assert "audio" in types
            stub_response = next(r for r in responses if r["type"] == "transcript")
            assert "stub" in stub_response["text"].lower() or "placeholder" in stub_response["text"].lower()


@respx.mock
@pytest.mark.asyncio
async def test_voice_ws_end_session(app: FastAPI) -> None:
    """Sending 'end' terminates the session with a summary."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/runtime/voice") as ws:
            ws.send_json({"type": "auth", "token": _DUMMY_TOKEN})
            ws.receive_json()

            ws.send_json({"type": "end", "store_memory": False})
            data = ws.receive_json()
            assert data["type"] == "end"
            assert data["summary"] is not None
            assert data["memory_stored"] is False


@respx.mock
@pytest.mark.asyncio
async def test_voice_ws_interrupt(app: FastAPI) -> None:
    """Interrupt message resets session to idle."""
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/runtime/voice") as ws:
            ws.send_json({"type": "auth", "token": _DUMMY_TOKEN})
            ws.receive_json()

            ws.send_json({"type": "interrupt"})
            data = ws.receive_json()
            assert data["type"] == "state"
            assert data["state"] == "idle"


# ---- Browser API tests ------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_browser_navigate_returns_stub_result(app: FastAPI) -> None:
    """POST /api/v1/runtime/browser/run with navigate task returns stub result."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/runtime/browser/run",
            json={
                "url": "https://example.com/invoice",
                "actions": [{"type": "navigate", "url": "https://example.com/invoice"}],
            },
            headers=_AUTH_HEADER,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["stub"] is True
    assert "session_id" in data
    assert data["pages_visited"] == ["https://example.com/invoice"]


@respx.mock
@pytest.mark.asyncio
async def test_browser_fill_form_returns_stub_result(app: FastAPI) -> None:
    """POST /api/v1/runtime/browser/run with fields returns form-fill stub result."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/runtime/browser/run",
            json={
                "url": "https://example.com/contact",
                "fields": {"name": "Jane", "email": "jane@example.com"},
                "submit": True,
            },
            headers=_AUTH_HEADER,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["stub"] is True
    assert data["pages_visited"] == ["https://example.com/contact"]


@respx.mock
@pytest.mark.asyncio
async def test_browser_sessions_list_endpoint(app: FastAPI) -> None:
    """GET /api/v1/runtime/browser/sessions returns active sessions."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First create a session
        create_resp = await client.post(
            "/api/v1/runtime/browser/run",
            json={"url": "https://example.com"},
            headers=_AUTH_HEADER,
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        # Then list sessions
        response = await client.get(
            "/api/v1/runtime/browser/sessions",
            headers=_AUTH_HEADER,
        )

    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    user_sessions = [s for s in data["sessions"] if s["session_id"] == session_id]
    assert len(user_sessions) == 1
    assert user_sessions[0]["last_url"] == "https://example.com"


@respx.mock
@pytest.mark.asyncio
async def test_browser_endpoint_requires_auth(app: FastAPI) -> None:
    """Browser endpoints return 401 without auth."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/runtime/browser/run",
            json={"url": "https://example.com"},
        )
    assert response.status_code == 401
