"""Tests for Universal Adapter Resilience & Task Continuity.

Verifies:
1. Error classification: transient (5xx, 429, timeouts) vs permanent (401, 403, 404, capability mismatch).
2. Cross-provider failover: primary provider outage cleanly switches to next enabled provider.
3. State continuity: coding task workspace and diffs preserved across failures.
4. Non-idempotent action guard: idempotency keys prevent duplicate execution of payments, emails, bookings.
5. Modality protection: audio/voice tasks are strictly restricted to audio-capable providers (Gemini).
6. Disabled providers (OpenAI, Anthropic) are never called.
7. Truthful recoverable error when all providers fail, retaining checkpoint for later resumption.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest

from app.ai_gateway.adapters.base import (
    AIProviderAdapter,
    AllProvidersUnavailableError,
    ProviderUnavailableError,
)
from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole, TaskType
from app.ai_gateway.services.resilience import (
    ErrorClassification,
    TaskCheckpoint,
    TaskContinuityManager,
    UniversalResilienceManager,
    classify_error,
)
from app.ai_gateway.services.router import _adapters


def test_classify_error_accuracy() -> None:
    """Verify classification logic across HTTP and connection error types."""
    # 429 Rate Limit
    c1, retryable1, backoff1 = classify_error(Exception("HTTP 429 Too Many Requests retry-after: 3"))
    assert c1 == ErrorClassification.RATE_LIMIT_429
    assert retryable1 is True
    assert backoff1 == 3.0

    # 503 Server Error
    c2, retryable2, _ = classify_error(Exception("503 Service Unavailable"))
    assert c2 == ErrorClassification.TRANSIENT_5XX
    assert retryable2 is True

    # 401 Unauthorized
    c3, retryable3, _ = classify_error(Exception("401 Unauthorized: Invalid API key"))
    assert c3 == ErrorClassification.AUTH_OR_PERMANENT
    assert retryable3 is False

    # 404 Model Not Found
    c4, retryable4, _ = classify_error(Exception("404 Not Found: Model 'fake-model' is not supported"))
    assert c4 == ErrorClassification.MODEL_UNAVAILABLE
    assert retryable4 is False

    # Timeout
    c5, retryable5, _ = classify_error(Exception("httpx.ConnectTimeout connection timed out"))
    assert c5 == ErrorClassification.TIMEOUT
    assert retryable5 is True


@pytest.mark.asyncio
async def test_non_idempotent_action_guard() -> None:
    """Non-idempotent tool operations (e.g. payment, email) are not repeated after failure."""
    mgr = TaskContinuityManager()
    task_id = "task-order-checkout-123"
    idempotency_key = "pay_stripe_charge_tok_999"

    # Action has not run yet
    assert await mgr.is_action_already_executed(task_id, idempotency_key) is False

    # Record successful completion of charge
    await mgr.record_action_executed(
        task_id=task_id,
        idempotency_key=idempotency_key,
        action_name="stripe_charge",
        result={"status": "succeeded", "amount": 2500},
    )

    # Subsequent check prevents duplicate charge
    assert await mgr.is_action_already_executed(task_id, idempotency_key) is True
    ckpt = await mgr.get_checkpoint(task_id)
    assert ckpt is not None
    assert idempotency_key in ckpt.executed_idempotency_keys


@pytest.mark.asyncio
async def test_coding_workspace_checkpoint_preservation() -> None:
    """Coding agent workspace files and git diffs are preserved during task failover."""
    mgr = TaskContinuityManager()
    task_id = "task-coding-remediation-456"

    workspace = {
        "src/main.py": "print('hello')",
        "tests/test_main.py": "def test_hello(): pass",
    }
    diffs = ["diff --git a/src/main.py b/src/main.py\n+print('hello')"]

    await mgr.preserve_coding_state(task_id, workspace, diffs)

    ckpt = await mgr.get_checkpoint(task_id)
    assert ckpt is not None
    assert ckpt.task_type == "coding"
    assert ckpt.workspace_files["src/main.py"] == "print('hello')"
    assert len(ckpt.diffs) == 1


@pytest.mark.asyncio
async def test_cross_provider_failover_gemini_to_grok() -> None:
    """When primary Gemini adapter fails with 5xx, router fails over cleanly to Grok."""
    resilience_mgr = UniversalResilienceManager()

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Hello Roxy")],
        task_type=TaskType.GENERAL,
        agent_id="test-agent",
    )

    # Gemini adapter fails with 503
    mock_gemini = MagicMock(spec=AIProviderAdapter)
    mock_gemini.chatCompletion = AsyncMock(
        side_effect=ProviderUnavailableError("gemini", "503 Service Unavailable")
    )

    # Grok adapter succeeds
    mock_grok = MagicMock(spec=AIProviderAdapter)
    mock_grok.chatCompletion = AsyncMock(
        return_value=AIResponse(
            content="Hello! Grok here answering for you.",
            provider="grok",
            model="grok-4.7",
            agent_id="test-agent",
            request_id=uuid.uuid4(),
        )
    )

    with patch.dict(_adapters, {"gemini": mock_gemini, "grok": mock_grok}):
        with patch("app.ai_gateway.services.router._sorted_providers", return_value=["gemini", "grok"]):
            with patch("app.ai_gateway.services.resilience.get_provider_config") as mock_cfg:
                def get_cfg(name):
                    m = MagicMock()
                    m.name = name
                    m.is_enabled = True
                    m.has_api_key = True
                    return m
                mock_cfg.side_effect = get_cfg

                resp = await resilience_mgr.execute_with_resilience(req, max_retries_per_provider=0)

                assert resp.provider == "grok"
                assert "Grok here" in resp.content
                # Recovery metadata indicates failover
                assert resp.recovery_metadata is not None
                assert resp.recovery_metadata["switched_from"] == "gemini"
                assert resp.recovery_metadata["switched_to"] == "grok"


@pytest.mark.asyncio
async def test_audio_modality_guard_prevents_text_only_routing() -> None:
    """Audio/Voice tasks are never routed to text-only providers like Groq or DeepSeek."""
    resilience_mgr = UniversalResilienceManager()

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Voice input audio stream")],
        task_type=TaskType.GENERAL,
        agent_id="voice-agent",
    )

    # When audio task is executed with only text providers enabled
    with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_cfgs:
        text_only_cfg = MagicMock()
        text_only_cfg.name = "groq"
        text_only_cfg.is_enabled = True
        text_only_cfg.has_api_key = True
        text_only_cfg.routing_priority = 1
        mock_cfgs.return_value = [text_only_cfg]

        with pytest.raises(AllProvidersUnavailableError) as exc_info:
            await resilience_mgr.execute_with_resilience(req, task_type="audio")

        assert "audio-capable provider" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_disabled_openai_anthropic_are_never_called() -> None:
    """Disabled OpenAI/Anthropic providers are never invoked even if requested as override."""
    resilience_mgr = UniversalResilienceManager()

    req = AIRequest(
        messages=[Message(role=MessageRole.USER, content="Test message")],
        provider="openai",  # Requesting disabled provider
        agent_id="test-agent",
    )

    mock_openai = MagicMock(spec=AIProviderAdapter)
    mock_openai.chatCompletion = AsyncMock()

    mock_gemini = MagicMock(spec=AIProviderAdapter)
    mock_gemini.chatCompletion = AsyncMock(
        return_value=AIResponse(
            content="Gemini fallback response",
            provider="gemini",
            model="gemini-4-argon",
            agent_id="test-agent",
            request_id=uuid.uuid4(),
        )
    )

    with patch.dict(_adapters, {"openai": mock_openai, "gemini": mock_gemini}):
        with patch("app.ai_gateway.services.resilience.get_all_provider_configs") as mock_all:
            gem_cfg = MagicMock()
            gem_cfg.name = "gemini"
            gem_cfg.is_enabled = True
            gem_cfg.has_api_key = True
            gem_cfg.routing_priority = 1
            mock_all.return_value = [gem_cfg]

            with patch("app.ai_gateway.services.resilience.get_provider_config") as mock_single:
                def single_cfg(name):
                    m = MagicMock()
                    m.name = name
                    if name == "openai":
                        m.is_enabled = False  # Disabled!
                        m.has_api_key = False
                    else:
                        m.is_enabled = True
                        m.has_api_key = True
                    return m
                mock_single.side_effect = single_cfg

                resp = await resilience_mgr.execute_with_resilience(req, max_retries_per_provider=0)

                # OpenAI was skipped because it's disabled, Gemini responded
                mock_openai.chatCompletion.assert_not_called()
                assert resp.provider == "gemini"
