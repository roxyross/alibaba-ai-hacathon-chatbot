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

            # Primary: Groq Whisper (sub-300ms latency, high accuracy)
            text, confidence = await self._whisper(audio_bytes, language)
            if not text:
                # Fallback: Google Gemini 2.0 Flash multimodal audio
                text, confidence = await self._gemini_transcribe(audio_bytes, language)
            if not text and model == "deepgram":
                text, confidence = await self._deepgram(audio_bytes, language)

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
        if not os.environ.get("GROQ_API_KEY") and not os.environ.get("GROK_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            try:
                import dotenv
                env_path = Path(__file__).resolve().parents[3] / ".env"
                if env_path.exists():
                    dotenv.load_dotenv(env_path)
            except Exception:
                pass

        groq_key = (os.environ.get("GROQ_API_KEY") or os.environ.get("GROK_API_KEY", "")).strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

        if not groq_key and not openai_key:
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
        if groq_key:
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
                        headers={"Authorization": f"Bearer {groq_key}"},
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

        # 3. Fallback to Gemini Multimodal Transcription
        gemini_text, _ = await self._gemini_transcribe(audio_bytes, language)
        if gemini_text:
            return gemini_text, 0.95

        return self._mock_transcribe(), None

    async def _gemini_transcribe(self, audio_bytes: bytes, language: str | None) -> tuple[str, float | None]:
        """Transcribe audio via Google Gemini multimodal audio API.
        
        Excels at catching whispering, shouting, distinct emotional modulation,
        and multilingual speech (Urdu, Hindi, English, regional accents).
        """
        import os
        import httpx

        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            return "", None

        is_webm = audio_bytes.startswith(b"\x1a\x45\xdf\xa3") or (len(audio_bytes) > 4 and audio_bytes[:4] != b"RIFF")
        mime_type = "audio/webm" if is_webm else "audio/wav"
        audio_b64 = base64.b64encode(audio_bytes).decode()

        prompt = (
            "Transcribe this speech verbatim. The audio may be whispered, shouted, or spoken in various accents "
            "and languages including Urdu (اردو), Hindi (हिन्दी), English, Arabic, or mixed dialects. "
            "Detect and transcribe the exact words spoken. Return ONLY the transcribed text, with no explanations, "
            "no markdown formatting, and no commentary."
        )
        if language:
            prompt += f" The primary expected language or dialect is {language}."

        models_to_try = [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            for m in models_to_try:
                try:
                    payload = {
                        "contents": [
                            {
                                "parts": [
                                    {
                                        "inlineData": {
                                            "mimeType": mime_type,
                                            "data": audio_b64,
                                        }
                                    },
                                    {"text": prompt},
                                ]
                            }
                        ]
                    }
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}",
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )
                    if resp.is_success:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text_parts = [p.get("text", "") for p in parts if "text" in p]
                            transcription = "".join(text_parts).strip()
                            if transcription:
                                return transcription, 0.95
                except Exception as exc:
                    log.warning("speech_to_text.gemini_failed", model=m, error=str(exc))
                    continue

        return "", None

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
