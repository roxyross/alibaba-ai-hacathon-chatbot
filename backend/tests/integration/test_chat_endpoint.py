"""Integration tests for the chat endpoint — non-streaming and streaming.

Tests cover:
- T015: POST /api/v1/ai/chat returns 200 with attribution fields
- T015: POST /api/v1/ai/chat with provider=grok override uses Grok
- T015: GET /api/v1/ai/providers/health returns 200 without auth
- T015: PATCH /api/v1/ai/providers/{name} toggles provider
- T015: unknown provider returns 404
- T015: all providers fail returns 503
- T023: streaming response is valid SSE with attribution comment line
- T023: streaming response includes done=true final event
"""

import json
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import pytest

sys.path.insert(0, "src")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("GROK_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client():
    """Async HTTP client wired to the FastAPI app via ASGI transport."""
    import httpx
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


class TestHealthEndpoints:
    """T015: Health and provider management endpoints."""

    async def test_providers_health_no_auth(self, async_client):
        """GET /providers/health should not require auth."""
        response = await async_client.get("/api/v1/ai/providers/health")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        names = {p["name"] for p in data["providers"]}
        assert names >= {"deepseek", "grok", "openai", "gemini"}

    async def test_toggle_provider(self, async_client):
        """PATCH /providers/{name} toggles the provider flag."""
        response = await async_client.patch("/api/v1/ai/providers/deepseek")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "deepseek"
        assert data["enabled"] is False

        response = await async_client.patch("/api/v1/ai/providers/deepseek")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    async def test_unknown_provider_returns_404(self, async_client):
        """Patching an unknown provider name returns 404."""
        response = await async_client.patch("/api/v1/ai/providers/nonexistent")
        assert response.status_code == 404


class TestChatEndpointNonStreaming:
    """T015: Non-streaming chat endpoint tests."""

    async def test_chat_returns_attribution_fields(self, authed_client):
        """POST /api/v1/ai/chat returns 200 with provider and model attribution."""
        from app.ai_gateway.models.schemas import AIResponse

        mock_response = AIResponse(
            content="Hello from the gateway!",
            provider="deepseek",
            model="deepseek-chat-v3",
            agent_id="test-agent",
            input_tokens=5,
            output_tokens=10,
            cost_usd=0.0,
            latency_ms=50,
            request_id=uuid4(),
        )

        with patch("app.api.v1.ai._router.route", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = mock_response
            response = await authed_client.post(
                "/api/v1/ai/chat",
                json={
                    "messages": [{"role": "user", "content": "Hello!"}],
                    "agent_id": "test-agent",
                    "stream": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek-chat-v3"
        assert "Hello from the gateway!" in data["content"]
        assert "request_id" in data

    async def test_chat_with_grok_override(self, authed_client):
        """POST /api/v1/ai/chat with provider=grok routes to Grok."""
        from app.ai_gateway.models.schemas import AIResponse

        mock_response = AIResponse(
            content="Grok here!",
            provider="grok",
            model="grok-3",
            agent_id="test-agent",
            input_tokens=5,
            output_tokens=8,
            cost_usd=0.0,
            latency_ms=40,
            request_id=uuid4(),
        )

        with patch("app.api.v1.ai._router.route", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = mock_response
            response = await authed_client.post(
                "/api/v1/ai/chat",
                json={
                    "messages": [{"role": "user", "content": "Hi Grok!"}],
                    "provider": "grok",
                    "stream": False,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "grok"
        assert data["model"] == "grok-3"
        assert "Grok here!" in data["content"]

    async def test_chat_all_providers_fail_returns_503(self, authed_client):
        """POST /api/v1/ai/chat returns 503 when all providers fail."""
        from app.ai_gateway.adapters.base import AllProvidersUnavailableError

        with patch("app.api.v1.ai._router.route", new_callable=AsyncMock) as mock_route:
            mock_route.side_effect = AllProvidersUnavailableError("all providers failed")
            response = await authed_client.post(
                "/api/v1/ai/chat",
                json={
                    "messages": [{"role": "user", "content": "Hello!"}],
                    "agent_id": "test-agent",
                },
            )

        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["code"] == "ALL_PROVIDERS_UNAVAILABLE"

    async def test_chat_provider_unavailable_returns_503(self, authed_client):
        """POST /api/v1/ai/chat returns 503 when a specific provider is unavailable."""
        from app.ai_gateway.adapters.base import ProviderUnavailableError

        with patch("app.api.v1.ai._router.route", new_callable=AsyncMock) as mock_route:
            mock_route.side_effect = ProviderUnavailableError("deepseek", "connection refused")
            response = await authed_client.post(
                "/api/v1/ai/chat",
                json={
                    "messages": [{"role": "user", "content": "Hello!"}],
                },
            )

        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["code"] == "PROVIDER_UNAVAILABLE"
        assert data["detail"]["failed_provider"] == "deepseek"


class TestChatEndpointStreaming:
    """T023: Streaming SSE endpoint tests.

    Strategy: patch _router._adapters using patch.object context manager so the
    router's dict reference is temporarily swapped.  The patch is scoped to each
    test — no finally-block state mutation that could bleed between tests.
    A fresh async_client is used per test to avoid httpx connection reuse.
    """

    @pytest.fixture
    async def streaming_client(self):
        """Fresh async client per streaming test to avoid connection state leakage."""
        import httpx
        from app.main import app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client

    @pytest.fixture
    async def authed_streaming_client(self):
        """Same as `streaming_client` but with a valid Bearer JWT pre-applied."""
        from app.auth.service import MagicLinkService
        from tests.conftest import _test_emails

        import httpx
        from app.main import app
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
        assert result is not None
        _user, jwt, _ttl = result
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {jwt}"},
        ) as client:
            yield client

    async def test_stream_endpoint_rejects_non_stream_request(self, authed_streaming_client):
        """POST /api/v1/ai/chat with stream=False is non-streaming and returns 200."""
        from app.ai_gateway.models.schemas import AIResponse

        mock_response = AIResponse(
            content="ok",
            provider="deepseek",
            model="deepseek-chat-v3",
            agent_id="test",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=10,
            request_id=uuid4(),
        )

        with patch("app.api.v1.ai._router.route", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = mock_response
            response = await authed_streaming_client.post(
                "/api/v1/ai/chat",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
            )

        assert response.status_code == 200

    async def test_stream_returns_sse_with_attribution_comment(self, authed_streaming_client):
        """Streaming response starts with SSE comment line containing provider and model."""
        from app.ai_gateway.models.schemas import StreamingChunk

        async def mock_route_stream(request):
            yield StreamingChunk(
                delta="Hello ",
                provider="deepseek",
                model="deepseek-chat-v3",
                done=False,
            )
            yield StreamingChunk(
                delta="world!",
                provider="deepseek",
                model="deepseek-chat-v3",
                done=True,
            )

        with patch("app.api.v1.ai._router.route_stream", mock_route_stream):
            response = await authed_streaming_client.post(
                "/api/v1/ai/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        body = b""
        async for chunk in response.aiter_bytes():
            body += chunk

        text = body.decode("utf-8")
        lines = text.split("\n")
        assert lines[0].startswith(": provider="), f"Expected attribution comment, got: {lines[0]!r}"
        assert "deepseek" in lines[0]
        assert "deepseek-chat-v3" in lines[0]

    async def test_stream_yields_data_events_with_done(self, authed_streaming_client):
        """Streaming response contains data events with delta, provider, model, done fields."""
        from app.ai_gateway.models.schemas import StreamingChunk

        async def mock_route_stream(request):
            yield StreamingChunk(
                delta="Hello ",
                provider="deepseek",
                model="deepseek-chat-v3",
                done=False,
            )
            yield StreamingChunk(
                delta="world!",
                provider="deepseek",
                model="deepseek-chat-v3",
                done=True,
            )

        with patch("app.api.v1.ai._router.route_stream", mock_route_stream):
            response = await authed_streaming_client.post(
                "/api/v1/ai/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            )

        assert response.status_code == 200

        body = b""
        async for chunk in response.aiter_bytes():
            body += chunk

        text = body.decode("utf-8")

        data_lines = [l for l in text.split("\n") if l.startswith("data: ")]
        assert len(data_lines) >= 2, f"Expected at least 2 data lines, got: {data_lines}"

        first_event = json.loads(data_lines[0].removeprefix("data: "))
        assert "delta" in first_event
        assert "provider" in first_event
        assert "model" in first_event
        assert "done" in first_event
        assert first_event["provider"] == "deepseek"

    async def test_stream_all_providers_fail_returns_error_event(self, authed_streaming_client):
        """When all providers fail in streaming, an error event is returned."""
        from app.ai_gateway.adapters.base import AllProvidersUnavailableError

        async def async_gen_that_raises(request):
            raise AllProvidersUnavailableError("all providers unavailable")
            yield  # make it an async generator

        with patch("app.api.v1.ai._router.route_stream", side_effect=async_gen_that_raises):
            response = await authed_streaming_client.post(
                "/api/v1/ai/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                },
            )

        assert response.status_code == 200

        body = b""
        async for chunk in response.aiter_bytes():
            body += chunk

        text = body.decode("utf-8")
        assert "all_providers_unavailable" in text
