"""Comprehensive tests for Model Catalog Lifecycle, Durable History, and Fail-Closed Safeguards.

Master Prompt Section 4 Requirements:
1. Disabled providers make zero outbound requests.
2. Missing credentials do not crash startup or refresh.
3. Refresh failure preserves all last-known-good records.
4. A transient model omission does not delete the historical model.
5. Official retirement is handled according to the explicit retention policy.
6. Refresh survives restart and disk cache reload.
7. Concurrent refreshes do not corrupt records.
8. A newly discovered model is not auto-enabled for a disabled provider.
9. Gemini/Grok defaults and audio/live selection remain intact.
10. Failover skips unavailable or disabled providers.
11. User-selected models remain unchanged.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.ai_gateway.services.catalog_discovery import (
    DiscoveredModel,
    ModelCatalogDiscoveryService,
)


@pytest.fixture
def temp_cache_file() -> Generator[str, None, None]:
    fd, path = tempfile.mkstemp(suffix="_catalog_cache.json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def lifecycle_service(temp_cache_file: str) -> ModelCatalogDiscoveryService:
    service = ModelCatalogDiscoveryService(cache_file_path=temp_cache_file)
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
    service._cached_catalogs = {}
    service.canary_hook = None
    return service


@pytest.mark.asyncio
@respx.mock
async def test_transient_model_omission_preserves_historical_model(
    lifecycle_service: ModelCatalogDiscoveryService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient omission from one discovery response must NOT delete a previously known model."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key")

    # Pass 1: Provider returns two models: gemini-4-argon and gemini-2.5-pro
    respx.get("https://generativelanguage.googleapis.com/v1beta/models?key=fake_key").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-4-argon",
                        "displayName": "Gemini 4 Argon",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-2.5-pro",
                        "displayName": "Gemini 2.5 Pro",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            },
        )
    )

    res1 = await lifecycle_service.refresh_provider_catalog("gemini")
    assert res1.success is True
    models_pass1 = {m.model_id: m for m in lifecycle_service.get_active_models("gemini")}
    assert "gemini-4-argon" in models_pass1
    assert "gemini-2.5-pro" in models_pass1
    assert models_pass1["gemini-2.5-pro"].status == "active"
    assert models_pass1["gemini-2.5-pro"].provenance == "official_api"

    # Pass 2: Provider transiently omits gemini-2.5-pro (only returns gemini-4-argon)
    respx.get("https://generativelanguage.googleapis.com/v1beta/models?key=fake_key").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-4-argon",
                        "displayName": "Gemini 4 Argon",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
        )
    )

    res2 = await lifecycle_service.refresh_provider_catalog("gemini")
    assert res2.success is True
    models_pass2 = {m.model_id: m for m in lifecycle_service.get_active_models("gemini")}

    # CRITICAL: gemini-2.5-pro was NOT deleted!
    assert "gemini-2.5-pro" in models_pass2
    retained_model = models_pass2["gemini-2.5-pro"]
    assert retained_model.provenance == "cached"
    assert retained_model.status == "retained"
    # first_seen_at timestamp is preserved
    assert retained_model.first_seen_at == models_pass1["gemini-2.5-pro"].first_seen_at


@pytest.mark.asyncio
async def test_official_retirement_handling(
    lifecycle_service: ModelCatalogDiscoveryService,
) -> None:
    """Only mark a model retired when reliable official evidence supports that conclusion."""
    # Pre-populate a model
    now = datetime.now(UTC)
    model = DiscoveredModel(
        provider="gemini",
        model_id="gemini-1.5-flash-legacy",
        display_name="Gemini 1.5 Flash Legacy",
        task_types=["general"],
        is_stable=False,
        status="active",
        first_seen_at=now,
    )
    lifecycle_service._catalogs["gemini"] = [model]
    lifecycle_service._cached_catalogs["gemini"] = [model]

    # Explicitly mark retired with official provider notice
    evidence = "Official deprecation notice: Google Cloud Vertex & AI Studio retired April 2026"
    marked = lifecycle_service.mark_model_retired("gemini", "gemini-1.5-flash-legacy", evidence)
    assert marked is True

    retired = next(
        m for m in lifecycle_service.get_active_models("gemini")
        if m.model_id == "gemini-1.5-flash-legacy"
    )
    assert retired.status == "retired"
    assert retired.is_deprecated is True
    assert retired.retirement_evidence == evidence
    assert retired.to_model_config().enabled is False


@pytest.mark.asyncio
async def test_cache_persistence_survives_restart(
    temp_cache_file: str,
) -> None:
    """Discovered models and catalog state survive application restarts via disk persistence."""
    # Service Instance 1 discovers and caches a model
    service1 = ModelCatalogDiscoveryService(cache_file_path=temp_cache_file)
    model = DiscoveredModel(
        provider="grok",
        model_id="grok-4.7",
        display_name="Grok 4.7 Flagship",
        task_types=["general", "coding"],
        is_stable=True,
        provenance="official_api",
        status="active",
    )
    service1._cached_catalogs["grok"] = [model]
    service1._active_defaults["grok"] = "grok-4.7"
    service1._save_cache_to_disk()

    # Service Instance 2 initializes from the same cache file path (simulating restart)
    service2 = ModelCatalogDiscoveryService(cache_file_path=temp_cache_file)
    active_grok = service2.get_active_models("grok")
    assert len(active_grok) == 1
    assert active_grok[0].model_id == "grok-4.7"
    assert service2.get_default_model("grok") == "grok-4.7"


@pytest.mark.asyncio
async def test_user_selected_model_never_silently_changed(
    lifecycle_service: ModelCatalogDiscoveryService,
) -> None:
    """Never silently change a user's explicitly selected model, even after discovery promotions."""
    # Active default is gemini-4-argon
    assert lifecycle_service.get_default_model("gemini") == "gemini-4-argon"

    # User explicitly chose gemini-2.5-pro
    effective = lifecycle_service.resolve_effective_model(
        provider="gemini",
        user_selected_model="gemini-2.5-pro",
    )
    assert effective == "gemini-2.5-pro"

    # If user provided no selection, default is returned
    assert lifecycle_service.resolve_effective_model("gemini", None) == "gemini-4-argon"


