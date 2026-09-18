"""Phase 2 Master Integration Test Suite: Database Schema Enhancements and Settings API.

Covers:
1. Chat session pinning (pinned=True sorts before unpinned sessions).
2. Chat session archiving (archived sessions hidden by default, visible with include_archived=True).
3. Chat session unarchiving.
4. User settings API (GET /api/v1/settings returns defaults for new users).
5. User settings persistence (PATCH /api/v1/settings saves theme, persona, speed, sound, scroll).
6. Multi-tenant settings isolation (User A settings changes never affect User B).
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator

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


async def _get_auth_headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    jwt = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()["access_token"]
    return {"Authorization": f"Bearer {jwt}"}


async def test_session_pinning_and_archiving(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "session_features_user@roxy.ai")

    # 1. Create two sessions
    sess1_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "gemini", "model": "gemini-2.5-flash", "title": "First Session"},
    )
    assert sess1_resp.status_code == 201
    sess1 = sess1_resp.json()
    assert sess1["pinned"] is False
    assert sess1["archived_at"] is None

    sess2_resp = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"provider": "gemini", "model": "gemini-2.5-flash", "title": "Second Session"},
    )
    assert sess2_resp.status_code == 201
    sess2 = sess2_resp.json()

    # 2. Pin the first session
    pin_resp = await client.patch(
        f"/api/v1/sessions/{sess1['id']}",
        headers=headers,
        json={"pinned": True},
    )
    assert pin_resp.status_code == 200
    assert pin_resp.json()["pinned"] is True

    # 3. List sessions: pinned session should appear first
    list_resp = await client.get("/api/v1/sessions", headers=headers)
    assert list_resp.status_code == 200
    sessions = list_resp.json()
    assert len(sessions) >= 2
    assert sessions[0]["id"] == sess1["id"]
    assert sessions[0]["pinned"] is True

    # 4. Archive second session
    archive_resp = await client.patch(
        f"/api/v1/sessions/{sess2['id']}",
        headers=headers,
        json={"archived": True},
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["archived_at"] is not None

    # 5. List sessions without include_archived: sess2 must be excluded
    active_sessions = (await client.get("/api/v1/sessions", headers=headers)).json()
    assert any(s["id"] == sess1["id"] for s in active_sessions)
    assert all(s["id"] != sess2["id"] for s in active_sessions)

    # 6. List sessions with include_archived=true: sess2 must be included
    all_sessions = (await client.get("/api/v1/sessions?include_archived=true", headers=headers)).json()
    assert any(s["id"] == sess2["id"] for s in all_sessions)

    # 7. Unarchive second session
    unarchive_resp = await client.patch(
        f"/api/v1/sessions/{sess2['id']}",
        headers=headers,
        json={"archived": False},
    )
    assert unarchive_resp.status_code == 200
    assert unarchive_resp.json()["archived_at"] is None

    # Cleanup
    await client.delete(f"/api/v1/sessions/{sess1['id']}", headers=headers)
    await client.delete(f"/api/v1/sessions/{sess2['id']}", headers=headers)


async def test_user_settings_lifecycle_and_isolation(client: httpx.AsyncClient) -> None:
    headers_a = await _get_auth_headers(client, "settings_user_a@roxy.ai")
    headers_b = await _get_auth_headers(client, "settings_user_b@roxy.ai")

    # 1. Unauthenticated request rejected with 401
    unauth_resp = await client.get("/api/v1/settings")
    assert unauth_resp.status_code == 401

    # 2. User A gets initial settings (defaults)
    get_a_resp = await client.get("/api/v1/settings", headers=headers_a)
    assert get_a_resp.status_code == 200
    settings_a = get_a_resp.json()
    assert settings_a["theme"] == "dark"
    assert settings_a["custom_persona"] == ""
    assert settings_a["stream_speed"] == "fast"
    assert settings_a["sound_effects"] is True
    assert settings_a["auto_scroll"] is True

    # 3. User A updates settings
    update_payload = {
        "theme": "light",
        "custom_persona": "You are a senior staff engineer with deep systems knowledge.",
        "stream_speed": "smooth",
        "sound_effects": False,
        "auto_scroll": False,
    }
    patch_a_resp = await client.patch("/api/v1/settings", headers=headers_a, json=update_payload)
    assert patch_a_resp.status_code == 200
    updated_a = patch_a_resp.json()
    assert updated_a["theme"] == "light"
    assert updated_a["custom_persona"] == "You are a senior staff engineer with deep systems knowledge."
    assert updated_a["stream_speed"] == "smooth"
    assert updated_a["sound_effects"] is False
    assert updated_a["auto_scroll"] is False

    # 4. Subsequent GET confirms persistence
    verify_a_resp = await client.get("/api/v1/settings", headers=headers_a)
    assert verify_a_resp.status_code == 200
    assert verify_a_resp.json()["theme"] == "light"
    assert verify_a_resp.json()["stream_speed"] == "smooth"

    # 5. User B settings remain untouched (tenant isolation)
    get_b_resp = await client.get("/api/v1/settings", headers=headers_b)
    assert get_b_resp.status_code == 200
    settings_b = get_b_resp.json()
    assert settings_b["theme"] == "dark"  # default, untouched by User A
    assert settings_b["custom_persona"] == ""
    assert settings_b["stream_speed"] == "fast"
    assert settings_b["sound_effects"] is True
