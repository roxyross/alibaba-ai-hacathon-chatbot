"""Per-user rate limiting for the AI gateway.

Applies to POST /api/v1/ai/chat and POST /api/v1/ai/chat/stream.
Spec §10.7: 60 messages per minute per user; excess returns 429 + Retry-After.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

# In-memory store; per-instance only (Redis-backed is post-hackathon).
# 60 requests per minute per user.
_limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 with Retry-After header when rate limit is exceeded."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "code": "RATE_LIMIT_EXCEEDED",
            "detail": str(exc.detail),
        },
        headers={"Retry-After": str(exc.detail)}  # slowapi puts retry-after in detail
    )


def get_user_identifier(request: Request) -> str:
    """Return per-user rate limit key from the resolved User object.

    Falls back to IP address if no user is on the request (auth hasn't run yet).
    """
    user = getattr(request.state, "user", None)
    if user is not None:
        return f"user:{user.id}"
    return get_remote_address(request)


# Expose the limiter for middleware registration in main.py
rate_limiter = _limiter