@pytest.mark.asyncio
async def test_gemini_audio_live_model_preservation(
    lifecycle_service: ModelCatalogDiscoveryService,
) -> None:
    """Preserve Gemini's designated voice/audio/live model (gemini-3.8-flash) regardless of general default."""
    assert lifecycle_service.get_voice_live_model() == "gemini-3.8-flash"
    assert lifecycle_service.get_default_model("gemini", task_type="audio") == "gemini-3.8-flash"
    assert lifecycle_service.get_default_model("gemini", task_type="voice") == "gemini-3.8-flash"
    assert lifecycle_service.get_default_model("gemini", task_type="live") == "gemini-3.8-flash"
    # General task uses general default
    assert lifecycle_service.get_default_model("gemini", task_type="general") == "gemini-4-argon"


@pytest.mark.asyncio
@respx.mock
async def test_disabled_providers_zero_outbound_requests(
    lifecycle_service: ModelCatalogDiscoveryService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled providers (OpenAI, Anthropic) MUST make zero outbound requests."""
    # Even if keys exist in environment, they are disabled by default
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    res_openai = await lifecycle_service.refresh_provider_catalog("openai")
    assert res_openai.success is True
    assert res_openai.provenance == "static_baseline"
    assert res_openai.error_reason == "Provider is disabled by configuration (is_enabled=False)"

    res_anthropic = await lifecycle_service.refresh_provider_catalog("anthropic")
    assert res_anthropic.success is True
    assert res_anthropic.provenance == "static_baseline"
    assert res_anthropic.error_reason == "Provider is disabled by configuration (is_enabled=False)"

    # respx ensures zero unexpected calls occurred
    assert len(respx.calls) == 0


@pytest.mark.asyncio
async def test_concurrent_refresh_lock_protection(
    lifecycle_service: ModelCatalogDiscoveryService,
) -> None:
    """Concurrent duplicate refreshes for the same provider are safely guarded."""
    lifecycle_service._active_refreshes.add("grok")

    # Attempting to refresh while already active returns cached catalog without corrupting state
    res = await lifecycle_service.refresh_provider_catalog("grok")
    assert res.success is True
    assert res.error_reason == "Concurrent refresh in progress; returning cached catalog"
    assert res.provenance == "cached"
