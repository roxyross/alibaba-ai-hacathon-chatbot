"""Comprehensive tests for Automatic Model Catalog Discovery and Safe Promotion.

Verifies:
1. Google Gemini API model discovery with capability & supported method parsing.
2. xAI model discovery with official identifiers and Grok isolation.
3. Groq model discovery with Qwen/GPT-OSS/Llama models isolated under Groq.
4. OpenAI and Anthropic are disabled by default; discovery does not send outbound requests.
5. Deprecated/preview models are distinguished from stable GA models.
6. Safe canary validation: failed canary retains last known-good default and records reason.
7. Successful canary promotes the newest stable GA model and preserves previous default.
8. Voice/TTS/Live preservation: gemini-3.8-flash remains designated for audio/voice.
9. Startup/offline resilience: missing credentials or network errors fall back cleanly without crash.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.ai_gateway.models.provider import ProviderConfig
from app.ai_gateway.services.catalog_discovery import (
    CatalogSyncResult,
    DiscoveredModel,
    ModelCatalogDiscoveryService,
)


@pytest.fixture
def discovery_service() -> ModelCatalogDiscoveryService:
    service = ModelCatalogDiscoveryService()
    # Reset state
    service._active_defaults = {
        "gemini": "gemini-4-argon",
        "grok": "grok-4.7",
        "groq": "qwen/qwen3.8-27b",
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-latest",
    }
    service._previous_defaults = {
        "gemini": "gemini-3.8-flash",
        "grok": "grok-3",
        "groq": "llama-3.3-70b-versatile",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-latest",
    }
    service._catalogs = {}
    service.canary_hook = None
    return service


@pytest.mark.asyncio
@respx.mock
async def test_gemini_model_discovery_and_promotion(discovery_service: ModelCatalogDiscoveryService, monkeypatch) -> None:
    """Discovers models from Gemini API, identifies stable GA models, and promotes newest."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake_gemini_key")

    mock_gemini_response = {
        "models": [
            {
                "name": "models/gemini-5-pro",
                "displayName": "Gemini 5 Pro (Future GA Flagship)",
                "description": "Next generation general reasoning and coding",
                "supportedGenerationMethods": ["generateContent", "countTokens"],
                "inputTokenLimit": 2000000,
                "outputTokenLimit": 32768,
            },
            {
                "name": "models/gemini-4.5-flash-preview",
                "displayName": "Gemini 4.5 Flash Preview",
                "supportedGenerationMethods": ["generateContent"],
                "inputTokenLimit": 1000000,
                "outputTokenLimit": 8192,
            },
            {
                "name": "models/gemini-3.8-flash",
                "displayName": "Gemini 3.8 Flash (Multimodal Audio)",
                "supportedGenerationMethods": ["generateContent", "audioContent"],
                "inputTokenLimit": 1000000,
                "outputTokenLimit": 8192,
            },
            {
                "name": "models/text-embedding-004",
                "displayName": "Text Embedding",
                "supportedGenerationMethods": ["embedContent"],
            },
        ]
    }

    respx.get("https://generativelanguage.googleapis.com/v1beta/models?key=fake_gemini_key").mock(
        return_value=httpx.Response(200, json=mock_gemini_response)
    )

    # Allow canary to pass
    discovery_service.canary_hook = lambda prov, m_id: True

    result = await discovery_service.refresh_provider_catalog("gemini")
    assert result.success is True
    assert result.discovered_count == 3  # embedding model excluded

    # Future unknown model gemini-5-pro was promoted based on metadata and ranking rules
    assert result.promoted_default == "gemini-5-pro"
    # Previous default gemini-4-argon was preserved in rollback slot
    assert result.previous_default == "gemini-4-argon"

    # Audio/voice remains designated to gemini-3.8-flash
    assert discovery_service.get_default_model("gemini", task_type="audio") == "gemini-3.8-flash"


