"""Google OAuth service: build authorize URL, exchange code, verify id_token.

The Authorization Code flow goes:

  1. Frontend hits GET /auth/oauth/google/start → backend sets state cookie
     and 302s to Google's consent screen.
  2. User approves. Google redirects to
     GET /auth/oauth/google/callback?code=...&state=...
  3. Backend exchanges the code for tokens, verifies the id_token's
     signature against Google's JWKS, checks `email_verified`, and
     upserts the user by email.
  4. Backend mints a session JWT (same shape as magic-link flow) and
     302s to ${APP_BASE_URL}/auth/callback#access_token=...&expires_in=...
     so the frontend can pick it up from the URL hash.

Security notes:
  - We never persist Google's access_token, refresh_token, or id_token.
  - We never log `email`, `sub`, or any token value.
  - JWKS responses are cached in-process with a 5-minute TTL; a `kid`
    miss forces a refetch.
  - The redirect URI is constructed from env, never from request input.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
import structlog
from sqlalchemy import select

from app.auth.jwt import create_session_token
from app.auth.models import User
from app.db import get_session_factory

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS: tuple[str, ...] = ("https://accounts.google.com", "accounts.google.com")
JWKS_TTL_SECONDS = 5 * 60


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str  # absolute, https in prod
    scopes: tuple[str, ...] = ("openid", "email", "profile")

    @classmethod
    def from_env(cls) -> "GoogleConfig | None":
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        app_base = os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/")
        # OAUTH_REDIRECT_BASE_URL overrides the *backend* host (the API). The
        # Google redirect URI is to /api/v1/auth/oauth/google/callback on the
        # backend — never to the frontend.
        backend_base = os.environ.get(
            "OAUTH_REDIRECT_BASE_URL", "http://localhost:8000"
        ).rstrip("/")
        redirect_uri = f"{backend_base}/api/v1/auth/oauth/google/callback"
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OAuthError(Exception):
    """Base error for OAuth flows. `reason` is a short machine-friendly tag."""

    def __init__(self, reason: str, message: str = "") -> None:
        self.reason = reason
        super().__init__(message or reason)


# ---------------------------------------------------------------------------
# JWKS cache (kid-aware)
# ---------------------------------------------------------------------------

# Module-level cache. We fetch the JWKS document (a JSON of {keys: [...]}) via
# httpx (so tests can mock it with respx) and look up the signing key by `kid`
# ourselves. The `pyjwt` PyJWKClient uses urllib under the hood, which is
# harder to mock.
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_fetched_at: float = 0.0


async def _fetch_jwks(force: bool = False) -> dict[str, Any]:
    """Return the cached JWKS document, fetching on miss or after TTL."""
    global _jwks_cache, _jwks_cache_fetched_at
    now = time.time()
    if (
        not force
        and _jwks_cache is not None
        and (now - _jwks_cache_fetched_at) < JWKS_TTL_SECONDS
    ):
        return _jwks_cache
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GOOGLE_JWKS_URL)
    if resp.status_code != 200:
        raise OAuthError("jwks_unavailable", f"JWKS fetch returned {resp.status_code}")
    _jwks_cache = resp.json()
    _jwks_cache_fetched_at = now
    return _jwks_cache


def _reset_jwks_cache() -> None:
    """Force the next verify to refetch JWKS — used when a `kid` is unknown."""
    global _jwks_cache, _jwks_cache_fetched_at
    _jwks_cache = None
    _jwks_cache_fetched_at = 0.0


def _key_for_kid(jwks: dict[str, Any], kid: str | None) -> Any:
    """Pick the JWK whose `kid` matches, or the only key if there's just one."""
    keys = jwks.get("keys", [])
    if not keys:
        raise OAuthError("jwks_unavailable", "JWKS contains no keys")
    if kid is None:
        if len(keys) == 1:
            return keys[0]
        raise OAuthError("jwks_unavailable", "No `kid` in id_token and JWKS has multiple keys")
    for k in keys:
        if k.get("kid") == kid:
            return k
    raise OAuthError("kid_not_found", f"No JWKS key matches kid={kid}")


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------


def build_authorize_url(state: str, config: GoogleConfig) -> str:
    """Compose the Google consent-screen URL with our state and PKCE-less flow."""
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
        "access_type": "online",  # we don't need a refresh token
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Code → token exchange
# ---------------------------------------------------------------------------


