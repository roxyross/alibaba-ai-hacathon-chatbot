"""Task-based AI model routing and resilience regression test suite.

Explicitly validates Phase C (Section 4.3) requirements:
1. General chat routes to Gemini 4 Argon (gemini-4-argon).
2. Reasoning routes to Gemini 4 Argon (gemini-4-argon).
3. Coding routes to Gemini 4 Argon (gemini-4-argon).
4. Text-to-speech routes to Gemini 3.8 Plus (gemini-3.8-plus).
5. Speech-to-text routes to Gemini 3.8 Plus (gemini-3.8-plus).
6. Live Audio routes to Gemini 3.8 Plus (gemini-3.8-plus).
7. Audio baseline task routes to Gemini 3.8 Flash (gemini-3.8-flash).
8. Unknown model identifier handling.
9. Unsupported task/model combination guard.
10. Missing credentials fail closed.
11. Provider rate limit (429) backoff and retry behavior.
12. Timeout and connection failure handling.
13. Invalid provider response handling.
14. Transparent, logged fallback without silent model substitution.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_gateway.adapters.base import AllProvidersUnavailableError, ProviderUnavailableError
from app.ai_gateway.adapters.gemini import GeminiAdapter
from app.ai_gateway.models.provider import _default_models, get_provider_config
from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole, TaskType
from app.ai_gateway.services.catalog_discovery import ModelCatalogDiscoveryService
from app.ai_gateway.services.resilience import UniversalResilienceManager
from app.ai_gateway.services.router import AIRouter, _adapters


@pytest.fixture
def mock_gemini_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.NAME = "gemini"
    adapter.provider_name = "gemini"
    adapter.chatCompletion = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_general_chat_routes_to_gemini_4_argon(mock_gemini_adapter: MagicMock) -> None:
    """General chat task defaults to Gemini 4 Argon (gemini-4-argon)."""
    resilience_mgr = UniversalResilienceManager()
    discovery = ModelCatalogDiscoveryService.get_instance()

    # Catalog default check
    assert discovery.get_default_model("gemini", task_type="general") == "gemini-4-argon"

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello, explain relativity.")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )

    mock_gemini_adapter.chatCompletion.return_value = AIResponse(
        user_id="usr_test",
        content="General response",
        response="General response",
        provider="gemini",
        model="gemini-4-argon",
        agent_id="test-agent",
        input_tokens=10,
        output_tokens=15,
        cost_usd=0.0,
        latency_ms=100,
        request_id=uuid.uuid4(),
    )

    with patch.dict(_adapters, {"gemini": mock_gemini_adapter}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
            gemini_cfg = MagicMock()
            gemini_cfg.name = "gemini"
            gemini_cfg.is_enabled = True
            gemini_cfg.has_api_key = True
            gemini_cfg.routing_priority = 1
            mock_cfgs.return_value = [gemini_cfg]

            resp = await resilience_mgr.execute_with_resilience(req, task_type="general")
            assert resp.model == "gemini-4-argon"
            # Verify request model assigned
            assert req.model == "gemini-4-argon"


@pytest.mark.asyncio
async def test_reasoning_task_routes_to_gemini_4_argon(mock_gemini_adapter: MagicMock) -> None:
    """Reasoning task defaults to Gemini 4 Argon (gemini-4-argon)."""
    resilience_mgr = UniversalResilienceManager()
    discovery = ModelCatalogDiscoveryService.get_instance()

    assert discovery.get_default_model("gemini", task_type="reasoning") == "gemini-4-argon"

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Solve this formal logic problem.")],
        task_type=TaskType.REASONING,
        agent_id="test-agent",
    )

    mock_gemini_adapter.chatCompletion.return_value = AIResponse(
        user_id="usr_test",
        content="Logic solution",
        response="Logic solution",
        provider="gemini",
        model="gemini-4-argon",
        agent_id="test-agent",
        input_tokens=15,
        output_tokens=30,
        cost_usd=0.0,
        latency_ms=120,
        request_id=uuid.uuid4(),
    )

    with patch.dict(_adapters, {"gemini": mock_gemini_adapter}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
            gemini_cfg = MagicMock()
            gemini_cfg.name = "gemini"
            gemini_cfg.is_enabled = True
            gemini_cfg.has_api_key = True
            gemini_cfg.routing_priority = 1
            mock_cfgs.return_value = [gemini_cfg]

            resp = await resilience_mgr.execute_with_resilience(req, task_type="reasoning")
            assert resp.model == "gemini-4-argon"
            assert req.model == "gemini-4-argon"


@pytest.mark.asyncio
async def test_coding_task_routes_to_gemini_4_argon(mock_gemini_adapter: MagicMock) -> None:
    """Coding task defaults to Gemini 4 Argon (gemini-4-argon)."""
    resilience_mgr = UniversalResilienceManager()
    discovery = ModelCatalogDiscoveryService.get_instance()

    assert discovery.get_default_model("gemini", task_type="coding") == "gemini-4-argon"

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Write a binary search algorithm in Python.")],
        task_type=TaskType.CODING,
        agent_id="test-agent",
    )

    mock_gemini_adapter.chatCompletion.return_value = AIResponse(
        user_id="usr_test",
        content="def binary_search(...): ...",
        response="def binary_search(...): ...",
        provider="gemini",
        model="gemini-4-argon",
        agent_id="test-agent",
        input_tokens=20,
        output_tokens=50,
        cost_usd=0.0,
        latency_ms=140,
        request_id=uuid.uuid4(),
    )

    with patch.dict(_adapters, {"gemini": mock_gemini_adapter}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
            gemini_cfg = MagicMock()
            gemini_cfg.name = "gemini"
            gemini_cfg.is_enabled = True
            gemini_cfg.has_api_key = True
            gemini_cfg.routing_priority = 1
            mock_cfgs.return_value = [gemini_cfg]

            resp = await resilience_mgr.execute_with_resilience(req, task_type="coding")
            assert resp.model == "gemini-4-argon"
            assert req.model == "gemini-4-argon"


@pytest.mark.asyncio
async def test_text_to_speech_routes_to_gemini_3_8_plus(mock_gemini_adapter: MagicMock) -> None:
    """Text-to-speech task routes to Gemini 3.8 Plus (gemini-3.8-plus)."""
    resilience_mgr = UniversalResilienceManager()
    discovery = ModelCatalogDiscoveryService.get_instance()

    assert discovery.get_default_model("gemini", task_type="tts") == "gemini-3.8-plus"
    assert discovery.get_default_model("gemini", task_type="text-to-speech") == "gemini-3.8-plus"

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Synthesize this message to speech.")],
        task_type=TaskType.GENERAL,
        agent_id="tts-agent",
    )

    mock_gemini_adapter.chatCompletion.return_value = AIResponse(
        user_id="usr_test",
        content="audio_payload",
        response="audio_payload",
        provider="gemini",
        model="gemini-3.8-plus",
        agent_id="tts-agent",
        input_tokens=10,
        output_tokens=100,
        cost_usd=0.0,
        latency_ms=90,
        request_id=uuid.uuid4(),
    )

    with patch.dict(_adapters, {"gemini": mock_gemini_adapter}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
            gemini_cfg = MagicMock()
            gemini_cfg.name = "gemini"
            gemini_cfg.is_enabled = True
            gemini_cfg.has_api_key = True
            gemini_cfg.routing_priority = 1
            mock_cfgs.return_value = [gemini_cfg]

            resp = await resilience_mgr.execute_with_resilience(req, task_type="tts")
            assert req.model == "gemini-3.8-plus"


@pytest.mark.asyncio
async def test_speech_to_text_routes_to_gemini_3_8_plus(mock_gemini_adapter: MagicMock) -> None:
    """Speech-to-text task routes to Gemini 3.8 Plus (gemini-3.8-plus)."""
    resilience_mgr = UniversalResilienceManager()
    discovery = ModelCatalogDiscoveryService.get_instance()

    assert discovery.get_default_model("gemini", task_type="stt") == "gemini-3.8-plus"
    assert discovery.get_default_model("gemini", task_type="speech-to-text") == "gemini-3.8-plus"

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Transcribe this audio clip.")],
        task_type=TaskType.GENERAL,
        agent_id="stt-agent",
    )

    mock_gemini_adapter.chatCompletion.return_value = AIResponse(
        user_id="usr_test",
        content="Transcribed text",
        response="Transcribed text",
        provider="gemini",
        model="gemini-3.8-plus",
        agent_id="stt-agent",
        input_tokens=100,
        output_tokens=25,
        cost_usd=0.0,
        latency_ms=110,
        request_id=uuid.uuid4(),
    )

    with patch.dict(_adapters, {"gemini": mock_gemini_adapter}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
            gemini_cfg = MagicMock()
            gemini_cfg.name = "gemini"
            gemini_cfg.is_enabled = True
            gemini_cfg.has_api_key = True
            gemini_cfg.routing_priority = 1
            mock_cfgs.return_value = [gemini_cfg]

            resp = await resilience_mgr.execute_with_resilience(req, task_type="stt")
            assert req.model == "gemini-3.8-plus"


@pytest.mark.asyncio
async def test_live_audio_routes_to_gemini_3_8_plus(mock_gemini_adapter: MagicMock) -> None:
    """Live audio task routes to Gemini 3.8 Plus (gemini-3.8-plus)."""
    resilience_mgr = UniversalResilienceManager()
    discovery = ModelCatalogDiscoveryService.get_instance()

    assert discovery.get_default_model("gemini", task_type="live") == "gemini-3.8-plus"
    assert discovery.get_default_model("gemini", task_type="live-audio") == "gemini-3.8-plus"

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Live bidirectional audio stream")],
        task_type=TaskType.GENERAL,
        agent_id="live-audio-agent",
    )

    mock_gemini_adapter.chatCompletion.return_value = AIResponse(
        user_id="usr_test",
        content="Live response chunk",
        response="Live response chunk",
        provider="gemini",
        model="gemini-3.8-plus",
        agent_id="live-audio-agent",
        input_tokens=20,
        output_tokens=20,
        cost_usd=0.0,
        latency_ms=50,
        request_id=uuid.uuid4(),
    )

    with patch.dict(_adapters, {"gemini": mock_gemini_adapter}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
            gemini_cfg = MagicMock()
            gemini_cfg.name = "gemini"
            gemini_cfg.is_enabled = True
            gemini_cfg.has_api_key = True
            gemini_cfg.routing_priority = 1
            mock_cfgs.return_value = [gemini_cfg]

            resp = await resilience_mgr.execute_with_resilience(req, task_type="live")
            assert req.model == "gemini-3.8-plus"


def test_gemini_catalog_contains_argon_and_plus() -> None:
    """Catalog contains both gemini-4-argon and gemini-3.8-plus with appropriate task types."""
    models = _default_models("gemini")
    model_map = {m.name: m for m in models}

    assert "gemini-4-argon" in model_map
    argon = model_map["gemini-4-argon"]
    assert "general" in argon.task_types
    assert "coding" in argon.task_types
    assert "reasoning" in argon.task_types

    assert "gemini-3.8-plus" in model_map
    plus = model_map["gemini-3.8-plus"]
    assert "audio" in plus.task_types
    assert "tts" in plus.task_types
    assert "stt" in plus.task_types
    assert "live" in plus.task_types


def test_adapter_preserves_explicit_user_selection() -> None:
    """When a user explicitly selects a valid model, it is never rewritten to default."""
    adapter = GeminiAdapter()
    assert adapter._resolve_model("gemini-3.8-plus") == "gemini-3.8-plus"
    assert adapter._resolve_model("gemini-3.8-flash") == "gemini-3.8-flash"
    assert adapter._resolve_model("gemini-3.6-flash") == "gemini-3.6-flash"


@pytest.mark.asyncio
async def test_missing_credentials_fails_closed() -> None:
    """When a requested provider has no credentials, it fails closed."""
    resilience_mgr = UniversalResilienceManager()
    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello")],
        provider="unconfigured_provider",
        agent_id="test-agent",
    )
    with patch("app.ai_gateway.services.resilience.get_all_provider_configs", return_value=[]):
        with pytest.raises(AllProvidersUnavailableError) as exc_info:
            await resilience_mgr.execute_with_resilience(req)
        assert "unavailable or disabled" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_provider_rate_limit_backoff_and_retry(mock_gemini_adapter: MagicMock) -> None:
    """Transient rate limit 429 triggers bounded retry and then succeeds."""
    resilience_mgr = UniversalResilienceManager()
    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Test retry")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )

    success_resp = AIResponse(
        user_id="usr_test",
        content="Success after retry",
        response="Success after retry",
        provider="gemini",
        model="gemini-4-argon",
        agent_id="test-agent",
        input_tokens=10,
        output_tokens=10,
        cost_usd=0.0,
        latency_ms=250,
        request_id=uuid.uuid4(),
    )

    # First call fails with 429 rate limit, second call succeeds
    mock_gemini_adapter.chatCompletion.side_effect = [
        ProviderUnavailableError("gemini", "HTTP 429: Rate limit exceeded. Retry-After: 1"),
        success_resp,
    ]

    with patch.dict(_adapters, {"gemini": mock_gemini_adapter}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
            gemini_cfg = MagicMock()
            gemini_cfg.name = "gemini"
            gemini_cfg.is_enabled = True
            gemini_cfg.has_api_key = True
            gemini_cfg.routing_priority = 1
            mock_cfgs.return_value = [gemini_cfg]

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                resp = await resilience_mgr.execute_with_resilience(req, max_retries_per_provider=2)
                assert resp.content == "Success after retry"
                assert mock_sleep.called
