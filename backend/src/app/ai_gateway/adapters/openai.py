"""OpenAI API adapter.

Implements AIProviderAdapter for the OpenAI API.
https://api.openai.com/v1 — OpenAI-compatible endpoint.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, AsyncGenerator

import httpx

from app.ai_gateway.adapters.base import AIProviderAdapter, ProviderUnavailableError
from app.ai_gateway.models.schemas import (
    AIRequest,
    AIResponse,
    StreamingChunk,
)


class OpenAIAdapter(AIProviderAdapter):
    """OpenAI provider adapter using the OpenAI API /chat/completions endpoint."""

    NAME = "openai"
    TIMEOUT_SECONDS = 10.0

    def __init__(self) -> None:
        super().__init__(self.NAME)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url,
                timeout=httpx.Timeout(self.TIMEOUT_SECONDS, connect=5.0),
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
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
                    raise ProviderUnavailableError(
                        self.provider_name,
                        f"HTTP {response.status_code}: {await response.aread()}",
                    )

                model_name = "gpt-4o"
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    if line.strip() == "data: [DONE]":
                        break
                    data = line.removeprefix("data: ").strip()
                    if not data or data == "[DONE]":
                        break
                    chunk = self._parse_stream_chunk(data)
                    yield AIResponse(
                        user_id=request.user_id,
                        content=chunk.delta,
                        provider="openai",
                        model=chunk.model or model_name,
                        agent_id=request.agent_id or "unknown",
                        input_tokens=0,
                        output_tokens=0,
                        cost_usd=0.0,
                        latency_ms=int((time.monotonic() - start) * 1000),
                        request_id=request.request_id or uuid.uuid4(),
                    )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderUnavailableError(self.provider_name, str(exc)) from exc

    def _build_payload(self, request: AIRequest, stream: bool) -> dict[str, Any]:
        return {
            "model": request.model or "gpt-4o",
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or 4096,
            "stream": stream,
        }

    def _parse_response(self, data: dict[str, Any], request: AIRequest, elapsed_ms: int) -> AIResponse:
        usage = data.get("usage", {})
        return AIResponse(
            user_id=request.user_id,
            content=data["choices"][0]["message"]["content"],
            provider="openai",
            model=data.get("model", "gpt-4o"),
            agent_id=request.agent_id or "unknown",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cost_usd=0.0,
            latency_ms=elapsed_ms,
            request_id=getattr(request, "request_id", None) or uuid.uuid4(),
        )

    def _parse_stream_chunk(self, data: str) -> StreamingChunk:
        import json
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return StreamingChunk(delta="", provider="openai", model="", done=True)
        delta = obj.get("choices", [{}])[0].get("delta", {}).get("content", "")
        model_name = obj.get("model", "")
        return StreamingChunk(delta=delta, provider="openai", model=model_name, done=False)
