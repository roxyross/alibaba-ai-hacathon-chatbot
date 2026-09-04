"""Dedicated integration tests for the streaming SSE endpoint.

T023: Write integration test for streaming `backend/tests/integration/test_chat_stream.py`

Tests:
- POST /api/v1/ai/chat/stream with stream=false returns 400
- Streaming response is valid SSE with attribution comment line (": provider=X model=Y")
- Streaming response contains data events with delta, provider, model, done fields
- When all providers fail, an error event is returned in SSE format
"""

import json
import os
import sys
from unittest.mock import AsyncMock, patch
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
async def streaming_client():
    """Fresh async client per streaming test to avoid connection state leakage."""
    import httpx
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
async def authed_streaming_client():
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


class TestChatStreamEndpoint:
    """T023: Streaming SSE endpoint tests."""

    async def test_stream_requires_stream_true(self, authed_streaming_client):
        """POST /api/v1/ai/chat/stream without stream=true returns 400."""
        response = await authed_streaming_client.post(
            "/api/v1/ai/chat/stream",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        assert response.status_code == 400
        assert "stream=true" in response.text

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
                provider="grok",
                model="grok-3",
                done=False,
            )
            yield StreamingChunk(
                delta="world!",
                provider="grok",
                model="grok-3",
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
        assert first_event["provider"] == "grok"
        assert first_event["model"] == "grok-3"
        assert first_event["done"] is False

        # Last data event should have done=True
        last_event = json.loads(data_lines[-1].removeprefix("data: "))
        assert last_event.get("done") is True

    async def test_stream_all_providers_fail_returns_error_event(self, authed_streaming_client):
        """When all providers fail in streaming, an error event is returned with SSE format."""
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
        assert "error" in text

    async def test_stream_provider_unavailable_returns_error_event(self, authed_streaming_client):
        """When one provider fails in streaming, an error event is returned."""
        from app.ai_gateway.adapters.base import ProviderUnavailableError

        async def async_gen_that_raises(request):
            raise ProviderUnavailableError("deepseek", "connection refused")
            yield

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
        assert "provider_unavailable" in text or "provider_error" in text

    async def test_stream_content_type_headers(self, authed_streaming_client):
        """Streaming response includes correct SSE headers."""
        from app.ai_gateway.models.schemas import StreamingChunk

        async def mock_route_stream(request):
            yield StreamingChunk(delta="hi", provider="openai", model="gpt-4o", done=True)

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
        assert response.headers.get("cache-control") == "no-cache"
