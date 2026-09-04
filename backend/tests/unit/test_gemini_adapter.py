"""Unit tests for GeminiAdapter — response mapping, error handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai_gateway.adapters.gemini import GeminiAdapter
from app.ai_gateway.adapters.base import ProviderUnavailableError
from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole, TaskType


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")


@pytest.fixture
def adapter():
    return GeminiAdapter()


@pytest.fixture
def base_request():
    return AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello, Gemini.")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )


@pytest.mark.asyncio
class TestGeminiAdapter:
    async def test_successful_response_maps_correctly(self, adapter, base_request):
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Hello from Gemini!"}],
                    "role": "model",
                }
            }],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 8,
                "totalTokenCount": 18,
            },
        }
        mock_response_obj = MagicMock()
        mock_response_obj.is_success = True
        mock_response_obj.json.return_value = mock_response

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response_obj

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            result = await adapter.chatCompletion(base_request)

        assert result.provider == "gemini"
        assert result.model == "gemini-2.0-flash"
        assert "Hello from Gemini!" in result.content

    async def test_timeout_raises_provider_unavailable(self, adapter, base_request):
        import httpx
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ProviderUnavailableError) as exc_info:
                await adapter.chatCompletion(base_request)

        assert exc_info.value.provider == "gemini"

    async def test_http_error_raises_provider_unavailable(self, adapter, base_request):
        mock_response_obj = MagicMock()
        mock_response_obj.is_success = False
        mock_response_obj.status_code = 400
        mock_response_obj.text = "Invalid request"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response_obj

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            with pytest.raises(ProviderUnavailableError) as exc_info:
                await adapter.chatCompletion(base_request)

        assert exc_info.value.provider == "gemini"
