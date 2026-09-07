"""text_to_speech skill — synthesize speech from text.

Uses OpenAI TTS API or ElevenLabs. Falls back to a placeholder when not configured.
"""

from __future__ import annotations

import base64
import io
import os
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import TextToSpeechRequest, TextToSpeechResponse


log = structlog.get_logger()


class TextToSpeechSkill(SkillExecutor[TextToSpeechRequest, TextToSpeechResponse]):
    slug = "text_to_speech"

    async def execute(self, input_data: TextToSpeechRequest) -> TextToSpeechResponse:
        text = input_data.text
        speed = input_data.speed or 1.0
        voice = input_data.voice
        model = input_data.model or "openai"

        try:
            if model == "elevenlabs":
                audio_b64, fmt, duration = await self._elevenlabs(text, speed, voice)
            else:
                audio_b64, fmt, duration = await self._openai_tts(text, speed, voice)

            return TextToSpeechResponse(
                audio_data=audio_b64,
                format=fmt,
                duration_seconds=duration,
                model=model,
            )
        except Exception as exc:
            log.error("text_to_speech.failed", model=model, error=str(exc))
            return TextToSpeechResponse(
                audio_data="",
                format="mp3",
                duration_seconds=None,
                model=model,
            )

    async def _openai_tts(self, text: str, speed: float, voice: str | None) -> tuple[str, str, float | None]:
        """Synthesize via OpenAI TTS API."""
        import httpx

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return self._mock_tts(), "mp3", None

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": text[:5000],
                    "voice": voice or "alloy",
                    "speed": speed,
                    "response_format": "mp3",
                },
            )
        resp.raise_for_status()
        audio_bytes = resp.content
        duration = len(audio_bytes) / (16_000 * 2)  # rough estimate at 16kHz mono
        return base64.b64encode(audio_bytes).decode(), "mp3", round(duration, 1)

    async def _elevenlabs(self, text: str, speed: float, voice: str | None) -> tuple[str, str, float | None]:
        """Synthesize via ElevenLabs API."""
        import httpx

        api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            return self._mock_tts(), "mp3", None

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice or 'JBFqnCBsd6RMkjVBOzmu'}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text[:5000],
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "speed": speed,
                    },
                },
            )
        resp.raise_for_status()
        audio_bytes = resp.content
        duration = len(audio_bytes) / (16_000 * 2)
        return base64.b64encode(audio_bytes).decode(), "mp3", round(duration, 1)

    @staticmethod
    def _mock_tts() -> str:
        """Fallback when no TTS API key is configured."""
        return base64.b64encode(b"MOCK_TTS_AUDIO").decode()


def get_executor() -> TextToSpeechSkill:
    return TextToSpeechSkill()
