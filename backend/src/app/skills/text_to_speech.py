"""text_to_speech skill — synthesize speech from text.

Uses OpenAI TTS API or ElevenLabs. Falls back to a placeholder when not configured.
"""

from __future__ import annotations

import base64
import io
import os
import re
import wave
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import TextToSpeechRequest, TextToSpeechResponse


log = structlog.get_logger()


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw 16-bit linear PCM audio into a standard RIFF/WAV container."""
    if pcm_bytes.startswith(b"RIFF"):
        return pcm_bytes
    if pcm_bytes.startswith(b"ID3") or (len(pcm_bytes) > 2 and pcm_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
        return pcm_bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


class TextToSpeechSkill(SkillExecutor[TextToSpeechRequest, TextToSpeechResponse]):
    slug = "text_to_speech"

    async def execute(self, input_data: TextToSpeechRequest) -> TextToSpeechResponse:
        text = input_data.text
        speed = input_data.speed or 1.0
        voice = input_data.voice
        model = input_data.model or "gemini"
        modulation = getattr(input_data, "voice_modulation", None)

        try:
            if model in ("gemini", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.1-flash", "gemini-tts"):
                audio_b64, fmt, duration = await self._gemini_tts(text, speed, voice, modulation)
                if not audio_b64:
                    # Fallback to OpenAI if Gemini TTS returned empty
                    audio_b64, fmt, duration = await self._openai_tts(text, speed, voice)
            elif model == "elevenlabs":
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

    async def _gemini_tts(
        self, text: str, speed: float, voice: str | None, modulation: str | None
    ) -> tuple[str, str, float | None]:
        """Synthesize via Google Gemini Multimodal Audio TTS with steerable voice modulation."""
        import httpx

        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            return "", "mp3", None

        # Apply voice modulation tags if requested
        mod_prefix = ""
        if modulation:
            mod_map = {
                "whispering": "[whispers] ",
                "shouting": "[shouting] ",
                "excited": "[excitedly] ",
                "dramatic": "[dramatically] ",
                "calm": "[calmly] ",
                "fast": "[fast] ",
                "slow": "[slow] ",
            }
            mod_prefix = mod_map.get(modulation.lower(), f"[{modulation}] ")

        full_prompt = mod_prefix + text if not text.startswith("[") else text

        # Selected Gemini voice (default "Kore" or "Puck", "Fenrir", "Aoede", "Zephyr")
        target_voice = voice or "Kore"

        models_to_try = [
            "gemini-2.5-flash-preview-tts",
            "gemini-3.1-flash-tts-preview",
            "gemini-2.5-pro-preview-tts",
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            for gemini_model in models_to_try:
                try:
                    payload = {
                        "contents": [{"parts": [{"text": full_prompt[:5000]}]}],
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {
                                "voiceConfig": {
                                    "prebuiltVoiceConfig": {
                                        "voiceName": target_voice,
                                    }
                                }
                            },
                        },
                    }
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}",
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )
                    if resp.is_success:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for part in parts:
                                inline_data = part.get("inlineData", {})
                                if inline_data and "data" in inline_data:
                                    raw_b64 = inline_data["data"]
                                    mime = inline_data.get("mimeType", "audio/pcm;rate=24000")
                                    rate_match = re.search(r"rate=(\d+)", mime)
                                    sample_rate = int(rate_match.group(1)) if rate_match else 24000

                                    pcm_bytes = base64.b64decode(raw_b64)
                                    wav_bytes = _pcm_to_wav(pcm_bytes, sample_rate=sample_rate)
                                    wav_b64 = base64.b64encode(wav_bytes).decode("utf-8")
                                    duration = len(pcm_bytes) / (sample_rate * 2)
                                    return wav_b64, "wav", round(duration, 1)
                except Exception as exc:
                    log.warning("gemini_tts.model_attempt_failed", model=gemini_model, error=str(exc))
                    continue

        return "", "mp3", None


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
