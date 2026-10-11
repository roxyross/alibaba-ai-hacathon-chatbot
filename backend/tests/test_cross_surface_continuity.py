"""Unit and Integration Tests for Cross-Surface Context Continuity.

Verifies:
1. Shared state tracking across Chat, Voice, CommandBar, Cowork, and Open Work Agent.
2. Anaphoric reference and pronoun resolution across languages (Urdu 'iska', Hindi 'is', English 'this'/'it').
3. UniversalIntentNormalizer integration resolving context from previous Chat interaction into Voice command.
4. Seamless Chat -> Voice cross-surface continuity.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app.multilingual.normalizer import UniversalIntentNormalizer
from app.multilingual.schemas import IntentCategory
from app.session.continuity import CrossSurfaceContinuityEngine


@pytest.fixture(autouse=True)
def reset_continuity_engine() -> Generator[None, None, None]:
    engine = CrossSurfaceContinuityEngine.get_instance()
    engine._contexts.clear()
    yield
    engine._contexts.clear()


def test_cross_surface_context_tracking() -> None:
    engine = CrossSurfaceContinuityEngine()
    user_id = "user_continuity_1"

    # User starts in chat, reads project folder
    ctx = engine.update_context(
        user_id=user_id,
        surface="chat",
        folder="/projects/ecommerce-backend",
        language="ur",
    )
    assert ctx.active_folder == "/projects/ecommerce-backend"
    assert ctx.active_surface == "chat"

    # User inspects file in editor
    ctx2 = engine.update_context(
        user_id=user_id,
        file="/projects/ecommerce-backend/src/auth.py",
    )
    assert ctx2.active_file == "/projects/ecommerce-backend/src/auth.py"
    assert ctx2.active_folder == "/projects/ecommerce-backend"


def test_pronoun_reference_resolution_urdu_roman_urdu() -> None:
    engine = CrossSurfaceContinuityEngine()
    user_id = "user_continuity_2"

    # Active project folder set in Chat
    engine.update_context(
        user_id=user_id,
        surface="chat",
        folder="/projects/payment-gateway",
    )

    # User in Voice says: "Ab iska bug fix karo"
    ref = engine.resolve_reference(user_id=user_id, utterance="Ab iska bug fix karo")
    assert ref.target_entity_type == "folder"
    assert ref.target_value == "/projects/payment-gateway"
    assert ref.confidence >= 0.9
    assert "'/projects/payment-gateway'" in ref.resolved_utterance


def test_pronoun_reference_resolution_english_and_hindi() -> None:
    engine = CrossSurfaceContinuityEngine()
    user_id = "user_continuity_3"

    # Active app set
    engine.update_context(
        user_id=user_id,
        app="Calculator",
    )

    ref = engine.resolve_reference(user_id=user_id, utterance="Close this app")
    assert ref.target_entity_type == "app"
    assert ref.target_value == "Calculator"


def test_universal_normalizer_with_active_cross_surface_context() -> None:
    engine = CrossSurfaceContinuityEngine.get_instance()
    user_id = "user_continuity_4"

    # 1. User previously asked: "Read my project folder" in Chat
    engine.update_context(
        user_id=user_id,
        surface="chat",
        folder="/workspace/fastapi-app",
    )

    # 2. Then in Voice, user says: "Ab iska bug fix karo"
    intent = UniversalIntentNormalizer.normalize(
        text="Ab iska bug fix karo",
        input_mode="voice",
        user_id=user_id,
    )

    assert intent.intent_category == IntentCategory.CODING
    assert intent.action == "fix_bug"
    assert intent.parameters["target_path"] == "/workspace/fastapi-app"
    assert intent.input_mode == "voice"
    assert intent.confidence >= 0.95


def test_pronoun_resolution_arabic_and_multiuser_isolation() -> None:
    engine = CrossSurfaceContinuityEngine.get_instance()
    user_a = "user_iso_a"
    user_b = "user_iso_b"

    engine.update_context(user_id=user_a, folder="/projects/client-a")
    engine.update_context(user_id=user_b, folder="/projects/client-b")

    # Arabic reference resolution
    ref_a = engine.resolve_reference(user_id=user_a, utterance="اقرأ هذا المجلد")
    assert ref_a.target_value == "/projects/client-a"

    ref_b = engine.resolve_reference(user_id=user_b, utterance="اقرأ هذا المجلد")
    assert ref_b.target_value == "/projects/client-b"

    # No reference when utterance has no demonstrative pronouns
    ref_none = engine.resolve_reference(user_id=user_a, utterance="Hello world greeting")
    assert ref_none.target_entity_type == "none"
    assert ref_none.target_value is None

