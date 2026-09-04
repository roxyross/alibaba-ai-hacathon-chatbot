"""Unit tests for AIRouter — routing priority, overrides, and failover logic."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole, TaskType
from app.ai_gateway.services.router import AIRouter, _sorted_providers, _adapters
from app.ai_gateway.adapters.base import AllProvidersUnavailableError, ProviderUnavailableError


@pytest.fixture
def router():
    return AIRouter()


@pytest.fixture
def base_request():
    return AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello, AI.")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )


class TestProviderPriority:
    """Test that providers are sorted by routing priority."""

    def test_sorted_providers_returns_list(self):
        result = _sorted_providers()
        assert isinstance(result, list)

    def test_deepseek_first_when_enabled(self):
        """When both deepseek and openai are enabled, deepseek (priority 1) comes first."""
        mock_deepseek = MagicMock()
        mock_deepseek.name = "deepseek"
        mock_deepseek.routing_priority = 1
        mock_deepseek.is_enabled = True
        mock_deepseek.has_api_key = True

        mock_openai = MagicMock()
        mock_openai.name = "openai"
        mock_openai.routing_priority = 3
        mock_openai.is_enabled = True
        mock_openai.has_api_key = True

        mock_configs = [mock_openai, mock_deepseek]

        with patch("app.ai_gateway.services.router.get_all_provider_configs", return_value=mock_configs):
            result = _sorted_providers()
            assert result == ["deepseek", "openai"]


class TestRequestOverride:
    """Test request-level override skips priority ordering."""

    def test_provider_field_takes_priority(self, router, base_request):
        base_request.provider = "openai"
        assert router._resolve_override(base_request) == "openai"

    def test_none_when_no_override(self, router, base_request):
        base_request.provider = None
        assert router._resolve_override(base_request) is None


class TestRouterRoute:
    """Integration tests for AIRouter.route()."""

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises_all_unavailable(self, router, base_request, monkeypatch):
        """When every provider fails, AllProvidersUnavailableError is raised."""
        from app.ai_gateway.adapters.base import AIProviderAdapter
        from app.ai_gateway.models.schemas import AIResponse
        import uuid

        # Create a mock adapter that always fails
        mock_adapter = MagicMock(spec=AIProviderAdapter)
        mock_adapter.chatCompletion = AsyncMock(
            side_effect=ProviderUnavailableError("deepseek", "connection refused")
        )

        # Patch the adapter registry
        with patch.dict(_adapters, {"deepseek": mock_adapter}):
            with patch("app.ai_gateway.services.router._sorted_providers", return_value=["deepseek"]):
                with pytest.raises(AllProvidersUnavailableError):
                    await router.route(base_request)

    @pytest.mark.asyncio
    async def test_provider_override_skips_default_priority(self, router, base_request, monkeypatch):
        """When request.provider is set, only that provider is tried."""
        from app.ai_gateway.adapters.base import AIProviderAdapter
        from uuid import uuid4

        mock_response = AIResponse(
            content="hello",
            provider="deepseek",
            model="deepseek-chat-v3",
            agent_id="test-agent",
            input_tokens=5,
            output_tokens=5,
            cost_usd=0.0,
            latency_ms=100,
            request_id=uuid4(),
        )

        mock_adapter = MagicMock(spec=AIProviderAdapter)
        mock_adapter.chatCompletion = AsyncMock(return_value=mock_response)

        base_request.provider = "deepseek"

        with patch.dict(_adapters, {"deepseek": mock_adapter}):
            with patch("app.ai_gateway.services.router._sorted_providers") as mock_sorted:
                mock_sorted.return_value = ["grok", "openai"]  # should NOT be called
                result = await router.route(base_request)

            mock_adapter.chatCompletion.assert_called_once()
            assert result.content == "hello"

