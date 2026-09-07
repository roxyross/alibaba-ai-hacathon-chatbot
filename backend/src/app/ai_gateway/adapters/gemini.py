"""Google Gemini API adapter.

Implements AIProviderAdapter for the Gemini API.
https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
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


class GeminiAdapter(AIProviderAdapter):
    """Gemini provider adapter using Google's Gemini REST API."""

    NAME = "gemini"
    TIMEOUT_SECONDS = 10.0
    # Default model; can be made configurable
    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self) -> None:
        super().__init__(self.NAME)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # Gemini API key goes in the query param, not the header
            api_key = self._config.api_key or ""
            self._client = httpx.AsyncClient(
                base_url=f"{self._config.base_url}/models",
                timeout=httpx.Timeout(self.TIMEOUT_SECONDS, connect=5.0),
                headers={"Content-Type": "application/json"},
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
        model = request.model or self.DEFAULT_MODEL
        api_key = self._config.api_key or ""
        payload = self._build_payload(request)
        start = time.monotonic()

        url = f"/{model}:generateContent?key={api_key}"
        try:
            response = await client.post(url, json=payload)
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
        model = request.model or self.DEFAULT_MODEL
        api_key = self._config.api_key or ""
        payload = self._build_payload(request)
        start = time.monotonic()

        url = f"/{model}:streamGenerateContent?key={api_key}"
        try:
            async with client.stream("POST", url, json=payload) as response:
                if not response.is_success:
                    raise ProviderUnavailableError(
                        self.provider_name,
                        f"HTTP {response.status_code}: {await response.aread()}",
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = self._parse_stream_chunk(line)
                    if chunk.delta:
                        yield AIResponse(
                            user_id=request.user_id,
                            content=chunk.delta,
                            provider="gemini",
                            model=model,
                            agent_id=request.agent_id or "unknown",
                            input_tokens=0,
                            output_tokens=0,
                            cost_usd=0.0,
                            latency_ms=int((time.monotonic() - start) * 1000),
                            request_id=request.request_id or uuid.uuid4(),
                        )
                    if chunk.done:
                        return
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderUnavailableError(self.provider_name, str(exc)) from exc

    def _build_payload(self, request: AIRequest) -> dict[str, Any]:
        """Build Gemini API request payload."""
        contents = []
        for msg in request.messages:
            role = "user" if msg.role.value in ("user", "model") else "model"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens or 4096,
            },
        }

    def _parse_response(self, data: dict[str, Any], request: AIRequest, elapsed_ms: int) -> AIResponse:
        """Parse Gemini generateContent response."""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            text = ""
        usage = data.get("usageMetadata", {})
        return AIResponse(
            user_id=request.user_id,
            content=text,
            provider="gemini",
            model=self.DEFAULT_MODEL,
            agent_id=request.agent_id or "unknown",
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            cost_usd=0.0,
            latency_ms=elapsed_ms,
            request_id=getattr(request, "request_id", None) or uuid.uuid4(),
        )

    def _parse_stream_chunk(self, data: str) -> StreamingChunk:
        """Parse a Gemini streaming SSE line into StreamingChunk."""
        import json
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return StreamingChunk(delta="", provider="gemini", model="", done=True)

        try:
            delta = obj["candidates"][0]["content"]["parts"][0]["text"]
            done = False
        except (KeyError, IndexError):
            delta = ""
            done = True

        return StreamingChunk(delta=delta, provider="gemini", model=self.DEFAULT_MODEL, done=done)
