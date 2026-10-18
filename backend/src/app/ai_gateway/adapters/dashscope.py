"""Alibaba DashScope (Qwen) API adapter.

Implements AIProviderAdapter for the Alibaba DashScope OpenAI-compatible inference endpoint:
https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog

from app.ai_gateway.adapters.base import AIProviderAdapter, ProviderUnavailableError
from app.ai_gateway.models.schemas import AIRequest, AIResponse

log = structlog.get_logger()


class DashScopeAdapter(AIProviderAdapter):
    """Alibaba DashScope / Qwen provider adapter using OpenAI-compatible /chat/completions."""

    NAME = "dashscope"
    TIMEOUT_SECONDS = 30.0

    def __init__(self) -> None:
        super().__init__(self.NAME)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            api_key = self._config.api_key or ""
            base_url = self._config.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(self.TIMEOUT_SECONDS, connect=10.0),
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
                f"HTTP {response.status_code}: {response.text[:250]}",
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
                default_model = payload.get("model", "qwen-max")
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    if line.strip() == "data: [DONE]":
                        break
                    raw_chunk = line[6:]
                    try:
                        parsed = json.loads(raw_chunk)
                        choices = parsed.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {}).get("content", "")
                            if delta:
                                accumulated += delta
                                yield AIResponse(
                                    request_id=request.request_id or uuid.uuid4(),
                                    provider=self.provider_name,
                                    model=parsed.get("model", default_model),
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
        if not model or model.lower() in ("default", "dashscope", "qwen", "alibaba"):
            try:
                from app.ai_gateway.services.catalog_discovery import ModelCatalogDiscoveryService
                model = ModelCatalogDiscoveryService.get_instance().get_default_model(self.NAME)
            except Exception:
                model = "qwen-max"

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    def _parse_response(
        self, raw: dict[str, Any], request: AIRequest, latency_ms: int
    ) -> AIResponse:
        choices = raw.get("choices", [])
        if not choices:
            raise ProviderUnavailableError(self.provider_name, "Empty choices returned from DashScope")

        message = choices[0].get("message", {})
        content = message.get("content", "")

        usage = raw.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # Estimate cost based on DashScope standard pricing
        cost_usd = 0.0
        model_name = raw.get("model", request.model or "qwen-max")
        for m in self._config.models:
            if m.name == model_name:
                cost_usd = (prompt_tokens / 1000.0 * m.cost_per_1k_input) + (
                    completion_tokens / 1000.0 * m.cost_per_1k_output
                )
                break

        return AIResponse(
            request_id=request.request_id or uuid.uuid4(),
            provider=self.provider_name,
            model=model_name,
            content=content,
            agent_id=request.agent_id or "unknown",
            user_id=request.user_id,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cost_usd=round(cost_usd, 6),
            latency_ms=latency_ms,
        )
