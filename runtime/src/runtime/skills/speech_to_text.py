"""Real `speech_to_text` skill using Google Cloud Speech-to-Text API.

Supports:
- Streaming audio chunks (WebSocket context)
- Interim (partial) transcript results
- Multiple language hints
- Configurable sample rate

The API key is read from the ``google_api_key`` config setting.
"""

from __future__ import annotations

import asyncio
import base64
import structlog

from google.cloud import speech_v1
from google.cloud.speech_v1 import SpeechClient
from google.cloud.speech_v1.types import RecognitionConfig, StreamingRecognitionConfig, StreamingRecognizeRequest

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()


class STTError(Exception):
    """Raised when STT processing fails."""


async def speech_to_text(
    audio_data: str | None = None,
    session_id: str | None = None,
    language: str | None = None,
    interim: bool = False,
    sample_rate: int = 16000,
    *,
    user_id: str,
) -> SkillResult:
    """Transcribe audio to text using Google Cloud Speech-to-Text.

    Args:
        audio_data: Base64-encoded audio bytes (16-bit PCM, 16kHz mono recommended).
                    Pass ``None`` to signal end-of-stream.
        session_id: Voice session identifier (logged only).
        language: BCP-47 language tag hint, e.g. ``"en-US"``. Default ``"en-US"``.
        interim: If ``True``, return interim (partial) results as they arrive.
                 Default ``False`` (only final transcripts).
        sample_rate: Audio sample rate in Hz. Default 16000 (optimal for Cloud STT).
                     Supported: 8000–48000.
        user_id: Authenticated user (logged only).

    Returns:
        SkillResult with transcripts list::

            {
                "transcripts": [
                    {
                        "text": "the recognized words",
                        "language": "en-US",
                        "confidence": 0.95,   # 0–1, final only
                        "is_final": true,
                        "duration_seconds": 2.3,
                    }
                ],
                "session_id": "...",
            }

        ``confidence`` is ``null`` for interim results.
    """
    log.info(
        "speech_to_text.invoked",
        user_id=user_id,
        session_id=session_id,
        language=language or "en-US",
        interim=interim,
        has_audio=audio_data is not None,
        sample_rate=sample_rate,
    )

    # Empty / None audio means end-of-stream (no speech detected)
    if audio_data is None:
        return SkillResult(
            ok=True,
            data={"transcripts": [], "session_id": session_id},
        )

    if not settings.google_api_key:
        return SkillResult(
            ok=False,
            data=None,
            error="GOOGLE_API_KEY is not configured; speech_to_text is unavailable.",
        )

    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_data)

        # Build streaming recognize requests using the REST-safe client
        client = SpeechClient()
        config = RecognitionConfig(
            encoding=RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code=language or "en-US",
            enable_interim_results=interim,
            model="latest_long",
            use_enhanced=True,
        )
        streaming_config = StreamingRecognitionConfig(
            config=config,
            interim_results=interim,
            single_utterance=False,
        )

        # Build a queue to receive results from the streaming RPC
        transcript_event: asyncio.Event = asyncio.Event()
        results: list[dict] = []
        error: str | None = None

        async def _stream_audio():
            """Send audio chunks to the streaming RPC as they arrive."""
            try:
                # First request must carry the streaming config
                yield StreamingRecognizeRequest(
                    streaming_config=streaming_config,
                )
                # Subsequent requests carry audio content
                yield StreamingRecognizeRequest(audio_content=audio_bytes)
            except Exception as exc:
                nonlocal error
                error = str(exc)
            finally:
                transcript_event.set()

        # Run the streaming recognition in a task so we can await it
        def _run():
            responses = client.streaming_recognize(_stream_audio())
            for response in responses:
                for result in response.results:
                    alt = result.alternatives[0] if result.alternatives else None
                    if alt:
                        results.append(
                            {
                                "text": alt.transcript,
                                "language": language or "en-US",
                                "confidence": round(alt.confidence, 4) if result.is_final else None,
                                "is_final": result.is_final,
                            }
                        )
                if result.is_final:
                    transcript_event.set()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _run)
        await transcript_event.wait()

        if error:
            raise STTError(error)

        if not results:
            return SkillResult(
                ok=True,
                data={"transcripts": [], "session_id": session_id},
            )

        return SkillResult(
            ok=True,
            data={
                "transcripts": results,
                "session_id": session_id,
            },
        )

    except STTError as exc:
        log.error("speech_to_text.stt_error", user_id=user_id, error=str(exc))
        return SkillResult(ok=False, data=None, error=f"STT error: {exc}")

    except Exception as exc:  # noqa: BLE001
        log.error(
            "speech_to_text.unexpected_error",
            user_id=user_id,
            error=str(exc),
            exc_info=True,
        )
        return SkillResult(
            ok=False,
            data=None,
            error=f"Unexpected error during speech recognition: {exc}",
        )
