"""Adversarial security regression tests for OAuth redirect origin and token handoff.

Validates:
- Exact trusted origins (e.g. https://roxy-personal-ai.vercel.app, localhost) are accepted.
- Attacker-controlled origins (https://attacker.com) are rejected.
- Lookalike domains (https://roxy-personal-ai.vercel.app.attacker.com) are rejected.
- Attacker-controlled HTTP origins are rejected in production.
- Malicious cookies (roxy.oauth_origin) or Referer/Origin headers cannot override the allowlist.
- _redirect_with_jwt strictly ensures destination is trusted before redirecting.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from starlette.requests import Request

from app.auth.router import (
    _is_origin_trusted,
    _redirect_with_jwt,
    _resolve_frontend_base,
)


def _mock_request(cookies: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/oauth/google/callback",
        "headers": [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in (headers or {}).items()],
    }
    req = Request(scope)
    # Patch cookies if needed
    if cookies:
        req._cookies = cookies
    return req


def test_trusted_origin_accepted():
    """Exact allowlisted production and local origins are recognized as trusted."""
    assert _is_origin_trusted("https://roxy-personal-ai.vercel.app") is True
    assert _is_origin_trusted("https://roxy.ai") is True
    assert _is_origin_trusted("https://app.roxy.ai") is True
    assert _is_origin_trusted("http://localhost:5173") is True


def test_attacker_https_origin_rejected():
    """Arbitrary third-party domains must be rejected."""
    assert _is_origin_trusted("https://attacker.com") is False
    assert _is_origin_trusted("https://evil-phishing-roxy.com") is False


def test_lookalike_subdomains_rejected():
    """Lookalike subdomains targeting roxy domains must be rejected."""
    assert _is_origin_trusted("https://roxy-personal-ai.vercel.app.evil.com") is False
    assert _is_origin_trusted("https://app.roxy.ai.attacker.org") is False


def test_unencrypted_http_rejected_in_production():
    """In production (APP_ENV=production), plain HTTP origins must be rejected."""
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        assert _is_origin_trusted("http://attacker.com") is False
        assert _is_origin_trusted("http://roxy.ai") is False


def test_malformed_and_unexpected_scheme_rejected():
    """Javascript schemes, data schemes, or malformed URIs are rejected."""
    assert _is_origin_trusted("javascript:alert(1)") is False
    assert _is_origin_trusted("data:text/html,<script>alert(1)</script>") is False
    assert _is_origin_trusted("ftp://roxy.ai") is False
    assert _is_origin_trusted("") is False
    assert _is_origin_trusted(None) is False


def test_resolve_frontend_base_ignores_attacker_explicit_origin():
    """Passing ?origin=https://attacker.com falls back to trusted canonical base."""
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        resolved = _resolve_frontend_base(explicit_origin="https://attacker.com")
        assert resolved == "https://roxy-personal-ai.vercel.app"
        assert "attacker.com" not in resolved


def test_resolve_frontend_base_ignores_attacker_cookie():
    """Attacker setting roxy.oauth_origin cookie to https://evil.com is ignored."""
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        req = _mock_request(cookies={"roxy.oauth_origin": "https://evil.com"})
        resolved = _resolve_frontend_base(request=req)
        assert resolved == "https://roxy-personal-ai.vercel.app"


def test_resolve_frontend_base_ignores_attacker_referer():
    """Attacker setting Referer or Origin header to https://evil.com is ignored."""
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        req = _mock_request(headers={"referer": "https://evil.com/login", "origin": "https://evil.com"})
        resolved = _resolve_frontend_base(request=req)
        assert resolved == "https://roxy-personal-ai.vercel.app"


def test_redirect_with_jwt_never_redirects_to_attacker_destination():
    """_redirect_with_jwt must refuse to redirect tokens to an untrusted origin."""
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        resp = _redirect_with_jwt(
            jwt_token="secret_user_jwt_token_12345",
            ttl=3600,
            frontend_base="https://attacker.com",
        )
        assert resp.status_code == 302
        target_url = resp.headers["location"]
        # Must redirect to trusted canonical base, NEVER attacker.com
        assert target_url.startswith("https://roxy-personal-ai.vercel.app/auth/callback#")
        assert "attacker.com" not in target_url
        assert "access_token=secret_user_jwt_token_12345" in target_url
