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
import contextlib
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import structlog

from app.ai_gateway.adapters.base import (
    AIProviderAdapter,
    AllProvidersUnavailableError,
    ProviderUnavailableError,
)
from app.ai_gateway.adapters.deepseek import DeepSeekAdapter
from app.ai_gateway.models.provider import get_all_provider_configs
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

        # Inject grounded knowledge vault context if user has relevant documents
        await self._inject_rag_context(request)

        # Resolve override
        provider_override = self._resolve_override(request)

        # Route to provider(s)
        if provider_override:
            providers = [provider_override] + [p for p in _sorted_providers() if p != provider_override]
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
                err_msg = exc.reason or str(exc)
                last_error = f"{provider_name}: {err_msg}"
                log.warning("router.provider_failed_failover", provider=provider_name, error=err_msg)
                continue  # failover to next provider

        raise AllProvidersUnavailableError(
            f"All providers failed. Last error: {last_error}"
        )

    async def route_stream(
        self, request: AIRequest
    ) -> AsyncGenerator[AIResponse, None]:
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

        # Inject grounded knowledge vault context if user has relevant documents
        await self._inject_rag_context(request)

        provider_override = self._resolve_override(request)
        if provider_override:
            providers = [provider_override] + [p for p in _sorted_providers() if p != provider_override]
        else:
            providers = _sorted_providers()

        last_error: str | None = None
        for provider_name in providers:
            try:
                adapter = _get_adapter(provider_name)
                accumulated_text: list[str] = []
                last_chunk = None
                start_time = time.monotonic()
                persisted = False

                async def _save_and_persist(
                    last_c: Any,
                    text_list: list[str],
                    prov_name: str = provider_name,
                    st_time: float = start_time,
                ) -> None:
                    nonlocal persisted
                    if persisted:
                        return
                    persisted = True
                    full_content = "".join(text_list)
                    if isinstance(last_c, AIResponse):
                        final_resp = last_c.model_copy(
                            update={
                                "content": full_content,
                                "response": full_content,
                                "output_tokens": len(full_content.split()),
                            }
                        )
                    else:
                        prov = getattr(last_c, "provider", prov_name)
                        mod = getattr(last_c, "model", request.model or "unknown")
                        final_resp = AIResponse(
                            user_id=request.user_id,
                            content=full_content,
                            response=full_content,
                            provider=prov,
                            model=mod,
                            agent_id=request.agent_id or "unknown",
                            input_tokens=0,
                            output_tokens=len(full_content.split()),
                            cost_usd=0.0,
                            latency_ms=int((time.monotonic() - st_time) * 1000),
                            request_id=getattr(request, "request_id", None) or uuid.uuid4(),
                        )
                    with contextlib.suppress(Exception):
                        asyncio.create_task(self._token_logger.log(request, final_resp))
                    await self._persist_turn(request, final_resp)

                async for chunk in adapter.chatCompletionStream(request):
                    last_chunk = chunk
                    delta = getattr(chunk, "delta", None)
                    if delta is None:
                        delta = getattr(chunk, "content", "")
                    if delta:
                        accumulated_text.append(str(delta))
                    if getattr(chunk, "done", False):
                        await _save_and_persist(chunk, accumulated_text)
                        yield chunk
                        return
                    yield chunk

                if not persisted and last_chunk is not None:
                    await _save_and_persist(last_chunk, accumulated_text)
                return  # stream ended normally
            except ProviderUnavailableError as exc:
                err_msg = exc.reason or str(exc)
                last_error = f"{provider_name}: {err_msg}"
                log.warning("router.provider_stream_failed_failover", provider=provider_name, error=err_msg)
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

    async def _inject_rag_context(self, request: AIRequest) -> None:
        """Query user's Knowledge Vault and inject grounded context if relevant chunks exist."""
        if not getattr(request, "user_id", None):
            return
        try:
            user_text = ""
            if request.messages:
                for m in reversed(request.messages):
                    role_val = getattr(getattr(m, "role", None), "value", getattr(m, "role", None))
                    if role_val == "user":
                        user_text = getattr(m, "content", "")
                        break
            if not user_text:
                return

            from app.ai_gateway.models.schemas import Message, MessageRole
            from app.skills.document_rag_query import DocumentRAGSkill
            from app.skills.schemas import DocumentRagQueryRequest

            rag_skill = DocumentRAGSkill()
            rag_res = await rag_skill.execute(
                DocumentRagQueryRequest(
                    query=user_text,
                    user_id=str(request.user_id),
                    top_k=3,
                    min_score=0.20,
                )
            )
            if rag_res.chunks:
                grounded = [
                    f"[Source: {c.document_name}]\n{c.content}"
                    for c in rag_res.chunks
                    if c.relevance_score >= 0.20
                ]
                if grounded:
                    rag_msg = Message(
                        role=MessageRole.SYSTEM,
                        content=(
                            "[KNOWLEDGE VAULT CONTEXT — USER PRIVATE DOCUMENTS]:\n"
                            + "\n\n".join(grounded)
                            + "\n\nAnswer using the documents above. Cite consulted documents using [Source: <document_name>]."
                        ),
                    )
                    request.messages.insert(0, rag_msg)
        except Exception as exc:
            log.warning("router.rag_inject_failed", error=str(exc))

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

            session = None
            if request.user_id:
                session = await sessions.get(request.session_id, request.user_id)
            if session is None:
                session = await sessions.get_by_id(request.session_id)

            if session is None:
                log.warning(
                    "ai.persist.session_not_found",
                    session_id=request.session_id,
                )
                return

            user_text = ""
            if request.messages:
                for m in reversed(request.messages):
                    role_val = getattr(getattr(m, "role", None), "value", getattr(m, "role", None))
                    if role_val == "user":
                        user_text = getattr(m, "content", "")
                        break

            if user_text:
                await history.append(
                    session_id=request.session_id,
                    role="user",
                    content=user_text,
                )

            assistant_text = getattr(response, "content", None) or getattr(response, "response", "") or ""
            await history.append(
                session_id=request.session_id,
                role="assistant",
                content=assistant_text,
                provider=getattr(response, "provider", session.provider),
                model=getattr(response, "model", session.model),
                input_tokens=getattr(response, "input_tokens", 0) or 0,
                output_tokens=getattr(response, "output_tokens", 0) or 0,
                cost_usd=getattr(response, "cost_usd", 0.0) or 0.0,
            )

            # Auto-title the session from the first user message if untitled or generic title.
            current_title = getattr(session, "title", None)
            default_titles = {"New chat", "New task", "New Conversation"}
            if (not current_title or current_title in default_titles) and user_text:
                from app.api.v1.greeting import generate_smart_title, is_greeting
                if is_greeting(user_text):
                    if current_title != "New Conversation":
                        await sessions.rename(session.id, session.user_id, "New Conversation")
                else:
                    smart_title = generate_smart_title(user_text)
                    await sessions.rename(session.id, session.user_id, smart_title)
        except Exception as exc:  # noqa: BLE001
            log.error("ai.persist.failed", error=str(exc))
