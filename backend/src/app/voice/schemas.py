"""Pydantic schemas for Voice Recording & Audio Intelligence (Phase 13)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VoiceRecordingCreate(BaseModel):
    """Payload to create or persist a voice recording note."""

    title: str | None = Field(default=None, max_length=255)
    transcript: str = Field(..., min_length=1, description="Transcribed spoken text")
    summary: str | None = Field(default=None, description="Concise executive summary")
    language: str | None = Field(default="en", max_length=20)
    audio_url: str | None = Field(default=None, description="Data URI or audio URL")
    duration_seconds: float | None = Field(default=None, ge=0)
    voice_model: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = Field(default=None, description="List of category/topic tags")


class VoiceRecordingUpdate(BaseModel):
    """Payload to patch a voice recording note."""

    title: str | None = Field(default=None, max_length=255)
    transcript: str | None = Field(default=None, min_length=1)
    summary: str | None = Field(default=None)
    language: str | None = Field(default=None, max_length=20)
    tags: list[str] | None = Field(default=None)


class VoiceRecordingResponse(BaseModel):
    """Response containing a single voice recording."""

    recording: dict[str, Any]


class VoiceRecordingListResponse(BaseModel):
    """Response containing a list of voice recordings."""

    recordings: list[dict[str, Any]]
    total: int


class VoiceTranscribeRequest(BaseModel):
    """Payload to transcribe audio and optionally persist as a voice note."""

    audio_data: str = Field(..., description="Base64-encoded audio payload")
    language: str | None = Field(default=None, description="Language hint e.g. en, ur, es")
    model: str | None = Field(default="whisper", description="whisper, gemini, or deepgram")
    save_as_note: bool = Field(default=False, description="Persist transcript as a voice note")
    title: str | None = Field(default=None, description="Optional custom title if saving as note")


class VoiceTranscribeResponse(BaseModel):
    """Response from speech-to-text audio ingestion."""

    text: str
    language: str | None = None
    confidence: float | None = None
    duration_seconds: float | None = None
    recording_id: str | None = None


class VoiceSynthesizeRequest(BaseModel):
    """Payload to synthesize speech from text."""

    text: str = Field(..., min_length=1, max_length=5000)
    voice: str | None = Field(default=None, description="e.g. Kore, Puck, Alloy, Echo")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    model: str | None = Field(default="gemini", description="gemini, openai, or elevenlabs")
    modulation: str | None = Field(
        default=None,
        description="Voice tone modulation: normal, whispering, excited, dramatic, calm, shouting",
    )


class VoiceSynthesizeResponse(BaseModel):
    """Response from text-to-speech audio synthesis."""

    audio_data: str
    format: str = "mp3"
    duration_seconds: float | None = None
    model: str


class VoiceEnhanceRequest(BaseModel):
    """Payload to extract summary and action items from voice transcript."""

    transcript: str = Field(..., min_length=1)


class VoiceEnhanceResponse(BaseModel):
    """Enhanced audio intelligence metadata."""

    title: str
    summary: str
    action_items: list[str]
    key_topics: list[str]
