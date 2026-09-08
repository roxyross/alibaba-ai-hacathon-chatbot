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
        """Transcribe via Groq Whisper API (primary, ultra-fast) or OpenAI Whisper."""
        import os
        import io
        import httpx
        from pathlib import Path

        # Ensure .env is loaded if keys aren't in os.environ
        if not os.environ.get("GROK_API_KEY") and not os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            try:
                import dotenv
                env_path = Path(__file__).resolve().parents[3] / ".env"
                if env_path.exists():
                    dotenv.load_dotenv(env_path)
            except Exception:
                pass

        grok_key = (os.environ.get("GROK_API_KEY") or os.environ.get("GROQ_API_KEY", "")).strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

        if not grok_key and not openai_key:
            return self._mock_transcribe(), None

        # Determine audio filename & mime type
        is_webm = audio_bytes.startswith(b"\x1a\x45\xdf\xa3") or (len(audio_bytes) > 4 and audio_bytes[:4] != b"RIFF")
        filename = "audio.webm" if is_webm else "audio.wav"
        mime_type = "audio/webm" if is_webm else "audio/wav"

        # Hallucination filter for quiet audio / silence
        silence_hallucinations = {
            "thank you",
            "thank you.",
            "thank you very much",
            "thank you very much.",
            "thanks for watching",
            "thanks for watching.",
            "thank you for watching",
            "thank you for watching.",
            "subtitles by",
            "you",
            "you.",
            "bye",
            "bye.",
            "[music]",
            "[applause]",
        }

        # Multilingual vocabulary hint for high accuracy across languages
        multilingual_prompt = "Conversational speech in English, Urdu (اردو), Roman Urdu, Hindi, Arabic, Spanish, French, or other languages."
        whisper_lang = language.split("-")[0].lower() if language else None

        # 1. Try Groq Whisper (blazing fast, high accuracy, active key)
        if grok_key:
            try:
                files = {"file": (filename, io.BytesIO(audio_bytes), mime_type)}
                data = {
                    "model": "whisper-large-v3-turbo",
                    "prompt": multilingual_prompt,
                }
                if whisper_lang:
                    data["language"] = whisper_lang

                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {grok_key}"},
                        files=files,
                        data=data,
                    )
                if resp.is_success:
                    result = resp.json()
                    raw_text = (result.get("text") or "").strip()
                    norm = raw_text.lower().rstrip(".,!?")
                    if norm in silence_hallucinations or not norm:
                        return "", None
                    return raw_text, None
                else:
                    log.warning("speech_to_text.groq_failed", status=resp.status_code, body=resp.text[:200])
            except Exception as exc:
                log.warning("speech_to_text.groq_exc", error=str(exc))

        # 2. Fallback to OpenAI Whisper
        if openai_key:
            try:
                files = {"file": (filename, io.BytesIO(audio_bytes), mime_type)}
                data = {
                    "model": "whisper-1",
                    "prompt": multilingual_prompt,
                }
                if whisper_lang:
                    data["language"] = whisper_lang

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        files=files,
                        data=data,
                    )
                if resp.is_success:
                    result = resp.json()
                    raw_text = (result.get("text") or "").strip()
                    norm = raw_text.lower().rstrip(".,!?")
                    if norm in silence_hallucinations or not norm:
                        return "", None
                    return raw_text, result.get("confidence", None)
            except Exception as exc:
                log.warning("speech_to_text.openai_exc", error=str(exc))

        return self._mock_transcribe(), None

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
        """Fallback when no STT API key is configured. Return empty so browser STT can take over."""
        return ""


def get_executor() -> SpeechToTextSkill:
    return SpeechToTextSkill()
