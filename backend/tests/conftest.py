"""Shared pytest fixtures for the backend.

Provides:
- `async_client`: plain ASGI-wired httpx client (no auth).
- `authed_client`: same client with a valid `Authorization: Bearer <jwt>`
  header pre-applied. Used by integration tests that exercise routes
  guarded by `get_current_user`.
"""

from __future__ import annotations

import os
import sys
import asyncio
import itertools
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# CRITICAL: Set blocking values BEFORE any app imports.
#
# app.main calls load_dotenv(".env", override=False) which loads the .env file.
# Since override=False, dotenv SKIPS vars that are ALREADY in os.environ.
# By pre-setting the vars we want to isolate, load_dotenv sees them as
# "already set" and leaves our test values untouched.
# ---------------------------------------------------------------------------
# Block the real DATABASE_URL from being loaded → forces in-memory auth storage.
os.environ["DATABASE_URL"] = ""

# Ensure all providers start in known enabled state (override .env defaults).
os.environ["PROVIDER_DEEPSEEK_ENABLED"] = "true"
os.environ["PROVIDER_OPENAI_ENABLED"] = "true"
os.environ["PROVIDER_GROK_ENABLED"] = "true"
os.environ["PROVIDER_GEMINI_ENABLED"] = "true"

sys.path.insert(0, "src")

# Set deterministic test env AFTER blocking above.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("GROK_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("APP_BASE_URL", "http://localhost:5173")


# A unique email per fixture invocation so each test gets a fresh user and
# token (tokens are single-use and consume themselves on first verify).
_test_emails = (f"test{i}@example.com" for i in itertools.count())


# ---------------------------------------------------------------------------
# Event loop / async backend
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------

async def _make_client() -> tuple["httpx.AsyncClient", "object"]:
    import httpx
    from app.main import app

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    return client, app


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator["httpx.AsyncClient"]:
    """Plain ASGI-wired httpx client (no auth)."""
    client, _ = await _make_client()
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def authed_client() -> AsyncIterator["httpx.AsyncClient"]:
    """ASGI-wired httpx client with a valid Bearer JWT.

    Mints a magic link, verifies it, and stores the issued JWT on the
    client. Tests using this fixture can hit routes protected by
    `get_current_user` (chat history, sessions, etc.) without further setup.
    """
    import httpx
    from app.auth.service import MagicLinkService

    client, _ = await _make_client()
    service = MagicLinkService()
    test_email = next(_test_emails)
    await service.request_link(test_email)
    user_id = next(
        u.id for email, u in service._mem_users.items() if email == test_email
    )
    token_value = next(
        t for t, row in service._mem_tokens.items() if row.user_id == user_id
    )
    result = await service.verify(token_value)
    if result is None:
        raise RuntimeError("Failed to verify magic-link token in test fixture")
    _user, jwt, _ttl = result
    client.headers["Authorization"] = f"Bearer {jwt}"
    try:
        yield client
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Reset provider feature flags before each test so toggle-test assumptions hold.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_provider_flags():
    """Ensure each test starts with all providers in the known enabled state.

    The toggle test modifies os.environ[PROVIDER_DEEPSEEK_ENABLED] directly.
    Without this, a prior test that left it at 'false' breaks the next test.
    """
    os.environ["PROVIDER_DEEPSEEK_ENABLED"] = "true"
    os.environ["PROVIDER_OPENAI_ENABLED"] = "true"
    yield
    # No cleanup needed — each test gets a fresh known state.


# ---------------------------------------------------------------------------
# Compatibility shim: let tests keep using the bare `async_client` name.
# This overrides the per-file fixtures via pytest's fixture precedence so
# `authed_client` can be requested where needed. The local `async_client`
# fixtures in test files still work unchanged.
# ---------------------------------------------------------------------------
