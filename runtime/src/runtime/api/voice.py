"""Voice session WebSocket API.

Per spec §3.6: The Voice Agent owns the full voice session lifecycle:
- Streaming STT in (user speaks → transcript) via Google Cloud Speech-to-Text
- Streaming TTS out (agent speaks → audio) via Google Cloud TTS
- Turn-taking and interruption handling
- Session end: summarize and optionally store in memory

This module exposes:
  WebSocket /api/v1/runtime/voice  — voice session endpoint
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from runtime.infrastructure.auth import decode_bearer, AuthError
from runtime.skills.speech_to_text import speech_to_text
from runtime.skills.text_to_speech import text_to_speech

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/runtime", tags=["voice"])

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


class VoiceSessionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ENDED = "ended"


@dataclass
class VoiceSession:
    """Per-connection voice session state."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    state: VoiceSessionState = VoiceSessionState.IDLE
    turns: list[dict] = field(default_factory=list)  # conversation history
    language: str = "en"
    interrupt_requested: bool = False


# In-flight sessions: session_id -> session
_sessions: dict[str, VoiceSession] = {}
_session_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# WebSocket message schemas (JSON over WS)
# ---------------------------------------------------------------------------


class WSAudioMessage(BaseModel):
    """Client → Server: audio chunk for STT."""

    type: str = "audio"
    data: str  # base64-encoded audio
    chunk_index: int = 0
    is_final: bool = False


class WSTextMessage(BaseModel):
    """Client → Server: text input (fallback / TTY mode)."""

    type: str = "text"
    text: str


class WSInterruptMessage(BaseModel):
    """Client → Server: user interrupted the agent."""

    type: str = "interrupt"


class WSEndMessage(BaseModel):
    """Client → Server: session end requested."""

    type: str = "end"
    store_memory: bool = False


class WSServerTranscript(BaseModel):
    """Server → Client: STT transcript (interim or final)."""

    type: str = "transcript"
    text: str
    is_final: bool
    confidence: float | None = None


class WSServerAudio(BaseModel):
    """Server → Client: TTS audio chunk."""

    type: str = "audio"
    data: str  # base64-encoded audio (or None for stub)
    is_final: bool
    duration_seconds: float | None = None


class WSServerState(BaseModel):
    """Server → Client: session state update."""

    type: str = "state"
    state: str
    session_id: str


class WSServerEnd(BaseModel):
    """Server → Client: session ended."""

    type: str = "end"
    summary: str | None = None
    memory_stored: bool = False


class WSServerError(BaseModel):
    """Server → Client: error."""

    type: str = "error"
    message: str


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


