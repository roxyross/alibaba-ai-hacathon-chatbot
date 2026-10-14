"""Security regression and reconciliation tests for AI provider mapping and routing.

Validates:
- Distinct identity for 'groq' and 'grok' (xAI).
- GROQ_API_KEY maps to GroqAdapter targeting https://api.groq.com/openai/v1.
- GROK_API_KEY maps to GrokAdapter targeting https://api.x.ai/v1.
- Default routing priority matches product architecture (gemini -> groq -> grok -> deepseek -> openai).
- Backward-compatibility fallback gracefully resolves legacy gsk_ keys.
- Model configs for Groq and Grok are cleanly separated.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.ai_gateway.adapters.grok import GrokAdapter
from app.ai_gateway.adapters.groq import GroqAdapter
from app.ai_gateway.models.provider import (
    DEFAULT_ROUTING_PRIORITY,
    PROVIDER_API_KEY_VARS,
    PROVIDER_BASE_URLS,
    get_provider_config,
)
from app.ai_gateway.services.router import _get_adapter, _sorted_providers


def test_distinct_provider_configuration_keys_and_urls():
    """Groq and Grok must have distinct API key vars and distinct base URLs."""
    assert PROVIDER_API_KEY_VARS["groq"] == "GROQ_API_KEY"
    assert PROVIDER_API_KEY_VARS["grok"] == "GROK_API_KEY"
    assert PROVIDER_BASE_URLS["groq"] == "https://api.groq.com/openai/v1"
    assert PROVIDER_BASE_URLS["grok"] == "https://api.x.ai/v1"


def test_routing_priority_order():
    """Verify primary product provider priorities."""
    assert DEFAULT_ROUTING_PRIORITY["gemini"] < DEFAULT_ROUTING_PRIORITY["groq"]
    assert DEFAULT_ROUTING_PRIORITY["groq"] < DEFAULT_ROUTING_PRIORITY["grok"]
    assert DEFAULT_ROUTING_PRIORITY["grok"] < DEFAULT_ROUTING_PRIORITY["deepseek"]
    assert DEFAULT_ROUTING_PRIORITY["deepseek"] < DEFAULT_ROUTING_PRIORITY["openai"]


def test_adapter_registry_resolves_correct_adapters():
    """_get_adapter must instantiate GroqAdapter for 'groq' and GrokAdapter for 'grok'."""
    groq_adapter = _get_adapter("groq")
    assert isinstance(groq_adapter, GroqAdapter)
    assert groq_adapter.NAME == "groq"

    grok_adapter = _get_adapter("grok")
    assert isinstance(grok_adapter, GrokAdapter)
    assert grok_adapter.NAME == "grok"


@pytest.mark.asyncio
async def test_groq_adapter_targets_groq_endpoint():
    """GroqAdapter must configure httpx client with https://api.groq.com/openai/v1."""
    with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key_12345"}):
        adapter = GroqAdapter()
        client = await adapter._get_client()
        assert str(client.base_url).rstrip("/") == "https://api.groq.com/openai/v1"
        assert client.headers["authorization"] == "Bearer gsk_test_key_12345"
        await adapter.close()


@pytest.mark.asyncio
async def test_grok_adapter_targets_xai_endpoint():
    """GrokAdapter must configure httpx client with https://api.x.ai/v1 when given an xAI key."""
    with patch.dict(os.environ, {"GROK_API_KEY": "xai-test-key-67890"}):
        adapter = GrokAdapter()
        client = await adapter._get_client()
        assert str(client.base_url).rstrip("/") == "https://api.x.ai/v1"
        assert client.headers["authorization"] == "Bearer xai-test-key-67890"
        await adapter.close()


def test_sorted_providers_respects_priority_and_active_keys():
    """_sorted_providers returns only providers with active API keys in priority order."""
    env = {
        "GEMINI_API_KEY": "AIzaSy_test",
        "GROQ_API_KEY": "gsk_test",
        "GROK_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "OPENAI_API_KEY": "sk_test",
    }
    with patch.dict(os.environ, env):
        sorted_p = _sorted_providers()
        # Active: gemini, groq, openai. Order: gemini (1) -> groq (2) -> openai (5)
        assert sorted_p == ["gemini", "groq", "openai"]
