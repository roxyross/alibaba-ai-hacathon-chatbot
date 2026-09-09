"""Google Gemini API adapter.

Implements AIProviderAdapter for the Gemini API.
https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
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


class GeminiAdapter(AIProviderAdapter):
    """Gemini provider adapter using Google's Gemini REST API."""

    NAME = "gemini"
    TIMEOUT_SECONDS = 30.0
    DEFAULT_MODEL = "gemini-3.6-flash"

    def _resolve_model(self, model: str | None) -> str:
        if not model:
            return self.DEFAULT_MODEL
        # Strip provider prefix if present (e.g. "gemini/gemini-2.0-flash")
        if "/" in model:
            model = model.split("/", 1)[-1]
        # Google directs new users on this API key to gemini-3.6-flash
        if model in (
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.7",
            "gemini-3.1-flash",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-3.6-flash",
        ):
            return self.DEFAULT_MODEL
        return model


    def __init__(self) -> None:
        super().__init__(self.NAME)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
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
        model = self._resolve_model(request.model)
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
                f"HTTP {response.status_code}: {response.text[:250]}",
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return self._parse_response(response.json(), request, model, elapsed_ms)

    async def _circuit_protected_stream(
        self, request: AIRequest
    ) -> AsyncGenerator[AIResponse, None]:
        async for chunk in self._stream(request):
            yield chunk

    async def _stream(self, request: AIRequest) -> AsyncGenerator[AIResponse, None]:
        client = await self._get_client()
        model = self._resolve_model(request.model)
        api_key = self._config.api_key or ""
        payload = self._build_payload(request)
        start = time.monotonic()

        # Google Gemini streaming requires alt=sse
        url = f"/{model}:streamGenerateContent?alt=sse&key={api_key}"
        try:
            async with client.stream("POST", url, json=payload) as response:
                if not response.is_success:
                    err_bytes = await response.aread()
                    raise ProviderUnavailableError(
                        self.provider_name,
                        f"HTTP {response.status_code}: {err_bytes.decode('utf-8', errors='replace')[:250]}",
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    line_str = line.strip()
                    if not line_str.startswith("data: "):
                        continue
                    data_str = line_str.removeprefix("data: ").strip()
                    if not data_str or data_str == "[DONE]":
                        break

                    chunk = self._parse_stream_chunk(data_str, model)
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
                            request_id=getattr(request, "request_id", None) or uuid.uuid4(),
                        )
                    if chunk.done:
                        break
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise ProviderUnavailableError(self.provider_name, str(exc)) from exc

    def _build_payload(self, request: AIRequest) -> dict[str, Any]:
        """Build Gemini API request payload."""
        contents: list[dict[str, Any]] = []
        system_parts: list[dict[str, str]] = []

        for msg in request.messages:
            role_val = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            if role_val == "system":
                system_parts.append({"text": msg.content})
            else:
                role = "user" if role_val == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg.content}]})

        # Gemini requires at least one user content and cannot begin with 'model'
        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]
        elif contents[0]["role"] == "model":
            contents.insert(0, {"role": "user", "parts": [{"text": "Please continue."}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens or 4096,
            },
        }

        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        return payload

    def _parse_response(
        self, data: dict[str, Any], request: AIRequest, model: str, elapsed_ms: int
    ) -> AIResponse:
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
            model=model,
            agent_id=request.agent_id or "unknown",
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            cost_usd=0.0,
            latency_ms=elapsed_ms,
            request_id=getattr(request, "request_id", None) or uuid.uuid4(),
        )

    def _parse_stream_chunk(self, data: str, model: str) -> StreamingChunk:
        """Parse a Gemini streaming SSE JSON payload into StreamingChunk."""
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return StreamingChunk(delta="", provider="gemini", model=model, done=False)

        candidates = obj.get("candidates", [])
        if not candidates:
            return StreamingChunk(delta="", provider="gemini", model=model, done=False)

        candidate = candidates[0]
        delta = ""
        parts = candidate.get("content", {}).get("parts", [])
        if parts and isinstance(parts, list):
            delta = parts[0].get("text", "")

        finish_reason = candidate.get("finishReason")
        done = finish_reason in ("STOP", "MAX_TOKENS", "SAFETY")

        return StreamingChunk(delta=delta, provider="gemini", model=model, done=done)
