"""Anthropic API adapter.

Implements AIProviderAdapter for the Anthropic Claude API.
https://api.anthropic.com/v1/messages
OpenAI and Anthropic remain disabled by default in Roxy.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.ai_gateway.adapters.base import AIProviderAdapter, ProviderUnavailableError
from app.ai_gateway.models.schemas import (
    AIRequest,
    AIResponse,
    StreamingChunk,
)


class AnthropicAdapter(AIProviderAdapter):
    """Anthropic provider adapter using the /v1/messages endpoint."""

    NAME = "anthropic"
    TIMEOUT_SECONDS = 15.0

    def __init__(self) -> None:
        super().__init__(self.NAME)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            api_key = self._config.api_key or ""
            base_url = self._config.base_url or "https://api.anthropic.com/v1"
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(self.TIMEOUT_SECONDS, connect=5.0),
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
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
            response = await client.post("/messages", json=payload)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderUnavailableError(self.provider_name, str(exc)) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if response.status_code != 200:
            raise ProviderUnavailableError(
                self.provider_name,
                f"HTTP {response.status_code}: {response.text[:200]}",
            )

        data = response.json()
        return self._parse_response(data, request, elapsed_ms)

    async def _circuit_protected_stream(
        self, request: AIRequest
    ) -> AsyncGenerator[AIResponse, None]:
        client = await self._get_client()
        payload = self._build_payload(request, stream=True)
        start = time.monotonic()

        try:
            async with client.stream("POST", "/messages", json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise ProviderUnavailableError(
                        self.provider_name,
                        f"HTTP {resp.status_code}: {body.decode()[:200]}",
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if not data_str:
                        continue
                    try:
                        chunk_data = json.loads(data_str)
                        c_type = chunk_data.get("type")
                        if c_type == "content_block_delta":
                            delta_text = chunk_data.get("delta", {}).get("text", "")
                            if delta_text:
                                yield AIResponse(
                                    content=delta_text,
                                    provider=self.NAME,
                                    model=request.model or "claude-3-5-sonnet-latest",
                                    agent_id=request.agent_id or "unknown",
                                    latency_ms=int((time.monotonic() - start) * 1000),
                                    request_id=request.request_id or uuid.uuid4(),
                                )
                    except Exception:
                        continue
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderUnavailableError(self.provider_name, str(exc)) from exc

    def _build_payload(self, request: AIRequest, stream: bool = False) -> dict[str, Any]:
        system_prompt = ""
        user_messages = []
        for m in request.messages:
            role = m.role.value if hasattr(m.role, "value") else str(m.role)
            if role == "system":
                system_prompt = m.content
            else:
                user_messages.append({"role": role, "content": m.content})

        model = request.model or "claude-3-5-sonnet-latest"
        payload: dict[str, Any] = {
            "model": model,
            "messages": user_messages,
            "max_tokens": min(request.max_tokens or 4096, 8192),
            "stream": stream,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    def _parse_response(
        self, data: dict[str, Any], request: AIRequest, elapsed_ms: int
    ) -> AIResponse:
        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        usage = data.get("usage", {})
        return AIResponse(
            user_id=request.user_id,
            content=text,
            provider=self.NAME,
            model=data.get("model", request.model or "claude-3-5-sonnet-latest"),
            agent_id=request.agent_id or "unknown",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=0.0,
            latency_ms=elapsed_ms,
            request_id=getattr(request, "request_id", None) or uuid.uuid4(),
        )
