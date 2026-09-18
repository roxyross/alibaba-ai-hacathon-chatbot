"""VoiceService — Speech-to-text, text-to-speech, and audio intelligence."""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.skills.schemas import SpeechToTextRequest, TextToSpeechRequest
from app.skills.speech_to_text import SpeechToTextSkill
from app.skills.text_to_speech import TextToSpeechSkill
from app.voice.repository import VoiceRepository

log = structlog.get_logger()


class VoiceService:
    """Core domain service for audio processing, synthesis, and voice intelligence."""

    def __init__(self, repo: VoiceRepository | None = None) -> None:
        self.repo = repo or VoiceRepository()
        self.stt_skill = SpeechToTextSkill()
        self.tts_skill = TextToSpeechSkill()

    async def transcribe_audio(
        self,
        audio_data: str,
        language: str | None = None,
        model: str | None = "whisper",
        save_as_note: bool = False,
        title: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe base64 audio payload, optionally persisting the output as a voice note."""
        stt_req = SpeechToTextRequest(
            audio_data=audio_data,
            language=language,
            model=model,
        )
        res = await self.stt_skill.execute(stt_req)
        raw_text = (res.text or "").strip()

        recording_id: str | None = None
        if save_as_note and user_id:
            transcript_content = raw_text or title or "Audio recording (speech transcription unavailable)"
            note_title = title or self._generate_title_from_text(transcript_content)
            enhanced = self.enhance_transcript(transcript_content)
            created = await self.repo.create_recording(
                user_id=user_id,
                data={
                    "title": note_title,
                    "transcript": transcript_content,
                    "summary": enhanced["summary"],
                    "language": res.language or language or "en",
                    "duration_seconds": res.duration_seconds,
                    "voice_model": model,
                    "tags": enhanced["key_topics"],
                },
            )
            recording_id = created["id"]

        return {
            "text": raw_text,
            "language": res.language or language,
            "confidence": res.confidence,
            "duration_seconds": res.duration_seconds,
            "recording_id": recording_id,
        }

    async def synthesize_speech(
        self,
        text: str,
        voice: str | None = None,
        speed: float = 1.0,
        model: str | None = "gemini",
        modulation: str | None = None,
    ) -> dict[str, Any]:
        """Synthesize spoken audio from text with steerable persona and modulation."""
        tts_req = TextToSpeechRequest(
            text=text,
            voice=voice,
            speed=speed,
            model=model or "gemini",
            voice_modulation=modulation,
        )
        res = await self.tts_skill.execute(tts_req)
        return {
            "audio_data": res.audio_data,
            "format": res.format,
            "duration_seconds": res.duration_seconds,
            "model": res.model,
        }

    def enhance_transcript(self, transcript: str) -> dict[str, Any]:
        """Extract structured insights, title, summary, and action items from transcript."""
        text = transcript.strip()
        if not text:
            return {
                "title": "Voice Note",
                "summary": "No transcript available.",
                "action_items": [],
                "key_topics": [],
            }

        title = self._generate_title_from_text(text)
        summary = self._generate_summary(text)
        action_items = self._extract_action_items(text)
        key_topics = self._extract_key_topics(text)

        return {
            "title": title,
            "summary": summary,
            "action_items": action_items,
            "key_topics": key_topics,
        }

    def get_available_voices(self) -> dict[str, Any]:
        """Return catalog of available AI voice personas, models, and tone modulations."""
        return {
            "models": [
                {
                    "id": "gemini-3.8-flash",
                    "name": "Gemini 3.8 Flash (Multimodal Audio)",
                    "description": "Ultra-low latency real-time voice with emotion & tone steering",
                },
                {
                    "id": "gemini-3.7-flash",
                    "name": "Gemini 3.7 Flash",
                    "description": "High fidelity audio synthesis and multi-speaker reasoning",
                },
                {
                    "id": "openai",
                    "name": "OpenAI TTS",
                    "description": "Natural sounding speech with consistent pacing",
                },
                {
                    "id": "elevenlabs",
                    "name": "ElevenLabs",
                    "description": "Studio-grade neural voice synthesis",
                },
            ],
            "voices": [
                {"id": "Kore", "name": "Kore", "gender": "Female", "description": "Warm, reassuring, professional", "model": "gemini"},
                {"id": "Puck", "name": "Puck", "gender": "Male", "description": "Energetic, upbeat, dynamic", "model": "gemini"},
                {"id": "Fenrir", "name": "Fenrir", "gender": "Male", "description": "Deep, authoritative, calm", "model": "gemini"},
                {"id": "Aoede", "name": "Aoede", "gender": "Female", "description": "Expressive, melodic, articulate", "model": "gemini"},
                {"id": "Zephyr", "name": "Zephyr", "gender": "Neutral", "description": "Soft, calm, relaxed", "model": "gemini"},
                {"id": "alloy", "name": "Alloy", "gender": "Neutral", "description": "Balanced and versatile", "model": "openai"},
                {"id": "echo", "name": "Echo", "gender": "Male", "description": "Clear and focused", "model": "openai"},
                {"id": "shimmer", "name": "Shimmer", "gender": "Female", "description": "Expressive and gentle", "model": "openai"},
            ],
            "modulations": [
                {"id": "normal", "label": "Normal Tone", "emoji": "🗣️"},
                {"id": "whispering", "label": "Whispering", "emoji": "🤫"},
                {"id": "excited", "label": "Excited", "emoji": "🤩"},
                {"id": "dramatic", "label": "Dramatic", "emoji": "🎭"},
                {"id": "calm", "label": "Calm", "emoji": "🧘"},
                {"id": "shouting", "label": "Shouting / High Energy", "emoji": "📢"},
            ],
            "supported_languages": [
                {"code": "en", "name": "English"},
                {"code": "ur", "name": "Urdu (اردو)"},
                {"code": "es", "name": "Spanish (Español)"},
                {"code": "fr", "name": "French (Français)"},
                {"code": "de", "name": "German (Deutsch)"},
                {"code": "hi", "name": "Hindi (हिंदी)"},
                {"code": "ar", "name": "Arabic (العربية)"},
                {"code": "zh", "name": "Chinese (中文)"},
                {"code": "ja", "name": "Japanese (日本語)"},
            ],
        }

    def _generate_title_from_text(self, text: str) -> str:
        """Create a concise 4-8 word title from the beginning of the text."""
        cleaned = re.sub(r"[#*_`\[\]()\"'\n]+", " ", text).strip()
        words = cleaned.split()
        if len(words) <= 6:
            return " ".join(words).rstrip(".!?")
        cand = " ".join(words[:6]).rstrip(",;:-.!?")
        return f"{cand}…"

    def _generate_summary(self, text: str) -> str:
        """Produce a concise executive summary from the transcript."""
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", text) if s.strip()]
        if not sentences:
            return text[:200]
        if len(sentences) <= 2:
            return ". ".join(sentences) + "."
        return f"{sentences[0]}. {sentences[1]}."

    def _extract_action_items(self, text: str) -> list[str]:
        """Detect action items and commitments within spoken audio."""
        action_triggers = (
            "need to",
            "have to",
            "must",
            "will",
            "should",
            "follow up",
            "send",
            "call",
            "email",
            "schedule",
            "review",
            "todo",
            "to-do",
            "remember to",
            "don't forget to",
        )
        actions: list[str] = []
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", text) if s.strip()]
        for s in sentences:
            lower = s.lower()
            if any(trig in lower for trig in action_triggers):
                cleaned_item = s.strip()
                if cleaned_item and cleaned_item not in actions:
                    actions.append(cleaned_item)

        # If no explicit modal detected, but text has list indicators
        if not actions and ("1." in text or "-" in text):
            for line in text.splitlines():
                if re.match(r"^\s*(\d+\.|\-|\*)\s+", line):
                    actions.append(re.sub(r"^\s*(\d+\.|\-|\*)\s+", "", line).strip())

        return actions[:5]

    def _extract_key_topics(self, text: str) -> list[str]:
        """Extract top representative keywords and topics."""
        stop_words = {
            "the", "and", "a", "an", "in", "on", "at", "to", "for", "with", "of",
            "is", "are", "was", "were", "it", "this", "that", "we", "i", "you",
            "they", "he", "she", "have", "had", "be", "been", "will", "would",
            "can", "could", "should", "from", "by", "as", "or", "about",
        }
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        meaningful = [w for w in words if w not in stop_words]
        counts: dict[str, int] = {}
        for w in meaningful:
            counts[w] = counts.get(w, 0) + 1

        sorted_words = sorted(counts, key=lambda k: counts[k], reverse=True)
        return sorted_words[:4]
