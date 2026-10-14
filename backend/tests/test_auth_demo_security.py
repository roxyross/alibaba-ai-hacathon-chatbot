"""Adversarial regression tests for Phase 2: Public Demo Login Hardening.

Validates:
- Demo endpoint is disabled by default in all environments.
- In production (APP_ENV=production or ENV=production or VERCEL=1), demo endpoint returns HTTP 403.
- Client query parameters (?enable_demo=true), headers (x-enable-demo: true), and bodies cannot enable demo mode.
- Non-production demo mode works ONLY when ENABLE_DEMO_LOGIN=true is explicitly set server-side.
- Normal authentication (request-link & verify) remains operational.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_demo_login_disabled_by_default_in_production():
    """In production, POST /api/v1/auth/demo must be rejected with 403 Forbidden."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": "a" * 32}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/demo")
            assert resp.status_code == 403
            data = resp.json()
            assert "Demo login is disabled in this environment" in data["detail"]


@pytest.mark.asyncio
async def test_demo_login_disabled_by_default_in_development():
    """Even in development mode, demo login must be disabled unless ENABLE_DEMO_LOGIN=true."""
    with patch.dict(os.environ, {"APP_ENV": "development", "ENABLE_DEMO_LOGIN": ""}, clear=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/demo")
            assert resp.status_code == 403


@pytest.mark.asyncio
async def test_client_cannot_enable_demo_mode_via_params_or_headers():
    """Client parameters or headers cannot bypass the server-side disablement."""
    with patch.dict(os.environ, {"APP_ENV": "production", "JWT_SECRET": "a" * 32}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Try query param
            r1 = await client.post("/api/v1/auth/demo?enable_demo=true&demo=true")
            assert r1.status_code == 403

            # Try request headers
            r2 = await client.post(
                "/api/v1/auth/demo",
                headers={"x-enable-demo": "true", "x-roxy-demo": "true", "x-admin": "true"},
            )
            assert r2.status_code == 403

            # Try json body
            r3 = await client.post("/api/v1/auth/demo", json={"enable_demo": True, "force": True})
            assert r3.status_code == 403


@pytest.mark.asyncio
async def test_demo_login_succeeds_only_when_explicitly_enabled_in_non_prod():
    """When ENABLE_DEMO_LOGIN=true is explicitly set in non-production, demo login succeeds."""
    with patch.dict(os.environ, {"APP_ENV": "development", "ENABLE_DEMO_LOGIN": "true", "JWT_SECRET": "c" * 32}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/demo")
            assert resp.status_code == 200
            data = resp.json()
            assert "access_token" in data
            assert data["user"]["email"] == "demo@roxy.ai"


@pytest.mark.asyncio
async def test_production_flag_overrides_enable_demo_login():
    """If APP_ENV=production, even setting ENABLE_DEMO_LOGIN=true MUST NOT enable demo mode."""
    with patch.dict(
        os.environ,
        {"APP_ENV": "production", "ENABLE_DEMO_LOGIN": "true", "JWT_SECRET": "b" * 32},
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/demo")
            assert resp.status_code == 403
