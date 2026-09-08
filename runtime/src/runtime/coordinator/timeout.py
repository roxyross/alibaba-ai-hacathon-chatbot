"""Per-specialist timeout.

Spec §3.2: each specialist gets a 30-second response budget. On
timeout, the Coordinator returns a "specialist is taking too long"
message and offers the user alternatives. Spec §10.2 distinguishes
a timeout (the budget elapsed) from a crash (an exception in the
executor) — they are handled separately.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


class SpecialistTimeout(Exception):
    """Raised when a specialist exceeds its response budget."""

    def __init__(self, agent_slug: str, elapsed: float, budget: float) -> None:
        super().__init__(
            f"{agent_slug} exceeded {budget:.0f}s budget (elapsed {elapsed:.1f}s)"
        )
        self.agent_slug = agent_slug
        self.elapsed = elapsed
        self.budget = budget


async def with_specialist_budget(
    coro_factory: Awaitable[T],
    *,
    agent_slug: str,
    budget_seconds: float,
) -> T:
    """Run a specialist coroutine with a wall-clock budget.

    Uses `asyncio.wait_for` so cancellation propagates cleanly. The
    inner coroutine receives a `CancelledError` on timeout; it may
    choose to swallow it (e.g. to release resources) but the caller
    gets a `SpecialistTimeout` regardless.
    """
    try:
        return await asyncio.wait_for(coro_factory, timeout=budget_seconds)
    except asyncio.TimeoutError as exc:
        # asyncio.wait_for does not surface the elapsed time directly;
        # the caller's logging is the only place to record it. We don't
        # have it here; the router logs it after.
        raise SpecialistTimeout(agent_slug, elapsed=budget_seconds, budget=budget_seconds) from exc
