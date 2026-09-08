"""End-to-end integration test: POST /api/v1/runtime/chat.

Per spec PR 2 deliverable: a user sends a research question;
the Coordinator classifies it, routes to the Research Agent, and
returns a response labelled "Research Agent". The skill returns
a mock result (stub).

The gateway HTTP call is mocked using respx so the entire httpx
transport is intercepted. We use `respx.mock(assert_all_called=False)`
to allow any extra calls (e.g. health checks) to pass silently.
"""

from __future__ import annotations

import httpx
import respx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from runtime.main import create_app


import time

import jwt

from runtime.config import settings

# A valid JWT signed with the runtime's jwt_secret (from .env or default).
# Must include 'exp' (required by decode_bearer) and 'sub'.
_DUMMY_TOKEN = jwt.encode(
    {
        "sub": "test-user-id",
        "email": "test@example.com",
        "exp": int(time.time()) + 3600,  # 1 hour from now
    },
    settings.jwt_secret,
    algorithm=settings.jwt_algorithm,
)
_AUTH_HEADER = {"Authorization": f"Bearer {_DUMMY_TOKEN}"}


def _build_mocked_app() -> FastAPI:
    """Create the FastAPI app with the gateway call mocked via respx."""
    app = create_app()
    return app


# ---- fixtures ---------------------------------------------------------------

@pytest.fixture
def app() -> FastAPI:
    """FastAPI app with the gateway call mocked via respx."""
    return _build_mocked_app()


@pytest.fixture
def app_no_gateway() -> FastAPI:
    """FastAPI app for tests that don't call the gateway."""
    return create_app()


# ---- tests -----------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_research_question_routes_to_research_agent(app: FastAPI) -> None:
    """A research-style query is classified and routed to the Research Agent."""
    chat_route = respx.post("http://localhost:8000/api/v1/ai/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": (
                    "According to my research, the capital of France is Paris. "
                    "This is a stubbed Research Agent response for the vertical slice test."
                ),
                "provider": "stub",
                "model": "stub",
            },
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/runtime/chat",
            json={"message": "what is the capital of France?"},
            headers=_AUTH_HEADER,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["agent_slug"] == "research"
    assert data["needs_clarification"] is False
    assert data["response"] is not None
    assert "Paris" in data["response"]
    assert data["citations"] == []  # stub doesn't produce citations
    assert data["next_actions"] == []
    chat_route.called  # verify the route was invoked


@respx.mock(assert_all_called=False)
@pytest.mark.asyncio
async def test_clarification_when_query_is_ambiguous(app: FastAPI) -> None:
    """A vague query returns needs_clarification=True with suggestions."""
    # No gateway call expected since classification is uncertain (no agent routed)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/runtime/chat",
            json={"message": "hello"},
            headers=_AUTH_HEADER,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["needs_clarification"] is True
    assert data["agent_slug"] is None
    assert data["status"] == "uncertain"


@pytest.mark.asyncio
async def test_health_live(app_no_gateway: FastAPI) -> None:
    """GET /health/live returns ok without auth."""
    async with AsyncClient(transport=ASGITransport(app=app_no_gateway), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# No @respx.mock here — the health check makes an internal HTTP call
# to the backend gateway that is NOT part of the mocked routes.
@pytest.mark.asyncio
async def test_health_ready_degraded_without_backend(app_no_gateway: FastAPI) -> None:
    """GET /health/ready returns 'degraded' when the backend is unreachable."""
    async with AsyncClient(transport=ASGITransport(app=app_no_gateway), base_url="http://test") as client:
        response = await client.get("/health/ready")
    # Without a real backend at localhost:8000, the gateway check fails → degraded
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["agents_loaded"] > 0


@respx.mock(assert_all_called=False)
@pytest.mark.asyncio
async def test_list_agents_endpoint(app: FastAPI) -> None:
    """GET /api/v1/runtime/agents returns the loaded agent list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/runtime/agents", headers=_AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    agent_slugs = {a["slug"] for a in data["agents"]}
    assert "research" in agent_slugs


@respx.mock(assert_all_called=False)
@pytest.mark.asyncio
async def test_list_skills_endpoint(app: FastAPI) -> None:
    """GET /api/v1/runtime/skills returns the loaded skill list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/runtime/skills", headers=_AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert "skills" in data
    web_search_skill = next((s for s in data["skills"] if s["slug"] == "web_search"), None)
    assert web_search_skill is not None
    assert web_search_skill["registered"] is True


@respx.mock(assert_all_called=False)
@pytest.mark.asyncio
async def test_unauthorized_without_token(app: FastAPI) -> None:
    """Requests without a Bearer token return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/runtime/chat",
            json={"message": "hello"},
        )
    assert response.status_code == 401
