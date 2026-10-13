"""Phase 5.1 Regression Tests: Gemini 3.8 Flash default, Gemini/Grok preservation, routing & error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_gateway.adapters.base import ProviderUnavailableError
from app.ai_gateway.adapters.gemini import GeminiAdapter
from app.ai_gateway.models.provider import _default_models
from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole
from app.ai_gateway.services.router import AIRouter
from app.model_provider.router import list_models
from app.models.subscription import UsageLog
from app.settings.schemas import SettingsResponse

# -----------------------------------------------------------------------------
# 1. Baseline Model Inventories (Ground Truth)
# -----------------------------------------------------------------------------

BASELINE_GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.1-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

BASELINE_GROK_MODELS = [
    "grok-3",
    "grok-3-mini",
    "grok-2",
    "grok-2-vision-1212",
    "grok-beta",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
]


# -----------------------------------------------------------------------------
# 2. Gemini Catalog & Defaults
# -----------------------------------------------------------------------------

class TestGeminiCatalogAndDefaults:
    """Verify gemini-3.8-flash default, gemini-3.6-flash preservation, and model resolution."""

    def test_gemini_38_is_default_model_in_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        assert adapter.DEFAULT_MODEL == "gemini-3.8-flash"
        assert adapter._resolve_model(None) == "gemini-3.8-flash"
        assert adapter._resolve_model("") == "gemini-3.8-flash"

    def test_gemini_36_is_preserved_and_not_rewritten(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        # Selecting gemini-3.6-flash must NOT be rewritten to gemini-3.8-flash
        assert adapter._resolve_model("gemini-3.6-flash") == "gemini-3.6-flash"
        assert adapter._resolve_model("gemini/gemini-3.6-flash") == "gemini-3.6-flash"

    def test_gemini_38_resolves_directly_without_mangling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        assert adapter._resolve_model("gemini-3.8-flash") == "gemini-3.8-flash"
        assert adapter._resolve_model("gemini/gemini-3.8-flash") == "gemini-3.8-flash"

    def test_all_baseline_gemini_models_preserved_in_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        for model_id in BASELINE_GEMINI_MODELS:
            resolved = adapter._resolve_model(model_id)
            assert resolved == model_id, f"Model {model_id} was improperly mutated to {resolved}"

    def test_all_baseline_gemini_models_present_in_provider_config(self) -> None:
        models = _default_models("gemini")
        model_names = [m.name for m in models]

        for expected in BASELINE_GEMINI_MODELS:
            assert expected in model_names, f"Missing Gemini model {expected} in provider config"

        # gemini-3.8-flash must be the first model in the list
        assert model_names[0] == "gemini-3.8-flash"
        # gemini-3.6-flash must be the second model in the list
        assert model_names[1] == "gemini-3.6-flash"

    @pytest.mark.asyncio
    async def test_all_baseline_gemini_models_present_in_models_api(self) -> None:
        response = await list_models()
        gemini_provider = next((p for p in response.providers if p.name == "gemini"), None)
        assert gemini_provider is not None
        api_model_names = [m.name for m in gemini_provider.models]

        for expected in BASELINE_GEMINI_MODELS:
            assert expected in api_model_names, f"Missing Gemini model {expected} in GET /models API"

        # Default model is first
        assert api_model_names[0] == "gemini-3.8-flash"

    def test_generic_aliases_map_to_default_without_clobbering(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        assert adapter._resolve_model("gemini-flash") == "gemini-3.8-flash"
        assert adapter._resolve_model("gemini") == "gemini-3.8-flash"
        assert adapter._resolve_model("default") == "gemini-3.8-flash"
        assert adapter._resolve_model("auto") == "gemini-3.8-flash"

        # Legitimate models are never clobbered
        assert adapter._resolve_model("gemini-2.0-flash") == "gemini-2.0-flash"
        assert adapter._resolve_model("gemini-1.5-pro") == "gemini-1.5-pro"

    def test_settings_and_subscription_defaults_align_with_gemini_38(self) -> None:
        settings = SettingsResponse()
        assert settings.default_chat_model == "gemini-3.8-flash"

        column_default = UsageLog.__table__.columns["model"].default.arg
        assert column_default == "gemini-3.8-flash"


# -----------------------------------------------------------------------------
# 3. Grok Preservation & Isolation
# -----------------------------------------------------------------------------

class TestGrokPreservation:
    """Verify that every Grok model is preserved and isolated from Gemini."""

    def test_all_baseline_grok_models_present_in_provider_config(self) -> None:
        models = _default_models("grok")
        model_names = [m.name for m in models]

        for expected in BASELINE_GROK_MODELS:
            assert expected in model_names, f"Missing Grok model {expected} in provider config"

    @pytest.mark.asyncio
    async def test_all_baseline_grok_models_present_in_models_api(self) -> None:
        response = await list_models()
        grok_provider = next((p for p in response.providers if p.name == "grok"), None)
        assert grok_provider is not None
        api_model_names = [m.name for m in grok_provider.models]

        for expected in BASELINE_GROK_MODELS:
            assert expected in api_model_names, f"Missing Grok model {expected} in GET /models API"

    def test_grok_requests_never_route_to_gemini(self) -> None:
        router = AIRouter()

        # Explicit provider override
        req_prov = AIRequest(
            messages=[Message(role=MessageRole.USER, content="hi")],
            provider="grok",
            model="grok-3",
        )
        assert router._resolve_override(req_prov) == "grok"

        # Model-inferred provider routing
        for grok_model in ["grok-3", "grok-3-mini", "grok-2", "grok-beta", "qwen/qwen3.8-27b"]:
            req_model = AIRequest(
                messages=[Message(role=MessageRole.USER, content="hi")],
                model=grok_model,
            )
            resolved = router._resolve_override(req_model)
            assert resolved == "grok", f"Model {grok_model} incorrectly routed to {resolved}"
            assert resolved != "gemini", f"Model {grok_model} illegally routed to gemini"

    def test_gemini_requests_never_route_to_grok(self) -> None:
        router = AIRouter()

        for gemini_model in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.0-flash"]:
            req_model = AIRequest(
                messages=[Message(role=MessageRole.USER, content="hi")],
                model=gemini_model,
            )
            resolved = router._resolve_override(req_model)
            assert resolved == "gemini", f"Model {gemini_model} incorrectly routed to {resolved}"
            assert resolved != "grok", f"Model {gemini_model} illegally routed to grok"


# -----------------------------------------------------------------------------
# 4. Routing, Endpoints, and Honest Error Handling
# -----------------------------------------------------------------------------

class TestRoutingAndErrorHandling:
    """Verify endpoint calls, error propagation, and fallback attribution."""

    @pytest.mark.asyncio
    async def test_gemini_38_request_reaches_provider_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini 3.8 response"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 10},
        }
        mock_client.post.return_value = mock_resp

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            req = AIRequest(
                messages=[Message(role=MessageRole.USER, content="Hello")],
                model="gemini-3.8-flash",
                user_id="u1",
            )
            res = await adapter.chatCompletion(req)

        assert res.model == "gemini-3.8-flash"
        assert res.provider == "gemini"
        assert res.content == "Gemini 3.8 response"

        # Check the POST URL received gemini-3.8-flash
        called_url = mock_client.post.call_args[0][0]
        assert "gemini-3.8-flash:generateContent" in called_url

    @pytest.mark.asyncio
    async def test_gemini_36_request_reaches_provider_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini 3.6 response"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 10},
        }
        mock_client.post.return_value = mock_resp

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            req = AIRequest(
                messages=[Message(role=MessageRole.USER, content="Hello")],
                model="gemini-3.6-flash",
                user_id="u1",
            )
            res = await adapter.chatCompletion(req)

        assert res.model == "gemini-3.6-flash"
        assert res.provider == "gemini"
        assert res.content == "Gemini 3.6 response"

        # Check the POST URL received gemini-3.6-flash
        called_url = mock_client.post.call_args[0][0]
        assert "gemini-3.6-flash:generateContent" in called_url

    @pytest.mark.asyncio
    async def test_missing_gemini_api_key_raises_honest_configuration_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        adapter = GeminiAdapter()

        req = AIRequest(
            messages=[Message(role=MessageRole.USER, content="Hello")],
            model="gemini-3.8-flash",
        )

        with pytest.raises(ProviderUnavailableError) as exc_info:
            await adapter.chatCompletion(req)

        assert "API key env var 'GEMINI_API_KEY' not set" in str(exc_info.value)
        assert exc_info.value.provider == "gemini"

    @pytest.mark.asyncio
    async def test_fallback_is_explicitly_logged_and_attributed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        adapter = GeminiAdapter()

        mock_client = AsyncMock()

        # Primary call fails with 404 (model not found)
        primary_fail_resp = MagicMock()
        primary_fail_resp.is_success = False
        primary_fail_resp.status_code = 404
        primary_fail_resp.text = "Model not found"

        # Fallback call succeeds
        fallback_ok_resp = MagicMock()
        fallback_ok_resp.is_success = True
        fallback_ok_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Fallback response from default"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 10},
        }

        mock_client.post.side_effect = [primary_fail_resp, fallback_ok_resp]

        with patch.object(adapter, "_get_client", AsyncMock(return_value=mock_client)):
            req = AIRequest(
                messages=[Message(role=MessageRole.USER, content="Hello")],
                model="gemini-3.7-flash",  # non-default model
                user_id="u1",
            )
            res = await adapter.chatCompletion(req)

        # Truthful attribution: model is attributed to gemini-3.8-flash (the default fallback that actually responded)
        assert res.model == "gemini-3.8-flash"
        assert res.content == "Fallback response from default"

        # Verify fallback called
        assert mock_client.post.call_count == 2
        first_call_url = mock_client.post.call_args_list[0][0][0]
        second_call_url = mock_client.post.call_args_list[1][0][0]
        assert "gemini-3.7-flash:generateContent" in first_call_url
        assert "gemini-3.8-flash:generateContent" in second_call_url
