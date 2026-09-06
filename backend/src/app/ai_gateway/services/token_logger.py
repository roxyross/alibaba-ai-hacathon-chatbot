"""Token usage logger — records per-request AI token consumption.

Cost is computed from ModelConfig rate data (cost_per_1k_input / cost_per_1k_output).
Persistence is delegated to TokenUsageRepository (SQLAlchemy async; in-memory fallback).
"""

from __future__ import annotations

import structlog
from uuid import UUID

from app.ai_gateway.models.provider import get_provider_config
from app.ai_gateway.models.schemas import AIRequest, AIResponse, TokenUsageLogCreate
from app.repositories.token_usage import TokenUsageRepository

log = structlog.get_logger()


class TokenUsageLogger:
    """Logs token usage for every AI request for billing and observability."""

    def __init__(self) -> None:
        self._repo = TokenUsageRepository()

    async def log(
        self,
        request: AIRequest,
        response: AIResponse,
    ) -> None:
        """Persist a token usage record after a successful AI request.

        Cost is computed from the model's published per-1k-token rates.
        """
        provider_cfg = get_provider_config(response.provider)
        cost_per_1k_input = 0.0
        cost_per_1k_output = 0.0

        if provider_cfg:
            for model in provider_cfg.models:
                if model.name == response.model:
                    cost_per_1k_input = model.cost_per_1k_input
                    cost_per_1k_output = model.cost_per_1k_output
                    break

        cost_usd = (
            (response.input_tokens / 1000.0) * cost_per_1k_input
            + (response.output_tokens / 1000.0) * cost_per_1k_output
        )

        usage_record = TokenUsageLogCreate(
            request_id=response.request_id,
            provider_id=response.provider,
            model_id=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=round(cost_usd, 6),
            latency_ms=response.latency_ms,
        )

        await self._repo.create(usage_record)

        # Structured log line — no prompt contents (privacy §4)
        log.info(
            "ai.token_usage",
            request_id=str(response.request_id),
            provider=response.provider,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=cost_usd,
            latency_ms=response.latency_ms,
            user_id=request.user_id or None,
            agent_id=request.agent_id or None,
        )

    async def get_recent(
        self,
        limit: int = 100,
        provider: str | None = None,
    ) -> list[dict]:
        """Return recent token usage records."""
        return await self._repo.find_recent(limit=limit, provider=provider)
