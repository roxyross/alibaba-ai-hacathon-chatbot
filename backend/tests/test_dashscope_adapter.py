"""Tests for Alibaba DashScope (Qwen) adapter and router integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_gateway.adapters.base import ProviderUnavailableError
from app.ai_gateway.adapters.dashscope import DashScopeAdapter
from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole
from app.ai_gateway.services.router import _get_adapter


@pytest.fixture(autouse=True)
def mock_dashscope_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-mock-dashscope-key-12345")
    monkeypatch.setenv("PROVIDER_DASHSCOPE_ENABLED", "true")


def test_router_get_adapter_dashscope() -> None:
    """Verify router lazily instantiates DashScopeAdapter for aliases."""
    adapter1 = _get_adapter("dashscope")
    assert isinstance(adapter1, DashScopeAdapter)
    assert adapter1.provider_name == "dashscope"

    adapter2 = _get_adapter("qwen")
    assert isinstance(adapter2, DashScopeAdapter)

    adapter3 = _get_adapter("alibaba")
    assert isinstance(adapter3, DashScopeAdapter)


def test_dashscope_payload_building() -> None:
    """Test standard OpenAI-compatible payload format for DashScope."""
    adapter = DashScopeAdapter()
    req = AIRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            Message(role=MessageRole.USER, content="Hello Qwen!"),
        ],
        model="qwen-max",
        temperature=0.8,
        max_tokens=2048,
    )
    payload = adapter._build_payload(req, stream=False)
    assert payload["model"] == "qwen-max"
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "Hello Qwen!"
    assert payload["temperature"] == 0.8
    assert payload["max_tokens"] == 2048
    assert payload["stream"] is False


def test_dashscope_parse_response() -> None:
    """Test parsing of DashScope completion JSON."""
    adapter = DashScopeAdapter()
    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Explain quantum computing")],
        model="qwen-plus",
    )
    raw = {
        "id": "chatcmpl-qwen-123",
        "model": "qwen-plus",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Quantum computing uses qubits."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 15, "completion_tokens": 30, "total_tokens": 45},
    }
    resp = adapter._parse_response(raw, req, latency_ms=120)
    assert resp.provider == "dashscope"
    assert resp.model == "qwen-plus"
    assert resp.content == "Quantum computing uses qubits."
    assert resp.input_tokens == 15
    assert resp.output_tokens == 30
    assert resp.latency_ms == 120
    assert resp.cost_usd > 0.0


@pytest.mark.asyncio
async def test_dashscope_completion_success() -> None:
    """Mock HTTP call and verify complete flow."""
    adapter = DashScopeAdapter()
    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hi")],
        model="qwen-turbo",
    )
    mock_json = {
        "model": "qwen-turbo",
        "choices": [{"message": {"content": "Hello from Qwen!"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10},
    }

    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_resp.json.return_value = mock_json

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        response = await adapter.chatCompletion(req)
        assert response.content == "Hello from Qwen!"
        assert response.provider == "dashscope"
        assert response.model == "qwen-turbo"


@pytest.mark.asyncio
async def test_dashscope_error_handling() -> None:
    """Verify ProviderUnavailableError raised on HTTP error status."""
    adapter = DashScopeAdapter()
    req = AIRequest(messages=[Message(role=MessageRole.USER, content="Hi")])

    mock_resp = MagicMock()
    mock_resp.is_success = False
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await adapter.chatCompletion(req)
        assert "429" in str(exc_info.value)