async def _get_user_from_query(token: str | None) -> str:
    """Validate JWT and return user_id. Raises if invalid."""
    if not token:
        raise ValueError("Missing auth token")
    try:
        ctx = decode_bearer(f"Bearer {token}")
    except AuthError as exc:
        raise ValueError(str(exc)) from exc
    return ctx.user_id


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/voice")
async def voice_session(websocket: WebSocket):
    """WebSocket voice session endpoint.

    Protocol (JSON messages, bidirectional):

    Client → Server:
      { "type": "audio", "data": "<base64>", chunk_index: 0, is_final: false }
      { "type": "text", "text": "hello" }
      { "type": "interrupt" }
      { "type": "end", "store_memory": false }

    Server → Client:
      { "type": "transcript", "text": "...", "is_final": true, "confidence": 0.95 }
      { "type": "audio", "data": "<base64>", "is_final": false }
      { "type": "state", "state": "listening", "session_id": "..." }
      { "type": "end", "summary": "...", "memory_stored": false }
      { "type": "error", "message": "..." }

    Auth: first client message must include { "type": "auth", "token": "<jwt>" }.
    The token is validated before the session proceeds.
    """
    await websocket.accept()
    session: VoiceSession | None = None
    session_id: str | None = None

    try:
        # ---- 1. Auth handshake (first message must be auth) ---------------
        raw = await websocket.receive_text()
        init = json.loads(raw)

        if init.get("type") != "auth":
            await _send_json(websocket, {"type": "error", "message": "First message must be auth"})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        token = init.get("token")
        try:
            user_id = await _get_user_from_query(token)
        except ValueError as exc:
            await _send_json(websocket, {"type": "error", "message": str(exc)})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        session = VoiceSession(user_id=user_id)
        session_id = session.session_id
        async with _session_lock:
            _sessions[session_id] = session

        await _send_json(
            websocket,
            {"type": "state", "state": VoiceSessionState.IDLE.value, "session_id": session_id},
        )
        log.info("voice.session.started", session_id=session_id, user_id=user_id)

        # ---- 2. Session loop -----------------------------------------------
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "auth":
                await _send_json(websocket, {"type": "error", "message": "Already authenticated"})
                continue

            if msg_type == "interrupt":
                session.interrupt_requested = True
                session.state = VoiceSessionState.IDLE
                await _send_json(
                    websocket,
                    {"type": "state", "state": VoiceSessionState.IDLE.value, "session_id": session_id},
                )
                log.info("voice.session.interrupted", session_id=session_id)
                continue

            if msg_type == "end":
                store_memory = msg.get("store_memory", False)
                summary = _generate_summary(session)
                session.state = VoiceSessionState.ENDED
                await _send_json(
                    websocket,
                    {
                        "type": "end",
                        "summary": summary,
                        "memory_stored": store_memory,
                    },
                )
                log.info(
                    "voice.session.ended",
                    session_id=session_id,
                    user_id=user_id,
                    turns=len(session.turns),
                    store_memory=store_memory,
                )
                break

            if msg_type == "audio":
                await _handle_audio(websocket, session, msg, websocket.app.state.coordinator, token)
                continue

            if msg_type == "text":
                await _handle_text(websocket, session, msg)
                continue

            await _send_json(websocket, {"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        log.info("voice.session.disconnected", session_id=session_id)
    except Exception as exc:
        log.error("voice.session.error", session_id=session_id, error=str(exc), exc_info=True)
        try:
            await _send_json(websocket, {"type": "error", "message": "Internal error"})
        except Exception:
            pass
    finally:
        if session_id:
            async with _session_lock:
                _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------


async def _handle_audio(
    websocket: WebSocket,
    session: VoiceSession,
    msg: dict,
    coordinator,  # Coordinator
    bearer_token: str,
) -> None:
    """Process an audio chunk: STT → route to Voice Agent → TTS → stream back."""
    session.state = VoiceSessionState.PROCESSING
    await _send_json(
        websocket,
        {"type": "state", "state": VoiceSessionState.PROCESSING.value, "session_id": session.session_id},
    )

    # ---- STT: speech_to_text skill ----------------------------------------
    audio_b64 = msg.get("data", "")
    stt_result = await speech_to_text(
        audio_data=audio_b64 or None,
        session_id=session.session_id,
        language=session.language,
        interim=False,
        user_id=session.user_id,
    )

    if not stt_result.ok:
        await _send_json(
            websocket,
            {"type": "error", "message": f"STT failed: {stt_result.error}"},
        )
        session.state = VoiceSessionState.IDLE
        await _send_json(
            websocket,
            {"type": "state", "state": VoiceSessionState.IDLE.value, "session_id": session.session_id},
        )
        return

    transcripts: list[dict] = stt_result.data.get("transcripts", [])  # type: ignore[union-attr]
    if not transcripts:
        # No speech detected
        session.state = VoiceSessionState.IDLE
        await _send_json(
            websocket,
            {"type": "state", "state": VoiceSessionState.IDLE.value, "session_id": session.session_id},
        )
        return

    # Use the final transcript
    top = next((t for t in transcripts if t.get("is_final")), transcripts[-1])
    transcript_text = top.get("text", "")
    await _send_json(
        websocket,
        {
            "type": "transcript",
            "text": transcript_text,
            "is_final": True,
            "confidence": top.get("confidence"),
        },
    )
    session.turns.append({"role": "user", "content": transcript_text})

    # ---- Coordinator: route transcript to the right agent ---------------
    coord_result = await coordinator.handle(
        transcript_text,
        user_id=session.user_id,
        session_id=session.session_id,
        bearer_token=bearer_token,
    )

    if coord_result.needs_clarification:
        response_text = (
            "I'm not sure which agent can handle that. "
            "Could you rephrase or be more specific?"
        )
    elif coord_result.status in ("timeout", "error"):
        response_text = (
            f"Something went wrong on my end. "
            f"Status: {coord_result.status}. "
            "Would you like to try again?"
        )
    else:
        response_text = coord_result.response or ""

    session.turns.append({"role": "assistant", "content": response_text})

    # ---- TTS: text_to_speech skill ----------------------------------------
    tts_result = await text_to_speech(
        text=response_text,
        user_id=session.user_id,
    )

    if not tts_result.ok:
        await _send_json(
            websocket,
            {"type": "error", "message": f"TTS failed: {tts_result.error}"},
        )
        session.state = VoiceSessionState.IDLE
        await _send_json(
            websocket,
            {"type": "state", "state": VoiceSessionState.IDLE.value, "session_id": session.session_id},
        )
        return

    tts_data: dict = tts_result.data  # type: ignore[assignment]
    await _send_json(
        websocket,
        {
            "type": "audio",
            "data": tts_data.get("audio_data"),
            "is_final": True,
            "duration_seconds": tts_data.get("duration_seconds"),
        },
    )

    session.state = VoiceSessionState.IDLE
    await _send_json(
        websocket,
        {"type": "state", "state": VoiceSessionState.IDLE.value, "session_id": session.session_id},
    )


async def _handle_text(websocket: WebSocket, session: VoiceSession, msg: dict) -> None:
    """Process a text input (TTY fallback / typed voice mode)."""
    text = msg.get("text", "").strip()
    if not text:
        return

    session.state = VoiceSessionState.PROCESSING
    await _send_json(
        websocket,
        {"type": "state", "state": VoiceSessionState.PROCESSING.value, "session_id": session.session_id},
    )

    session.turns.append({"role": "user", "content": text})

    # TODO: wire to Coordinator for a real response
    response_text = (
        "[STUB] This is a placeholder response from the Voice Agent. "
        "STT and TTS are real; Coordinator integration lands next."
    )
    session.turns.append({"role": "assistant", "content": response_text})

    await _send_json(
        websocket,
        {"type": "transcript", "text": response_text, "is_final": True, "confidence": 1.0},
    )

    # Real TTS
    tts_result = await text_to_speech(text=response_text, user_id=session.user_id)
    if tts_result.ok:
        tts_data: dict = tts_result.data  # type: ignore[assignment]
        await _send_json(
            websocket,
            {
                "type": "audio",
                "data": tts_data.get("audio_data"),
                "is_final": True,
                "duration_seconds": tts_data.get("duration_seconds"),
            },
        )
    else:
        await _send_json(
            websocket,
            {
                "type": "audio",
                "data": None,
                "is_final": True,
                "duration_seconds": len(response_text.split()) * 0.4,
            },
        )

    session.state = VoiceSessionState.IDLE
    await _send_json(
        websocket,
        {"type": "state", "state": VoiceSessionState.IDLE.value, "session_id": session.session_id},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _send_json(websocket: WebSocket, data: dict) -> None:
    """Send a JSON dict over the WebSocket."""
    await websocket.send_text(json.dumps(data))


def _generate_summary(session: VoiceSession) -> str:
    """Generate a brief session summary for end-of-session."""
    if not session.turns:
        return "No substantive conversation occurred."
    turn_count = len([t for t in session.turns if t.get("role") == "user"])
    return f"Session ended with {turn_count} user turn(s)."
