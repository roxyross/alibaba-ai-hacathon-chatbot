"""Language and Script Detector for ROXY's Universal Multilingual Input Layer."""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

from app.multilingual.schemas import ScriptType, SupportedLanguage


class DetectionResult(NamedTuple):
    language: SupportedLanguage | str
    script: ScriptType | str
    confidence: float
    is_mixed: bool


class MultilingualDetector:
    """Classifies writing scripts and natural languages across global scripts and transliterations."""

    # Roman Urdu common function words & verbs
    _ROMAN_URDU_LEXICON = {
        "kholo", "khol", "karo", "kar", "bhejo", "bhej", "chalao", "chala", "band", "roko",
        "hai", "hain", "tha", "thi", "the", "mera", "meri", "mere", "mujhe", "mujh",
        "aur", "par", "pe", "mein", "me", "se", "ko", "ka", "ki", "ke", "yeh", "ye",
        "woh", "wo", "iska", "iski", "iske", "uska", "uski", "uske", "kya", "kyun",
        "kaise", "kahan", "kab", "kuch", "sab", "apna", "apni", "apne", "batao", "bata",
        "dikhao", "dikhaye", "hisab", "sunao", "likho", "parho", "dekho",
    }

    # Spanish lexicon
    _SPANISH_LEXICON = {
        "abrir", "abre", "calcular", "calcula", "archivo", "carpeta", "enviar", "mensaje",
        "hola", "por", "favor", "como", "esta", "este", "para", "con", "que", "hacer",
    }

    # French lexicon
    _FRENCH_LEXICON = {
        "ouvrir", "ouvre", "calculer", "calcule", "fichier", "dossier", "envoyer", "message",
        "bonjour", "pour", "avec", "dans", "faire", "ceci", "cela", "comment",
    }

    # German lexicon
    _GERMAN_LEXICON = {
        "öffnen", "oeffnen", "berechnen", "datei", "ordner", "senden", "nachricht", "hallo",
        "bitte", "wie", "dieser", "diese", "dieses", "machen", "kannst",
    }

    # Turkish lexicon
    _TURKISH_LEXICON = {
        "aç", "ac", "kapat", "hesapla", "dosya", "klasör", "gönder", "mesaj", "merhaba", "lütfen",
    }

    @classmethod
    def detect_script(cls, text: str) -> ScriptType:
        """Analyze Unicode code points to determine script families."""
        scripts_count: dict[str, int] = {
            ScriptType.LATIN: 0,
            ScriptType.ARABIC: 0,
            ScriptType.DEVANAGARI: 0,
            ScriptType.BENGALI: 0,
            ScriptType.CJK: 0,
            ScriptType.CYRILLIC: 0,
        }

        total_alpha = 0
        for char in text:
            if not char.isalpha():
                continue
            total_alpha += 1
            cp = ord(char)

            # Arabic / Perso-Arabic / Nastaliq
            if (0x0600 <= cp <= 0x06FF) or (0x0750 <= cp <= 0x077F) or (0x08A0 <= cp <= 0x08FF) or (0xFB50 <= cp <= 0xFDFF) or (0xFE70 <= cp <= 0xFEFF):
                scripts_count[ScriptType.ARABIC] += 1
            # Devanagari (Hindi, Sanskrit, Marathi)
            elif 0x0900 <= cp <= 0x097F:
                scripts_count[ScriptType.DEVANAGARI] += 1
            # Bengali (Bengali, Assamese)
            elif 0x0980 <= cp <= 0x09FF:
                scripts_count[ScriptType.BENGALI] += 1
            # CJK / Hiragana / Katakana / Hangul
            elif (0x4E00 <= cp <= 0x9FFF) or (0x3040 <= cp <= 0x30FF) or (0xAC00 <= cp <= 0xD7AF):
                scripts_count[ScriptType.CJK] += 1
            # Cyrillic
            elif 0x0400 <= cp <= 0x04FF:
                scripts_count[ScriptType.CYRILLIC] += 1
            # Latin
            elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A) or (0x00C0 <= cp <= 0x024F):
                scripts_count[ScriptType.LATIN] += 1

        if total_alpha == 0:
            return ScriptType.OTHER

        dominant_script, max_count = max(scripts_count.items(), key=lambda x: x[1])
        if max_count == 0:
            return ScriptType.OTHER

        # Check for mixed script (e.g. Urdu + English brand names)
        non_dominant = total_alpha - max_count
        if non_dominant > 0 and (non_dominant / total_alpha) > 0.25:
            return ScriptType.MIXED

        return ScriptType(dominant_script)

    @classmethod
    def detect(cls, text: str) -> DetectionResult:
        """Detect the language and writing system of the given input."""
        trimmed = text.strip()
        if not trimmed:
            return DetectionResult(SupportedLanguage.ENGLISH, ScriptType.LATIN, 1.0, False)

        script = cls.detect_script(trimmed)
        tokens = [w.lower() for w in re.findall(r"\b\w+\b", trimmed, re.UNICODE)]

        # 1. Arabic Script (Urdu, Arabic, Persian, Sindhi, Pashto)
        if script == ScriptType.ARABIC or (script == ScriptType.MIXED and any(0x0600 <= ord(c) <= 0x06FF for c in trimmed)):
            # Check for distinctive Urdu Nastaliq characters: ٹ, ڈ, ڑ, ں, ے, ھ, چ, پ, گ
            urdu_specific_chars = set("ٹڈڑںےھچپگ")
            arabic_specific_tokens = {"في", "من", "على", "إلى", "هذا", "هذه", "الذي", "التي", "اقرأ", "احسب", "افتح"}

            has_urdu_chars = any(c in urdu_specific_chars for c in trimmed)
            has_arabic_tokens = any(t in arabic_specific_tokens for t in tokens)

            if has_urdu_chars or not has_arabic_tokens:
                # Default to Urdu for Perso-Arabic unless explicit standard Arabic markers
                return DetectionResult(SupportedLanguage.URDU, ScriptType.ARABIC, 0.95, script == ScriptType.MIXED)
            else:
                return DetectionResult(SupportedLanguage.ARABIC, ScriptType.ARABIC, 0.95, script == ScriptType.MIXED)

        # 2. Devanagari Script (Hindi)
        if script == ScriptType.DEVANAGARI:
            return DetectionResult(SupportedLanguage.HINDI, ScriptType.DEVANAGARI, 0.98, False)

        # 3. Bengali Script
        if script == ScriptType.BENGALI:
            return DetectionResult(SupportedLanguage.BENGALI, ScriptType.BENGALI, 0.98, False)

        # 4. CJK / East Asian
        if script == ScriptType.CJK:
            # Check for Hiragana/Katakana for Japanese
            if any(0x3040 <= ord(c) <= 0x30FF for c in trimmed):
                return DetectionResult(SupportedLanguage.JAPANESE, ScriptType.CJK, 0.95, False)
            # Check for Hangul for Korean
            if any(0xAC00 <= ord(c) <= 0xD7AF for c in trimmed):
                return DetectionResult(SupportedLanguage.KOREAN, ScriptType.CJK, 0.95, False)
            return DetectionResult(SupportedLanguage.CHINESE, ScriptType.CJK, 0.95, False)

        # 5. Latin Script & Transliterations
        roman_urdu_matches = sum(1 for t in tokens if t in cls._ROMAN_URDU_LEXICON)
        spanish_matches = sum(1 for t in tokens if t in cls._SPANISH_LEXICON)
        french_matches = sum(1 for t in tokens if t in cls._FRENCH_LEXICON)
        german_matches = sum(1 for t in tokens if t in cls._GERMAN_LEXICON)
        turkish_matches = sum(1 for t in tokens if t in cls._TURKISH_LEXICON)

        # Roman Urdu / Hindi transliteration detection
        if roman_urdu_matches >= 1:
            confidence = min(0.98, 0.70 + (roman_urdu_matches * 0.10))
            is_mixed = any(w in ("python", "code", "fastapi", "react", "chrome", "calculator", "spotify", "whatsapp", "file", "folder") for w in tokens)
            return DetectionResult(SupportedLanguage.ROMAN_URDU, ScriptType.LATIN, confidence, is_mixed)

        if spanish_matches >= 2:
            return DetectionResult(SupportedLanguage.SPANISH, ScriptType.LATIN, 0.90, False)
        if french_matches >= 2:
            return DetectionResult(SupportedLanguage.FRENCH, ScriptType.LATIN, 0.90, False)
        if german_matches >= 2:
            return DetectionResult(SupportedLanguage.GERMAN, ScriptType.LATIN, 0.90, False)
        if turkish_matches >= 1:
            return DetectionResult(SupportedLanguage.TURKISH, ScriptType.LATIN, 0.88, False)

        # Default to English for Latin script
        return DetectionResult(SupportedLanguage.ENGLISH, ScriptType.LATIN, 0.92, False)
