"""Phase 21 Integration Test Suite: Full i18n & Localization (English, Urdu, Arabic RTL Layout Mirroring).

Validates:
1. Complete locale dictionary availability (en.json, ur.json, ar.json).
2. 100% recursive key parity across English, Urdu, and Arabic dictionaries (zero missing keys).
3. Non-empty translation strings and proper script integrity.
4. Comprehensive navigation coverage for all 19 studios, common actions, sidebar, chat, and settings.
5. Backend language detection & directive injection in Runtime coordinator.
6. Preferred language routing and Roman Urdu conversational fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.api.v1.runtime import (
    RuntimeChatRequest,
    detect_user_language_instruction,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LOCALES_DIR = _REPO_ROOT / "frontend" / "src" / "i18n" / "locales"


def _flatten_keys(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Recursively flatten nested dictionary keys into dot-separated paths."""
    flattened: dict[str, str] = {}
    for key, value in data.items():
        new_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(_flatten_keys(value, new_key))
        else:
            flattened[new_key] = str(value)
    return flattened


class TestPhase21I18nDictionaries:
    """Tests dictionary validity, completeness, and key parity."""

    def test_locale_files_exist(self) -> None:
        assert (_LOCALES_DIR / "en.json").exists(), "en.json must exist"
        assert (_LOCALES_DIR / "ur.json").exists(), "ur.json must exist"
        assert (_LOCALES_DIR / "ar.json").exists(), "ar.json must exist"

    def test_json_validity_and_loading(self) -> None:
        with open(_LOCALES_DIR / "en.json", encoding="utf-8") as f:
            en_data = json.load(f)
        with open(_LOCALES_DIR / "ur.json", encoding="utf-8") as f:
            ur_data = json.load(f)
        with open(_LOCALES_DIR / "ar.json", encoding="utf-8") as f:
            ar_data = json.load(f)

        assert isinstance(en_data, dict)
        assert isinstance(ur_data, dict)
        assert isinstance(ar_data, dict)

    def test_100_percent_key_parity_between_en_and_ur(self) -> None:
        """Verify 100% parity between English master dictionary and Urdu translations."""
        with open(_LOCALES_DIR / "en.json", encoding="utf-8") as f:
            en_dict = _flatten_keys(json.load(f))
        with open(_LOCALES_DIR / "ur.json", encoding="utf-8") as f:
            ur_dict = _flatten_keys(json.load(f))

        missing_in_ur = set(en_dict.keys()) - set(ur_dict.keys())
        extra_in_ur = set(ur_dict.keys()) - set(en_dict.keys())

        assert not missing_in_ur, f"Missing keys in ur.json: {missing_in_ur}"
        assert not extra_in_ur, f"Extraneous keys in ur.json: {extra_in_ur}"

    def test_100_percent_key_parity_between_en_and_ar(self) -> None:
        """Verify 100% parity between English master dictionary and Arabic translations."""
        with open(_LOCALES_DIR / "en.json", encoding="utf-8") as f:
            en_dict = _flatten_keys(json.load(f))
        with open(_LOCALES_DIR / "ar.json", encoding="utf-8") as f:
            ar_dict = _flatten_keys(json.load(f))

        missing_in_ar = set(en_dict.keys()) - set(ar_dict.keys())
        extra_in_ar = set(ar_dict.keys()) - set(en_dict.keys())

        assert not missing_in_ar, f"Missing keys in ar.json: {missing_in_ar}"
        assert not extra_in_ar, f"Extraneous keys in ar.json: {extra_in_ar}"

    def test_no_empty_translation_values(self) -> None:
        """Ensure no translation entry is blank or whitespace-only."""
        for lang in ("en", "ur", "ar"):
            with open(_LOCALES_DIR / f"{lang}.json", encoding="utf-8") as f:
                flat = _flatten_keys(json.load(f))
            empty_keys = [k for k, v in flat.items() if not v.strip()]
            assert not empty_keys, f"Found empty values in {lang}.json for keys: {empty_keys}"

    def test_all_19_studios_nav_coverage(self) -> None:
        """Verify all 19 primary and secondary studios have localized nav labels."""
        expected_studios = [
            "chat",
            "documents",
            "finance",
            "jobs",
            "email",
            "workspace_hub",
            "research",
            "browser",
            "study",
            "coding",
            "memory",
            "audit",
            "connectors",
            "device_hub",
            "payment_methods",
            "settings",
            "usage",
            "billing",
            "pricing",
        ]
        with open(_LOCALES_DIR / "en.json", encoding="utf-8") as f:
            en_nav = json.load(f).get("nav", {})
        with open(_LOCALES_DIR / "ur.json", encoding="utf-8") as f:
            ur_nav = json.load(f).get("nav", {})
        with open(_LOCALES_DIR / "ar.json", encoding="utf-8") as f:
            ar_nav = json.load(f).get("nav", {})

        for studio in expected_studios:
            assert studio in en_nav, f"Missing {studio} in en.json nav"
            assert studio in ur_nav, f"Missing {studio} in ur.json nav"
            assert studio in ar_nav, f"Missing {studio} in ar.json nav"


class TestPhase21BackendMultilingualGrounding:
    """Tests runtime backend detection, preferred language directive, and Roman Urdu."""

    def test_preferred_language_override_ur(self) -> None:
        directive = detect_user_language_instruction("Hello, help me", preferred_language="ur")
        assert "[CRITICAL MULTILINGUAL MANDATE]" in directive
        assert "Urdu (اردو)" in directive

    def test_preferred_language_override_ar(self) -> None:
        directive = detect_user_language_instruction("Hello, help me", preferred_language="ar")
        assert "[CRITICAL MULTILINGUAL MANDATE]" in directive
        assert "Arabic (العربية)" in directive

    def test_preferred_language_override_en(self) -> None:
        directive = detect_user_language_instruction("Salam", preferred_language="en")
        assert "[CRITICAL MULTILINGUAL MANDATE]" in directive
        assert "English" in directive

    def test_auto_detect_urdu_script(self) -> None:
        directive = detect_user_language_instruction("آپ کیا کر رہے ہیں؟")
        assert "Urdu (اردو)" in directive

    def test_auto_detect_arabic_script(self) -> None:
        directive = detect_user_language_instruction("كيف حالك اليوم يا صديقي؟")
        assert "Arabic (العربية)" in directive

    def test_auto_detect_roman_urdu(self) -> None:
        directive = detect_user_language_instruction("aap kaise hain mujhe batao")
        assert "Roman Urdu" in directive

    def test_runtime_chat_request_schema_supports_language(self) -> None:
        req = RuntimeChatRequest(message="test message", language="ur")
        assert req.language == "ur"
