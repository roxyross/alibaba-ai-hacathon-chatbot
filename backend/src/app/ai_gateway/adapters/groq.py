"""Groq API adapter.

Implements AIProviderAdapter for the Groq ultra-fast LPU inference endpoint.
https://api.groq.com/openai/v1 — OpenAI-compatible endpoint.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.ai_gateway.adapters.base import AIProviderAdapter, ProviderUnavailableError
from app.ai_gateway.models.schemas import (
    AIRequest,
    AIResponse,
)


class GroqAdapter(AIProviderAdapter):
    """Groq provider adapter using the OpenAI-compatible /chat/completions endpoint."""

    NAME = "groq"
    TIMEOUT_SECONDS = 10.0

    def __init__(self) -> None:
        super().__init__(self.NAME)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            api_key = self._config.api_key or ""
            base_url = self._config.base_url or "https://api.groq.com/openai/v1"
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(self.TIMEOUT_SECONDS, connect=5.0),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _circuit_protected_completion(self, request: AIRequest) -> AIResponse:
        return await self._complete(request)

    async def _complete(self, request: AIRequest) -> AIResponse:
        client = await self._get_client()
        payload = self._build_payload(request, stream=False)
        start = time.monotonic()

        try:
            response = await client.post("/chat/completions", json=payload)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderUnavailableError(self.provider_name, str(exc)) from exc

        if not response.is_success:
            raise ProviderUnavailableError(
                self.provider_name,
                f"HTTP {response.status_code}: {response.text[:200]}",
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return self._parse_response(response.json(), request, elapsed_ms)

    async def _circuit_protected_stream(
        self, request: AIRequest
    ) -> AsyncGenerator[AIResponse, None]:
        async for chunk in self._stream(request):
            yield chunk

    async def _stream(self, request: AIRequest) -> AsyncGenerator[AIResponse, None]:
        client = await self._get_client()
        payload = self._build_payload(request, stream=True)
        start = time.monotonic()

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                if not response.is_success:
                    err_bytes = await response.aread()
                    raise ProviderUnavailableError(
                        self.provider_name,
                        f"HTTP {response.status_code}: {err_bytes.decode('utf-8', errors='replace')[:250]}",
                    )

                accumulated = ""
                model_name = "qwen/qwen3.8-27b"
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    if line.strip() == "data: [DONE]":
                        break
                    raw_chunk = line[6:]
                    try:
                        import json
                        parsed = json.loads(raw_chunk)
                        choices = parsed.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {}).get("content", "")
                            if delta:
                                accumulated += delta
                                yield AIResponse(
                                    request_id=request.request_id or uuid.uuid4(),
                                    provider=self.provider_name,
                                    model=parsed.get("model", model_name),
                                    content=accumulated,
                                    agent_id=request.agent_id or "unknown",
                                    user_id=request.user_id,
                                    input_tokens=0,
                                    output_tokens=len(accumulated.split()),
                                    cost_usd=0.0,
                                    latency_ms=int((time.monotonic() - start) * 1000),
                                )
                    except Exception:
                        continue
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderUnavailableError(self.provider_name, str(exc)) from exc

    def _build_payload(self, request: AIRequest, stream: bool = False) -> dict[str, Any]:
        messages = [
            {"role": m.role.value if hasattr(m.role, "value") else str(m.role), "content": m.content}
            for m in request.messages
        ]
        model = request.model
        if not model:
            try:
                from app.ai_gateway.services.catalog_discovery import ModelCatalogDiscoveryService
                model = ModelCatalogDiscoveryService.get_instance().get_default_model(self.NAME)
            except Exception:
                model = "qwen/qwen3.8-27b"
        max_tokens = min(request.max_tokens or 1000, 1000)
        return {
            "model": model,
            "messages": messages,
            "stream": stream,
            "max_tokens": max_tokens,
            "temperature": request.temperature if request.temperature is not None else 0.7,
        }

    def _parse_response(
        self, raw: dict[str, Any], request: AIRequest, latency_ms: int
    ) -> AIResponse:
        choices = raw.get("choices", [])
        if not choices:
            raise ProviderUnavailableError(self.provider_name, "Empty choices returned from Groq")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        usage = raw.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return AIResponse(
            request_id=request.request_id or uuid.uuid4(),
            provider=self.provider_name,
            model=raw.get("model", request.model or "qwen/qwen3.8-27b"),
            content=content,
            agent_id=request.agent_id or "unknown",
            user_id=request.user_id,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )
