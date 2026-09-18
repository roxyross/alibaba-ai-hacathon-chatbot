"""SQLAlchemy ORM models for Study Decks, Flashcards, and Quizzes (Phase 16).

Supports multi-tenant persistence of study materials, flashcard decks,
Leitner spaced repetition tracking, and interactive practice quiz sessions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


class StudyDeck(Base):
    """Study Deck entity grouping flashcards and tracking overall mastery."""

    __tablename__ = "study_decks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, default="General")
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Comma-separated tags
    card_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mastery_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    cards: Mapped[list[StudyCard]] = relationship(
        "StudyCard",
        back_populates="deck",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_study_decks_user_created", "user_id", "created_at"),
        Index("ix_study_decks_user_subject", "user_id", "subject"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize study deck to dictionary with type-safe fields."""
        tag_list: list[str] = []
        if isinstance(self.tags, str):
            tag_list = [t.strip() for t in self.tags.split(",") if t.strip()]
        elif isinstance(self.tags, (list, tuple)):
            tag_list = [str(t).strip() for t in self.tags if str(t).strip()]

        created_at_str = (
            self.created_at.isoformat()
            if hasattr(self.created_at, "isoformat")
            else (str(self.created_at) if self.created_at else None)
        )
        updated_at_str = (
            self.updated_at.isoformat()
            if hasattr(self.updated_at, "isoformat")
            else (str(self.updated_at) if self.updated_at else None)
        )

        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "subject": self.subject,
            "tags": tag_list,
            "card_count": int(self.card_count),
            "mastery_percentage": round(float(self.mastery_percentage), 1),
            "created_at": created_at_str,
            "updated_at": updated_at_str,
        }


class StudyCard(Base):
    """Individual Flashcard item with Leitner spaced repetition metadata."""

    __tablename__ = "study_cards"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    deck_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_decks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="intermediate")

    # Spaced Repetition (Leitner 1-5 box system)
    box: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    deck: Mapped[StudyDeck] = relationship("StudyDeck", back_populates="cards")

    __table_args__ = (
        Index("ix_study_cards_user_deck", "user_id", "deck_id"),
        Index("ix_study_cards_review_due", "user_id", "next_review_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize flashcard to dictionary with formatted timestamps."""
        created_at_str = (
            self.created_at.isoformat()
            if hasattr(self.created_at, "isoformat")
            else (str(self.created_at) if self.created_at else None)
        )
        updated_at_str = (
            self.updated_at.isoformat()
            if hasattr(self.updated_at, "isoformat")
            else (str(self.updated_at) if self.updated_at else None)
        )
        next_review_str = (
            self.next_review_at.isoformat()
            if hasattr(self.next_review_at, "isoformat") and self.next_review_at
            else (str(self.next_review_at) if self.next_review_at else None)
        )
        last_reviewed_str = (
            self.last_reviewed_at.isoformat()
            if hasattr(self.last_reviewed_at, "isoformat") and self.last_reviewed_at
            else (str(self.last_reviewed_at) if self.last_reviewed_at else None)
        )

        return {
            "id": self.id,
            "deck_id": self.deck_id,
            "user_id": self.user_id,
            "front": self.front,
            "back": self.back,
            "explanation": self.explanation,
            "level": self.level,
            "box": int(self.box),
            "next_review_at": next_review_str,
            "last_reviewed_at": last_reviewed_str,
            "review_count": int(self.review_count),
            "correct_count": int(self.correct_count),
            "created_at": created_at_str,
            "updated_at": updated_at_str,
        }


class QuizSession(Base):
    """Interactive Quiz Session with question bank, user responses, and scores."""

    __tablename__ = "quiz_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    deck_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Practice Quiz")
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")

    # Questions structure: list of {question, options, correct_index, explanation}
    questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    # User answers: dict mapping question index (str) to selected option index (int)
    user_answers: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )

    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_quiz_sessions_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize quiz session to dictionary with percentage and timestamps."""
        created_at_str = (
            self.created_at.isoformat()
            if hasattr(self.created_at, "isoformat")
            else (str(self.created_at) if self.created_at else None)
        )
        completed_at_str = (
            self.completed_at.isoformat()
            if hasattr(self.completed_at, "isoformat") and self.completed_at
            else (str(self.completed_at) if self.completed_at else None)
        )

        score_pct = (
            round((self.score / self.total_questions) * 100, 1)
            if self.total_questions > 0
            else 0.0
        )

        return {
            "id": self.id,
            "user_id": self.user_id,
            "deck_id": self.deck_id,
            "title": self.title,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "questions": self.questions,
            "user_answers": self.user_answers,
            "score": int(self.score),
            "total_questions": int(self.total_questions),
            "score_percentage": score_pct,
            "passed": bool(self.passed),
            "completed_at": completed_at_str,
            "created_at": created_at_str,
        }
