"""Greeting detection API router — detects greetings in any language and creates warm personalized greetings."""

from __future__ import annotations

import re
from typing import Any
from fastapi import APIRouter, Body
from pydantic import BaseModel

router = APIRouter(prefix="/greeting", tags=["greeting"])

# Multi-lingual greeting triggers and metadata
GREETING_PATTERNS: dict[str, dict[str, Any]] = {
    "urdu": {
        "pattern": r"\b(assalam\s*o\s*alaikum|salam|kese\s*ho|kia\s*hal\s*hai|adab|khushamdeed)\b",
        "warm": "Assalam o alaikum! Welcome back to ROXY AI. Ready when you are — what should we accomplish today?",
    },
    "english": {
        "pattern": r"\b(hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|greetings|howdy|sup)\b",
        "warm": "Hello! Welcome back to ROXY AI. Ready when you are — how can I assist you today?",
    },
    "arabic": {
        "pattern": r"\b(marhaban|ahlan|salam\s+alaykum|sabah\s+al\s*khair|masa\s+al\s*khair)\b",
        "warm": "Marhaban! Ahlan wa sahlan. ROXY AI is ready when you are. How may I help you?",
    },
    "spanish": {
        "pattern": r"\b(hola|buenos\s+dias|buenas\s+tardes|buenas\s+noches|que\s+tal)\b",
        "warm": "¡Hola! Bienvenido a ROXY AI. Listo cuando tú lo estés. ¿En qué puedo ayudarte hoy?",
    },
    "french": {
        "pattern": r"\b(bonjour|salut|bonsoir|coucou|bienvenue)\b",
        "warm": "Bonjour! Bienvenue sur ROXY AI. Prêt quand vous l'êtes. Que pouvons-nous faire ensemble aujourd'hui?",
    },
    "german": {
        "pattern": r"\b(hallo|guten\s+tag|guten\s+morgen|guten\s+abend|grüß\s+gott|servus)\b",
        "warm": "Hallo! Willkommen bei ROXY AI. Bereit, wenn Sie es sind. Wie kann ich helfen?",
    },
    "hindi": {
        "pattern": r"\b(namaste|namaskar|kaise\s+ho|shubh\s+prabhat)\b",
        "warm": "Namaste! Welcome back to ROXY AI. Ready when you are — how can I assist you?",
    },
    "japanese": {
        "pattern": r"\b(konnichiwa|ohayou|konbanwa|hajimemashite)\b",
        "warm": "Konnichiwa! Welcome to ROXY AI. Ready when you are. How can I assist today?",
    },
    "chinese": {
        "pattern": r"\b(ni\s*hao|nin\s*hao|zao\s*shang\s*hao|wan\s*shang\s*hao)\b",
        "warm": "Nǐ hǎo! Welcome back to ROXY AI. Ready when you are. How can I help today?",
    },
}


class GreetingDetectRequest(BaseModel):
    text: str


class GreetingDetectResponse(BaseModel):
    is_greeting: bool
    detected_language: str
    warm_greeting: str | None = None
    original_text: str


@router.post("/detect", response_model=GreetingDetectResponse)
async def detect_greeting(req: GreetingDetectRequest) -> GreetingDetectResponse:
    """Detect if input text contains a greeting in any language and return personalized greeting."""
    clean_text = req.text.strip().lower()

    for lang, data in GREETING_PATTERNS.items():
        if re.search(data["pattern"], clean_text, re.IGNORECASE):
            return GreetingDetectResponse(
                is_greeting=True,
                detected_language=lang,
                warm_greeting=data["warm"],
                original_text=req.text,
            )

    return GreetingDetectResponse(
        is_greeting=False,
        detected_language="unknown",
        warm_greeting=None,
        original_text=req.text,
    )
