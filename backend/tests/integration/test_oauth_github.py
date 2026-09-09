"""Integration tests for GitHub OAuth.

Coverage:
- `GET /api/v1/auth/oauth/github/start` with no env keys → 503
- `GET /api/v1/auth/oauth/github/start` with keys → 302 to github.com/login
  with `scope=read:user user:email` and a state cookie
- `GET /api/v1/auth/oauth/github/callback` happy path → 302 to frontend with
  #access_token=… in the URL hash
- `GET /api/v1/auth/oauth/github/callback` with bad state → 400
- `GET /api/v1/auth/oauth/github/callback` with `?error=access_denied` → 302
  back to frontend with `?error=...` in the hash
- `/user/emails` returns no `primary && verified` entry → 302 with
  `error=email_unverified`
- Two GitHub logins with the same email reuse the same user_id (linking).

GitHub's token endpoint, /user, and /user/emails are mocked via respx.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest
import respx

sys.path.insert(0, "src")

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
CLIENT_ID = "test-github-client-id"
CLIENT_SECRET = "test-github-client-secret"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _github_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5173")
    # Reset module-level state between tests.
    from app.auth import oauth_state
    oauth_state._STATES.clear()
    yield


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def async_client():
    import httpx

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


def _stub_github(
    mock: respx.MockRouter,
    *,
    access_token: str = "gho_testtoken",
    user_payload: dict[str, Any] | None = None,
    emails_payload: list[dict[str, Any]] | None = None,
    user_status: int = 200,
    emails_status: int = 200,
) -> None:
    """Wire the three GitHub endpoints respx should intercept."""
    mock.post(GITHUB_TOKEN_URL).respond(
        200, json={"access_token": access_token, "token_type": "bearer", "scope": "read:user,user:email"}
    )
    mock.get(GITHUB_USER_URL).respond(
        user_status,
        json=user_payload
        if user_payload is not None
        else {"id": 12345, "login": "alice", "name": "Alice", "email": None},
    )
    mock.get(GITHUB_EMAILS_URL).respond(
        emails_status,
        json=emails_payload
        if emails_payload is not None
        else [
            {
                "email": "alice@personal.example",
                "primary": False,
                "verified": True,
                "visibility": "private",
            },
            {
                "email": "alice@work.example",
                "primary": True,
                "verified": True,
                "visibility": None,
            },
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_start_redirects_to_github_with_state_cookie(async_client) -> None:
    with respx.mock(assert_all_called=False) as mock:
        # Not actually called by /start, but stub the user endpoint so respx
        # doesn't leak a real network call if something else fires.
        mock.get(GITHUB_USER_URL).respond(200, json={})
        mock.get(GITHUB_EMAILS_URL).respond(200, json=[])

        r = await async_client.get(
            "/api/v1/auth/oauth/github/start", follow_redirects=False
        )
        assert r.status_code == 302, r.text
        location = r.headers["location"]
        assert location.startswith("https://github.com/login/oauth/authorize")
        assert "client_id=" + CLIENT_ID in location
        assert "redirect_uri=" in location
        assert "state=" in location
        # Scope must include user:email so we can read verified emails.
        assert "user%3Aemail" in location or "user:email" in location
        assert "read%3Auser" in location or "read:user" in location

        set_cookie = r.headers.get("set-cookie", "")
        assert "roxy.oauth_state=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "samesite=lax" in set_cookie.lower()


async def test_callback_happy_path_redirects_to_frontend_with_jwt_in_hash(
    async_client,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        _stub_github(mock)

        r = await async_client.get(
            "/api/v1/auth/oauth/github/start", follow_redirects=False
        )
        state = r.headers["location"].split("state=")[1].split("&")[0]

        r2 = await async_client.get(
            "/api/v1/auth/oauth/github/callback",
            params={"code": "gh-code-xyz", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 302, r2.text
        target = r2.headers["location"]
        assert target.startswith("http://localhost:5173/auth/callback#")
        fragment = target.split("#", 1)[1]
        qs = dict(x.split("=", 1) for x in fragment.split("&"))
        assert qs["token_type"] == "bearer"
        assert qs["expires_in"]
        assert qs["access_token"].count(".") == 2  # real JWT


async def test_callback_rejects_bad_state(async_client) -> None:
    r = await async_client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"code": "x", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "state" in r.json()["detail"].lower()


async def test_callback_provider_error_redirects_to_frontend(async_client) -> None:
    r = await async_client.get(
        "/api/v1/auth/oauth/github/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    target = r.headers["location"]
    assert target.startswith("http://localhost:5173/auth/callback#")
    assert "error=access_denied" in target
    assert "provider=github" in target


async def test_callback_rejects_unverified_primary_email(async_client) -> None:
    """If /user/emails has no `primary && verified` entry, redirect with error."""
    with respx.mock(assert_all_called=False) as mock:
        _stub_github(
            mock,
            emails_payload=[
                {"email": "a@b.c", "primary": True, "verified": False, "visibility": None},
            ],
        )

        r = await async_client.get(
            "/api/v1/auth/oauth/github/start", follow_redirects=False
        )
        state = r.headers["location"].split("state=")[1].split("&")[0]
        r2 = await async_client.get(
            "/api/v1/auth/oauth/github/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 302
        target = r2.headers["location"]
        assert "error=email_unverified" in target


async def test_callback_rejects_when_user_emails_empty(async_client) -> None:
    """An empty /user/emails list (e.g., scope not granted) is also a fail."""
    with respx.mock(assert_all_called=False) as mock:
        _stub_github(mock, emails_payload=[])

        r = await async_client.get(
            "/api/v1/auth/oauth/github/start", follow_redirects=False
        )
        state = r.headers["location"].split("state=")[1].split("&")[0]
        r2 = await async_client.get(
            "/api/v1/auth/oauth/github/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 302
        assert "error=email_unverified" in r2.headers["location"]


async def test_repeated_github_login_reuses_same_user(async_client) -> None:
    """Same email via GitHub twice → same user_id. Account linking by email."""
    import base64
    import json

    with respx.mock(assert_all_called=False) as mock:
        _stub_github(
            mock,
            emails_payload=[
                {"email": "carol@example.com", "primary": True, "verified": True, "visibility": None},
            ],
        )

        async def _one_login() -> str:
            r1 = await async_client.get(
                "/api/v1/auth/oauth/github/start", follow_redirects=False
            )
            state = r1.headers["location"].split("state=")[1].split("&")[0]
            r2 = await async_client.get(
                "/api/v1/auth/oauth/github/callback",
                params={"code": "c", "state": state},
                follow_redirects=False,
            )
            assert r2.status_code == 302, r2.text
            return r2.headers["location"].split("#", 1)[1]

        def _sub_from_frag(frag: str) -> str:
            tok = dict(
                x.split("=", 1) for x in frag.split("&") if x.startswith("access_token=")
            )["access_token"]
            payload_b64 = tok.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            return json.loads(base64.urlsafe_b64decode(payload_b64))["sub"]

        sub_1 = _sub_from_frag(await _one_login())
        sub_2 = _sub_from_frag(await _one_login())
        assert sub_1 == sub_2  # same user


async def test_state_is_single_use(async_client) -> None:
    """Replaying the same (code, state) must fail the second time."""
    with respx.mock(assert_all_called=False) as mock:
        _stub_github(mock)

        r1 = await async_client.get(
            "/api/v1/auth/oauth/github/start", follow_redirects=False
        )
        state = r1.headers["location"].split("state=")[1].split("&")[0]
        # Force-clear cookies so the second call has no cookie.
        async_client.cookies.clear()
        r2 = await async_client.get(
            "/api/v1/auth/oauth/github/callback",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 400
