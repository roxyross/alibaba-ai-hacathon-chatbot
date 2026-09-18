"""Pydantic v2 schemas for Study & Learning Studio (Phase 16).

Validates decks, flashcards, spaced repetition reviews, AI generation requests,
and quiz submission sessions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Study Decks
# ---------------------------------------------------------------------------

class DeckCreate(BaseModel):
    """Payload for creating a new study deck."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None)
    subject: str = Field(default="General", max_length=100)
    tags: list[str] = Field(default_factory=list)


class DeckUpdate(BaseModel):
    """Payload for updating an existing study deck."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    subject: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = Field(default=None)


class DeckResponse(BaseModel):
    """Public representation of a study deck."""

    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: str
    title: str
    description: str | None = None
    subject: str = "General"
    tags: list[str] = Field(default_factory=list)
    card_count: int = 0
    mastery_percentage: float = 0.0
    created_at: str | None = None
    updated_at: str | None = None


class DeckListResponse(BaseModel):
    """Collection of study decks."""

    model_config = ConfigDict(extra="ignore")

    decks: list[DeckResponse] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------

class CardCreate(BaseModel):
    """Payload for manually adding a flashcard to a deck."""

    model_config = ConfigDict(extra="ignore")

    front: str = Field(..., min_length=1)
    back: str = Field(..., min_length=1)
    explanation: str | None = Field(default=None)
    level: str = Field(default="intermediate")


class CardUpdate(BaseModel):
    """Payload for updating an existing flashcard."""

    model_config = ConfigDict(extra="ignore")

    front: str | None = Field(default=None, min_length=1)
    back: str | None = Field(default=None, min_length=1)
    explanation: str | None = Field(default=None)
    level: str | None = Field(default=None)
    box: int | None = Field(default=None, ge=1, le=5)


class CardResponse(BaseModel):
    """Public representation of a flashcard."""

    model_config = ConfigDict(extra="ignore")

    id: str
    deck_id: str
    user_id: str
    front: str
    back: str
    explanation: str | None = None
    level: str = "intermediate"
    box: int = 1
    next_review_at: str | None = None
    last_reviewed_at: str | None = None
    review_count: int = 0
    correct_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class CardListResponse(BaseModel):
    """List of flashcards."""

    model_config = ConfigDict(extra="ignore")

    cards: list[CardResponse] = Field(default_factory=list)
    total: int = 0


class CardReviewRequest(BaseModel):
    """Payload for submitting a spaced repetition flashcard review."""

    model_config = ConfigDict(extra="ignore")

    is_correct: bool = Field(..., description="Whether the user correctly answered the card")


# ---------------------------------------------------------------------------
# AI Generation: Flashcards & Quizzes
# ---------------------------------------------------------------------------

class GenerateFlashcardsRequest(BaseModel):
    """Request payload to generate flashcards from topic or notes."""

    model_config = ConfigDict(extra="ignore")

    topic: str = Field(..., min_length=1, max_length=255)
    source_text: str | None = Field(default=None, description="Optional raw text, lecture notes, or markdown")
    count: int = Field(default=5, ge=1, le=25)
    level: str = Field(default="intermediate", description="beginner, intermediate, advanced")
    save_to_deck_id: str | None = Field(default=None, description="Existing deck ID to auto-save generated cards")
    new_deck_title: str | None = Field(default=None, description="If provided, creates a new deck with this title")


class GeneratedCard(BaseModel):
    """Single generated flashcard."""

    model_config = ConfigDict(extra="ignore")

    front: str
    back: str
    explanation: str | None = None
    tags: list[str] = Field(default_factory=list)


class GenerateFlashcardsResponse(BaseModel):
    """Response containing generated flashcards."""

    model_config = ConfigDict(extra="ignore")

    topic: str
    count: int
    level: str
    cards: list[GeneratedCard]
    deck_id: str | None = None
    deck_title: str | None = None


class GenerateQuizRequest(BaseModel):
    """Request payload to generate a practice quiz."""

    model_config = ConfigDict(extra="ignore")

    topic: str = Field(..., min_length=1, max_length=255)
    source_text: str | None = Field(default=None)
    count: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="medium", description="easy, medium, hard")
    deck_id: str | None = Field(default=None)


class QuizQuestion(BaseModel):
    """Single multiple-choice quiz question."""

    model_config = ConfigDict(extra="ignore")

    question: str
    options: list[str] = Field(..., min_length=2, max_length=6)
    correct_index: int = Field(..., ge=0)
    explanation: str


class GenerateQuizResponse(BaseModel):
    """Response containing generated quiz questions."""

    model_config = ConfigDict(extra="ignore")

    topic: str
    count: int
    difficulty: str
    questions: list[QuizQuestion]


# ---------------------------------------------------------------------------
# Quiz Sessions & Scoring
# ---------------------------------------------------------------------------

class QuizSubmitRequest(BaseModel):
    """Submission payload for a completed quiz session."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="Practice Quiz", max_length=255)
    topic: str = Field(..., min_length=1, max_length=255)
    difficulty: str = Field(default="medium")
    deck_id: str | None = Field(default=None)
    questions: list[dict[str, Any]] = Field(..., min_length=1)
    user_answers: dict[str, int] = Field(..., description="Mapping of question index string to selected option index")


class QuizSessionResponse(BaseModel):
    """Public representation of a completed quiz session."""

    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: str
    deck_id: str | None = None
    title: str
    topic: str
    difficulty: str
    questions: list[dict[str, Any]] = Field(default_factory=list)
    user_answers: dict[str, Any] = Field(default_factory=dict)
    score: int = 0
    total_questions: int = 0
    score_percentage: float = 0.0
    passed: bool = False
    completed_at: str | None = None
    created_at: str | None = None


class QuizListResponse(BaseModel):
    """List of past quiz sessions."""

    model_config = ConfigDict(extra="ignore")

    quizzes: list[QuizSessionResponse] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Study Overview Stats
# ---------------------------------------------------------------------------

class StudyStatsResponse(BaseModel):
    """Aggregated study overview metrics for the authenticated user."""

    model_config = ConfigDict(extra="ignore")

    total_decks: int = 0
    total_cards: int = 0
    cards_due_for_review: int = 0
    average_mastery: float = 0.0
    completed_quizzes: int = 0
    average_quiz_score: float = 0.0
