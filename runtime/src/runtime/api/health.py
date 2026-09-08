"""Health endpoints — /health/live and /health/ready.

Spec §11.4: every service exposes /health/live and /health/ready.
  - /health/live: the process is up. No external checks.
  - /health/ready: the process is up AND the registries are populated
    AND the gateway is reachable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from runtime.agents.registry import AgentRegistry
from runtime.infrastructure.gateway_client import GatewayClient, GatewayError
from runtime.skills.registry import SkillRegistry

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict:
    return {"status": "ok", "service": "runtime"}


@router.get("/health/ready")
async def ready(request: Request) -> dict:
    agent_reg: AgentRegistry | None = getattr(request.app.state, "agent_registry", None)
    skill_reg: SkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    gateway: GatewayClient | None = getattr(request.app.state, "gateway_client", None)

    agents_loaded = len(agent_reg) if agent_reg else 0
    skills_loaded = len(skill_reg) if skill_reg else 0

    gateway_ok = True
    gateway_error: str | None = None
    if gateway is not None:
        try:
            # The simplest reachability check: see if the gateway returns
            # anything at all on a no-op (it'll 405 or 422; either way
            # it's reachable). A real readiness probe against the
            # gateway's /health/live is a TODO for PR 3.
            import httpx
            from runtime.config import settings

            async with httpx.AsyncClient(timeout=2.0) as c:
                r = await c.get(f"{settings.backend_base_url}/health/live")
                gateway_ok = r.status_code < 500
        except (httpx.HTTPError, GatewayError) as exc:
            gateway_ok = False
            gateway_error = str(exc)

    status = "ok" if agents_loaded > 0 and gateway_ok else "degraded"
    return {
        "status": status,
        "service": "runtime",
        "agents_loaded": agents_loaded,
        "skills_loaded": skills_loaded,
        "gateway_reachable": gateway_ok,
        "gateway_error": gateway_error,
    }
