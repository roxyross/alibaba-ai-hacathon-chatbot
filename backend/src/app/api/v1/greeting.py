"""Greeting detection API router and smart title generator for Roxy-AI."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
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

# Set of single-word greetings normalized (lowercase, stripped of punctuation)
_SINGLE_WORD_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hiya",
    "howdy",
    "sup",
    "yo",
    "salam",
    "salaam",
    "hola",
    "bonjour",
    "salut",
    "bonsoir",
    "namaste",
    "namaskar",
    "hallo",
    "ciao",
    "ola",
    "olá",
    "ahoy",
}

# Set of multi-word greetings normalized
_MULTI_WORD_GREETINGS = {
    "good morning",
    "good afternoon",
    "good evening",
    "good day",
    "good night",
    "whats up",
    "what's up",
    "hey there",
    "hello there",
    "hi there",
    "assalamu alaikum",
    "assalam o alaikum",
    "assalam u alaikum",
    "asalam o alaikum",
    "asalam alaikum",
    "salam alaikum",
    "salaam alaikum",
    "as-salamu alaykum",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
}

# Subordinate filler prefixes to strip when extracting a concise smart title
_PROMPT_PREFIX_PATTERNS = [
    r"^(?:hi|hello|hey|salam|good morning|good evening)[,\s!.-]+",
    r"^(?:can you please help me (?:with|to)|can you help me (?:with|to)|could you please help me (?:with|to))\s+",
    r"^(?:can you please|could you please|please)\s+",
    r"^(?:can you|could you)\s+",
    r"^(?:i want to know about|tell me about|explain to me|explain|what is the|what are the|what is|what are)\s+",
    r"^(?:how do i|how can i|how to)\s+",
    r"^(?:write a python script to|write a script to|write a python function to|write code to|write a|write an)\s+",
    r"^(?:create a|create an|generate a|generate an|build a|build an)\s+",
]


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


def get_warm_greeting(text: str) -> tuple[str, str]:
    """Return a tailored warm greeting and detected language for greeting input."""
    clean_text = text.strip().lower()
    for lang, data in GREETING_PATTERNS.items():
        if re.search(data["pattern"], clean_text, re.IGNORECASE):
            return str(data["warm"]), lang
    return "Hello! Welcome to ROXY AI. Ready when you are — how can I assist you today?", "english"


def clean_greeting_text(text: str) -> str:
    """Normalize text by lowercasing, stripping punctuation, emoji, and collapsing whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s']", " ", text.lower())
    return " ".join(cleaned.split())


def is_greeting(text: str) -> bool:
    """Return True if the text is exclusively or predominantly a greeting without a substantive query.

    Examples returning True:
        - "Hi", "Hello!", "Hey there", "Salam Roxy", "Good morning"
    Examples returning False:
        - "Hi, what is the capital of France?"
        - "Hello, can you write a python script to parse CSV files?"
        - "Salam, how do I link my bank account?"
    """
    if not text:
        return False

    cleaned = clean_greeting_text(text)
    if not cleaned:
        return False

    # Check exact match against single-word greetings
    if cleaned in _SINGLE_WORD_GREETINGS:
        return True

    # Check exact match against multi-word greetings
    if cleaned in _MULTI_WORD_GREETINGS:
        return True

    # Remove assistant name references like 'roxy', 'roxy ai', 'jarvis'
    without_name = re.sub(r"\b(roxy|roxy ai|assistant|ai|bot|jarvis)\b", "", cleaned).strip()
    without_name = " ".join(without_name.split())

    if without_name in _SINGLE_WORD_GREETINGS or without_name in _MULTI_WORD_GREETINGS:
        return True

    # Words check: if message has more than 5 words, it is almost certainly a substantive query
    words = cleaned.split()
    if len(words) > 5:
        return False

    # Check if every word in a short phrase is a greeting word or polite filler
    filler_words = {"there", "everyone", "all", "friend", "buddy", "mate", "team", "to", "you"}
    return all(w in _SINGLE_WORD_GREETINGS or w in filler_words for w in words)


def generate_smart_title(text: str) -> str:
    """Extract a concise 2–7 word title from user message, capped at 60 characters."""
    if not text:
        return "New Conversation"

    # Take the first line or sentence
    first_chunk = text.strip().splitlines()[0]
    first_chunk = re.split(r"[.?!]\s+", first_chunk)[0]

    # Remove markdown formatting characters
    cleaned = re.sub(r"[*_`#~\[\]()]", "", first_chunk).strip()

    # Strip conversational prefixes iteratively
    prev = ""
    while prev != cleaned:
        prev = cleaned
        for pat in _PROMPT_PREFIX_PATTERNS:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    # If stripped to empty, fallback to original cleaned
    if not cleaned:
        cleaned = re.sub(r"[*_`#~\[\]()]", "", first_chunk).strip()

    words = cleaned.split()
    if not words:
        return "New Conversation"

    lowercase_words = {"of", "the", "in", "on", "at", "to", "for", "with", "and", "or", "a", "an", "by", "as", "from"}

    # Limit to 2–7 words
    selected_words = words[:7]
    title = " ".join(selected_words)

    # Title-case each word appropriately while keeping common acronyms intact and prepositions lowercase
    titled_words = []
    for idx, raw_w in enumerate(title.split()):
        w = raw_w.rstrip("?!.:;, -")
        if not w:
            continue
        if w.upper() in {"AI", "API", "URL", "CSV", "JSON", "SQL", "HTML", "CSS", "JS", "TS", "REST", "ID", "USD", "PKR", "EUR", "GBP"}:
            titled_words.append(w.upper())
        elif idx > 0 and w.lower() in lowercase_words:
            titled_words.append(w.lower())
        elif len(w) > 1 and w[0].islower():
            titled_words.append(w.capitalize())
        else:
            titled_words.append(w)

    final_title = " ".join(titled_words).rstrip("?!.:;, -")

    # Cap at 60 characters cleanly
    if len(final_title) > 60:
        final_title = final_title[:57].rsplit(" ", 1)[0] + "..."

    return final_title or "New Conversation"
