"""Settings and Preferences Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SettingsResponse(BaseModel):
    """User settings representation."""

    model_config = ConfigDict(from_attributes=True)

    theme: str = "dark"
    custom_persona: str = ""
    stream_speed: str = "fast"
    sound_effects: bool = True
    auto_scroll: bool = True
    voice_id: str = "aura-asteria-en"
    preferred_provider: str | None = None


class SettingsUpdateRequest(BaseModel):
    """Update user settings payload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    theme: str | None = Field(default=None, max_length=20)
    custom_persona: str | None = None
    stream_speed: str | None = Field(default=None, max_length=20)
    sound_effects: bool | None = None
    auto_scroll: bool | None = None
    voice_id: str | None = Field(default=None, max_length=50)
    preferred_provider: str | None = Field(default=None, max_length=50)
