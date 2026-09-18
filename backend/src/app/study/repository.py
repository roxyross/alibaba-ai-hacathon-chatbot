"""Dual-persistence repository for Study Decks, Flashcards, and Quizzes (Phase 16).

Supports async SQLAlchemy ORM queries with thread-safe in-memory fallback for
deterministic test isolation and offline resilience. Strict multi-tenant boundaries
are enforced across all operations.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_engine
from app.models.study_deck import QuizSession, StudyCard, StudyDeck

log = structlog.get_logger()

# Thread-safe in-memory fallback stores
_MEM_DECKS: dict[str, dict[str, Any]] = {}
_MEM_CARDS: dict[str, dict[str, Any]] = {}
_MEM_QUIZZES: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

# Leitner 5-box intervals (in days)
LEITNER_INTERVALS = {
    1: 1,    # Box 1: 1 day
    2: 3,    # Box 2: 3 days
    3: 7,    # Box 3: 7 days
    4: 14,   # Box 4: 14 days
    5: 30,   # Box 5: 30 days
}


def clear_in_memory_stores() -> None:
    """Deterministic reset for test suites."""
    with _LOCK:
        _MEM_DECKS.clear()
        _MEM_CARDS.clear()
        _MEM_QUIZZES.clear()


class StudyRepository:
    """Multi-tenant repository for Study Decks, Cards, and Quizzes."""

    # ---------------------------------------------------------------------------
    # Study Decks
    # ---------------------------------------------------------------------------

    async def create_deck(
        self,
        user_id: str,
        title: str,
        description: str | None = None,
        subject: str = "General",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create and persist a new study deck."""
        deck_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        tag_str = ",".join(tags) if tags else ""

        deck_dict: dict[str, Any] = {
            "id": deck_id,
            "user_id": user_id,
            "title": title,
            "description": description,
            "subject": subject,
            "tags": tags or [],
            "card_count": 0,
            "mastery_percentage": 0.0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                deck = StudyDeck(
                    id=deck_id,
                    user_id=user_id,
                    title=title,
                    description=description,
                    subject=subject,
                    tags=tag_str,
                    card_count=0,
                    mastery_percentage=0.0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(deck)
                await session.commit()
                await session.refresh(deck)
                deck_dict = deck.to_dict()
        except Exception as exc:
            log.warning("study_repo.create_deck.db_fallback", error=str(exc))

        with _LOCK:
            _MEM_DECKS[deck_id] = dict(deck_dict)

        return deck_dict

    async def get_deck(self, user_id: str, deck_id: str) -> dict[str, Any] | None:
        """Retrieve deck by ID ensuring strict multi-tenant ownership."""
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = select(StudyDeck).where(
                    StudyDeck.id == deck_id, StudyDeck.user_id == user_id
                )
                res = await session.execute(stmt)
                deck = res.scalar_one_or_none()
                if deck:
                    return deck.to_dict()
        except Exception as exc:
            log.debug("study_repo.get_deck.db_fallback", error=str(exc))

        with _LOCK:
            mem_deck = _MEM_DECKS.get(deck_id)
            if mem_deck and mem_deck["user_id"] == user_id:
                return dict(mem_deck)
        return None

    async def list_decks(
        self,
        user_id: str,
        query: str | None = None,
        subject: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List user's study decks with optional keyword search and subject filter."""
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = select(StudyDeck).where(StudyDeck.user_id == user_id)
                if subject and subject.lower() != "all":
                    stmt = stmt.where(StudyDeck.subject.ilike(f"%{subject}%"))
                if query:
                    q_pat = f"%{query}%"
                    stmt = stmt.where(
                        StudyDeck.title.ilike(q_pat)
                        | StudyDeck.description.ilike(q_pat)
                        | StudyDeck.tags.ilike(q_pat)
                    )
                stmt = stmt.order_by(desc(StudyDeck.created_at)).offset(offset).limit(limit)
                res = await session.execute(stmt)
                decks = res.scalars().all()
                if decks:
                    return [d.to_dict() for d in decks]
        except Exception as exc:
            log.debug("study_repo.list_decks.db_fallback", error=str(exc))

        with _LOCK:
            results: list[dict[str, Any]] = []
            for d in _MEM_DECKS.values():
                if d["user_id"] != user_id:
                    continue
                if subject and subject.lower() != "all" and subject.lower() not in d.get("subject", "").lower():
                    continue
                if query:
                    q_lower = query.lower()
                    title_match = q_lower in d.get("title", "").lower()
                    desc_match = q_lower in (d.get("description") or "").lower()
                    tags_match = any(q_lower in str(t).lower() for t in d.get("tags", []))
                    if not (title_match or desc_match or tags_match):
                        continue
                results.append(dict(d))
            results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            return results[offset : offset + limit]

    async def update_deck(
        self,
        user_id: str,
        deck_id: str,
        title: str | None = None,
        description: str | None = None,
        subject: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Update deck metadata with ownership guard."""
        existing = await self.get_deck(user_id, deck_id)
        if not existing:
            return None

        now = datetime.now(UTC)
        tag_str = ",".join(tags) if tags is not None else None

        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                update_vals: dict[str, Any] = {"updated_at": now}
                if title is not None:
                    update_vals["title"] = title
                if description is not None:
                    update_vals["description"] = description
                if subject is not None:
                    update_vals["subject"] = subject
                if tag_str is not None:
                    update_vals["tags"] = tag_str

                stmt = (
                    update(StudyDeck)
                    .where(StudyDeck.id == deck_id, StudyDeck.user_id == user_id)
                    .values(**update_vals)
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            log.debug("study_repo.update_deck.db_fallback", error=str(exc))

        with _LOCK:
            if deck_id in _MEM_DECKS and _MEM_DECKS[deck_id]["user_id"] == user_id:
                deck = _MEM_DECKS[deck_id]
                if title is not None:
                    deck["title"] = title
                if description is not None:
                    deck["description"] = description
                if subject is not None:
                    deck["subject"] = subject
                if tags is not None:
                    deck["tags"] = tags
                deck["updated_at"] = now.isoformat()
                return dict(deck)
        return await self.get_deck(user_id, deck_id)

    async def delete_deck(self, user_id: str, deck_id: str) -> bool:
        """Delete deck and cascade delete child flashcards."""
        existing = await self.get_deck(user_id, deck_id)
        if not existing:
            return False

        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                await session.execute(
                    delete(StudyCard).where(StudyCard.deck_id == deck_id, StudyCard.user_id == user_id)
                )
                stmt = delete(StudyDeck).where(
                    StudyDeck.id == deck_id, StudyDeck.user_id == user_id
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            log.debug("study_repo.delete_deck.db_fallback", error=str(exc))

        with _LOCK:
            _MEM_DECKS.pop(deck_id, None)
            # Cascade in-memory cards
            cards_to_remove = [
                c_id for c_id, c in _MEM_CARDS.items() if c.get("deck_id") == deck_id
            ]
            for c_id in cards_to_remove:
                _MEM_CARDS.pop(c_id, None)

        return True

    # ---------------------------------------------------------------------------
    # Flashcards
    # ---------------------------------------------------------------------------

    async def create_card(
        self,
        user_id: str,
        deck_id: str,
        front: str,
        back: str,
        explanation: str | None = None,
        level: str = "intermediate",
    ) -> dict[str, Any] | None:
        """Add a flashcard to a deck, enforcing deck ownership."""
        deck = await self.get_deck(user_id, deck_id)
        if not deck:
            return None

        card_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        next_review = now + timedelta(days=LEITNER_INTERVALS[1])

        card_dict: dict[str, Any] = {
            "id": card_id,
            "deck_id": deck_id,
            "user_id": user_id,
            "front": front,
            "back": back,
            "explanation": explanation,
            "level": level,
            "box": 1,
            "next_review_at": next_review.isoformat(),
            "last_reviewed_at": None,
            "review_count": 0,
            "correct_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                card = StudyCard(
                    id=card_id,
                    deck_id=deck_id,
                    user_id=user_id,
                    front=front,
                    back=back,
                    explanation=explanation,
                    level=level,
                    box=1,
                    next_review_at=next_review,
                    last_reviewed_at=None,
                    review_count=0,
                    correct_count=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(card)
                # Increment deck card_count
                await session.execute(
                    update(StudyDeck)
                    .where(StudyDeck.id == deck_id)
                    .values(card_count=StudyDeck.card_count + 1)
                )
                await session.commit()
                await session.refresh(card)
                card_dict = card.to_dict()
        except Exception as exc:
            log.warning("study_repo.create_card.db_fallback", error=str(exc))

        with _LOCK:
            _MEM_CARDS[card_id] = dict(card_dict)
            if deck_id in _MEM_DECKS:
                _MEM_DECKS[deck_id]["card_count"] = _MEM_DECKS[deck_id].get("card_count", 0) + 1

        await self._recompute_deck_mastery(user_id, deck_id)
        return card_dict

    async def get_card(self, user_id: str, card_id: str) -> dict[str, Any] | None:
        """Retrieve flashcard by ID ensuring user ownership."""
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = select(StudyCard).where(
                    StudyCard.id == card_id, StudyCard.user_id == user_id
                )
                res = await session.execute(stmt)
                card = res.scalar_one_or_none()
                if card:
                    return card.to_dict()
        except Exception as exc:
            log.debug("study_repo.get_card.db_fallback", error=str(exc))

        with _LOCK:
            mem_card = _MEM_CARDS.get(card_id)
            if mem_card and mem_card["user_id"] == user_id:
                return dict(mem_card)
        return None

    async def list_cards_for_deck(
        self, user_id: str, deck_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List flashcards belonging to a deck."""
        deck = await self.get_deck(user_id, deck_id)
        if not deck:
            return []

        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = (
                    select(StudyCard)
                    .where(StudyCard.deck_id == deck_id, StudyCard.user_id == user_id)
                    .order_by(StudyCard.box.asc(), StudyCard.created_at.asc())
                    .limit(limit)
                )
                res = await session.execute(stmt)
                cards = res.scalars().all()
                if cards:
                    return [c.to_dict() for c in cards]
        except Exception as exc:
            log.debug("study_repo.list_cards.db_fallback", error=str(exc))

        with _LOCK:
            mem_cards = [
                dict(c)
                for c in _MEM_CARDS.values()
                if c["deck_id"] == deck_id and c["user_id"] == user_id
            ]
            mem_cards.sort(key=lambda x: (x.get("box", 1), x.get("created_at") or ""))
            return mem_cards[:limit]

    async def update_card(
        self,
        user_id: str,
        card_id: str,
        front: str | None = None,
        back: str | None = None,
        explanation: str | None = None,
        level: str | None = None,
        box: int | None = None,
    ) -> dict[str, Any] | None:
        """Update flashcard content or Leitner box."""
        existing = await self.get_card(user_id, card_id)
        if not existing:
            return None

        now = datetime.now(UTC)
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                vals: dict[str, Any] = {"updated_at": now}
                if front is not None:
                    vals["front"] = front
                if back is not None:
                    vals["back"] = back
                if explanation is not None:
                    vals["explanation"] = explanation
                if level is not None:
                    vals["level"] = level
                if box is not None:
                    vals["box"] = max(1, min(5, box))

                stmt = (
                    update(StudyCard)
                    .where(StudyCard.id == card_id, StudyCard.user_id == user_id)
                    .values(**vals)
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            log.debug("study_repo.update_card.db_fallback", error=str(exc))

        with _LOCK:
            if card_id in _MEM_CARDS and _MEM_CARDS[card_id]["user_id"] == user_id:
                card = _MEM_CARDS[card_id]
                if front is not None:
                    card["front"] = front
                if back is not None:
                    card["back"] = back
                if explanation is not None:
                    card["explanation"] = explanation
                if level is not None:
                    card["level"] = level
                if box is not None:
                    card["box"] = max(1, min(5, box))
                card["updated_at"] = now.isoformat()

        await self._recompute_deck_mastery(user_id, existing["deck_id"])
        return await self.get_card(user_id, card_id)

    async def delete_card(self, user_id: str, card_id: str) -> bool:
        """Delete a flashcard with multi-tenant check."""
        existing = await self.get_card(user_id, card_id)
        if not existing:
            return False

        deck_id = existing["deck_id"]
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = delete(StudyCard).where(
                    StudyCard.id == card_id, StudyCard.user_id == user_id
                )
                await session.execute(stmt)
                await session.execute(
                    update(StudyDeck)
                    .where(StudyDeck.id == deck_id, StudyDeck.card_count > 0)
                    .values(card_count=StudyDeck.card_count - 1)
                )
                await session.commit()
        except Exception as exc:
            log.debug("study_repo.delete_card.db_fallback", error=str(exc))

        with _LOCK:
            _MEM_CARDS.pop(card_id, None)
            if deck_id in _MEM_DECKS:
                cnt = _MEM_DECKS[deck_id].get("card_count", 1)
                _MEM_DECKS[deck_id]["card_count"] = max(0, cnt - 1)

        await self._recompute_deck_mastery(user_id, deck_id)
        return True

    async def record_card_review(
        self, user_id: str, card_id: str, is_correct: bool
    ) -> dict[str, Any] | None:
        """Process spaced repetition review using the Leitner 5-box system.

        If correct:
            Advance to next box (max 5)
            Schedule next review in LEITNER_INTERVALS[new_box] days
        If incorrect:
            Reset to Box 1
            Schedule next review in LEITNER_INTERVALS[1] day
        """
        existing = await self.get_card(user_id, card_id)
        if not existing:
            return None

        current_box = existing.get("box", 1)
        new_box = min(5, current_box + 1) if is_correct else 1
        interval_days = LEITNER_INTERVALS.get(new_box, 1)

        now = datetime.now(UTC)
        next_review = now + timedelta(days=interval_days)

        rev_count = existing.get("review_count", 0) + 1
        corr_count = existing.get("correct_count", 0) + (1 if is_correct else 0)

        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = (
                    update(StudyCard)
                    .where(StudyCard.id == card_id, StudyCard.user_id == user_id)
                    .values(
                        box=new_box,
                        next_review_at=next_review,
                        last_reviewed_at=now,
                        review_count=rev_count,
                        correct_count=corr_count,
                        updated_at=now,
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            log.debug("study_repo.review_card.db_fallback", error=str(exc))

        with _LOCK:
            if card_id in _MEM_CARDS and _MEM_CARDS[card_id]["user_id"] == user_id:
                c = _MEM_CARDS[card_id]
                c["box"] = new_box
                c["next_review_at"] = next_review.isoformat()
                c["last_reviewed_at"] = now.isoformat()
                c["review_count"] = rev_count
                c["correct_count"] = corr_count
                c["updated_at"] = now.isoformat()

        await self._recompute_deck_mastery(user_id, existing["deck_id"])
        return await self.get_card(user_id, card_id)

    async def _recompute_deck_mastery(self, user_id: str, deck_id: str) -> None:
        """Recompute deck mastery percentage based on Leitner card boxes.

        Box 1: 0%, Box 2: 25%, Box 3: 50%, Box 4: 75%, Box 5: 100%.
        Mastery = (Sum of card weights) / (total_cards * 1.0) * 100
        """
        cards = await self.list_cards_for_deck(user_id, deck_id, limit=500)
        if not cards:
            mastery = 0.0
        else:
            box_weights = {1: 0.0, 2: 0.25, 3: 0.50, 4: 0.75, 5: 1.0}
            total_weight = sum(box_weights.get(c.get("box", 1), 0.0) for c in cards)
            mastery = round((total_weight / len(cards)) * 100, 1)

        now = datetime.now(UTC)
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                await session.execute(
                    update(StudyDeck)
                    .where(StudyDeck.id == deck_id, StudyDeck.user_id == user_id)
                    .values(
                        card_count=len(cards),
                        mastery_percentage=mastery,
                        updated_at=now,
                    )
                )
                await session.commit()
        except Exception:
            pass

        with _LOCK:
            if deck_id in _MEM_DECKS:
                _MEM_DECKS[deck_id]["card_count"] = len(cards)
                _MEM_DECKS[deck_id]["mastery_percentage"] = mastery
                _MEM_DECKS[deck_id]["updated_at"] = now.isoformat()

    # ---------------------------------------------------------------------------
    # Quiz Sessions
    # ---------------------------------------------------------------------------

    async def create_quiz_session(
        self,
        user_id: str,
        topic: str,
        questions: list[dict[str, Any]],
        user_answers: dict[str, Any],
        score: int,
        total_questions: int,
        title: str = "Practice Quiz",
        difficulty: str = "medium",
        deck_id: str | None = None,
    ) -> dict[str, Any]:
        """Save a completed quiz session."""
        quiz_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        passed = (score / total_questions >= 0.7) if total_questions > 0 else False
        score_pct = round((score / total_questions) * 100, 1) if total_questions > 0 else 0.0

        quiz_dict: dict[str, Any] = {
            "id": quiz_id,
            "user_id": user_id,
            "deck_id": deck_id,
            "title": title,
            "topic": topic,
            "difficulty": difficulty,
            "questions": questions,
            "user_answers": user_answers,
            "score": score,
            "total_questions": total_questions,
            "score_percentage": score_pct,
            "passed": passed,
            "completed_at": now.isoformat(),
            "created_at": now.isoformat(),
        }

        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                quiz = QuizSession(
                    id=quiz_id,
                    user_id=user_id,
                    deck_id=deck_id,
                    title=title,
                    topic=topic,
                    difficulty=difficulty,
                    questions=questions,
                    user_answers=user_answers,
                    score=score,
                    total_questions=total_questions,
                    passed=passed,
                    completed_at=now,
                    created_at=now,
                )
                session.add(quiz)
                await session.commit()
                await session.refresh(quiz)
                quiz_dict = quiz.to_dict()
        except Exception as exc:
            log.warning("study_repo.create_quiz.db_fallback", error=str(exc))

        with _LOCK:
            _MEM_QUIZZES[quiz_id] = dict(quiz_dict)

        return quiz_dict

    async def get_quiz_session(self, user_id: str, quiz_id: str) -> dict[str, Any] | None:
        """Retrieve a specific quiz session with tenant check."""
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = select(QuizSession).where(
                    QuizSession.id == quiz_id, QuizSession.user_id == user_id
                )
                res = await session.execute(stmt)
                quiz = res.scalar_one_or_none()
                if quiz:
                    return quiz.to_dict()
        except Exception as exc:
            log.debug("study_repo.get_quiz.db_fallback", error=str(exc))

        with _LOCK:
            q = _MEM_QUIZZES.get(quiz_id)
            if q and q["user_id"] == user_id:
                return dict(q)
        return None

    async def list_quiz_sessions(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List past quiz sessions for the user."""
        try:
            engine = get_engine()
            async with AsyncSession(engine) as session:
                stmt = (
                    select(QuizSession)
                    .where(QuizSession.user_id == user_id)
                    .order_by(desc(QuizSession.created_at))
                    .offset(offset)
                    .limit(limit)
                )
                res = await session.execute(stmt)
                quizzes = res.scalars().all()
                if quizzes:
                    return [q.to_dict() for q in quizzes]
        except Exception as exc:
            log.debug("study_repo.list_quizzes.db_fallback", error=str(exc))

        with _LOCK:
            mem_quizzes = [
                dict(q) for q in _MEM_QUIZZES.values() if q["user_id"] == user_id
            ]
            mem_quizzes.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            return mem_quizzes[offset : offset + limit]

    # ---------------------------------------------------------------------------
    # Study Overview Stats
    # ---------------------------------------------------------------------------

    async def get_study_stats(self, user_id: str) -> dict[str, Any]:
        """Compute holistic study stats for the user dashboard."""
        decks = await self.list_decks(user_id, limit=200)
        total_decks = len(decks)
        total_cards = sum(d.get("card_count", 0) for d in decks)

        avg_mastery = (
            round(sum(d.get("mastery_percentage", 0.0) for d in decks) / total_decks, 1)
            if total_decks > 0
            else 0.0
        )

        quizzes = await self.list_quiz_sessions(user_id, limit=100)
        completed_quizzes = len(quizzes)
        avg_quiz_score = (
            round(sum(q.get("score_percentage", 0.0) for q in quizzes) / completed_quizzes, 1)
            if completed_quizzes > 0
            else 0.0
        )

        # Count cards due for review (next_review_at <= now)
        now_str = datetime.now(UTC).isoformat()
        cards_due = 0
        with _LOCK:
            for c in _MEM_CARDS.values():
                if c["user_id"] == user_id:
                    nxt = c.get("next_review_at")
                    if nxt and nxt <= now_str:
                        cards_due += 1

        return {
            "total_decks": total_decks,
            "total_cards": total_cards,
            "cards_due_for_review": cards_due,
            "average_mastery": avg_mastery,
            "completed_quizzes": completed_quizzes,
            "average_quiz_score": avg_quiz_score,
        }
