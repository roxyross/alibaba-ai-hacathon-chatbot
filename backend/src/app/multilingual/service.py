"""Multilingual Input Service unifying text and voice commands into universal semantic intents."""

from __future__ import annotations

from typing import ClassVar

import structlog

from app.multilingual.detector import DetectionResult, MultilingualDetector
from app.multilingual.normalizer import UniversalIntentNormalizer
from app.multilingual.schemas import UniversalSemanticIntent

log = structlog.get_logger()


class MultilingualInputService:
    """Service providing language detection, script classification, and intent normalization."""

    _instance: ClassVar[MultilingualInputService | None] = None

    @classmethod
    def get_instance(cls) -> MultilingualInputService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def detect_language(self, text: str) -> DetectionResult:
        """Detect the natural language, writing script, and confidence for a prompt."""
        return MultilingualDetector.detect(text)

    def process_input(
        self,
        text: str,
        input_mode: str = "text",
    ) -> UniversalSemanticIntent:
        """Parse raw user input into a normalized, language-independent semantic intent object."""
        intent = UniversalIntentNormalizer.normalize(text, input_mode=input_mode)
        log.info(
            "multilingual.input_processed",
            raw_input=text[:60],
            language=intent.detected_language,
            script=intent.script,
            category=intent.intent_category,
            action=intent.action,
            target_app=intent.target_app,
        )
        return intent
