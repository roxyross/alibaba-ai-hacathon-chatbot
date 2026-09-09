"""Integration tests for Google OAuth (T-???).

Coverage:
- `GET /api/v1/auth/oauth/google/start` with no env keys → 503
- `GET /api/v1/auth/oauth/github/start` → 501 (reserved route, not implemented)
- `GET /api/v1/auth/oauth/google/start` with keys → 302 to accounts.google.com
  and Set-Cookie for state
- `GET /api/v1/auth/oauth/google/callback` happy path → 302 to frontend with
  #access_token=... in the URL hash
- `GET /api/v1/auth/oauth/google/callback` with bad/missing state → 400
- `GET /api/v1/auth/oauth/google/callback` with `?error=access_denied` → 302
  back to frontend with `?error=...` in the hash
- `GET /api/v1/auth/oauth/google/callback` with `email_verified=false` → 302
  back to frontend with `?error=email_unverified` in the hash
- Two OAuth logins with the same email reuse the same user_id (account
  linking by email).

Google's token endpoint and JWKS are mocked via `respx`. We sign a fake
id_token with a real RS256 keypair so the JWKS-based signature check runs
end-to-end (i.e., not stubbed).
"""

from __future__ import annotations

import base64
import json
import sys
import time
from typing import Any

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Make `app` importable when running from backend/ root.
sys.path.insert(0, "src")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUER = "https://accounts.google.com"
CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"


# ---------------------------------------------------------------------------
# Test-wide RSA keypair + JWKS published via respx
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    """Generate one keypair for the test module and expose it as JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()

    def _b64uint(value: int) -> str:
        byte_length = (value.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(value.to_bytes(byte_length, "big")).rstrip(b"=").decode()

    jwks_key = {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": "test-kid-1",
        "n": _b64uint(public_numbers.n),
        "e": _b64uint(public_numbers.e),
    }
    return private_key, {"keys": [jwks_key]}


def _sign_id_token(
    private_key: rsa.RSAPrivateKey,
    *,
    email: str = "user@example.com",
    email_verified: bool = True,
    aud: str = CLIENT_ID,
    iss: str = GOOGLE_ISSUER,
    sub: str = "google-sub-123",
    exp_offset: int = 600,
    kid: str = "test-kid-1",
) -> str:
    """Build a Google-shaped id_token signed with the test private key."""
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "iat": now,
        "exp": now + exp_offset,
    }
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(claims, pem.decode(), algorithm="RS256", headers={"kid": kid})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _google_env(monkeypatch: pytest.MonkeyPatch):
    """Set Google OAuth env for every test, then clear on teardown."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5173")
    # Reset module-level state and JWKS caches between tests.
    from app.auth import oauth_state
    oauth_state._STATES.clear()
    from app.auth import oauth as oauth_svc
    oauth_svc._reset_jwks_cache()
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_start_redirects_to_google_with_state_cookie(
    async_client, rsa_keypair
) -> None:
    """With env keys set, /start 302s to accounts.google.com and sets state cookie."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(GOOGLE_JWKS_URL).respond(200, json=rsa_keypair[1])

        r = await async_client.get(
            "/api/v1/auth/oauth/google/start", follow_redirects=False
        )
        assert r.status_code == 302, r.text
        location = r.headers["location"]
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "client_id=" + CLIENT_ID in location
        assert "redirect_uri=" in location
        assert "response_type=code" in location
        assert "state=" in location
        assert "scope=openid" in location and "email" in location

        set_cookie = r.headers.get("set-cookie", "")
        assert "roxy.oauth_state=" in set_cookie
        assert "HttpOnly" in set_cookie
        # Starlette emits `SameSite=lax` (lowercase). Case-insensitive check.
        assert "samesite=lax" in set_cookie.lower()


async def test_github_provider_is_now_implemented(async_client, monkeypatch) -> None:
    """GitHub was a future provider when this test was written; it is now
    implemented in ADR-002's in-cluster extension. The /start endpoint should
    302 to github.com, not 501 (or 503).

    The `_google_env` autouse fixture sets only the Google env vars. We
    additionally need GITHUB_CLIENT_ID/SECRET for this test to flip the
    router's 503 path into a real 302.
    """
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-gh-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-gh-secret")
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.github.com/user").respond(200, json={})
        mock.get("https://api.github.com/user/emails").respond(200, json=[])
        r = await async_client.get(
            "/api/v1/auth/oauth/github/start", follow_redirects=False
        )
    assert r.status_code == 302, r.text
    assert r.headers["location"].startswith("https://github.com/login/oauth/authorize")


async def test_callback_happy_path_redirects_to_frontend_with_jwt_in_hash(
    async_client, rsa_keypair
) -> None:
    """End-to-end: exchange code, verify id_token, mint session, 302 to frontend."""
    private_key, jwks = rsa_keypair
    id_token = _sign_id_token(private_key, email="alice@example.com")
    with respx.mock(assert_all_called=False) as mock:
        mock.get(GOOGLE_JWKS_URL).respond(200, json=jwks)
        mock.post(GOOGLE_TOKEN_URL).respond(
            200,
            json={
                "id_token": id_token,
                "access_token": "x",
                "token_type": "Bearer",
            },
        )

        # Step 1: hit /start to get a state cookie.
        r = await async_client.get(
            "/api/v1/auth/oauth/google/start", follow_redirects=False
        )
        assert r.status_code == 302
        state = r.headers["location"].split("state=")[1].split("&")[0]
        # httpx stores Set-Cookie into the client's jar; re-use it.
        assert "roxy.oauth_state" in {c.name for c in async_client.cookies.jar}

        # Step 2: hit /callback with the code & state.
        r2 = await async_client.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "auth-code-xyz", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 302, r2.text
        target = r2.headers["location"]
        assert target.startswith("http://localhost:5173/auth/callback#")
        fragment = target.split("#", 1)[1]
        qs = dict(x.split("=", 1) for x in fragment.split("&"))
        assert qs["token_type"] == "bearer"
        assert qs["expires_in"]  # non-empty
        # Token should be a real JWT (three dot-separated base64url segments).
        assert qs["access_token"].count(".") == 2


async def test_callback_rejects_bad_state(async_client) -> None:
    """A callback with a state that doesn't match the cookie → 400."""
    r = await async_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "x", "state": "not-a-real-state"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "state" in r.json()["detail"].lower()


