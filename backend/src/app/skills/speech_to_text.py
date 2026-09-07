"""speech_to_text skill — transcribe audio to text.

Uses the AI gateway's STT capability (OpenAI Whisper or Deepgram).
Falls back to a mock response when no STT provider is configured.
"""

from __future__ import annotations

import base64
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import SpeechToTextRequest, SpeechToTextResponse


log = structlog.get_logger()


class SpeechToTextSkill(SkillExecutor[SpeechToTextRequest, SpeechToTextResponse]):
    slug = "speech_to_text"

    async def execute(self, input_data: SpeechToTextRequest) -> SpeechToTextResponse:
        audio_b64 = input_data.audio_data
        model = input_data.model or "whisper"
        language = input_data.language

        try:
            # Decode audio for processing
            audio_bytes = base64.b64decode(audio_b64)

            # Route to appropriate STT backend
            if model == "deepgram":
                text, confidence = await self._deepgram(audio_bytes, language)
            else:
                # Default: OpenAI Whisper via AI gateway
                text, confidence = await self._whisper(audio_bytes, language)

            return SpeechToTextResponse(
                text=text,
                language=language,
                confidence=confidence,
                duration_seconds=None,
            )
        except Exception as exc:
            log.error("speech_to_text.failed", model=model, error=str(exc))
            return SpeechToTextResponse(
                text="",
                language=language,
                confidence=None,
                duration_seconds=None,
            )

    async def _whisper(self, audio_bytes: bytes, language: str | None) -> tuple[str, float | None]:
        """Transcribe via OpenAI Whisper API (routed through AI gateway)."""
        import os

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return self._mock_transcribe(), None

        import httpx
        import io

        file_obj = io.BytesIO(audio_bytes)
        files = {"file": ("audio.wav", file_obj, "audio/wav")}
        data = {"model": "whisper-1"}
        if language:
            data["language"] = language

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data,
            )
        resp.raise_for_status()
        result = resp.json()
        return result.get("text", ""), result.get("confidence", None)

    async def _deepgram(self, audio_bytes: bytes, language: str | None) -> tuple[str, float | None]:
        """Transcribe via Deepgram API."""
        import os

        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            return self._mock_transcribe(), None

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen",
                headers={"Authorization": f"Token {api_key}"},
                content=audio_bytes,
                params={
                    "model": "nova-2",
                    "language": language or "en",
                    "smart_format": "true",
                },
            )
        resp.raise_for_status()
        result = resp.json()
        # Deepgram structure
        try:
            transcript = result["results"]["channels"][0]["alternatives"][0]["transcript"]
            confidence = result["results"]["channels"][0]["alternatives"][0].get("confidence")
            return transcript, confidence
        except (KeyError, IndexError):
            return "", None

    @staticmethod
    def _mock_transcribe() -> str:
        """Fallback when no STT API key is configured."""
        return "[STT not configured — set OPENAI_API_KEY or DEEPGRAM_API_KEY to enable transcription]"


def get_executor() -> SpeechToTextSkill:
    return SpeechToTextSkill()
