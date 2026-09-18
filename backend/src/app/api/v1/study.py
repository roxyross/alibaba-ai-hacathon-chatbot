"""Study & Learning Studio API Router (Phase 16).

Provides multi-tenant endpoints for Study Decks, Flashcards, Leitner spaced
repetition reviews, AI flashcard & quiz generation, and practice quiz evaluation.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.study.repository import StudyRepository
from app.study.schemas import (
    CardCreate,
    CardListResponse,
    CardResponse,
    CardReviewRequest,
    CardUpdate,
    DeckCreate,
    DeckListResponse,
    DeckResponse,
    DeckUpdate,
    GenerateFlashcardsRequest,
    GenerateFlashcardsResponse,
    GenerateQuizRequest,
    GenerateQuizResponse,
    QuizListResponse,
    QuizSessionResponse,
    QuizSubmitRequest,
    StudyStatsResponse,
)
from app.study.service import StudyService

log = structlog.get_logger()

router = APIRouter(prefix="/study", tags=["Study Studio"])


# ---------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------

@router.get("/decks", response_model=DeckListResponse)
@router.get("", response_model=DeckListResponse)
@router.get("/", response_model=DeckListResponse)
async def list_decks(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> DeckListResponse:
    """List authenticated user's study decks with optional search and subject filters."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    decks = await repo.list_decks(user_id=user_id, query=q, subject=subject, limit=limit, offset=offset)
    return DeckListResponse(
        decks=[DeckResponse(**d) for d in decks],
        total=len(decks),
    )


@router.post("/decks", response_model=DeckResponse, status_code=status.HTTP_201_CREATED)
async def create_deck(
    payload: DeckCreate,
    current_user: User = Depends(get_current_user),
) -> DeckResponse:
    """Create a new study deck for the authenticated user."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    deck = await repo.create_deck(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        subject=payload.subject,
        tags=payload.tags,
    )
    return DeckResponse(**deck)


@router.get("/decks/{deck_id}", response_model=DeckResponse)
async def get_deck(
    deck_id: str,
    current_user: User = Depends(get_current_user),
) -> DeckResponse:
    """Retrieve single study deck by ID. Enforces strict multi-tenant 404 on unowned."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    deck = await repo.get_deck(user_id, deck_id)
    if not deck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study deck {deck_id} not found",
        )
    return DeckResponse(**deck)


@router.patch("/decks/{deck_id}", response_model=DeckResponse)
async def update_deck(
    deck_id: str,
    payload: DeckUpdate,
    current_user: User = Depends(get_current_user),
) -> DeckResponse:
    """Update study deck metadata. Enforces strict multi-tenant 404 on unowned."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    deck = await repo.update_deck(
        user_id=user_id,
        deck_id=deck_id,
        title=payload.title,
        description=payload.description,
        subject=payload.subject,
        tags=payload.tags,
    )
    if not deck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study deck {deck_id} not found",
        )
    return DeckResponse(**deck)


@router.delete("/decks/{deck_id}", status_code=status.HTTP_200_OK)
async def delete_deck(
    deck_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete study deck and all child flashcards. Enforces strict multi-tenant 404."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    deleted = await repo.delete_deck(user_id, deck_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study deck {deck_id} not found",
        )
    return {"status": "success", "deleted": True, "deck_id": deck_id}


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------

@router.get("/decks/{deck_id}/cards", response_model=CardListResponse)
async def list_deck_cards(
    deck_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
) -> CardListResponse:
    """List flashcards belonging to a study deck. Enforces 404 if deck is not owned."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    deck = await repo.get_deck(user_id, deck_id)
    if not deck:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study deck {deck_id} not found",
        )
    cards = await repo.list_cards_for_deck(user_id, deck_id, limit=limit)
    return CardListResponse(
        cards=[CardResponse(**c) for c in cards],
        total=len(cards),
    )


@router.post("/decks/{deck_id}/cards", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def add_card_to_deck(
    deck_id: str,
    payload: CardCreate,
    current_user: User = Depends(get_current_user),
) -> CardResponse:
    """Add a flashcard to a study deck."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    card = await repo.create_card(
        user_id=user_id,
        deck_id=deck_id,
        front=payload.front,
        back=payload.back,
        explanation=payload.explanation,
        level=payload.level,
    )
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study deck {deck_id} not found",
        )
    return CardResponse(**card)


@router.get("/cards/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: str,
    current_user: User = Depends(get_current_user),
) -> CardResponse:
    """Get single flashcard. Enforces strict multi-tenant 404 on unowned."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    card = await repo.get_card(user_id, card_id)
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flashcard {card_id} not found",
        )
    return CardResponse(**card)


