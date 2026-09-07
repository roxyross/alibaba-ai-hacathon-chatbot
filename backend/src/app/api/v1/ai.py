"""FastAPI router for AI Gateway endpoints.

All requests pass through the AIRouter for routing and failover.
Attribution is included in every response (streaming and non-streaming).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request as StarletteRequest, status
from fastapi.responses import StreamingResponse
import pybreaker

from app.ai_gateway.adapters.base import (
    AllProvidersUnavailableError,
    ProviderUnavailableError,
)
from app.ai_gateway.models.schemas import (
    AIRequest,
    AIResponse,
    CircuitState,
    ErrorResponse,
    HealthStatus,
    ProviderHealthResponse,
    ProviderStatus,
    StreamingChunk,
)
from app.ai_gateway.services.router import AIRouter
from app.api.v1.rate_limit import rate_limit as _check_rate_limit
from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/ai", tags=["AI"])
log = structlog.get_logger()

# Singleton router instance
_router = AIRouter()


# -----------------------------------------------------------------------------
# POST /api/v1/ai/chat
# -----------------------------------------------------------------------------

@router.post("/chat", response_model=AIResponse)
async def chat(
    body: AIRequest,
    current_user: User = Depends(get_current_user),
    http_request: StarletteRequest = None,
) -> AIResponse:
    """Non-streaming chat completion.

    Routes through AIRouter for failover and attribution.
    Raises 503 if all providers fail.
    Spec §10.7: per-user rate limit of 60 msg/min (429 + Retry-After on excess).
    """
    # Per-user rate limit (spec §10.7)
    if http_request is not None:
        _check_rate_limit(http_request, user_id=str(current_user.id))

    # Stamp the authenticated user onto the request for persistence.
    body.user_id = current_user.id
    log.info(
        "ai.chat.request",
        request_id=str(body.request_id),
        provider_override=body.provider,
        task_type=body.task_type,
        stream=body.stream,
        user_id=current_user.id,
    )

    try:
        return await _router.route(body)
    except ProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorResponse(
                error="Provider unavailable",
                code="PROVIDER_UNAVAILABLE",
                detail=exc.reason,
                provider_error=True,
                failed_provider=exc.provider,
            ).model_dump(),
        ) from exc
    except AllProvidersUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorResponse(
                error="All providers unavailable",
                code="ALL_PROVIDERS_UNAVAILABLE",
                detail=str(exc),
                provider_error=True,
            ).model_dump(),
        ) from exc


@router.post("/chat/stream")
async def chat_stream(
    body: AIRequest,
    current_user: User = Depends(get_current_user),
    http_request: StarletteRequest = None,
):
    """Streaming chat completion over SSE.

    First comment line: attribution header (provider, model)
    Then data events for each streaming chunk.
    Final chunk includes done=true and attribution metadata.
    Spec §10.7: per-user rate limit of 60 msg/min (429 + Retry-After on excess).
    """
    if not body.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="stream=true is required for this endpoint",
        )
    # Per-user rate limit (spec §10.7)
    if http_request is not None:
        _check_rate_limit(http_request, user_id=str(current_user.id))

    body.user_id = current_user.id

    log.info(
        "ai.chat.stream.request",
        request_id=str(body.request_id),
        provider_override=body.provider,
        user_id=current_user.id,
    )

    async def event_generator():
        provider_name = "unknown"
        model_name = "unknown"
        chunks_yielded = False

        try:
            async for chunk in _router.route_stream(body):
                chunks_yielded = True
                # Extract attribution from first chunk
                if provider_name == "unknown":
                    provider_name = chunk.provider
                    model_name = chunk.model
                    # SSE comment line with attribution
                    yield f": provider={provider_name} model={model_name}\n\n".encode()

                delta = chunk.delta
                import json
                data = json.dumps({
                    "delta": delta,
                    "provider": chunk.provider,
                    "model": chunk.model,
                    "done": chunk.done,
                })
                yield f"data: {data}\n\n".encode()
                if chunk.done:
                    break

        except AllProvidersUnavailableError as exc:
            import json
            error_data = json.dumps({
                "error": "all_providers_unavailable",
                "code": "ALL_PROVIDERS_UNAVAILABLE",
                "detail": str(exc),
                "provider_error": True,
                "done": True,
            })
            yield f"data: {error_data}\n\n".encode()
            return
        except ProviderUnavailableError as exc:
            import json
            error_data = json.dumps({
                "error": "provider_unavailable",
                "code": "PROVIDER_UNAVAILABLE",
                "detail": exc.reason,
                "failed_provider": exc.provider,
                "provider_error": True,
                "done": True,
            })
            yield f"data: {error_data}\n\n".encode()
            return

        # Final attribution event
        if chunks_yielded:
            import json
            final = json.dumps({
                "done": True,
                "provider": provider_name,
                "model": model_name,
            })
            yield f"event: attribution\ndata: {final}\n\n".encode()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -----------------------------------------------------------------------------
# GET /api/v1/ai/providers
# -----------------------------------------------------------------------------

def _get_adapter_for_provider(name: str):
    """Return the correct adapter instance for a named provider."""
    if name == "deepseek":
        from app.ai_gateway.adapters.deepseek import DeepSeekAdapter
        return DeepSeekAdapter()
    elif name == "grok":
        from app.ai_gateway.adapters.grok import GrokAdapter
        return GrokAdapter()
    elif name == "openai":
        from app.ai_gateway.adapters.openai import OpenAIAdapter
        return OpenAIAdapter()
    elif name == "gemini":
        from app.ai_gateway.adapters.gemini import GeminiAdapter
        return GeminiAdapter()
    raise ValueError(f"No adapter for provider: {name}")


@router.get("/providers", response_model=ProviderHealthResponse)
async def list_providers() -> ProviderHealthResponse:
    """List all configured providers with health and circuit state.

    Requires authentication.
    """
    from app.ai_gateway.models.provider import get_all_provider_configs

    configs = get_all_provider_configs()
    providers = []
    for cfg in configs:
        # Map circuit breaker state — use per-provider adapter instance
        # Note: pybreaker state is per-process; shared state via Redis is post-hackathon
        try:
            adapter = _get_adapter_for_provider(cfg.name)
            cb = adapter.circuit_breaker
            if cb.current_state == pybreaker.CIRCUIT_OPEN:
                circuit_state = CircuitState.OPEN
            elif cb.current_state == pybreaker.CIRCUIT_HALF_OPEN:
                circuit_state = CircuitState.HALF_OPEN
            else:
                circuit_state = CircuitState.CLOSED
        except Exception:
            circuit_state = CircuitState.CLOSED

        if not cfg.is_enabled:
            status = HealthStatus.UNAVAILABLE
        elif circuit_state == CircuitState.OPEN:
            status = HealthStatus.UNAVAILABLE
        elif circuit_state == CircuitState.HALF_OPEN:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        providers.append(ProviderStatus(
            name=cfg.name,
            status=status,
            circuit_state=circuit_state,
            last_error=None,
            last_success=None,
        ))

    return ProviderHealthResponse(providers=providers)


# -----------------------------------------------------------------------------
# PATCH /api/v1/ai/providers/{name}
# -----------------------------------------------------------------------------

@router.patch("/providers/{name}")
async def toggle_provider(name: str):
    """Enable or disable a provider by name.

    Requires admin or operator role (enforced at gateway layer).
    Operator env var: PROVIDER_<NAME>_ENABLED.
    """
    from app.ai_gateway.models.provider import PROVIDER_FEATURE_FLAGS

    flag_env = PROVIDER_FEATURE_FLAGS.get(name.lower())
    if flag_env is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown provider: {name}",
        )

    import os
    current = os.environ.get(flag_env, "true").lower()
    new_val = "false" if current == "true" else "true"
    os.environ[flag_env] = new_val

    return {"provider": name, "enabled": new_val == "true", "flag": flag_env}


# -----------------------------------------------------------------------------
# GET /api/v1/ai/providers/health
# -----------------------------------------------------------------------------

@router.get("/providers/health", response_model=ProviderHealthResponse)
async def health_check() -> ProviderHealthResponse:
    """Unauthenticated health check endpoint.

    Returns current circuit breaker state for all providers.
    No probing — reflects in-process state only (Redis-backed shared state is post-hackathon).
    """
    from app.ai_gateway.models.provider import get_all_provider_configs

    configs = get_all_provider_configs()
    providers = []
    for cfg in configs:
        try:
            adapter = _get_adapter_for_provider(cfg.name)
            cb = adapter.circuit_breaker
            if cb.current_state == pybreaker.CIRCUIT_OPEN:
                circuit_state = CircuitState.OPEN
            elif cb.current_state == pybreaker.CIRCUIT_HALF_OPEN:
                circuit_state = CircuitState.HALF_OPEN
            else:
                circuit_state = CircuitState.CLOSED
        except Exception:
            circuit_state = CircuitState.CLOSED

        if not cfg.is_enabled:
            status = HealthStatus.UNAVAILABLE
        elif circuit_state == CircuitState.OPEN:
            status = HealthStatus.UNAVAILABLE
        elif circuit_state == CircuitState.HALF_OPEN:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        providers.append(ProviderStatus(
            name=cfg.name,
            status=status,
            circuit_state=circuit_state,
            last_error=None,
            last_success=None,
        ))

    return ProviderHealthResponse(providers=providers)


# -----------------------------------------------------------------------------
# GET /api/v1/ai/usage
# -----------------------------------------------------------------------------

@router.get("/usage")
async def token_usage(limit: int = 100, provider: str | None = None):
    """Return recent token usage logs.

    Requires authentication.
    Persistence: in-memory (T026) → SQLAlchemy async (T027/ADR-001).
    """
    records = await _router._token_logger.get_recent(limit=limit, provider=provider)
    return {
        "usage": records,
        "provider_filter": provider,
        "limit": limit,
    }
