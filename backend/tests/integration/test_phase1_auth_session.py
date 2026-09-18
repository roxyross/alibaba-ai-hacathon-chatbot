"""Phase 1 Master Integration Test Suite: Authentication, Session Management, and Data Isolation.

Covers:
1. Magic-link request & verify flow issuing valid JWT.
2. JWT decoding and payload verification (sub, email, exp).
3. Authenticated endpoint protection (/auth/me returns 401 when missing/invalid).
4. Protected session creation (/sessions returns 401 when unauthenticated).
5. User-isolated session persistence (User A cannot access or tamper with User B's sessions).
6. Session rename, retrieval, and deletion lifecycle.
7. Replay protection on magic-link token consumption.
"""

from __future__ import annotations

import base64
import json
import sys
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

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


def _decode_jwt(token: str) -> dict[str, Any]:
    parts = token.split(".")
    assert len(parts) == 3, "JWT must contain 3 segments"
    payload_b64 = parts[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload_b64))
    return cast(dict[str, Any], data)


async def test_magic_link_auth_and_session_lifecycle(client: httpx.AsyncClient) -> None:
    """Test full Phase 1 auth flow: request-link -> verify -> me -> create session -> list -> delete."""
    test_email = "phase1_tester@roxy.ai"

    # 1. Request magic link
    req_resp = await client.post(
        "/api/v1/auth/request-link",
        json={"email": test_email},
    )
    assert req_resp.status_code == 200
    data = req_resp.json()
    assert data["ok"] is True
    dev_token = data.get("dev_token")
    assert dev_token is not None and len(dev_token) > 10

    # 2. Verify token & obtain JWT
    verify_resp = await client.post(
        "/api/v1/auth/verify",
        json={"token": dev_token},
    )
    assert verify_resp.status_code == 200
    auth_data = verify_resp.json()
    access_token = auth_data["access_token"]
    user = auth_data["user"]
    assert user["email"] == test_email
    assert user["id"] is not None

    # 3. Verify JWT payload contains both sub and email
    claims = _decode_jwt(access_token)
    assert claims["sub"] == user["id"]
    assert claims["email"] == test_email
    assert claims["exp"] > claims["iat"]

    # 4. Access /auth/me with Bearer token
    headers = {"Authorization": f"Bearer {access_token}"}
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["id"] == user["id"]
    assert me_data["email"] == test_email

    # 5. Magic link token is single-use: replay must fail with 400
    replay_resp = await client.post(
        "/api/v1/auth/verify",
        json={"token": dev_token},
    )
    assert replay_resp.status_code == 400

    # 6. Unauthenticated requests to /auth/me or /sessions are rejected (401)
    unauth_me = await client.get("/api/v1/auth/me")
    assert unauth_me.status_code == 401

    bad_token_me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert bad_token_me.status_code == 401

    unauth_session_create = await client.post(
        "/api/v1/sessions",
        json={"provider": "gemini", "model": "gemini-2.5-flash", "title": "Test Session"},
    )
    assert unauth_session_create.status_code == 401

    # 7. Create chat session as authenticated user
    create_sess_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "title": "Phase 1 Test Session",
            "session_type": "chat",
        },
    )
    assert create_sess_resp.status_code == 201
    sess_data = create_sess_resp.json()
    session_id = sess_data["id"]
    assert sess_data["title"] == "Phase 1 Test Session"
    assert sess_data["provider"] == "gemini"

    # 8. List sessions returns newly created session
    list_resp = await client.get("/api/v1/sessions", headers=headers)
    assert list_resp.status_code == 200
    user_sessions = list_resp.json()
    assert any(s["id"] == session_id for s in user_sessions)

    # 9. Get specific session
    get_resp = await client.get(f"/api/v1/sessions/{session_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id

    # 10. Rename session
    patch_resp = await client.patch(
        f"/api/v1/sessions/{session_id}",
        headers=headers,
        json={"title": "Updated Session Title"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Updated Session Title"

    # 11. Delete session
    del_resp = await client.delete(f"/api/v1/sessions/{session_id}", headers=headers)
    assert del_resp.status_code == 204

    # 12. Confirm session no longer exists
    get_deleted = await client.get(f"/api/v1/sessions/{session_id}", headers=headers)
    assert get_deleted.status_code == 404


async def test_user_data_isolation(client: httpx.AsyncClient) -> None:
    """Verify strict tenant data isolation between two distinct users."""
    user_a_email = "tenant_a@roxy.ai"
    user_b_email = "tenant_b@roxy.ai"

    # Auth User A
    tok_a = (await client.post("/api/v1/auth/request-link", json={"email": user_a_email})).json()["dev_token"]
    jwt_a = (await client.post("/api/v1/auth/verify", json={"token": tok_a})).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {jwt_a}"}

    # Auth User B
    tok_b = (await client.post("/api/v1/auth/request-link", json={"email": user_b_email})).json()["dev_token"]
    jwt_b = (await client.post("/api/v1/auth/verify", json={"token": tok_b})).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {jwt_b}"}

    # User A creates a confidential session
    sess_a_resp = await client.post(
        "/api/v1/sessions",
        headers=headers_a,
        json={"provider": "openai", "model": "gpt-4o", "title": "User A Secret Session"},
    )
    assert sess_a_resp.status_code == 201
    sess_a_id = sess_a_resp.json()["id"]

    # User B lists sessions -> MUST NOT see User A's session
    sess_b_list = (await client.get("/api/v1/sessions", headers=headers_b)).json()
    assert all(s["id"] != sess_a_id for s in sess_b_list)

    # User B attempts to read User A's session -> MUST return 404 (or 403)
    read_attempt = await client.get(f"/api/v1/sessions/{sess_a_id}", headers=headers_b)
    assert read_attempt.status_code == 404

    # User B attempts to rename User A's session -> MUST return 404
    rename_attempt = await client.patch(
        f"/api/v1/sessions/{sess_a_id}",
        headers=headers_b,
        json={"title": "Hacked Title"},
    )
    assert rename_attempt.status_code == 404

    # User B attempts to delete User A's session -> MUST return 404
    delete_attempt = await client.delete(f"/api/v1/sessions/{sess_a_id}", headers=headers_b)
    assert delete_attempt.status_code == 404

    # User A can still access their session safely
    verify_a_access = await client.get(f"/api/v1/sessions/{sess_a_id}", headers=headers_a)
    assert verify_a_access.status_code == 200
    assert verify_a_access.json()["title"] == "User A Secret Session"

    # Clean up User A's session
    await client.delete(f"/api/v1/sessions/{sess_a_id}", headers=headers_a)
