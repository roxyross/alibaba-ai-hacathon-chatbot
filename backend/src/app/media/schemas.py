"""Pydantic schemas for unified Media Registry, Generation Jobs, and Asset Library."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MediaModelCapability(BaseModel):
    """Declared capabilities and parameter constraints for a creative media model."""

    id: str
    name: str
    provider: str  # "google", "pollinations", "replicate", etc.
    media_type: str  # "image" | "video"
    badge: str
    description: str
    supported_aspect_ratios: list[str]
    supported_resolutions: list[str]
    supported_durations: list[int] = Field(default_factory=list)
    supported_inputs: list[str] = Field(default_factory=lambda: ["text"])  # "text", "image", "video"
    supports_negative_prompt: bool = False
    supports_guidance_scale: bool = False
    supports_seed: bool = True
    supports_audio: bool = False
    supports_camera_motion: bool = False
    supports_first_frame: bool = False
    supports_last_frame: bool = False
    credit_cost: int = 1
    is_available: bool = True
    availability_reason: str = "Ready for synthesis"


class MediaModelListResponse(BaseModel):
    """Available models across both Image and Video creative suites."""

    models: list[MediaModelCapability]


class MediaGenerateRequest(BaseModel):
    """Payload to initiate a creative media generation job."""

    media_type: str = Field(default="image")  # "image" | "video"
    provider: str = Field(default="google")
    model: str = Field(default="imagen-3.0-generate-002")
    prompt: str = Field(..., min_length=2, max_length=4000)
    negative_prompt: str | None = None
    aspect_ratio: str = Field(default="1:1")
    resolution: str = Field(default="1024x1024")
    quality: str = Field(default="High")
    duration: int = Field(default=5)
    fps: int = Field(default=24)
    audio: bool = Field(default=True)
    seed: int | None = None
    style_preset: str = Field(default="photorealistic")
    first_frame_url: str | None = None
    last_frame_url: str | None = None
    reference_images: list[str] = Field(default_factory=list)
    mask_image: str | None = None

    model_config = {"extra": "allow"}


class MediaJobResponse(BaseModel):
    """Asynchronous generation job state and progress metadata."""

    id: str
    user_id: str
    media_type: str
    provider: str
    model: str
    prompt: str
    status: str  # "queued", "processing", "completed", "failed"
    progress: int = 0
    media_url: str | None = None
    thumbnail_url: str | None = None
    error_message: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    completed_at: str | None = None


class MediaJobListResponse(BaseModel):
    """List of recent media generation jobs."""

    jobs: list[MediaJobResponse]


class MediaAssetResponse(BaseModel):
    """A persistent item in the user's Media Asset Library."""

    id: str
    title: str
    media_type: str
    source_type: str
    url: str
    thumbnail_url: str | None = None
    prompt: str | None = None
    model: str | None = None
    provider: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    file_size_bytes: int | None = None
    is_favorite: bool = False
    tags: list[str] = Field(default_factory=list)
    created_at: str


class MediaAssetListResponse(BaseModel):
    """List of media assets in the library."""

    assets: list[MediaAssetResponse]