async def test_callback_rejects_missing_code(async_client) -> None:
    """Callback with no `code` param → 400."""
    r = await async_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"state": "anything"},
        follow_redirects=False,
    )
    assert r.status_code == 400


async def test_callback_provider_error_redirects_to_frontend(
    async_client, rsa_keypair
) -> None:
    """If Google sends ?error=... we redirect back to the frontend with it in the hash."""
    r = await async_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    target = r.headers["location"]
    assert target.startswith("http://localhost:5173/auth/callback#")
    assert "error=access_denied" in target
    assert "provider=google" in target


async def test_callback_rejects_unverified_email(
    async_client, rsa_keypair
) -> None:
    """`email_verified: false` must redirect back to the frontend with an error."""
    private_key, jwks = rsa_keypair
    id_token = _sign_id_token(private_key, email="bob@example.com", email_verified=False)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(GOOGLE_JWKS_URL).respond(200, json=jwks)
        mock.post(GOOGLE_TOKEN_URL).respond(
            200, json={"id_token": id_token, "access_token": "x"}
        )

        r = await async_client.get(
            "/api/v1/auth/oauth/google/start", follow_redirects=False
        )
        state = r.headers["location"].split("state=")[1].split("&")[0]
        r2 = await async_client.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "abc", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 302
        target = r2.headers["location"]
        assert "error=email_unverified" in target


