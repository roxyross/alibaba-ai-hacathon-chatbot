"""Abstract base class for all AI provider adapters.

Every provider adapter implements AIProviderAdapter, providing chatCompletion()
and chatCompletionStream() against a uniform interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncGenerator

import pybreaker

from app.ai_gateway.models.schemas import AIRequest, AIResponse
from app.ai_gateway.models.provider import (
    CB_FAILURES,
    CB_RESET_SECONDS,
    ProviderConfig,
    get_provider_config,
)

if TYPE_CHECKING:
    pass


class ProviderUnavailableError(Exception):
    """Raised when a provider is unreachable, returns 5xx, or times out."""

    def __init__(self, provider: str, reason: str = "") -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"Provider {provider!r} unavailable: {reason}")


class AllProvidersUnavailableError(Exception):
    """Raised when all configured providers are unavailable."""

    pass


class AIProviderAdapter(ABC):
    """Abstract base for a provider adapter.

    Subclasses must implement:
    - provider_name   (property)
    - _build_request_payload()
    - _parse_response()
    - _build_stream_payload()
    - _parse_stream_chunk()
    """

    def __init__(self, name: str) -> None:
        self._name = name
        cfg = get_provider_config(name)
        if cfg is None:
            raise ValueError(f"No provider config found for {name!r}")

        self._config = cfg

        # pybreaker circuit breaker per provider
        self._cb: pybreaker.CircuitBreaker = pybreaker.CircuitBreaker(
            fail_max=CB_FAILURES,
            reset_timeout=CB_RESET_SECONDS,
            name=f"ai_gateway.{name}",
        )

    @property
    def provider_name(self) -> str:
        """Canonical provider name, e.g. 'deepseek'."""
        return self._name

    @property
    def circuit_breaker(self) -> pybreaker.CircuitBreaker:
        """Per-provider circuit breaker instance."""
        return self._cb

    @property
    def config(self) -> ProviderConfig:
        """Provider runtime configuration."""
        return self._config

    async def chatCompletion(self, request: AIRequest) -> AIResponse:
        """Call the provider and return a structured AIResponse.

        Raises:
            ProviderUnavailableError: on timeout, HTTP 5xx, or circuit open.
        """
        if not self._config.is_enabled:
            raise ProviderUnavailableError(self._name, "provider disabled via feature flag")

        if not self._config.has_api_key:
            raise ProviderUnavailableError(self._name, f"API key env var {self._config.api_key_env_var!r} not set")

        # Wrap in circuit breaker
        try:
            return await self._circuit_protected_completion(request)
        except pybreaker.CircuitBreakerError as exc:
            raise ProviderUnavailableError(self._name, f"circuit open: {exc}") from exc

    async def chatCompletionStream(
        self, request: AIRequest
    ) -> AsyncGenerator[AIResponse, None]:
        """Stream chunks from the provider.

        Yields:
            StreamingChunk objects with delta, provider, model, done flag.

        Raises:
            ProviderUnavailableError: on timeout, HTTP 5xx, or circuit open.
        """
        if not self._config.is_enabled:
            raise ProviderUnavailableError(self._name, "provider disabled via feature flag")

        if not self._config.has_api_key:
            raise ProviderUnavailableError(self._name, f"API key env var {self._config.api_key_env_var!r} not set")

        try:
            async for chunk in self._circuit_protected_stream(request):
                yield chunk
        except pybreaker.CircuitBreakerError as exc:
            raise ProviderUnavailableError(self._name, f"circuit open: {exc}") from exc

    # -------------------------------------------------------------------------
    # Abstract methods — implemented per-provider
    # -------------------------------------------------------------------------

    @abstractmethod
    async def _circuit_protected_completion(self, request: AIRequest) -> AIResponse:
        """Internal implementation of chatCompletion — runs inside the circuit breaker."""
        raise NotImplementedError

    @abstractmethod
    def _circuit_protected_stream(
        self, request: AIRequest
    ) -> AsyncGenerator[AIResponse, None]:
        """Internal streaming implementation — runs inside the circuit breaker."""
        raise NotImplementedError
