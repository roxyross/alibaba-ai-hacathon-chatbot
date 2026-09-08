"""Real `text_to_speech` skill using Google Cloud TTS API.

Synthesizes natural speech from plain text using Google's Neural2 voice library.
Returns base64-encoded audio (MP3 or LINEAR16 PCM) suitable for streaming.

The API key is read from the ``google_api_key`` config setting.
"""

from __future__ import annotations

import base64
import structlog

from google.cloud import texttospeech_v1
from google.cloud.texttospeech_v1 import TextToSpeechClient, SynthesisInput, VoiceSelectionParams, AudioConfig
from google.cloud.texttospeech_v1 import AudioEncoding

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()


class TTSError(Exception):
    """Raised when TTS synthesis fails."""


# Supported audio formats
AUDIO_FORMATS = {"mp3", "ogg_opus", "linear16", "mulaw", "alaw"}


async def text_to_speech(
    text: str,
    voice: str | None = None,
    speed: float = 1.0,
    format: str = "mp3",
    language_code: str | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Synthesize text into speech using Google Cloud TTS.

    Args:
        text: Plain text to synthesize. Must not be empty.
        voice: Voice name, e.g. ``"en-US-Neural2-J"``. Default from config.
        speed: Speaking rate, ``0.25``–``4.0``. Default ``1.0``.
        format: Output audio format. One of: mp3, ogg_opus, linear16, mulaw, alaw.
                 Default ``"mp3"``.
        language_code: BCP-47 language tag, e.g. ``"en-US"``. Default from config.
        user_id: Authenticated user (logged only).

    Returns:
        SkillResult::

            {
                "audio_data": "<base64-encoded audio>",
                "audio_url": null,         # not used with direct audio
                "duration_seconds": 2.5,
                "format": "mp3",
                "voice": "en-US-Neural2-J",
                "speed": 1.0,
            }
    """
    log.info(
        "text_to_speech.invoked",
        user_id=user_id,
        text_length=len(text),
        voice=voice,
        speed=speed,
        format=format,
    )

    if not text or not text.strip():
        return SkillResult(ok=False, data=None, error="text is required and must not be empty")

    if not settings.google_api_key:
        return SkillResult(
            ok=False,
            data=None,
            error="GOOGLE_API_KEY is not configured; text_to_speech is unavailable.",
        )

    if format not in AUDIO_FORMATS:
        return SkillResult(
            ok=False,
            data=None,
            error=f"Unsupported audio format '{format}'. Supported: {', '.join(sorted(AUDIO_FORMATS))}",
        )

    if not (0.25 <= speed <= 4.0):
        return SkillResult(
            ok=False,
            data=None,
            error=f"speed must be between 0.25 and 4.0; got {speed}",
        )

    # Map format string to Google Cloud TTS enum
    format_map = {
        "mp3": AudioEncoding.MP3,
        "ogg_opus": AudioEncoding.OGG_OPUS,
        "linear16": AudioEncoding.LINEAR16,
        "mulaw": AudioEncoding.MULAW,
        "alaw": AudioEncoding.ALAW,
    }

    try:
        client = TextToSpeechClient()

        input_text = SynthesisInput(text=text)

        voice_params = VoiceSelectionParams(
            name=voice or settings.tts_voice,
            language_code=language_code or settings.tts_language_code,
        )

        audio_config = AudioConfig(
            audio_encoding=format_map[format],
            speaking_rate=speed,
            pitch=settings.tts_pitch,
        )

        response = client.synthesize_speech(
            input=input_text,
            voice=voice_params,
            audio_config=audio_config,
        )

        audio_b64 = base64.b64encode(response.audio_content).decode("ascii")

        # Estimate duration from text length and speed
        # ~150 words/min at speed 1.0 → 2.5 words/second → 12 chars/second
        word_count = len(text.split())
        estimated_duration = (word_count / 2.5) / speed

        log.info(
            "text_to_speech.done",
            user_id=user_id,
            audio_size_bytes=len(response.audio_content),
            estimated_duration=round(estimated_duration, 2),
        )

        return SkillResult(
            ok=True,
            data={
                "audio_data": audio_b64,
                "audio_url": None,
                "duration_seconds": round(estimated_duration, 2),
                "format": format,
                "voice": voice or settings.tts_voice,
                "speed": speed,
            },
        )

    except TTSError:
        raise

    except Exception as exc:  # noqa: BLE001
        log.error(
            "text_to_speech.unexpected_error",
            user_id=user_id,
            error=str(exc),
            exc_info=True,
        )
        return SkillResult(
            ok=False,
            data=None,
            error=f"Unexpected error during speech synthesis: {exc}",
        )
