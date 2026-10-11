"""Pydantic schemas and types for the Universal Multilingual Input Layer."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SupportedLanguage(StrEnum):
    """Core supported and recognized natural languages and scripts."""
    ENGLISH = "en"
    URDU = "ur"
    ROMAN_URDU = "ur_roman"
    HINDI = "hi"
    ARABIC = "ar"
    BENGALI = "bn"
    PUNJABI = "pa"
    SINDHI = "sd"
    PASHTO = "ps"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    TURKISH = "tr"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    MIXED = "mixed"
    UNSUPPORTED = "unsupported"


class ScriptType(StrEnum):
    """Writing script system classification."""
    LATIN = "latin"
    ARABIC = "arabic"  # Covers Perso-Arabic, Urdu Nastaliq, Sindhi, Pashto
    DEVANAGARI = "devanagari"
    BENGALI = "bengali"
    CJK = "cjk"
    CYRILLIC = "cyrillic"
    MIXED = "mixed"
    OTHER = "other"


class IntentCategory(StrEnum):
    """Universal semantic intent taxonomy."""
    APP_CONTROL = "app_control"
    CODING = "coding"
    FILE_OPERATION = "file_operation"
    CALCULATION = "calculation"
    COMMUNICATION = "communication"
    RESEARCH = "research"
    DEVICE_FLEET = "device_fleet"
    QUESTION = "question"
    UNKNOWN = "unknown"


class UniversalSemanticIntent(BaseModel):
    """Language-independent, canonical structured representation of user requests."""
    detected_language: SupportedLanguage | str = SupportedLanguage.ENGLISH
    script: ScriptType | str = ScriptType.LATIN
    input_mode: str = Field(default="text", description="'text' or 'voice'")
    intent_category: IntentCategory = IntentCategory.UNKNOWN
    target_app: str | None = None
    target_device_hint: str | None = None
    action: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_input: str
    normalized_query: str
    is_mixed_language: bool = False
    is_supported: bool = True