@pytest.mark.asyncio
@respx.mock
async def test_canary_failure_keeps_last_known_good_default(discovery_service: ModelCatalogDiscoveryService, monkeypatch) -> None:
    """If canary validation fails on a new model, previous default is kept and failure recorded."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake_gemini_key")

    mock_gemini_response = {
        "models": [
            {
                "name": "models/gemini-5-pro-unstable",
                "displayName": "Gemini 5 Pro Unstable",
                "supportedGenerationMethods": ["generateContent"],
                "inputTokenLimit": 2000000,
                "outputTokenLimit": 32768,
            },
        ]
    }

    respx.get("https://generativelanguage.googleapis.com/v1beta/models?key=fake_gemini_key").mock(
        return_value=httpx.Response(200, json=mock_gemini_response)
    )

    # Canary fails
    discovery_service.canary_hook = lambda prov, m_id: False

    result = await discovery_service.refresh_provider_catalog("gemini")
    assert result.success is True
    # Kept existing default
    assert result.promoted_default == "gemini-4-argon"
    assert discovery_service.get_default_model("gemini") == "gemini-4-argon"


@pytest.mark.asyncio
@respx.mock
async def test_grok_model_discovery_and_provider_isolation(discovery_service: ModelCatalogDiscoveryService, monkeypatch) -> None:
    """xAI endpoint only discovers native Grok models, never Qwen or GPT-OSS."""
    monkeypatch.setenv("GROK_API_KEY", "fake_xai_key")

    mock_xai_response = {
        "data": [
            {"id": "grok-4.7", "object": "model", "max_tokens": 131072},
            {"id": "grok-3", "object": "model", "max_tokens": 131072},
            {"id": "qwen/qwen-fake-injected", "object": "model"},  # Foreign model ID
        ]
    }

    respx.get("https://api.x.ai/v1/models").mock(
        return_value=httpx.Response(200, json=mock_xai_response)
    )

    result = await discovery_service.refresh_provider_catalog("grok")
    assert result.success is True
    # Foreign model excluded
    model_ids = [m.model_id for m in result.models]
    assert "grok-4.7" in model_ids
    assert "grok-3" in model_ids
    assert "qwen/qwen-fake-injected" not in model_ids


@pytest.mark.asyncio
@respx.mock
async def test_groq_model_discovery_excludes_deprecated(discovery_service: ModelCatalogDiscoveryService, monkeypatch) -> None:
    """Groq endpoint discovers active fast models and excludes deprecated or inactive models."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake_groq_key")

    mock_groq_response = {
        "data": [
            {"id": "qwen/qwen3.8-27b", "active": True, "context_window": 32768},
            {"id": "llama-3.3-70b-versatile", "active": True, "context_window": 32768},
            {"id": "deprecated-llama-2-70b", "active": False, "deprecated": True},
            {"id": "whisper-large-v3", "active": True},  # Audio-only
        ]
    }

    respx.get("https://api.groq.com/openai/v1/models").mock(
        return_value=httpx.Response(200, json=mock_groq_response)
    )

    result = await discovery_service.refresh_provider_catalog("groq")
    assert result.success is True
    model_ids = [m.model_id for m in result.models]
    assert "qwen/qwen3.8-27b" in model_ids
    assert "llama-3.3-70b-versatile" in model_ids
    assert "deprecated-llama-2-70b" not in model_ids
    assert "whisper-large-v3" not in model_ids


@pytest.mark.asyncio
async def test_disabled_providers_do_not_send_requests(discovery_service: ModelCatalogDiscoveryService, monkeypatch) -> None:
    """OpenAI and Anthropic remain disabled by default and make zero outbound requests."""
    # Even if environment variables exist, feature flags default to disabled
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")

    openai_res = await discovery_service.refresh_provider_catalog("openai")
    assert openai_res.success is True
    assert openai_res.live_verified is False
    assert "disabled" in openai_res.error_reason.lower()

    anthropic_res = await discovery_service.refresh_provider_catalog("anthropic")
    assert anthropic_res.success is True
    assert anthropic_res.live_verified is False
    assert "disabled" in anthropic_res.error_reason.lower()


@pytest.mark.asyncio
async def test_missing_credentials_fails_safe_without_crashing(discovery_service: ModelCatalogDiscoveryService, monkeypatch) -> None:
    """When credentials are not present, service falls back to static baseline without raising."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = await discovery_service.refresh_provider_catalog("gemini")
    assert result.success is True
    assert result.live_verified is False
    assert "not configured" in result.error_reason.lower()
    # Baseline defaults still returned safely
    active_models = discovery_service.get_active_models("gemini")
    assert len(active_models) > 0
    assert active_models[0].model_id == "gemini-4-argon"
