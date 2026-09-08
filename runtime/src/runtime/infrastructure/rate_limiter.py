"""In-process per-user rate limiter using a sliding time-window.

Spec §10.7 (CHK032): 60 messages per minute per user on POST /api/v1/runtime/chat.
Exceeding the limit returns HTTP 429 with a `Retry-After` header.

Design:
  - Sliding window — a request is allowed if it is the Nth or earlier
    in the last `window_seconds` (default 60 s).
  - State is kept in a process-local dict: user_id → deque of timestamps.
    This is correct for single-worker deployments; a multi-worker production
    deployment would replace the store with a Redis cluster.
  - Scheduled jobs are not subject to this limit (they call the Coordinator
    directly via `_fire_job`, bypassing the HTTP endpoint entirely).

Thread-safety note:
  asyncio events run on a single thread within a process, so concurrent
  updates to the same user's deque from the same event loop are
  implicitly safe. Concurrent updates from multiple workers (gunicorn -w N)
  are not safe — use a shared rate limit store in that case.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable

import structlog

from runtime.config import settings

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

# user_id → deque of accepted request timestamps (UTC seconds as float)
_rate_store: dict[str, list[float]] = defaultdict(list)

# Global lock for the store (prevents races when multiple asyncio tasks
# for the same user interleave at the boundary of the window)
_store_lock = asyncio.Lock()


def _evict_old(user_id: str, window_seconds: float, now: float) -> None:
    """Remove timestamps outside the sliding window for a single user."""
    cutoff = now - window_seconds
    rate_store = _rate_store[user_id]
    # Find first index not older than cutoff (bisection would be faster for
    # large windows; linear scan is fine for 60-second windows with ≤60 entries)
    while rate_store and rate_store[0] < cutoff:
        rate_store.pop(0)
    if not rate_store:
        del _rate_store[user_id]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    """True if the request is allowed; False if rate-limited."""

    retry_after: float | None
    """Seconds the client should wait before retrying (only set when allowed=False)."""

    remaining: int
    """Messages remaining in the window after this request (allowed only)."""

    limit: int
    """Configured messages-per-window limit."""

    reset_at: float | None
    """Unix timestamp when the oldest entry in the window will expire."""


async def check_rate_limit(
    user_id: str,
    limit: int | None = None,
    window_seconds: float = 60.0,
) -> RateLimitResult:
    """Check (and record) a request against the per-user rate limit.

    This is a sliding-window check: a request is allowed if the total number
    of recorded timestamps within the last `window_seconds` (including the new
    one) is at most `limit`.

    Call this early in the request handler; if ``allowed`` is False, return
    HTTP 429 immediately without doing any other work.

    Args:
        user_id: The user making the request.
        limit: Max requests per window (default: from settings).
        window_seconds: Size of the sliding window in seconds (default 60).

    Returns:
        RateLimitResult with allowed/retry_after/remaining/limit/reset_at.
    """
    if limit is None:
        limit = settings.rate_limit_per_minute

    now = time.monotonic()

    async with _store_lock:
        # Evict entries outside the window first
        _evict_old(user_id, window_seconds, now)

        store = _rate_store[user_id]
        current_count = len(store)

        if current_count >= limit:
            # Oldest entry is at index 0; its expiry is the reset time
            oldest = store[0] if store else now
            retry_after = round(oldest - now + window_seconds, 2)
            # Cap retry_after to window_seconds (oldest could be exactly on the
            # boundary, giving 0; floor to 1 second minimum so the header is
            # useful for the client)
            retry_after = max(1.0, min(retry_after, window_seconds))

            log.info(
                "rate_limit.exceeded",
                user_id=user_id,
                current=current_count,
                limit=limit,
                retry_after=retry_after,
            )
            return RateLimitResult(
                allowed=False,
                retry_after=retry_after,
                remaining=0,
                limit=limit,
                reset_at=oldest + window_seconds,
            )

        # Record this request
        store.append(now)

        log.debug(
            "rate_limit.allowed",
            user_id=user_id,
            current=current_count + 1,
            limit=limit,
            remaining=max(0, limit - current_count - 1),
        )
        return RateLimitResult(
            allowed=True,
            retry_after=None,
            remaining=max(0, limit - current_count - 1),
            limit=limit,
            reset_at=(store[0] + window_seconds) if store else None,
        )
