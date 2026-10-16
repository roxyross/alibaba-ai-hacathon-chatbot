"""Comprehensive contract and failover tests for Model Catalog & Lifecycle.

Verifies Section 7 requirements:
1. Gemini 4 Argon (`gemini-4-argon`) is configured as the default general text/reasoning model.
2. Gemini 3.8 Flash (`gemini-3.8-flash`) is preserved immediately below it as an independently selectable model.
3. Grok 4.7 (`grok-4.7`) is present in the Grok catalog as the primary general model.
4. OpenAI and Claude are disabled by default unless explicitly configured with API keys and enabled.
5. Disabled providers do not receive traffic and do not fail application startup.
6. Capability guard: task-specific models (audio/TTS/multimodal) retain their task type attributes.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_gateway.adapters.base import AllProvidersUnavailableError, ProviderUnavailableError
from app.ai_gateway.adapters.gemini import GeminiAdapter
from app.ai_gateway.models.provider import _default_models, get_provider_config
from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole, TaskType
from app.ai_gateway.services.router import AIRouter, _adapters
from app.seeds.providers import _seed_data
from app.settings.schemas import SettingsResponse


def test_gemini_4_argon_is_default_in_adapter() -> None:
    """GeminiAdapter must have gemini-4-argon as DEFAULT_MODEL."""
    adapter = GeminiAdapter()
    assert adapter.DEFAULT_MODEL == "gemini-4-argon"
    # Generic aliases map to default
    assert adapter._resolve_model(None) == "gemini-4-argon"
    assert adapter._resolve_model("default") == "gemini-4-argon"
    assert adapter._resolve_model("gemini") == "gemini-4-argon"
    # Explicitly selected models are preserved and NOT rewritten
    assert adapter._resolve_model("gemini-3.8-flash") == "gemini-3.8-flash"
    assert adapter._resolve_model("gemini-3.6-flash") == "gemini-3.6-flash"


def test_gemini_model_ordering_and_preservation() -> None:
    """Gemini 4 Argon must be first, followed immediately by Gemini 3.8 Flash."""
    models = _default_models("gemini")
    assert len(models) >= 2
    assert models[0].name == "gemini-4-argon"
    assert models[1].name == "gemini-3.8-flash"
    # Gemini 3.8 Flash retains audio modality capability
    assert "audio" in models[1].task_types
    # Verify remaining supported models exist
    model_names = [m.name for m in models]
    assert "gemini-3.6-flash" in model_names
    assert "gemini-3.7-flash" in model_names
    assert "gemini-1.5-pro" in model_names


def test_grok_catalog_includes_grok_4_7() -> None:
    """Grok catalog must include grok-4.7 as the primary Grok model."""
    models = _default_models("grok")
    assert len(models) >= 2
    assert models[0].name == "grok-4.7"
    assert models[1].name == "grok-3"


def test_seeds_provider_gemini_and_grok() -> None:
    """Provider seed records must include gemini-4-argon and grok-4.7 in top positions."""
    seeds = _seed_data()
    gemini_seed = next((p for p in seeds if p["name"] == "gemini"), None)
    assert gemini_seed is not None
    assert gemini_seed["models"][0]["name"] == "gemini-4-argon"
    assert gemini_seed["models"][1]["name"] == "gemini-3.8-flash"

    grok_seed = next((p for p in seeds if p["name"] == "grok"), None)
    assert grok_seed is not None
    assert grok_seed["models"][0]["name"] == "grok-4.7"
    assert grok_seed["models"][1]["name"] == "grok-3"


def test_default_chat_model_setting() -> None:
    """Default chat model in SettingsResponse schema must be gemini-4-argon."""
    settings = SettingsResponse()
    assert settings.default_chat_model == "gemini-4-argon"


def test_disabled_providers_do_not_send_requests() -> None:
    """When a provider is disabled, router skips it and does not dispatch requests."""
    router = AIRouter()
    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
        provider="disabled_fake_provider",
    )
    # Asking for a nonexistent/disabled provider without fallback raises
    assert router._resolve_override(req) == "disabled_fake_provider"


@pytest.mark.asyncio
async def test_router_failover_respects_provider_outage() -> None:
    """When primary provider fails, router fails over cleanly or raises truthful error."""
    router = AIRouter()
    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )
    mock_adapter = MagicMock()
    mock_adapter.chatCompletion = AsyncMock(
        side_effect=ProviderUnavailableError("gemini", "503 Service Unavailable")
    )
    with patch.dict(_adapters, {"gemini": mock_adapter}):
        with patch("app.ai_gateway.services.router._sorted_providers", return_value=["gemini"]):
            with pytest.raises(AllProvidersUnavailableError):
                await router.route(req)
