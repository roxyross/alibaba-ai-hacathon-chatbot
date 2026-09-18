"""Voice & Real-Time Audio Intelligence API router (Phase 13).

Provides multi-tenant voice notes persistence, speech-to-text ingestion,
text-to-speech synthesis, transcript enhancement, and voice catalog metadata.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.voice.repository import VoiceRepository
from app.voice.schemas import (
    VoiceEnhanceRequest,
    VoiceEnhanceResponse,
    VoiceRecordingCreate,
    VoiceRecordingListResponse,
    VoiceRecordingResponse,
    VoiceRecordingUpdate,
    VoiceSynthesizeRequest,
    VoiceSynthesizeResponse,
    VoiceTranscribeRequest,
    VoiceTranscribeResponse,
)
from app.voice.service import VoiceService

log = structlog.get_logger()

router = APIRouter(prefix="/voice", tags=["voice"])

_repo = VoiceRepository()
_service = VoiceService(repo=_repo)


# ---------------------------------------------------------------------------
# GET /api/v1/voice/recordings
# ---------------------------------------------------------------------------

@router.get("/recordings", response_model=VoiceRecordingListResponse)
async def list_recordings(
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> VoiceRecordingListResponse:
    """List all voice recording notes belonging to the authenticated user."""
    items = await _repo.list_recordings(
        user_id=current_user.id,
        limit=limit,
        search=search,
        tag=tag,
    )
    return VoiceRecordingListResponse(recordings=items, total=len(items))


# ---------------------------------------------------------------------------
# POST /api/v1/voice/recordings
# ---------------------------------------------------------------------------

@router.post("/recordings", response_model=VoiceRecordingResponse, status_code=status.HTTP_201_CREATED)
async def create_recording(
    payload: VoiceRecordingCreate,
    current_user: User = Depends(get_current_user),
) -> VoiceRecordingResponse:
    """Create and persist a new voice recording note for the authenticated user."""
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Transcript cannot be empty",
        )

    title = payload.title
    summary = payload.summary
    tags = payload.tags

    # Automatically derive title & summary if omitted
    if not title or not summary:
        enhanced = _service.enhance_transcript(transcript)
        title = title or enhanced["title"]
        summary = summary or enhanced["summary"]
        if not tags:
            tags = enhanced["key_topics"]

    created = await _repo.create_recording(
        user_id=current_user.id,
        data={
            "title": title,
            "transcript": transcript,
            "summary": summary,
            "language": payload.language or "en",
            "audio_url": payload.audio_url,
            "duration_seconds": payload.duration_seconds,
            "voice_model": payload.voice_model,
            "tags": tags,
        },
    )
    return VoiceRecordingResponse(recording=created)


# ---------------------------------------------------------------------------
# GET /api/v1/voice/recordings/{id}
# ---------------------------------------------------------------------------

@router.get("/recordings/{recording_id}", response_model=VoiceRecordingResponse)
async def get_recording(
    recording_id: str,
    current_user: User = Depends(get_current_user),
) -> VoiceRecordingResponse:
    """Retrieve a single voice recording note (strictly isolated to owner)."""
    rec = await _repo.get_recording(user_id=current_user.id, recording_id=recording_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice recording not found",
        )
    return VoiceRecordingResponse(recording=rec)


# ---------------------------------------------------------------------------
# PATCH /api/v1/voice/recordings/{id}
# ---------------------------------------------------------------------------

@router.patch("/recordings/{recording_id}", response_model=VoiceRecordingResponse)
async def update_recording(
    recording_id: str,
    payload: VoiceRecordingUpdate,
    current_user: User = Depends(get_current_user),
) -> VoiceRecordingResponse:
    """Update an existing voice recording note (strictly isolated to owner)."""
    existing = await _repo.get_recording(user_id=current_user.id, recording_id=recording_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice recording not found",
        )

    update_data: dict[str, Any] = {}
    if payload.title is not None:
        update_data["title"] = payload.title
    if payload.transcript is not None:
        update_data["transcript"] = payload.transcript
    if payload.summary is not None:
        update_data["summary"] = payload.summary
    if payload.language is not None:
        update_data["language"] = payload.language
    if payload.tags is not None:
        update_data["tags"] = payload.tags

    updated = await _repo.update_recording(
        user_id=current_user.id,
        recording_id=recording_id,
        data=update_data,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice recording not found",
        )
    return VoiceRecordingResponse(recording=updated)


# ---------------------------------------------------------------------------
# DELETE /api/v1/voice/recordings/{id}
# ---------------------------------------------------------------------------

@router.delete("/recordings/{recording_id}")
async def delete_recording(
    recording_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a voice recording note (strictly isolated to owner)."""
    deleted = await _repo.delete_recording(user_id=current_user.id, recording_id=recording_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice recording not found",
        )
    return {"deleted": True, "id": recording_id}


# ---------------------------------------------------------------------------
# POST /api/v1/voice/transcribe
# ---------------------------------------------------------------------------

@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_voice(
    payload: VoiceTranscribeRequest,
    current_user: User = Depends(get_current_user),
) -> VoiceTranscribeResponse:
    """Ingest audio data, transcribe via STT, and optionally save as a voice note."""
    res = await _service.transcribe_audio(
        audio_data=payload.audio_data,
        language=payload.language,
        model=payload.model,
        save_as_note=payload.save_as_note,
        title=payload.title,
        user_id=current_user.id,
    )
    return VoiceTranscribeResponse(
        text=res["text"],
        language=res["language"],
        confidence=res["confidence"],
        duration_seconds=res["duration_seconds"],
        recording_id=res["recording_id"],
    )


# ---------------------------------------------------------------------------
# POST /api/v1/voice/synthesize
# ---------------------------------------------------------------------------

@router.post("/synthesize", response_model=VoiceSynthesizeResponse)
async def synthesize_speech(
    payload: VoiceSynthesizeRequest,
    current_user: User = Depends(get_current_user),
) -> VoiceSynthesizeResponse:
    """Synthesize text into speech audio with steerable voice personas."""
    res = await _service.synthesize_speech(
        text=payload.text,
        voice=payload.voice,
        speed=payload.speed,
        model=payload.model,
        modulation=payload.modulation,
    )
    return VoiceSynthesizeResponse(
        audio_data=res["audio_data"],
        format=res["format"],
        duration_seconds=res["duration_seconds"],
        model=res["model"],
    )


# ---------------------------------------------------------------------------
# POST /api/v1/voice/enhance
# ---------------------------------------------------------------------------

@router.post("/enhance", response_model=VoiceEnhanceResponse)
async def enhance_voice_transcript(
    payload: VoiceEnhanceRequest,
    current_user: User = Depends(get_current_user),
) -> VoiceEnhanceResponse:
    """Enhance voice transcript with AI executive summary, action items, and title."""
    enhanced = _service.enhance_transcript(payload.transcript)
    return VoiceEnhanceResponse(
        title=enhanced["title"],
        summary=enhanced["summary"],
        action_items=enhanced["action_items"],
        key_topics=enhanced["key_topics"],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/voice/voices
# ---------------------------------------------------------------------------

@router.get("/voices")
async def list_available_voices(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve catalog of available voice models, personas, and tone modulations."""
    return _service.get_available_voices()
