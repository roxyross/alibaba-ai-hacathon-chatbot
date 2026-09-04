"""Unit tests for DeepSeekAdapter — response mapping, error handling, circuit breaker."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.ai_gateway.adapters.deepseek import DeepSeekAdapter
from app.ai_gateway.adapters.base import ProviderUnavailableError
from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole, TaskType


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Ensure DeepSeek API key is set for all adapter tests."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-for-unit-tests")


@pytest.fixture
def adapter():
    return DeepSeekAdapter()


@pytest.fixture
def base_request():
    return AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello, DeepSeek.")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )


@pytest.mark.asyncio
class TestDeepSeekAdapter:
    """Tests for DeepSeek adapter non-streaming path."""

    async def test_successful_response_maps_correctly(self, adapter, base_request):
        """A 200 response from DeepSeek maps to AIResponse with attribution."""
        mock_response = {
            "model": "deepseek-chat-v3",
            "choices": [{
                "message": {"role": "assistant", "content": "Hello from DeepSeek!"}
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 8,
                "total_tokens": 18,
            },
        }

        mock_response_obj = MagicMock()
        mock_response_obj.is_success = True
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.status_code = 200

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response_obj

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            result = await adapter.chatCompletion(base_request)

        assert result.provider == "deepseek"
        assert result.model == "deepseek-chat-v3"
        assert result.agent_id == "test-agent"
        assert "Hello from DeepSeek!" in result.content

    async def test_timeout_raises_provider_unavailable(self, adapter, base_request):
        """A timeout raises ProviderUnavailableError with the provider name."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("connection timed out")

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ProviderUnavailableError) as exc_info:
                await adapter.chatCompletion(base_request)

        assert exc_info.value.provider == "deepseek"
        assert "timed out" in exc_info.value.reason.lower()

    async def test_http_5xx_raises_provider_unavailable(self, adapter, base_request):
        """HTTP 5xx responses raise ProviderUnavailableError."""
        mock_response_obj = MagicMock()
        mock_response_obj.is_success = False
        mock_response_obj.status_code = 503
        mock_response_obj.text = "Service Unavailable"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response_obj

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ProviderUnavailableError) as exc_info:
                await adapter.chatCompletion(base_request)

        assert exc_info.value.provider == "deepseek"
        assert "503" in exc_info.value.reason

    async def test_connection_error_raises_provider_unavailable(self, adapter, base_request):
        """Connection errors raise ProviderUnavailableError."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ProviderUnavailableError) as exc_info:
                await adapter.chatCompletion(base_request)

        assert exc_info.value.provider == "deepseek"

    async def test_disabled_provider_raises_unavailable(self, adapter, base_request, monkeypatch):
        """A disabled provider raises ProviderUnavailableError immediately."""
        monkeypatch.setenv("PROVIDER_DEEPSEEK_ENABLED", "false")
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await adapter.chatCompletion(base_request)
        assert "disabled" in exc_info.value.reason.lower()

    async def test_missing_api_key_raises_unavailable(self, adapter, base_request, monkeypatch):
        """Missing API key raises ProviderUnavailableError."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await adapter.chatCompletion(base_request)
        assert "not set" in exc_info.value.reason.lower()