async def exchange_code(code: str, config: GoogleConfig) -> dict[str, Any]:
    """POST the code to Google and return the parsed token response."""
    data = {
        "code": code,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=data)
    if resp.status_code != 200:
        log.warning(
            "auth.oauth.exchange_failed",
            status=resp.status_code,
            body=resp.text[:200],
        )
        raise OAuthError("exchange_failed", "Token endpoint returned non-200")
    payload = resp.json()
    if "id_token" not in payload:
        raise OAuthError("no_id_token", "Token response missing id_token")
    return payload


# ---------------------------------------------------------------------------
# ID-token verification
# ---------------------------------------------------------------------------


async def _verify_with_jwks(id_token: str, config: GoogleConfig) -> dict[str, Any]:
    """Verify the id_token signature & standard claims. Returns the claims dict."""
    # Pull the unverified header so we know which `kid` to look for. This does
    # NOT trust any claim — it just reads the header.
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise OAuthError("id_token_malformed", str(exc)) from exc
    kid = header.get("kid")

    jwks = await _fetch_jwks()
    try:
        jwk_dict = _key_for_kid(jwks, kid)
    except OAuthError:
        # `kid` not in cache — refetch and try once before giving up.
        _reset_jwks_cache()
        jwks = await _fetch_jwks(force=True)
        jwk_dict = _key_for_kid(jwks, kid)

    import json as _json
    from jwt.algorithms import RSAAlgorithm

    try:
        public_key = RSAAlgorithm.from_jwk(_json.dumps(jwk_dict))
    except Exception as exc:  # noqa: BLE001 — pyjwt raises various low-level errors
        raise OAuthError("jwks_unavailable", f"Could not parse JWK: {exc}") from exc

    try:
        claims = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=config.client_id,
            issuer=list(GOOGLE_ISSUERS),
            leeway=60,  # tolerate small clock skew
            options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]},
        )
    except jwt.PyJWTError as exc:
        raise OAuthError("id_token_invalid", str(exc)) from exc

    if not claims.get("email_verified"):
        raise OAuthError("email_unverified", "Google account email is not verified")

    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise OAuthError("id_token_no_email", "id_token missing usable email claim")

    return claims


# ---------------------------------------------------------------------------
# User upsert (parity with magic-link: same email → same user)
# ---------------------------------------------------------------------------

# Module-level in-memory fallback mirrors auth/service.py.
_MEM_USERS: dict[str, User] = {}


def _memory_upsert(email: str) -> User:
    user = _MEM_USERS.get(email)
    if user is None:
        import secrets as _s
        from datetime import datetime, timezone
        user = User(
            id=_s.token_urlsafe(16),
            email=email,
            created_at=datetime.now(timezone.utc),
        )
        _MEM_USERS[email] = user
    return user


async def _db_upsert(email: str) -> User:
    factory = get_session_factory()
    assert factory is not None
    async with factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            from datetime import datetime, timezone
            existing.last_login_at = datetime.now(timezone.utc)
            await session.commit()
            return existing
        user = User(email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def upsert_user_by_email(email: str) -> User:
    """Find the user with this email or create one. Used by both auth flows."""
    factory = get_session_factory()
    if factory is None:
        return _memory_upsert(email)
    return await _db_upsert(email)


# ---------------------------------------------------------------------------
# Public entry points used by the router
# ---------------------------------------------------------------------------


async def complete_google_callback(
    code: str, config: GoogleConfig
) -> tuple[User, str, int]:
    """End-to-end: exchange code, verify id_token, upsert user, mint JWT.

    Returns (user, jwt, ttl_seconds).
    """
    token_payload = await exchange_code(code, config)
    claims = await _verify_with_jwks(token_payload["id_token"], config)
    email = str(claims["email"]).lower().strip()

    # Optional allowlist for hackathon demo (comma-separated env var).
    allowed = os.environ.get("GOOGLE_ALLOWED_EMAILS", "").strip()
    if allowed:
        allow = {e.strip().lower() for e in allowed.split(",") if e.strip()}
        if email not in allow:
            log.warning("auth.oauth.email_not_allowed", email=email)
            raise OAuthError("email_not_allowed", "Email not in allowlist")

    user = await upsert_user_by_email(email)
    log.info("auth.oauth.signed_in", user_id=user.id)
    jwt_token, ttl = create_session_token(user.id)
    return user, jwt_token, ttl


# ===========================================================================
# GitHub OAuth
# ===========================================================================
#
# GitHub's flow differs from Google's in three concrete ways:
#   1. No `id_token` / no JWKS. The code-exchange returns an opaque
#      `access_token`; we call /user and /user/emails with it to learn the
#      user's identity and a verified primary email.
#   2. Email is in a separate endpoint. /user.email can be null; /user/emails
#      is the source of truth for verified addresses.
#   3. We enforce `primary && verified` ourselves — there is no `email_verified`
#      claim to check.
#
# Everything else (state cookie, URL-hash handoff, JWT, user upsert) is shared
# with Google via the helpers above.
# ---------------------------------------------------------------------------

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_ACCEPT = "application/vnd.github+json"
GITHUB_API_VERSION = "2022-11-28"


@dataclass(frozen=True)
class GitHubConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "GitHubConfig | None":
        client_id = os.environ.get("GITHUB_CLIENT_ID")
        client_secret = os.environ.get("GITHUB_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        backend_base = os.environ.get(
            "OAUTH_REDIRECT_BASE_URL", "http://localhost:8000"
        ).rstrip("/")
        redirect_uri = f"{backend_base}/api/v1/auth/oauth/github/callback"
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )


