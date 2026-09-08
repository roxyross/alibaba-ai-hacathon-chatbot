"""Unit tests for P2 skill stubs.

Tests that each stub:
- Returns a SkillResult with ok=True
- Includes a stub warning
- Accepts the expected inputs
- Handles missing/empty optional args gracefully
"""

from __future__ import annotations

import pytest

from runtime.skills.document_rag_query import document_rag_query
from runtime.skills.flashcard_generate import flashcard_generate
from runtime.skills.quiz_generate import quiz_generate
from runtime.skills.speech_to_text import speech_to_text
from runtime.skills.text_to_speech import text_to_speech
from runtime.skills.browser_navigate import browser_navigate
from runtime.skills.browser_fill_form import browser_fill_form


# ---- document_rag_query ----------------------------------------------------

@pytest.mark.asyncio
async def test_document_rag_query_returns_result() -> None:
    result = await document_rag_query(query="what does the contract say about liability", user_id="u1")
    assert result.ok is True
    assert result.warning is not None
    assert "stub" in result.warning.lower()
    assert "chunks" in result.data
    assert len(result.data["chunks"]) == 1
    assert result.data["chunks"][0]["document_id"] == "stub-doc-001"


@pytest.mark.asyncio
async def test_document_rag_query_with_doc_ids() -> None:
    result = await document_rag_query(
        query="liability clause",
        document_ids=["doc-1", "doc-2"],
        top_k=5,
        user_id="u1",
    )
    assert result.ok is True
    assert result.data["total_candidates"] == 1


@pytest.mark.asyncio
async def test_document_rag_query_empty_query() -> None:
    result = await document_rag_query(query="", user_id="u1")
    # Empty query is still a stub result (real impl would validate)
    assert result.ok is True


# ---- flashcard_generate ----------------------------------------------------

@pytest.mark.asyncio
async def test_flashcard_generate_returns_deck() -> None:
    result = await flashcard_generate(
        source="Python decorators and closures",
        count=5,
        user_id="u1",
    )
    assert result.ok is True
    assert result.warning is not None
    assert "stub" in result.warning.lower()
    assert "deck_id" in result.data
    assert len(result.data["cards"]) == 5
    assert result.data["cards"][0]["front"] != result.data["cards"][0]["back"]


@pytest.mark.asyncio
async def test_flashcard_generate_respects_level() -> None:
    result = await flashcard_generate(
        source="machine learning",
        level="expert",
        user_id="u1",
    )
    assert result.ok is True
    assert result.data["cards"][0]["tags"] == ["stub", "placeholder"]


@pytest.mark.asyncio
async def test_flashcard_generate_respects_format() -> None:
    result = await flashcard_generate(source="calculus", format="cloze", user_id="u1")
    assert result.ok is True
    # All cards should mention the source topic
    assert all("calculus" in c["front"] or "calculus" in c["back"] for c in result.data["cards"])


# ---- quiz_generate --------------------------------------------------------

@pytest.mark.asyncio
async def test_quiz_generate_returns_questions() -> None:
    result = await quiz_generate(source="world war 2", count=5, user_id="u1")
    assert result.ok is True
    assert result.warning is not None
    assert "quiz_id" in result.data
    assert len(result.data["questions"]) <= 5


@pytest.mark.asyncio
async def test_quiz_generate_with_types() -> None:
    result = await quiz_generate(
        source="organic chemistry",
        types=["mcq"],
        count=3,
        user_id="u1",
    )
    assert result.ok is True
    assert all(q["type"] == "mcq" for q in result.data["questions"])
    # Each MCQ should have 4 choices
    for q in result.data["questions"]:
        assert len(q["choices"]) == 4


@pytest.mark.asyncio
async def test_quiz_generate_answer_key_hidden() -> None:
    result = await quiz_generate(source="roman history", count=3, user_id="u1")
    assert result.ok is True
    assert "answer_key_hidden" in result.data
    # No answer should appear in the prompt (answer may be int index for MCQ or str)
    for q in result.data["questions"]:
        answer = q["answer"]
        prompt = q["prompt"]
        # Integer index (MCQ) never appears in prompt; string answer shouldn't either
        assert str(answer) not in prompt


# ---- speech_to_text --------------------------------------------------------

@pytest.mark.asyncio
async def test_speech_to_text_returns_transcript() -> None:
    result = await speech_to_text(session_id="s1", user_id="u1")
    assert result.ok is True
    assert result.warning is not None
    assert "stub" in result.warning.lower()
    assert "transcripts" in result.data
    assert len(result.data["transcripts"]) == 1
    assert result.data["transcripts"][0]["is_final"] is True


@pytest.mark.asyncio
async def test_speech_to_text_with_audio() -> None:
    result = await speech_to_text(audio_data="base64_audio_data", session_id="s1", user_id="u1")
    assert result.ok is True
    assert result.data["session_id"] == "s1"


# ---- text_to_speech --------------------------------------------------------

@pytest.mark.asyncio
async def test_text_to_speech_returns_audio_data() -> None:
    result = await text_to_speech(
        text="Hello, this is a test of the text to speech system.",
        user_id="u1",
    )
    assert result.ok is True
    assert result.warning is not None
    assert "stub" in result.warning.lower()
    assert result.data["stub"] is True
    assert result.data["voice"] == "default"


@pytest.mark.asyncio
async def test_text_to_speech_respects_params() -> None:
    result = await text_to_speech(
        text="Testing voice options.",
        voice="alex",
        speed=0.8,
        format="wav",
        user_id="u1",
    )
    assert result.ok is True
    assert result.data["voice"] == "alex"
    assert result.data["speed"] == 0.8
    assert result.data["format"] == "wav"


# ---- browser_navigate ------------------------------------------------------

@pytest.mark.asyncio
async def test_browser_navigate_returns_result() -> None:
    result = await browser_navigate(
        url="https://example.com/invoice",
        user_id="u1",
    )
    assert result.ok is True
    assert result.warning is not None
    assert "stub" in result.warning.lower()
    assert "pages_visited" in result.data
    assert result.data["pages_visited"][0] == "https://example.com/invoice"


@pytest.mark.asyncio
async def test_browser_navigate_with_actions() -> None:
    result = await browser_navigate(
        url="https://example.com/login",
        actions=[{"type": "click", "selector": "#submit"}],
        timeout_seconds=30,
        user_id="u1",
    )
    assert result.ok is True
    assert result.data["pages_visited"] == ["https://example.com/login"]


# ---- browser_fill_form -----------------------------------------------------

@pytest.mark.asyncio
async def test_browser_fill_form_returns_result() -> None:
    result = await browser_fill_form(
        url="https://example.com/contact",
        fields={"name": "Jane Doe", "email": "jane@example.com"},
        submit=True,
        user_id="u1",
    )
    assert result.ok is True
    assert result.warning is not None
    assert "stub" in result.warning.lower()
    assert result.data["url"] == "https://example.com/contact"
    assert result.data["submitted"] is True
    assert result.data["stub"] is True


@pytest.mark.asyncio
async def test_browser_fill_form_no_submit() -> None:
    result = await browser_fill_form(
        url="https://example.com/preview",
        fields={"comment": "Looks good"},
        submit=False,
        user_id="u1",
    )
    assert result.ok is True
    assert result.data["submitted"] is False
