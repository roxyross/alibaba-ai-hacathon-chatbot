"""Per-user rate limiting for the AI gateway.

Applies to POST /api/v1/ai/chat and POST /api/v1/ai/chat/stream.
Spec §10.7: 60 messages per minute per user; excess returns 429 + Retry-After.

Implementation: simple in-memory sliding window per user/IP.
Redis-backed shared state is post-hackathon.
"""

from __future__ import annotations

import ipaddress
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_RATE_LIMIT = 60
_WINDOW_SECONDS = 60

# In-memory store: key -> list of request timestamps.
# Race conditions on window updates are acceptable for hackathon scope
# (worst case: a few extra requests slip through before the counter syncs).
_window: dict[str, list[float]] = defaultdict(list)


def _make_key(request: Request, user_id: str | None) -> str:
    """Build the rate-limit key: prefer user_id, fall back to client IP."""
    if user_id is not None:
        return f"user:{user_id}"
    try:
        client_ip = ipaddress.ip_address(request.client.host if request.client else "0.0.0.0")
        return f"ip:{client_ip}"
    except Exception:
        return "ip:unknown"


def _clean(key: str, now: float) -> None:
    """Evict timestamps outside the current 60-second window."""
    _window[key] = [t for t in _window[key] if now - t < _WINDOW_SECONDS]


def rate_limit(request: Request, user_id: str | None = None) -> None:
    """Dependency that enforces 60 msg/min per user on the chat endpoint.

    Must be used **after** `get_current_user` in the endpoint signature so that
    `user_id` (from `current_user.id`) is available.  On unauthenticated requests
    the IP address is used as the fallback key.
    """
    key = _make_key(request, user_id)
    now = time.monotonic()
    _clean(key, now)

    if len(_window[key]) >= _RATE_LIMIT:
        oldest = _window[key][0]
        retry_after = int(_WINDOW_SECONDS - (now - oldest)) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "code": "RATE_LIMIT_EXCEEDED",
                "detail": f"Maximum {_RATE_LIMIT} messages per minute. Retry after {retry_after}s.",
            },
            headers={"Retry-After": str(retry_after)},
        )

    _window[key].append(now)
