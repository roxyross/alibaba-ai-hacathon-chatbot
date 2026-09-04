"""Re-export of the AI-gateway provider-health endpoints under /providers/*.

Keeps the existing /ai/providers/* endpoints functional while exposing a
cleaner import path for the frontend (e.g. /api/v1/providers/health).
"""

from __future__ import annotations

from fastapi import APIRouter

# The real provider routes live in app.api.v1.ai. We re-export them so that
# frontend code (and tests) can import from a stable path while we keep the
# existing routes intact.
from app.api.v1.ai import router as _ai_router

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/health", include_in_schema=True)
async def providers_health():
    """Re-export of /ai/providers/health."""
    # Delegate by calling the underlying route handler.
    from app.api.v1.ai import health_check

    return await health_check()


# Re-include the toggle and list endpoints so /api/v1/providers/* mirrors
# the AI-gateway surface. Using simple proxy handlers avoids a hard refactor.
@router.get("", include_in_schema=True)
async def providers_list():
    from app.api.v1.ai import list_providers
    return await list_providers()


@router.patch("/{name}", include_in_schema=True)
async def providers_toggle(name: str):
    from app.api.v1.ai import toggle_provider
    return await toggle_provider(name)
