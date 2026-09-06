"""AI Router — domain service for multi-provider request routing with failover.

Implements the three-tier override hierarchy:
  1. Operator / feature flag (env var PROVIDER_{NAME}_ENABLED)
  2. User preference (DB, per-ProviderPreference model)
  3. Request-level override (AIRequest.provider field)

Default priority order: Gemini → Grok → (DeepSeek, OpenAI — disabled)
Per Spec §5 and clarifications 2026-09-03.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog
from app.ai_gateway.adapters.base import (
    AIProviderAdapter,
    AllProvidersUnavailableError,
    ProviderUnavailableError,
)
from app.ai_gateway.adapters.deepseek import DeepSeekAdapter
from app.ai_gateway.models.provider import (
    DEFAULT_ROUTING_PRIORITY,
    get_all_provider_configs,
)
from app.ai_gateway.models.schemas import AIRequest, AIResponse
from app.ai_gateway.services.sanitizer import PromptInjectionError, PromptSanitizer
from app.ai_gateway.services.token_logger import TokenUsageLogger

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


# Lazy-initialized adapter registry
_adapters: dict[str, AIProviderAdapter] = {}


def _get_adapter(name: str) -> AIProviderAdapter:
    """Lazily instantiate and cache an adapter by provider name."""
    if name not in _adapters:
        if name == "deepseek":
            _adapters[name] = DeepSeekAdapter()
        elif name == "grok":
            from app.ai_gateway.adapters.grok import GrokAdapter
            _adapters[name] = GrokAdapter()
        elif name == "openai":
            from app.ai_gateway.adapters.openai import OpenAIAdapter
            _adapters[name] = OpenAIAdapter()
        elif name == "gemini":
            from app.ai_gateway.adapters.gemini import GeminiAdapter
            _adapters[name] = GeminiAdapter()
        else:
            raise ValueError(f"No adapter registered for provider {name!r}")
    return _adapters[name]


def _sorted_providers() -> list[str]:
    """Return provider names sorted by routing priority (lower = higher priority)."""
    configs = get_all_provider_configs()
    enabled = [c for c in configs if c.is_enabled and c.has_api_key]
    enabled.sort(key=lambda c: c.routing_priority)
    return [c.name for c in enabled]


class AIRouter:
    """Routes AI requests across providers with automatic failover and attribution."""

    def __init__(self) -> None:
        self._sanitizer = PromptSanitizer()
        self._token_logger = TokenUsageLogger()

    async def route(self, request: AIRequest) -> AIResponse:
        """Route a request to the best available provider with automatic failover.

        Priority: operator flag > user preference > request field > default priority.

        Raises:
            AllProvidersUnavailableError: when every provider fails.
            PromptInjectionError: when user input matches a blocklist pattern.
        """
        # Ensure request has a UUID for tracing
        if not hasattr(request, "request_id") or request.request_id is None:
            object.__setattr__(request, "request_id", uuid.uuid4())

        # Sanitize input before routing
        try:
            if request.messages and request.messages[-1].role.value == "user":
                user_text = request.messages[-1].content
                # Extract system prompt if present
                system_text = ""
                msgs = []
                for m in request.messages:
                    if m.role.value == "system":
                        system_text = m.content
                    else:
                        msgs.append(m)
                sanitized = self._sanitizer.sanitize(user_text, system_text)
                # Replace user messages with sanitized version
                request.messages = [m for m in request.messages if m.role.value != "user"] + sanitized
        except PromptInjectionError:
            raise  # re-raise sanitization errors

        # Resolve override
        provider_override = self._resolve_override(request)

        # Route to provider(s)
        if provider_override:
            providers = [provider_override]
        else:
            providers = _sorted_providers()

        last_error: str | None = None
        for provider_name in providers:
            try:
                adapter = _get_adapter(provider_name)
                response = await adapter.chatCompletion(request)
                # Log token usage after successful call (fire-and-forget via create_task)
                asyncio.create_task(self._token_logger.log(request, response))
                # Persist turn if session_id was set
                await self._persist_turn(request, response)
                return response
            except ProviderUnavailableError as exc:
                last_error = f"{provider_name}: {exc.reason}"
                continue  # failover to next provider

        raise AllProvidersUnavailableError(
            f"All providers failed. Last error: {last_error}"
        )

    async def route_stream(self, request: AIRequest):
        """Streaming version of route(). Yields AIResponse chunks.

        Raises:
            AllProvidersUnavailableError: when every provider fails.
            PromptInjectionError: when user input matches a blocklist pattern.
        """
        if not hasattr(request, "request_id") or request.request_id is None:
            object.__setattr__(request, "request_id", uuid.uuid4())

        # Sanitize input
        try:
            if request.messages and request.messages[-1].role.value == "user":
                user_text = request.messages[-1].content
                system_text = ""
                msgs = []
                for m in request.messages:
                    if m.role.value == "system":
                        system_text = m.content
                    else:
                        msgs.append(m)
                sanitized = self._sanitizer.sanitize(user_text, system_text)
                request.messages = [m for m in request.messages if m.role.value != "user"] + sanitized
        except PromptInjectionError:
            raise

        provider_override = self._resolve_override(request)
        if provider_override:
            providers = [provider_override]
        else:
            providers = _sorted_providers()

        last_error: str | None = None
        last_response: AIResponse | None = None
        for provider_name in providers:
            try:
                adapter = _get_adapter(provider_name)
                async for chunk in adapter.chatCompletionStream(request):
                    last_response = chunk
                    yield chunk
                # Log token usage after successful stream (fire-and-forget via create_task)
                # Tokens may be 0 for streaming; cost will reflect input only
                if last_response is not None:
                    asyncio.create_task(self._token_logger.log(request, last_response))
                    await self._persist_turn(request, last_response)
                return  # stream ended normally
            except ProviderUnavailableError as exc:
                last_error = f"{provider_name}: {exc.reason}"
                continue

        raise AllProvidersUnavailableError(
            f"All providers failed during stream. Last error: {last_error}"
        )

    def _resolve_override(self, request: AIRequest) -> str | None:
        """Resolve provider using three-tier hierarchy.

        1. Operator/feature flag: handled by adapter's is_enabled check
        2. User preference: TODO — needs DB integration (post-hackathon)
        3. Request-level override: AIRequest.provider field
        """
        # Tier 3: request-level override
        if request.provider:
            return request.provider.lower()

        # Tier 2: user preference — deferred to post-hackathon (needs DB)
        # Tier 1: operator flag — handled by adapter registry (is_enabled)

        return None

    # -------------------------------------------------------------------------
    # Chat history persistence (best-effort, fire-and-forget)
    # -------------------------------------------------------------------------

    async def _persist_turn(
        self,
        request: AIRequest,
        response: AIResponse,
    ) -> None:
        """Append the user + assistant turns to chat_messages, if session_id is set.

        Never raises into the request path: a persistence failure must not
        surface to the user.
        """
        if not request.session_id:
            return
        try:
            from app.chat_history.repository import ChatMessageRepository
            from app.session.repository import ChatSessionRepository
            sessions = ChatSessionRepository()
            history = ChatMessageRepository()
            session = await sessions.get(request.session_id, request.user_id or "")
            if session is None:
                log.warning(
                    "ai.persist.session_not_found",
                    session_id=request.session_id,
                )
                return

            user_text = ""
            if request.messages and request.messages[-1].role.value == "user":
                user_text = request.messages[-1].content
            if user_text:
                await history.append(
                    session_id=request.session_id,
                    role="user",
                    content=user_text,
                )
            await history.append(
                session_id=request.session_id,
                role="assistant",
                content=response.content,
                provider=response.provider,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            )

            # Auto-title the session from the first user message.
            if session.title is None and user_text:
                title = user_text.strip().splitlines()[0][:80]
                await sessions.rename(request.session_id, request.user_id or "", title)
        except Exception as exc:  # noqa: BLE001
            log.error("ai.persist.failed", error=str(exc))