@router.patch("/cards/{card_id}", response_model=CardResponse)
async def update_card(
    card_id: str,
    payload: CardUpdate,
    current_user: User = Depends(get_current_user),
) -> CardResponse:
    """Update flashcard content or Leitner box. Enforces strict multi-tenant 404."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    card = await repo.update_card(
        user_id=user_id,
        card_id=card_id,
        front=payload.front,
        back=payload.back,
        explanation=payload.explanation,
        level=payload.level,
        box=payload.box,
    )
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flashcard {card_id} not found",
        )
    return CardResponse(**card)


@router.delete("/cards/{card_id}", status_code=status.HTTP_200_OK)
async def delete_card(
    card_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete flashcard. Enforces strict multi-tenant 404."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    deleted = await repo.delete_card(user_id, card_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flashcard {card_id} not found",
        )
    return {"status": "success", "deleted": True, "card_id": card_id}


@router.post("/cards/{card_id}/review", response_model=CardResponse)
async def review_card(
    card_id: str,
    payload: CardReviewRequest,
    current_user: User = Depends(get_current_user),
) -> CardResponse:
    """Submit a Leitner spaced repetition review for a card.

    Correct: Advances card to next box (up to 5), increasing review interval.
    Incorrect: Resets card to Box 1 for immediate review.
    """
    user_id = str(current_user.id)
    repo = StudyRepository()
    card = await repo.record_card_review(user_id, card_id, payload.is_correct)
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flashcard {card_id} not found",
        )
    return CardResponse(**card)


# ---------------------------------------------------------------------------
# AI Generator: Flashcards & Quizzes
# ---------------------------------------------------------------------------

@router.post("/generate/flashcards", response_model=GenerateFlashcardsResponse)
async def generate_flashcards(
    payload: GenerateFlashcardsRequest,
    current_user: User = Depends(get_current_user),
) -> GenerateFlashcardsResponse:
    """Generate structured flashcards from topic or notes using the Study Agent."""
    user_id = str(current_user.id)
    service = StudyService()
    return await service.generate_flashcards(user_id, payload)


@router.post("/generate/quiz", response_model=GenerateQuizResponse)
async def generate_quiz(
    payload: GenerateQuizRequest,
    current_user: User = Depends(get_current_user),
) -> GenerateQuizResponse:
    """Generate multiple-choice practice quiz questions with explanations."""
    user_id = str(current_user.id)
    service = StudyService()
    return await service.generate_quiz(user_id, payload)


# ---------------------------------------------------------------------------
# Quizzes & Scoring
# ---------------------------------------------------------------------------

@router.post("/quizzes", response_model=QuizSessionResponse, status_code=status.HTTP_201_CREATED)
async def submit_quiz(
    payload: QuizSubmitRequest,
    current_user: User = Depends(get_current_user),
) -> QuizSessionResponse:
    """Submit a completed practice quiz, calculate score, and record history."""
    user_id = str(current_user.id)
    service = StudyService()
    return await service.submit_quiz(user_id, payload)


@router.get("/quizzes", response_model=QuizListResponse)
async def list_quizzes(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
) -> QuizListResponse:
    """List authenticated user's past quiz sessions."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    quizzes = await repo.list_quiz_sessions(user_id, limit=limit, offset=offset)
    return QuizListResponse(
        quizzes=[QuizSessionResponse(**q) for q in quizzes],
        total=len(quizzes),
    )


@router.get("/quizzes/{quiz_id}", response_model=QuizSessionResponse)
async def get_quiz(
    quiz_id: str,
    current_user: User = Depends(get_current_user),
) -> QuizSessionResponse:
    """Retrieve specific quiz session by ID. Enforces strict multi-tenant 404."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    quiz = await repo.get_quiz_session(user_id, quiz_id)
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quiz session {quiz_id} not found",
        )
    return QuizSessionResponse(**quiz)


# ---------------------------------------------------------------------------
# Overview Stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=StudyStatsResponse)
async def get_study_stats(
    current_user: User = Depends(get_current_user),
) -> StudyStatsResponse:
    """Retrieve overview metrics on user's decks, cards due, and mastery."""
    user_id = str(current_user.id)
    repo = StudyRepository()
    stats = await repo.get_study_stats(user_id)
    return StudyStatsResponse(**stats)