def _github_authorize_url(state: str, config: GitHubConfig) -> str:
    """Compose the GitHub consent-screen URL. We request `read:user` and
    `user:email` so we can read the verified primary email from /user/emails.
    """
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "scope": "read:user user:email",
        "state": state,
        "allow_signup": "true",
    }
    return f"{GITHUB_AUTH_URL}?{urlencode(params)}"


def _github_api_headers(access_token: str) -> dict[str, str]:
    """Common headers for GitHub REST API calls. The version header is required
    by GitHub for production apps; pinning protects us from silent breaking
    changes.
    """
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": GITHUB_API_ACCEPT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "roxy-jarvis",
    }


async def _github_exchange_code(code: str, config: GitHubConfig) -> str:
    """POST the code to GitHub. Returns the access_token.

    GitHub's token endpoint returns JSON only if we send `Accept: application/json`;
    otherwise it returns form-urlencoded. We always ask for JSON.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code": code,
                "redirect_uri": config.redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        log.warning(
            "auth.oauth.github.exchange_failed",
            status=resp.status_code,
            body=resp.text[:200],
        )
        raise OAuthError("exchange_failed", "GitHub token endpoint returned non-200")
    payload = resp.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        # GitHub returns {"error":"bad_verification_code", ...} on bad code
        # with status 200. Detect by absence of access_token.
        err = payload.get("error", "unknown")
        log.warning("auth.oauth.github.no_access_token", error=err)
        raise OAuthError("exchange_failed", f"GitHub returned no access_token ({err})")
    return access_token


async def _github_fetch_verified_primary_email(
    access_token: str,
) -> str:
    """Hit /user/emails and return the entry where primary && verified. Raise
    OAuthError("email_unverified") if no such entry exists.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/user/emails",
            headers=_github_api_headers(access_token),
        )
    if resp.status_code != 200:
        log.warning(
            "auth.oauth.github.user_emails_failed", status=resp.status_code
        )
        raise OAuthError("user_emails_failed", f"/user/emails returned {resp.status_code}")
    emails = resp.json()
    if not isinstance(emails, list):
        raise OAuthError("user_emails_unexpected", "/user/emails did not return a list")
    for entry in emails:
        if (
            isinstance(entry, dict)
            and entry.get("primary") is True
            and entry.get("verified") is True
        ):
            email = entry.get("email")
            if isinstance(email, str) and "@" in email:
                return email
    log.warning("auth.oauth.github.email_unverified")
    raise OAuthError("email_unverified", "No primary+verified email on GitHub account")


async def complete_github_callback(
    code: str, config: GitHubConfig
) -> tuple[User, str, int]:
    """End-to-end: exchange code, fetch verified email, upsert user, mint JWT.

    Returns (user, jwt, ttl_seconds).
    """
    access_token = await _github_exchange_code(code, config)
    email = await _github_fetch_verified_primary_email(access_token)
    email = email.lower().strip()

    # Optional allowlist for hackathon demo.
    allowed = os.environ.get("GITHUB_ALLOWED_EMAILS", "").strip()
    if allowed:
        allow = {e.strip().lower() for e in allowed.split(",") if e.strip()}
        if email not in allow:
            log.warning("auth.oauth.github.email_not_allowed", email=email)
            raise OAuthError("email_not_allowed", "Email not in allowlist")

    user = await upsert_user_by_email(email)
    log.info("auth.oauth.github.signed_in", user_id=user.id)
    jwt_token, ttl = create_session_token(user.id)
    return user, jwt_token, ttl
