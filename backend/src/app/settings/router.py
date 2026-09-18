"""Settings routes: GET and PATCH /settings for current user."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.settings.repository import SettingsRepository
from app.settings.schemas import SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])
_repo = SettingsRepository()


def _to_response(row: Any) -> SettingsResponse:
    return SettingsResponse(
        theme=getattr(row, "theme", "dark") or "dark",
        custom_persona=getattr(row, "custom_persona", "") or "",
        stream_speed=getattr(row, "stream_speed", "fast") or "fast",
        sound_effects=bool(getattr(row, "sound_effects", True)),
        auto_scroll=bool(getattr(row, "auto_scroll", True)),
        voice_id=getattr(row, "voice_id", "aura-asteria-en") or "aura-asteria-en",
        preferred_provider=getattr(row, "preferred_provider", None),
    )


@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: Annotated[User, Depends(get_current_user)],
) -> SettingsResponse:
    """Retrieve settings for the current authenticated user."""
    row = await _repo.get_for_user(current_user.id)
    return _to_response(row)


@router.patch("", response_model=SettingsResponse)
@router.put("", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> SettingsResponse:
    """Update settings for the current authenticated user."""
    row = await _repo.update_for_user(current_user.id, payload)
    return _to_response(row)
