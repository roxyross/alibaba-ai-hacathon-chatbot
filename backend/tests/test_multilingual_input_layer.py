"""Unit and Integration Tests for Universal Multilingual Input Layer & Voice Parity (Phase M2)."""

from __future__ import annotations

from app.multilingual.detector import MultilingualDetector
from app.multilingual.normalizer import UniversalIntentNormalizer
from app.multilingual.schemas import IntentCategory, ScriptType, SupportedLanguage
from app.multilingual.service import MultilingualInputService


def test_script_detection() -> None:
    """Verify Unicode code point script classification across writing systems."""
    assert MultilingualDetector.detect_script("Hello world") == ScriptType.LATIN
    assert MultilingualDetector.detect_script("روکسی کیلکولیٹر کھولو") == ScriptType.ARABIC
    assert MultilingualDetector.detect_script("रॉक्सी कैलकुलेटर खोलो") == ScriptType.DEVANAGARI
    assert MultilingualDetector.detect_script("রক্সি ক্যালকুলেটর খোল") == ScriptType.BENGALI
    assert MultilingualDetector.detect_script("打开计算器") == ScriptType.CJK
    assert MultilingualDetector.detect_script("電卓を開いて") == ScriptType.CJK


def test_language_detection() -> None:
    """Verify language detection across English, Roman Urdu, Urdu Nastaliq, Hindi, Arabic, and European languages."""
    # English
    d_en = MultilingualDetector.detect("Open Chrome and search for machine learning papers")
    assert d_en.language == SupportedLanguage.ENGLISH

    # Roman Urdu
    d_ur_roman = MultilingualDetector.detect("Calculator kholo aur 125 * 8 hisab karo")
    assert d_ur_roman.language == SupportedLanguage.ROMAN_URDU

    # Urdu Nastaliq
    d_ur = MultilingualDetector.detect("روکسی کیلکولیٹر کھولو اور حساب کرو")
    assert d_ur.language == SupportedLanguage.URDU

    # Hindi Devanagari
    d_hi = MultilingualDetector.detect("रॉक्सी कैलकुलेटर खोलो")
    assert d_hi.language == SupportedLanguage.HINDI

    # Arabic
    d_ar = MultilingualDetector.detect("افتح الآلة الحاسبة في هذا الجهاز")
    assert d_ar.language == SupportedLanguage.ARABIC

    # Spanish
    d_es = MultilingualDetector.detect("Hola abrir archivo por favor")
    assert d_es.language == SupportedLanguage.SPANISH


def test_mixed_language_detection() -> None:
    """Verify detection of mixed language input (Roman Urdu + English technical terminology)."""
    d_mixed = MultilingualDetector.detect("Python mein FastAPI API bana do aur iska test likho")
    assert d_mixed.language == SupportedLanguage.ROMAN_URDU
    assert d_mixed.is_mixed is True


def test_multilingual_app_control_normalization() -> None:
    """Verify that multilingual variations map to the canonical App Control intent."""
    queries = [
        "open calculator",
        "calculator kholo",
        "کیلکولیٹر کھولو",
        "कैलकुलेटर खोलो",
        "افتح الآلة الحاسبة",
        "ouvrir calculatrice",
    ]

    for q in queries:
        intent = UniversalIntentNormalizer.normalize(q)
        assert intent.intent_category == IntentCategory.APP_CONTROL, f"Failed for query: {q}"
        assert intent.target_app == "Calculator", f"Target app mismatch for query: {q}"
        assert intent.action == "open", f"Action mismatch for query: {q}"


def test_multilingual_calculation_normalization() -> None:
    """Verify that multilingual calculation queries normalize expression correctly."""
    calc_queries = [
        ("calculate 25 * 8", "25 * 8"),
        ("125 × 8 hisab karo", "125 * 8"),
        ("125 ضرب 8 کا حساب کرو", "125 * 8"),
        ("25 + 5 kitna hota hai", "25 + 5"),
    ]

    for q, expected_expr in calc_queries:
        intent = UniversalIntentNormalizer.normalize(q)
        assert intent.intent_category == IntentCategory.CALCULATION, f"Failed category for: {q}"
        assert intent.action == "calculate"
        assert expected_expr in intent.parameters.get("expression", ""), f"Expression mismatch for {q}"


def test_multilingual_file_and_folder_normalization() -> None:
    """Verify file and folder operations mapped into canonical intents."""
    f1 = UniversalIntentNormalizer.normalize("read this project folder and find the bug")
    assert f1.intent_category == IntentCategory.FILE_OPERATION
    assert f1.action == "analyze_folder"

    f2 = UniversalIntentNormalizer.normalize("ye folder read karo aur issue batao")
    assert f2.intent_category == IntentCategory.FILE_OPERATION
    assert f2.action == "analyze_folder"

    f3 = UniversalIntentNormalizer.normalize("اقرأ هذا المجلد")
    assert f3.intent_category == IntentCategory.FILE_OPERATION
    assert f3.action == "analyze_folder"


def test_multilingual_coding_intent_normalization() -> None:
    """Verify coding requests in various languages extract target language and prompt."""
    c1 = UniversalIntentNormalizer.normalize("Python mein FastAPI API bana do")
    assert c1.intent_category == IntentCategory.CODING
    assert c1.parameters.get("programming_language") == "python"

    c2 = UniversalIntentNormalizer.normalize("create a TypeScript API component")
    assert c2.intent_category == IntentCategory.CODING
    assert c2.parameters.get("programming_language") == "typescript"


def test_multilingual_service_singleton_and_process() -> None:
    """Verify MultilingualInputService singleton behaves consistently."""
    service = MultilingualInputService.get_instance()
    intent = service.process_input("Spotify chalao aur music sunao", input_mode="voice")
    assert intent.input_mode == "voice"
    assert intent.intent_category == IntentCategory.APP_CONTROL
    assert intent.target_app == "Spotify"
    assert intent.detected_language == SupportedLanguage.ROMAN_URDU