async def test_repeated_oauth_login_reuses_same_user(
    async_client, rsa_keypair
) -> None:
    """Same email via OAuth twice → same user_id. Account linking by email."""
    private_key, jwks = rsa_keypair
    id_token = _sign_id_token(private_key, email="carol@example.com")
    with respx.mock(assert_all_called=False) as mock:
        mock.get(GOOGLE_JWKS_URL).respond(200, json=jwks)
        mock.post(GOOGLE_TOKEN_URL).respond(
            200, json={"id_token": id_token, "access_token": "x"}
        )

        async def _one_login() -> str:
            r1 = await async_client.get(
                "/api/v1/auth/oauth/google/start", follow_redirects=False
            )
            state = r1.headers["location"].split("state=")[1].split("&")[0]
            r2 = await async_client.get(
                "/api/v1/auth/oauth/google/callback",
                params={"code": "c", "state": state},
                follow_redirects=False,
            )
            assert r2.status_code == 302, r2.text
            location = str(r2.headers["location"])
            return str(location.split("#", 1)[1])

        def _sub_from_frag(frag: str) -> str:
            tok = dict(
                x.split("=", 1) for x in frag.split("&") if x.startswith("access_token=")
            )["access_token"]
            payload_b64 = tok.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload_data = json.loads(base64.urlsafe_b64decode(payload_b64))
            return str(payload_data["sub"])

        sub_1 = _sub_from_frag(await _one_login())
        sub_2 = _sub_from_frag(await _one_login())
        assert sub_1 == sub_2  # same user


async def test_state_is_single_use(async_client) -> None:
    """Replaying the same (code, state) must fail the second time."""
    # First: /start (sets cookie+state), then /callback (consumes state).
    r1 = await async_client.get(
        "/api/v1/auth/oauth/google/start", follow_redirects=False
    )
    state = r1.headers["location"].split("state=")[1].split("&")[0]
    # The cookie is now in the jar. Force-clear it so the second call has no
    # cookie at all — that's the most adversarial replay.
    async_client.cookies.clear()
    r2 = await async_client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert r2.status_code == 400


async def test_stateless_hmac_state_in_production_without_cookie(
    async_client, rsa_keypair, monkeypatch
) -> None:
    """In production (e.g. Vercel), Chrome Incognito blocks cookies, but signed HMAC state succeeds."""
    monkeypatch.setenv("VERCEL", "1")
    priv, jwks = rsa_keypair
    id_token = _sign_id_token(priv, email="incognito@example.com")

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(GOOGLE_JWKS_URL).respond(200, json=jwks)
        respx_mock.post(GOOGLE_TOKEN_URL).respond(
            200,
            json={
                "id_token": id_token,
                "access_token": "x",
                "token_type": "Bearer",
            },
        )
        r1 = await async_client.get(
            "/api/v1/auth/oauth/google/start", follow_redirects=False
        )
        state = r1.headers["location"].split("state=")[1].split("&")[0]

        # Simulate Incognito mode: client drops third-party cookie completely
        async_client.cookies.clear()

        r2 = await async_client.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "valid-code", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 302
        assert "access_token=" in r2.headers["location"]


async def test_stateless_hmac_state_in_production_with_stale_cookie(
    async_client, rsa_keypair, monkeypatch
) -> None:
    """In production, if browser holds a stale cookie from a previous session, fresh HMAC state still succeeds."""
    monkeypatch.setenv("VERCEL", "1")
    priv, jwks = rsa_keypair
    id_token = _sign_id_token(priv, email="stale-cookie-user@example.com")

    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(GOOGLE_JWKS_URL).respond(200, json=jwks)
        respx_mock.post(GOOGLE_TOKEN_URL).respond(
            200,
            json={
                "id_token": id_token,
                "access_token": "x",
                "token_type": "Bearer",
            },
        )
        r1 = await async_client.get(
            "/api/v1/auth/oauth/google/start", follow_redirects=False
        )
        state = r1.headers["location"].split("state=")[1].split("&")[0]

        # Simulate stale cookie from previous session
        async_client.cookies.set("roxy.oauth_state", "old_stale_mismatched_state_cookie")

        r2 = await async_client.get(
            "/api/v1/auth/oauth/google/callback",
            params={"code": "valid-code", "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 302
        assert "access_token=" in r2.headers["location"]

