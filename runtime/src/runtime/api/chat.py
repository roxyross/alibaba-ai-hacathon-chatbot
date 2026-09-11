"""POST /api/v1/runtime/chat — the runtime's main entry point.

Spec §3 (PR 2 deliverable): a user sends a message; the Coordinator
classifies it, routes to a specialist, and returns a labelled reply.

The endpoint is the seam between the HTTP layer and the Coordinator.
It validates the JWT, rate-limits, hands off, and serializes the
CoordinatorResult back to JSON.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from runtime.coordinator.router import Coordinator, CoordinatorResult, security_check
from runtime.infrastructure.auth import AuthError, UserContext, decode_bearer
from runtime.infrastructure.rate_limiter import RateLimitResult, check_rate_limit

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    user_id: str | None = None
    needs_clarification: bool
    agent_slug: str | None
    response: str | None
    citations: list[str]
    status: str  # "ok" | "timeout" | "error" | "uncertain" | "agent_disabled"
    next_actions: list[str]


class SecurityCheckRequest(BaseModel):
    skill_slug: str = Field(..., min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class SecurityCheckResponse(BaseModel):
    verdict: str  # "clear" | "caution" | "block" | "error"
    warning: str
    recommendation: str | None


def _coordinator_dep(request: Request) -> Coordinator:
    """Pull the Coordinator off app state.

    Each FastAPI request has a `request.app.state` populated by
    `create_app()` at startup. We do not use a module-level singleton
    so that the runtime can be instantiated multiple times in tests
    with different registries.
    """
    coord: Coordinator | None = getattr(request.app.state, "coordinator", None)
    if coord is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime is not initialized yet",
        )
    return coord


def _user_dep(
    authorization: Annotated[str | None, Header()] = None,
) -> UserContext:
    try:
        return decode_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


async def _rate_limit_dep(
    response: Response,
    user: Annotated[UserContext, Depends(_user_dep)],
) -> UserContext:
    """Per-user rate limit check (spec §10.7: 60 msg/min on /api/v1/runtime/chat).

    Runs after _user_dep so we have the user_id. Sets X-RateLimit-* response
    headers on every request, and raises HTTPException 429 when the limit is
    exceeded.
    """
    result: RateLimitResult = await check_rate_limit(user.user_id)
    # Always set rate limit headers so clients can introspect
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    if result.reset_at is not None:
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: {result.limit} messages per minute. "
                f"Retry after {result.retry_after:.0f} seconds."
            ),
            headers={"Retry-After": str(int(result.retry_after or 60))},
        )
    return user


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    response: Response,
    user: Annotated[UserContext, Depends(_rate_limit_dep)],
    coord: Annotated[Coordinator, Depends(_coordinator_dep)],
) -> ChatResponse:
    # Forward the caller's bearer token to the gateway so the gateway
    # can attribute the LLM call to the same user. We do not strip it
    # or mint a new one — the gateway validates the same token.
    auth_header = request.headers.get("authorization")
    bearer: str | None = None
    if auth_header and auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip() or None

    from runtime.infrastructure.gateway_client import current_bearer_token
    current_bearer_token.set(bearer)

    result: CoordinatorResult = await coord.handle(
        body.message,
        user_id=user.user_id,
        session_id=body.session_id,
        bearer_token=bearer,
    )
    return ChatResponse(
        user_id=user.user_id,
        needs_clarification=result.needs_clarification,
        agent_slug=result.agent_slug,
        response=result.response,
        citations=result.citations,
        status=result.status,
        next_actions=result.next_actions,
    )


@router.post("/security-check", response_model=SecurityCheckResponse)
async def route_security_check(
    body: SecurityCheckRequest,
    request: Request,
    user: Annotated[UserContext, Depends(_user_dep)],
    coord: Annotated[Coordinator, Depends(_coordinator_dep)],
) -> SecurityCheckResponse:
    """Direct security review for a proposed sensitive action.

    Invokes the security-privacy internal agent to review the action
    and returns a verdict (clear / caution / block) with a warning.
    """
    auth_header = request.headers.get("authorization")
    bearer: str | None = None
    if auth_header and auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip() or None

    from runtime.coordinator.router import (
        SecurityCheckRequest as CoordinatorSecurityCheckRequest,
    )

    result = await security_check(
        coord,
        CoordinatorSecurityCheckRequest(
            skill_slug=body.skill_slug,
            inputs=body.inputs,
            user_id=user.user_id,
            bearer_token=bearer,
        ),
    )
    return SecurityCheckResponse(
        verdict=result.get("verdict", "error"),
        warning=result.get("warning", result.get("error", "")),
        recommendation=result.get("recommendation"),
    )
