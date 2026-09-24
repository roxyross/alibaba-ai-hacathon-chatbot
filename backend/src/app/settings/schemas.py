"""Settings and Preferences Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SettingsResponse(BaseModel):
    """User settings representation across all 10 settings tabs."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    theme: str = "dark"
    custom_persona: str = ""
    stream_speed: str = "fast"
    sound_effects: bool = True
    auto_scroll: bool = True
    voice_id: str = "aura-asteria-en"
    preferred_provider: str | None = None
    extra_settings: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdateRequest(BaseModel):
    """Update user settings payload across all 10 settings tabs."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="allow")

    theme: str | None = Field(default=None, max_length=20)
    custom_persona: str | None = None
    stream_speed: str | None = Field(default=None, max_length=20)
    sound_effects: bool | None = None
    auto_scroll: bool | None = None
    voice_id: str | None = Field(default=None, max_length=50)
    preferred_provider: str | None = Field(default=None, max_length=50)
    extra_settings: dict[str, Any] | None = None

