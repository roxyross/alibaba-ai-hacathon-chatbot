"""Settings and Preferences Pydantic schemas across all 15 sections."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SettingsResponse(BaseModel):
    """User settings representation across all 15 settings sections."""

    model_config = ConfigDict(from_attributes=True, extra="allow")

    # 1. Profile & Appearance
    theme: str = "dark"
    accent_color: str = "Teal"
    bubble_style: str = "Modern Cards"
    font_size: str = "Normal"
    display_name: str | None = None
    bio: str | None = None
    timezone: str | None = None
    avatar_url: str | None = None

    # 2. AI Persona & Instructions
    custom_persona: str = ""
    tone: str = "Balanced"
    temperature: float = 0.7
    response_length: str = "Standard"

    # 3. Models & Providers
    preferred_provider: str | None = None
    default_chat_model: str = "gemini-3.8-flash"
    stream_speed: str = "fast"
    auto_scroll: bool = True

    # 4. Voice & Audio
    voice_id: str = "aura-asteria-en"
    speech_speed: float = 1.0
    auto_play_audio: bool = False
    sound_effects: bool = True

    # 5. Global Image Generation Defaults
    image_default_provider: str = "google"
    image_default_model: str = "imagen-3.0-generate-002"
    image_default_quality: str = "High"
    image_default_resolution: str = "1024x1024"
    image_default_aspect_ratio: str = "1:1"
    image_default_count: int = 1
    image_style_preset: str = "photorealistic"
    image_character_consistency: bool = False

    # 6. Global Video Generation Defaults
    video_default_provider: str = "google"
    video_default_model: str = "veo-3.1-generate-preview"
    video_default_resolution: str = "1080p"
    video_default_aspect_ratio: str = "16:9"
    video_default_duration: int = 5
    video_default_audio: bool = True
    video_default_quality: str = "High"

    # 7. Notifications
    email_digests: bool = True
    job_alerts: bool = True
    budget_alerts: bool = True
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"

    # 8. Privacy & Data
    allow_learning: bool = False
    store_voice_recordings: bool = True
    store_generation_prompts: bool = True
    retention_days: str = "forever"

    # 9. Security
    two_factor_enabled: bool = False
    session_timeout_minutes: int = 1440

    # 10. Connected Accounts
    connected_google: bool = True
    connected_github: bool = False
    connected_apple: bool = False

    # 11. BYOK API Keys
    byok_gemini: str | None = None
    byok_openai: str | None = None
    byok_anthropic: str | None = None
    byok_flux: str | None = None

    # 12. Memory & Context
    auto_memory_extraction: bool = True
    context_window: str = "32k"

    extra_settings: dict[str, Any] = Field(default_factory=dict)


class SettingsUpdateRequest(BaseModel):
    """Update user settings payload across all 15 settings sections."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="allow")

    # 1. Profile & Appearance
    theme: str | None = Field(default=None, max_length=20)
    accent_color: str | None = None
    bubble_style: str | None = None
    font_size: str | None = None
    display_name: str | None = None
    bio: str | None = None
    timezone: str | None = None
    avatar_url: str | None = None

    # 2. AI Persona
    custom_persona: str | None = None
    tone: str | None = None
    temperature: float | None = None
    response_length: str | None = None

    # 3. Models
    preferred_provider: str | None = Field(default=None, max_length=50)
    default_chat_model: str | None = None
    stream_speed: str | None = Field(default=None, max_length=20)
    auto_scroll: bool | None = None

    # 4. Voice
    voice_id: str | None = Field(default=None, max_length=50)
    speech_speed: float | None = None
    auto_play_audio: bool | None = None
    sound_effects: bool | None = None

    # 5. Image Generation Defaults
    image_default_provider: str | None = None
    image_default_model: str | None = None
    image_default_quality: str | None = None
    image_default_resolution: str | None = None
    image_default_aspect_ratio: str | None = None
    image_default_count: int | None = None
    image_style_preset: str | None = None
    image_character_consistency: bool | None = None

    # 6. Video Generation Defaults
    video_default_provider: str | None = None
    video_default_model: str | None = None
    video_default_resolution: str | None = None
    video_default_aspect_ratio: str | None = None
    video_default_duration: int | None = None
    video_default_audio: bool | None = None
    video_default_quality: str | None = None

    # 7. Notifications
    email_digests: bool | None = None
    job_alerts: bool | None = None
    budget_alerts: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None

    # 8. Privacy
    allow_learning: bool | None = None
    store_voice_recordings: bool | None = None
    store_generation_prompts: bool | None = None
    retention_days: str | None = None

    # 9. Security
    two_factor_enabled: bool | None = None
    session_timeout_minutes: int | None = None

    # 10. Connected Accounts
    connected_google: bool | None = None
    connected_github: bool | None = None
    connected_apple: bool | None = None

    # 11. BYOK
    byok_gemini: str | None = None
    byok_openai: str | None = None
    byok_anthropic: str | None = None
    byok_flux: str | None = None

    # 12. Memory
    auto_memory_extraction: bool | None = None
    context_window: str | None = None

    extra_settings: dict[str, Any] | None = None
