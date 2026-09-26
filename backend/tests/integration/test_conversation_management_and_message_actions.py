"""Integration tests for Conversation Management, Message Actions, and Hello Greeting Stream.

Verifies:
- Hello response instant streaming in Chat and Task modes
- Multilingual greetings (Salam, Assalam o alaikum)
- Session Pin, Archive, Rename, and Delete persistence
- Message deletion with authorization and ownership checks
- Secure session sharing snapshot token endpoint
"""

from __future__ import annotations

import os
import sys
import httpx
import pytest

sys.path.insert(0, "src")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("GROK_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


async def get_auth_headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    jwt_token = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()["access_token"]
    return {"Authorization": f"Bearer {jwt_token}"}


class TestHelloAndGreetingStreaming:
    """Verifies that greeting messages ('Hello', 'hi', 'salam') stream immediately without delay."""

    async def test_hello_stream_in_chat_mode(self, client: httpx.AsyncClient):
        """TEST 1: Sending 'Hello' returns immediate streaming response with done: True."""
        res = await client.post(
            "/api/v1/runtime/chat/stream",
            json={"message": "Hello", "provider": "runtime", "model": "coordinator"},
        )
        assert res.status_code == 200
        text = res.text
        assert "data:" in text
        assert "ROXY AI" in text or "assist" in text
        assert '"done": true' in text.lower()

    async def test_hello_stream_in_new_task_mode(self, client: httpx.AsyncClient):
        """TEST 2: Sending 'Hello' in Task mode (agent_override='coding') also returns immediate greeting."""
        res = await client.post(
            "/api/v1/runtime/chat/stream",
            json={
                "message": "Hello",
                "agent_override": "coding",
                "provider": "runtime",
                "model": "coordinator",
            },
        )
        assert res.status_code == 200
        text = res.text
        assert "data:" in text
        assert "ROXY AI" in text or "assist" in text
        assert '"done": true' in text.lower()

    async def test_salam_greeting_streaming(self, client: httpx.AsyncClient):
        """Greeting in Urdu/Arabic returns warm cultural response immediately."""
        res = await client.post(
            "/api/v1/runtime/chat/stream",
            json={"message": "assalam o alaikum"},
        )
        assert res.status_code == 200
        text = res.text
        assert "Assalam o alaikum" in text
        assert '"done": true' in text.lower()


class TestSessionConversationActions:
    """Verifies Rename, Pin, Archive, Share, and Delete operations on conversations."""

    async def test_session_lifecycle_pin_archive_rename_delete(
        self, client: httpx.AsyncClient
    ):
        user_headers = await get_auth_headers(client, "user_lifecycle@roxy.ai")

        # 1. Create a session
        create_res = await client.post(
            "/api/v1/sessions",
            headers=user_headers,
            json={"provider": "gemini", "model": "gemini-2.0-flash", "title": "Original Title"},
        )
        assert create_res.status_code == 201
        sess_data = create_res.json()
        session_id = sess_data["id"]

        # 2. Pin conversation -> check persistence
        pin_res = await client.patch(
            f"/api/v1/sessions/{session_id}",
            headers=user_headers,
            json={"pinned": True},
        )
        assert pin_res.status_code == 200
        assert pin_res.json()["pinned"] is True

        # Verify via GET
        get_res = await client.get(f"/api/v1/sessions/{session_id}", headers=user_headers)
        assert get_res.status_code == 200
        assert get_res.json()["pinned"] is True

        # 3. Rename conversation -> check persistence
        rename_res = await client.patch(
            f"/api/v1/sessions/{session_id}",
            headers=user_headers,
            json={"title": "Renamed Roxy Chat"},
        )
        assert rename_res.status_code == 200
        assert rename_res.json()["title"] == "Renamed Roxy Chat"

        # 4. Archive conversation -> check persistence
        archive_res = await client.patch(
            f"/api/v1/sessions/{session_id}",
            headers=user_headers,
            json={"archived": True},
        )
        assert archive_res.status_code == 200
        assert archive_res.json()["archived_at"] is not None

        # Verify active session list excludes archived session
        list_res = await client.get("/api/v1/sessions", headers=user_headers)
        assert list_res.status_code == 200
        active_ids = [s["id"] for s in list_res.json()]
        assert session_id not in active_ids

        # 5. Share conversation -> check secure token generated
        share_res = await client.post(
            f"/api/v1/sessions/{session_id}/share",
            headers=user_headers,
        )
        assert share_res.status_code == 200
        share_data = share_res.json()
        assert "token" in share_data
        assert "share_url" in share_data
        assert len(share_data["token"]) == 24

        # 6. Delete conversation -> check persistent deletion
        del_res = await client.delete(
            f"/api/v1/sessions/{session_id}",
            headers=user_headers,
        )
        assert del_res.status_code == 204

        # Verify session is truly deleted
        del_verify = await client.get(f"/api/v1/sessions/{session_id}", headers=user_headers)
        assert del_verify.status_code == 404


class TestMessageActionsAndSecurity:
    """Verifies message deletion and authorization enforcement."""

    async def test_message_deletion_and_isolation(
        self, client: httpx.AsyncClient
    ):
        user_a_headers = await get_auth_headers(client, "user_msg_a@roxy.ai")
        user_b_headers = await get_auth_headers(client, "user_msg_b@roxy.ai")

        # User A creates a session and sends a message
        create_res = await client.post(
            "/api/v1/sessions",
            headers=user_a_headers,
            json={"provider": "runtime", "model": "coordinator", "title": "Security Chat"},
        )
        session_id = create_res.json()["id"]

        # Send a greeting which persists interaction
        await client.post(
            "/api/v1/runtime/chat",
            headers=user_a_headers,
            json={"message": "Hello", "session_id": session_id},
        )

        # Get messages in session
        msgs_res = await client.get(
            f"/api/v1/sessions/{session_id}/messages",
            headers=user_a_headers,
        )
        assert msgs_res.status_code == 200
        messages = msgs_res.json()["messages"]
        assert len(messages) >= 1
        target_msg_id = messages[0]["id"]

        # User B tries to delete User A's message -> Must fail with 404 (ownership check)
        unauth_del = await client.delete(
            f"/api/v1/sessions/{session_id}/messages/{target_msg_id}",
            headers=user_b_headers,
        )
        assert unauth_del.status_code == 404

        # User A deletes their own message -> 200 or 204 Success
        auth_del = await client.delete(
            f"/api/v1/sessions/{session_id}/messages/{target_msg_id}",
            headers=user_a_headers,
        )
        assert auth_del.status_code in (200, 204)

        # Verify message is gone
        msgs_after = await client.get(
            f"/api/v1/sessions/{session_id}/messages",
            headers=user_a_headers,
        )
        after_ids = [m["id"] for m in msgs_after.json()["messages"]]
        assert target_msg_id not in after_ids
