"""Async HTTP client for the backend AI gateway.

The runtime calls the backend at `/api/v1/ai/chat` for LLM inference.
This is a thin wrapper around `httpx.AsyncClient` that:

  - Reads the backend URL from settings
  - Sets the per-request timeout from settings
  - Wraps circuit-breaker behavior (spec §10.10) around the call
  - Returns a typed `GatewayChatResponse` on success
  - Raises typed exceptions on failure (caller catches in the router)

We do not import anything from `backend/src/app/**`. The two services
communicate over HTTP only.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

import httpx
import structlog

from runtime.config import settings

log = structlog.get_logger()

current_bearer_token: ContextVar[str | None] = ContextVar("current_bearer_token", default=None)


class GatewayError(Exception):
    """Base class for gateway failures."""


class GatewayUnavailable(GatewayError):
    """The gateway is unreachable, returned a 5xx, or the breaker is open."""


class GatewayBadRequest(GatewayError):
    """The gateway returned 4xx — our request is malformed."""


@dataclass(frozen=True)
class GatewayChatResponse:
    response: str
    provider: str | None
    model: str | None


class GatewayClient:
    """Client for backend's `/api/v1/ai/chat`.

    Implements a simple circuit breaker (spec §10.10):
      - 5 consecutive failures within 30s opens the breaker
      - After 30s, the breaker half-opens (allows one trial request)
      - A successful trial closes it again
    The breaker is per-process; in a multi-worker deployment each
    worker has its own breaker state.
    """

    FAILURE_THRESHOLD = 5
    RESET_SECONDS = 30.0

    def __init__(self, default_bearer_token: str | None = None) -> None:
        self.default_bearer_token = default_bearer_token
        self._failures: list[float] = []  # monotonic timestamps of recent failures
        self._open_until: float = 0.0

    def _record_failure(self) -> None:
        now = __import__("time").monotonic()
        self._failures.append(now)
        # Drop failures older than the reset window
        cutoff = now - self.RESET_SECONDS
        self._failures = [t for t in self._failures if t >= cutoff]
        if len(self._failures) >= self.FAILURE_THRESHOLD:
            self._open_until = now + self.RESET_SECONDS
            log.warning(
                "gateway.circuit_breaker.open",
                failures=len(self._failures),
                open_until=round(self._open_until, 1),
            )

    def _record_success(self) -> None:
        if self._failures:
            self._failures.clear()
        if self._open_until:
            log.info("gateway.circuit_breaker.closed")

    def _is_open(self) -> bool:
        if self._open_until == 0.0:
            return False
        now = __import__("time").monotonic()
        if now >= self._open_until:
            # Half-open: allow one trial; if it fails, the next call re-opens.
            self._open_until = now + 0.001
            return False
        return True

    async def chat(
        self,
        *,
        system_prompt: str,
        user_message: str,
        bearer_token: str | None = None,
    ) -> GatewayChatResponse:
        """Call the gateway. Returns the assistant's reply."""
        if self._is_open():
            raise GatewayUnavailable("circuit breaker is open")

        url = settings.backend_ai_chat_url
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = bearer_token or self.default_bearer_token or current_bearer_token.get()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }

        try:
            async with httpx.AsyncClient(
                timeout=float(settings.gateway_timeout_seconds)
            ) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            self._record_failure()
            log.warning("gateway.unreachable", url=url, error=str(exc))
            raise GatewayUnavailable(f"gateway unreachable: {exc}") from exc

        if resp.status_code >= 500:
            self._record_failure()
            log.warning(
                "gateway.5xx",
                url=url,
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise GatewayUnavailable(f"gateway 5xx: {resp.status_code}")

        if resp.status_code >= 400:
            # 4xx is our fault; do not count toward the breaker.
            log.warning("gateway.4xx", url=url, status=resp.status_code, body=resp.text[:500])
            raise GatewayBadRequest(f"gateway 4xx: {resp.status_code} {resp.text[:200]}")

        self._record_success()
        data = resp.json()
        response_text = data.get("content") or data.get("response") or ""
        return GatewayChatResponse(
            response=response_text,
            provider=data.get("provider"),
            model=data.get("model"),
        )

    async def chat_multi(
        self,
        messages: list[dict[str, str]],
        *,
        bearer_token: str | None = None,
    ) -> GatewayChatResponse:
        """Call the gateway with a list of messages (multi-turn / skill loop).

        `messages` is a list of {"role": "system"|"user"|"assistant",
        "content": "..."} dicts. System messages are prepended as-is;
        the first non-system message's content is used as the user_message
        for the circuit breaker / logging.

        Raises GatewayUnavailable / GatewayBadRequest as `chat()` does.
        """
        if self._is_open():
            raise GatewayUnavailable("circuit breaker is open")

        url = settings.backend_ai_chat_url
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = bearer_token or self.default_bearer_token or current_bearer_token.get()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = {"messages": messages}

        try:
            async with httpx.AsyncClient(
                timeout=float(settings.gateway_timeout_seconds)
            ) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            self._record_failure()
            log.warning("gateway.unreachable", url=url, error=str(exc))
            raise GatewayUnavailable(f"gateway unreachable: {exc}") from exc

        if resp.status_code >= 500:
            self._record_failure()
            log.warning(
                "gateway.5xx",
                url=url,
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise GatewayUnavailable(f"gateway 5xx: {resp.status_code}")

        if resp.status_code >= 400:
            log.warning("gateway.4xx", url=url, status=resp.status_code, body=resp.text[:500])
            raise GatewayBadRequest(f"gateway 4xx: {resp.status_code} {resp.text[:200]}")

        self._record_success()
        data = resp.json()
        response_text = data.get("content") or data.get("response") or ""
        return GatewayChatResponse(
            response=response_text,
            provider=data.get("provider"),
            model=data.get("model"),
        )
