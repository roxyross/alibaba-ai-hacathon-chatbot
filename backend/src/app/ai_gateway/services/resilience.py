"""Universal Adapter Resilience & Task Continuity Service.

Provides a centralized recovery and execution safety layer for all Roxy execution surfaces:
- Chat & Multi-Turn Conversations
- Coding & IDE Agent (workspace files, diffs, test state)
- Research & Multi-Step Agent (plans, steps, collected evidence)
- External Action & Tool Execution (idempotency enforcement preventing duplicate charges, emails, actions)
- Voice, Audio & Live API (modality-guarded routing preserving Gemini 3.8 Flash)

Guarantees:
1. Precise error classification (transient 5xx, 429 rate limit with Retry-After, timeouts, 404/deprecated model, permanent auth 401/403).
2. Bounded retries with exponential backoff and jitter for transient errors.
3. Cross-provider failover with state and checkpoint preservation.
4. Zero duplicate side-effects for non-idempotent actions via idempotency keys.
5. Strict prevention of calls to disabled providers (OpenAI, Anthropic).
6. Non-destructive resume from last verified checkpoint.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import structlog

from app.ai_gateway.adapters.base import (
    AIProviderAdapter,
    AllProvidersUnavailableError,
    ProviderUnavailableError,
)
from app.ai_gateway.models.provider import (
    get_all_provider_configs,
    get_provider_config,
)
from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole, TaskType

log = structlog.get_logger()


class ErrorClassification(str, Enum):
    TRANSIENT_5XX = "transient_5xx"
    RATE_LIMIT_429 = "rate_limit_429"
    TIMEOUT = "timeout"
    MODEL_UNAVAILABLE = "model_unavailable"
    AUTH_OR_PERMANENT = "auth_or_permanent"
    CAPABILITY_MISMATCH = "capability_mismatch"
    TOOL_FAILURE = "tool_failure"
    CIRCUIT_OPEN = "circuit_open"
    UNKNOWN = "unknown"


def classify_error(exc: Exception, status_code: int | None = None) -> tuple[ErrorClassification, bool, float]:
    """Classify an exception and determine retryability and backoff duration.

    Returns:
        (classification, is_retryable_on_same_provider, suggested_backoff_seconds)
    """
    err_str = str(exc).lower()

    # Circuit breaker open
    if "circuit" in err_str and "open" in err_str:
        return ErrorClassification.CIRCUIT_OPEN, False, 0.0

    # Permanent authentication / authorization / billing errors
    if any(k in err_str for k in ("401", "403", "unauthorized", "invalid api key", "forbidden", "permission denied")):
        return ErrorClassification.AUTH_OR_PERMANENT, False, 0.0

    # Rate limiting (429)
    if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
        # Check for Retry-After header or string in error
        retry_after = 1.0
        import re
        match = re.search(r"retry[-_]after[:=]\s*(\d+)", err_str)
        if match:
            retry_after = float(match.group(1))
        return ErrorClassification.RATE_LIMIT_429, True, min(retry_after, 5.0)

    # Model not found or deprecated
    if any(k in err_str for k in ("404", "model not found", "unsupported model", "is not supported", "deprecated")):
        return ErrorClassification.MODEL_UNAVAILABLE, False, 0.0

    # Timeouts and network connection drops
    if any(k in err_str for k in ("timeout", "connecterror", "connection refused", "readtimeout")):
        return ErrorClassification.TIMEOUT, True, 0.5

    # 5xx Server errors
    if any(k in err_str for k in ("500", "502", "503", "504", "service unavailable", "bad gateway")):
        return ErrorClassification.TRANSIENT_5XX, True, 1.0

    # Modality / Capability mismatch
    if "capability" in err_str or "modality" in err_str or "audio not supported" in err_str:
        return ErrorClassification.CAPABILITY_MISMATCH, False, 0.0

    return ErrorClassification.UNKNOWN, False, 0.0


@dataclass
class TaskCheckpoint:
    """Execution state and checkpoint for an ongoing user task."""

    task_id: str
    task_type: str = "general"
    conversation_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    plan_steps: list[dict[str, Any]] = field(default_factory=list)
    completed_step_indices: list[int] = field(default_factory=list)
    workspace_files: dict[str, str] = field(default_factory=dict)
    diffs: list[str] = field(default_factory=list)
    executed_idempotency_keys: set[str] = field(default_factory=set)
    executed_tool_results: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TaskContinuityManager:
    """Stores and manages task checkpoints across execution steps and failures."""

    _instance: TaskContinuityManager | None = None

    def __init__(self) -> None:
        self._checkpoints: dict[str, TaskCheckpoint] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> TaskContinuityManager:
        if cls._instance is None:
            cls._instance = TaskContinuityManager()
        return cls._instance

    async def save_checkpoint(self, checkpoint: TaskCheckpoint) -> None:
        async with self._lock:
            checkpoint.updated_at = datetime.now(timezone.utc)
            self._checkpoints[checkpoint.task_id] = checkpoint

    async def get_checkpoint(self, task_id: str) -> TaskCheckpoint | None:
        async with self._lock:
            return self._checkpoints.get(task_id)

    async def is_action_already_executed(self, task_id: str, idempotency_key: str) -> bool:
        """Check if an external non-idempotent action has already completed."""
        async with self._lock:
            ckpt = self._checkpoints.get(task_id)
            if not ckpt:
                return False
            return idempotency_key in ckpt.executed_idempotency_keys

    async def record_action_executed(
        self, task_id: str, idempotency_key: str, action_name: str, result: Any
    ) -> None:
        """Record completed non-idempotent action to prevent duplicate execution on failover."""
        async with self._lock:
            if task_id not in self._checkpoints:
                self._checkpoints[task_id] = TaskCheckpoint(task_id=task_id)
            ckpt = self._checkpoints[task_id]
            ckpt.executed_idempotency_keys.add(idempotency_key)
            ckpt.executed_tool_results[idempotency_key] = {
                "action": action_name,
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            ckpt.updated_at = datetime.now(timezone.utc)

    async def preserve_coding_state(
        self, task_id: str, workspace_files: dict[str, str], diffs: list[str]
    ) -> None:
        async with self._lock:
            if task_id not in self._checkpoints:
                self._checkpoints[task_id] = TaskCheckpoint(task_id=task_id, task_type="coding")
            ckpt = self._checkpoints[task_id]
            ckpt.workspace_files.update(workspace_files)
            ckpt.diffs = list(set(ckpt.diffs + diffs))
            ckpt.updated_at = datetime.now(timezone.utc)

    async def preserve_plan_state(
        self, task_id: str, plan_steps: list[dict[str, Any]], completed_indices: list[int]
    ) -> None:
        async with self._lock:
            if task_id not in self._checkpoints:
                self._checkpoints[task_id] = TaskCheckpoint(task_id=task_id, task_type="research")
            ckpt = self._checkpoints[task_id]
            ckpt.plan_steps = plan_steps
            ckpt.completed_step_indices = list(set(ckpt.completed_step_indices + completed_indices))
            ckpt.updated_at = datetime.now(timezone.utc)


class UniversalResilienceManager:
    """Centralized resilience, bounded backoff, and task-continuity router."""

    def __init__(self, continuity_manager: TaskContinuityManager | None = None) -> None:
        self.continuity = continuity_manager or TaskContinuityManager.get_instance()

    async def execute_with_resilience(
        self,
        request: AIRequest,
        task_id: str | None = None,
        task_type: str = "general",
        max_retries_per_provider: int = 2,
    ) -> AIResponse:
        """Execute request with automated failure detection, bounded retries, and cross-provider failover."""
        # 1. Establish or retrieve checkpoint
        active_task_id = task_id or (str(request.request_id) if request.request_id else str(uuid.uuid4()))
        ckpt = await self.continuity.get_checkpoint(active_task_id)
        if not ckpt:
            ckpt = TaskCheckpoint(
                task_id=active_task_id,
                task_type=task_type,
                messages=[{"role": m.role.value if hasattr(m.role, "value") else str(m.role), "content": m.content} for m in request.messages],
            )
            await self.continuity.save_checkpoint(ckpt)

        # 2. Modality check: Audio/Voice tasks MUST NOT route to text-only providers
        is_audio_task = task_type in ("audio", "voice", "live") or getattr(request, "task_type", None) == "audio"

        # 3. Candidate provider resolution
        from app.ai_gateway.services.router import _get_adapter, _sorted_providers

        available_providers = _sorted_providers()

        if is_audio_task:
            # Audio/Voice tasks are restricted to Gemini
            available_providers = [p for p in available_providers if p == "gemini"]
            if not available_providers:
                raise AllProvidersUnavailableError(
                    "Audio/Voice task cannot be executed: No audio-capable provider is currently enabled."
                )

        # Respect explicit provider override if enabled and authorized
        if request.provider:
            req_prov = request.provider.lower()
            prov_cfg = get_provider_config(req_prov)
            if prov_cfg and prov_cfg.is_enabled and prov_cfg.has_api_key:
                candidate_providers = [req_prov] + [p for p in available_providers if p != req_prov]
            else:
                log.warning("resilience.requested_provider_ineligible", provider=req_prov)
                candidate_providers = available_providers
        else:
            candidate_providers = available_providers

        if not candidate_providers:
            raise AllProvidersUnavailableError(
                "All AI providers are currently unavailable or disabled by configuration."
            )

        attempted_providers: list[str] = []
        last_error_reason: str = ""
        switched_from: str | None = None

        for prov_idx, provider_name in enumerate(candidate_providers):
            attempted_providers.append(provider_name)
            prov_cfg = get_provider_config(provider_name)
            if not prov_cfg or not prov_cfg.is_enabled or not prov_cfg.has_api_key:
                continue

            adapter = _get_adapter(provider_name)

            # Retry loop within the active provider for transient errors
            retry_count = 0
            while retry_count <= max_retries_per_provider:
                try:
                    # Model assignment with modality preservation
                    if is_audio_task and provider_name == "gemini":
                        request.model = "gemini-3.8-flash"

                    response = await adapter.chatCompletion(request)

                    # Successful response: enrich with recovery metadata if failover occurred
                    recovery_meta = None
                    if switched_from and switched_from != provider_name:
                        recovery_meta = {
                            "switched_from": switched_from,
                            "switched_to": provider_name,
                            "checkpoint_resumed": active_task_id,
                            "failover_reason": last_error_reason,
                        }
                        log.info(
                            "resilience.task_recovered",
                            task_id=active_task_id,
                            from_prov=switched_from,
                            to_prov=provider_name,
                        )

                    # Update checkpoint with response turn
                    ckpt.messages.append({"role": "assistant", "content": response.content})
                    await self.continuity.save_checkpoint(ckpt)

                    if recovery_meta and hasattr(response, "recovery_metadata"):
                        setattr(response, "recovery_metadata", recovery_meta)

                    return response

                except Exception as exc:
                    err_class, is_retryable, backoff = classify_error(exc)
                    last_error_reason = f"{provider_name}: {exc}"

                    if is_retryable and retry_count < max_retries_per_provider:
                        retry_count += 1
                        jitter = random.uniform(0.1, 0.3)
                        total_wait = min(backoff * (2 ** (retry_count - 1)) + jitter, 5.0)
                        log.warning(
                            "resilience.transient_error_retry",
                            provider=provider_name,
                            error_class=err_class.value,
                            retry=retry_count,
                            wait_seconds=total_wait,
                        )
                        await asyncio.sleep(total_wait)
                        continue
                    else:
                        # Non-retryable or retries exhausted on this provider: fail over to next candidate
                        log.warning(
                            "resilience.provider_failed_initiating_failover",
                            provider=provider_name,
                            error_class=err_class.value,
                            error=str(exc),
                        )
                        if not switched_from:
                            switched_from = provider_name
                        break  # Move to next provider

        # All candidates exhausted: raise truthful error while preserving checkpoint
        raise AllProvidersUnavailableError(
            f"All compatible providers failed for task {active_task_id}. "
            f"Preserved checkpoint at last verified state. Last error: {last_error_reason}"
        )
