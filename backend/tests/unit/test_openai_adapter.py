"""Unit tests for OpenAIAdapter — response mapping, error handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai_gateway.adapters.openai import OpenAIAdapter
from app.ai_gateway.adapters.base import ProviderUnavailableError
from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole, TaskType


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")


@pytest.fixture
def adapter():
    return OpenAIAdapter()


@pytest.fixture
def base_request():
    return AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello, GPT.")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )


@pytest.mark.asyncio
class TestOpenAIAdapter:
    async def test_successful_response_maps_correctly(self, adapter, base_request):
        mock_response = {
            "model": "gpt-4o",
            "choices": [{"message": {"role": "assistant", "content": "Hello from GPT-4o!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
        }
        mock_response_obj = MagicMock()
        mock_response_obj.is_success = True
        mock_response_obj.json.return_value = mock_response

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response_obj

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            result = await adapter.chatCompletion(base_request)

        assert result.provider == "openai"
        assert result.model == "gpt-4o"
        assert "Hello from GPT-4o!" in result.content

    async def test_timeout_raises_provider_unavailable(self, adapter, base_request):
        import httpx
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ProviderUnavailableError) as exc_info:
                await adapter.chatCompletion(base_request)

        assert exc_info.value.provider == "openai"

    async def test_http_5xx_raises_provider_unavailable(self, adapter, base_request):
        mock_response_obj = MagicMock()
        mock_response_obj.is_success = False
        mock_response_obj.status_code = 429
        mock_response_obj.text = "Rate limited"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response_obj

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ProviderUnavailableError) as exc_info:
                await adapter.chatCompletion(base_request)

        assert exc_info.value.provider == "openai"
