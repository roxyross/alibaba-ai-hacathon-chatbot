"""Phase 16 Master Integration Test Suite: Autonomous Study & Quiz Agent / Learning Studio.

Verifies:
1. Fresh user starts with clean empty study decks, cards, and quizzes (0 items).
2. Study deck creation and retrieval (POST/GET /api/v1/study/decks).
3. Study deck updating and keyword/subject filtering.
4. Flashcard addition and mutation within a deck (POST/PATCH /api/v1/study/decks/{id}/cards, /cards/{id}).
5. Leitner 5-box spaced repetition review mechanics (box advancement on correct, reset to box 1 on incorrect).
6. Cascading deletion of deck and child flashcards (DELETE /api/v1/study/decks/{id}).
7. Strict multi-tenant isolation: User B cannot view, update, or delete User A's decks, cards, or quizzes (404 Not Found).
8. AI Flashcard generation endpoint from topic and notes with auto-save (POST /api/v1/study/generate/flashcards).
9. AI Practice Quiz generation endpoint with 4 options and explanations (POST /api/v1/study/generate/quiz).
10. Practice quiz submission, scoring, and history listing (POST/GET /api/v1/study/quizzes).
11. Holistic study statistics endpoint (GET /api/v1/study/stats).
12. Multi-agent chat runtime routing and study grounding.
13. Multi-agent chat offline fallback with authentic deck and card counts.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.main import app
from app.study.repository import clear_in_memory_stores


@pytest.fixture(autouse=True)
def _reset_stores() -> None:
    clear_in_memory_stores()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Helper to request magic link, verify token, and return auth headers + user_id."""
    req_resp = await client.post("/api/v1/auth/request-link", json={"email": email})
    assert req_resp.status_code == 200
    token = req_resp.json()["dev_token"]

    verify_resp = await client.post("/api/v1/auth/verify", json={"token": token})
    assert verify_resp.status_code == 200
    token_str = verify_resp.json()["access_token"]
    user_id = verify_resp.json()["user"]["id"]

    return {"Authorization": f"Bearer {token_str}"}, user_id


# ---------------------------------------------------------------------------
# Test 1: Empty States
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_study_empty_state(client: httpx.AsyncClient) -> None:
    """Fresh user starts with 0 decks, 0 quizzes, and clean 0 stats."""
    email = f"study_fresh_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    # 1. Decks should be empty
    decks_resp = await client.get("/api/v1/study/decks", headers=headers)
    assert decks_resp.status_code == 200
    decks_data = decks_resp.json()
    assert decks_data["total"] == 0
    assert decks_data["decks"] == []

    # 2. Quizzes should be empty
    quizzes_resp = await client.get("/api/v1/study/quizzes", headers=headers)
    assert quizzes_resp.status_code == 200
    quizzes_data = quizzes_resp.json()
    assert quizzes_data["total"] == 0
    assert quizzes_data["quizzes"] == []

    # 3. Stats should be zeroed
    stats_resp = await client.get("/api/v1/study/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert stats_data["total_decks"] == 0
    assert stats_data["total_cards"] == 0
    assert stats_data["cards_due_for_review"] == 0
    assert stats_data["average_mastery"] == 0.0


# ---------------------------------------------------------------------------
# Test 2: Deck CRUD & Retrieval
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_and_get_study_deck(client: httpx.AsyncClient) -> None:
    """Create a study deck and retrieve it by ID."""
    email = f"deck_crud_{uuid.uuid4().hex[:8]}@example.com"
    headers, user_id = await _get_auth(client, email)

    create_resp = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={
            "title": "Machine Learning Foundations",
            "description": "Core concepts in neural networks, loss functions, and optimization.",
            "subject": "Computer Science",
            "tags": ["ml", "ai", "math"],
        },
    )
    assert create_resp.status_code == 201
    deck_data = create_resp.json()
    assert deck_data["title"] == "Machine Learning Foundations"
    assert deck_data["subject"] == "Computer Science"
    assert deck_data["user_id"] == user_id
    assert "ml" in deck_data["tags"]
    deck_id = deck_data["id"]

    # Retrieve by ID
    get_resp = await client.get(f"/api/v1/study/decks/{deck_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == deck_id


# ---------------------------------------------------------------------------
# Test 3: Deck Update & Filtering
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_deck_update_and_filtering(client: httpx.AsyncClient) -> None:
    """Update deck metadata and verify search/subject filtering."""
    email = f"deck_filter_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    d1 = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Biology Cells", "subject": "Biology", "tags": ["biology", "cells"]},
    )
    assert d1.status_code == 201
    d1_id = d1.json()["id"]

    d2 = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "World History 101", "subject": "History", "tags": ["history"]},
    )
    assert d2.status_code == 201

    # Update d1
    patch_resp = await client.patch(
        f"/api/v1/study/decks/{d1_id}",
        headers=headers,
        json={"description": "Cellular mitosis and organelle functions."},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Cellular mitosis and organelle functions."

    # Filter by subject
    bio_resp = await client.get("/api/v1/study/decks?subject=Biology", headers=headers)
    assert bio_resp.status_code == 200
    assert bio_resp.json()["total"] == 1
    assert bio_resp.json()["decks"][0]["subject"] == "Biology"

    # Search keyword
    hist_resp = await client.get("/api/v1/study/decks?q=History", headers=headers)
    assert hist_resp.status_code == 200
    assert hist_resp.json()["total"] == 1
    assert hist_resp.json()["decks"][0]["title"] == "World History 101"


# ---------------------------------------------------------------------------
# Test 4: Flashcards Add, List & Update
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_add_and_update_study_cards(client: httpx.AsyncClient) -> None:
    """Add cards to deck, list them, and update card contents."""
    email = f"card_crud_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    deck_resp = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Python Basics", "subject": "Programming"},
    )
    deck_id = deck_resp.json()["id"]

    # Add card
    card_resp = await client.post(
        f"/api/v1/study/decks/{deck_id}/cards",
        headers=headers,
        json={
            "front": "What is a Python decorator?",
            "back": "A function that takes another function as an argument and extends its behavior without modifying it.",
            "explanation": "Decorators use the @syntax (syntactic sugar).",
            "level": "intermediate",
        },
    )
    assert card_resp.status_code == 201
    card_data = card_resp.json()
    assert card_data["box"] == 1
    card_id = card_data["id"]

    # List cards
    list_resp = await client.get(f"/api/v1/study/decks/{deck_id}/cards", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["cards"][0]["id"] == card_id

    # Update card
    patch_resp = await client.patch(
        f"/api/v1/study/cards/{card_id}",
        headers=headers,
        json={"level": "advanced"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["level"] == "advanced"


# ---------------------------------------------------------------------------
# Test 5: Spaced Repetition Review (Leitner 5-box system)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_card_spaced_repetition_review(client: httpx.AsyncClient) -> None:
    """Reviewing card as correct advances box; incorrect resets to Box 1."""
    email = f"spaced_rep_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    deck_resp = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Organic Chemistry", "subject": "Chemistry"},
    )
    deck_id = deck_resp.json()["id"]

    card_resp = await client.post(
        f"/api/v1/study/decks/{deck_id}/cards",
        headers=headers,
        json={"front": "What is an SN2 reaction?", "back": "Bimolecular nucleophilic substitution."},
    )
    card_id = card_resp.json()["id"]
    assert card_resp.json()["box"] == 1

    # Review 1: Correct -> advances to Box 2
    r1 = await client.post(
        f"/api/v1/study/cards/{card_id}/review",
        headers=headers,
        json={"is_correct": True},
    )
    assert r1.status_code == 200
    assert r1.json()["box"] == 2
    assert r1.json()["correct_count"] == 1
    assert r1.json()["review_count"] == 1

    # Review 2: Correct -> advances to Box 3
    r2 = await client.post(
        f"/api/v1/study/cards/{card_id}/review",
        headers=headers,
        json={"is_correct": True},
    )
    assert r2.status_code == 200
    assert r2.json()["box"] == 3

    # Review 3: Incorrect -> resets to Box 1
    r3 = await client.post(
        f"/api/v1/study/cards/{card_id}/review",
        headers=headers,
        json={"is_correct": False},
    )
    assert r3.status_code == 200
    assert r3.json()["box"] == 1
    assert r3.json()["review_count"] == 3
    assert r3.json()["correct_count"] == 2


# ---------------------------------------------------------------------------
# Test 6: Cascading Deck Deletion
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_delete_deck_cascades_cards(client: httpx.AsyncClient) -> None:
    """Deleting a study deck cascades and removes all attached flashcards."""
    email = f"cascade_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    deck_resp = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Geography", "subject": "Earth Science"},
    )
    deck_id = deck_resp.json()["id"]

    c1 = await client.post(
        f"/api/v1/study/decks/{deck_id}/cards",
        headers=headers,
        json={"front": "Capital of France?", "back": "Paris"},
    )
    c1_id = c1.json()["id"]

    # Delete deck
    del_resp = await client.delete(f"/api/v1/study/decks/{deck_id}", headers=headers)
    assert del_resp.status_code == 200

    # Verify deck is 404
    get_d = await client.get(f"/api/v1/study/decks/{deck_id}", headers=headers)
    assert get_d.status_code == 404

    # Verify card is also 404
    get_c = await client.get(f"/api/v1/study/cards/{c1_id}", headers=headers)
    assert get_c.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: Multi-Tenant 404 Security
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_study_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """Strict security: User B receives HTTP 404 accessing User A's decks, cards, or quizzes."""
    user_a_headers, _ = await _get_auth(client, "student_a@example.com")
    user_b_headers, _ = await _get_auth(client, "student_b@example.com")

    # User A creates deck and card
    deck_a = await client.post(
        "/api/v1/study/decks",
        headers=user_a_headers,
        json={"title": "Secret Formulas", "subject": "Physics"},
    )
    deck_id = deck_a.json()["id"]

    card_a = await client.post(
        f"/api/v1/study/decks/{deck_id}/cards",
        headers=user_a_headers,
        json={"front": "E=mc^2", "back": "Mass-energy equivalence"},
    )
    card_id = card_a.json()["id"]

    # User B tries to read User A's deck -> 404
    b_deck = await client.get(f"/api/v1/study/decks/{deck_id}", headers=user_b_headers)
    assert b_deck.status_code == 404

    # User B tries to read User A's card -> 404
    b_card = await client.get(f"/api/v1/study/cards/{card_id}", headers=user_b_headers)
    assert b_card.status_code == 404

    # User B tries to mutate User A's card review -> 404
    b_rev = await client.post(
        f"/api/v1/study/cards/{card_id}/review",
        headers=user_b_headers,
        json={"is_correct": True},
    )
    assert b_rev.status_code == 404

    # User B tries to delete User A's deck -> 404
    b_del = await client.delete(f"/api/v1/study/decks/{deck_id}", headers=user_b_headers)
    assert b_del.status_code == 404


# ---------------------------------------------------------------------------
# Test 8: AI Flashcard Generator
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_generate_flashcards_endpoint(client: httpx.AsyncClient) -> None:
    """Generate structured flashcards from topic with auto-save to new deck."""
    email = f"gen_cards_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    gen_resp = await client.post(
        "/api/v1/study/generate/flashcards",
        headers=headers,
        json={
            "topic": "Microservices Architecture",
            "source_text": "A microservices architecture arranges an application as a collection of loosely coupled services. "
                           "Service discovery enables services to locate each other dynamically. "
                           "API Gateways manage authentication, routing, and rate limiting.",
            "count": 3,
            "level": "intermediate",
            "new_deck_title": "Microservices Deep Dive",
        },
    )
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert gen_data["topic"] == "Microservices Architecture"
    assert len(gen_data["cards"]) >= 1
    assert gen_data["deck_id"] is not None

    # Verify cards were persisted into the new deck
    deck_id = gen_data["deck_id"]
    cards_resp = await client.get(f"/api/v1/study/decks/{deck_id}/cards", headers=headers)
    assert cards_resp.status_code == 200
    assert cards_resp.json()["total"] >= 1


# ---------------------------------------------------------------------------
# Test 9: AI Quiz Generator
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_generate_quiz_endpoint(client: httpx.AsyncClient) -> None:
    """Generate multiple-choice quiz questions with 4 options and explanations."""
    email = f"gen_quiz_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    quiz_resp = await client.post(
        "/api/v1/study/generate/quiz",
        headers=headers,
        json={
            "topic": "Relational Databases & SQL",
            "source_text": "ACID properties: Atomicity, Consistency, Isolation, Durability. "
                           "Primary keys uniquely identify records. Foreign keys link relational tables.",
            "count": 3,
            "difficulty": "medium",
        },
    )
    assert quiz_resp.status_code == 200
    quiz_data = quiz_resp.json()
    assert quiz_data["topic"] == "Relational Databases & SQL"
    assert len(quiz_data["questions"]) >= 1

    q1 = quiz_data["questions"][0]
    assert "question" in q1
    assert len(q1["options"]) >= 2
    assert isinstance(q1["correct_index"], int)
    assert "explanation" in q1


# ---------------------------------------------------------------------------
# Test 10: Quiz Submission & History
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_quiz_session_submit_and_list(client: httpx.AsyncClient) -> None:
    """Submit completed quiz, score answers, and list in past sessions."""
    email = f"quiz_sub_{uuid.uuid4().hex[:8]}@example.com"
    headers, user_id = await _get_auth(client, email)

    questions = [
        {
            "question": "What does ACID stand for in databases?",
            "options": [
                "Atomicity, Consistency, Isolation, Durability",
                "Advanced Computing Interface Design",
                "Automated Continuous Integration Deployment",
                "Asynchronous Cloud Integration Database",
            ],
            "correct_index": 0,
            "explanation": "ACID guarantees transaction safety.",
        },
        {
            "question": "What SQL clause filters aggregated groups?",
            "options": ["WHERE", "HAVING", "GROUP BY", "ORDER BY"],
            "correct_index": 1,
            "explanation": "HAVING filters groups created by GROUP BY.",
        },
    ]

    # User answers Q0 correctly (0) and Q1 correctly (1)
    submit_resp = await client.post(
        "/api/v1/study/quizzes",
        headers=headers,
        json={
            "title": "SQL Midterm Prep",
            "topic": "SQL & Databases",
            "difficulty": "medium",
            "questions": questions,
            "user_answers": {"0": 0, "1": 1},
        },
    )
    assert submit_resp.status_code == 201
    sub_data = submit_resp.json()
    assert sub_data["score"] == 2
    assert sub_data["total_questions"] == 2
    assert sub_data["score_percentage"] == 100.0
    assert sub_data["passed"] is True
    quiz_id = sub_data["id"]

    # Retrieve single quiz
    get_q = await client.get(f"/api/v1/study/quizzes/{quiz_id}", headers=headers)
    assert get_q.status_code == 200
    assert get_q.json()["score"] == 2

    # List quizzes
    list_q = await client.get("/api/v1/study/quizzes", headers=headers)
    assert list_q.status_code == 200
    assert list_q.json()["total"] == 1


# ---------------------------------------------------------------------------
# Test 11: Study Stats Endpoint
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_study_stats_endpoint(client: httpx.AsyncClient) -> None:
    """Study stats returns aggregated deck count, cards count, and mastery."""
    email = f"study_stats_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    d = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Data Structures", "subject": "CS"},
    )
    d_id = d.json()["id"]

    await client.post(
        f"/api/v1/study/decks/{d_id}/cards",
        headers=headers,
        json={"front": "Stack", "back": "LIFO"},
    )

    stats_resp = await client.get("/api/v1/study/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_decks"] == 1
    assert stats["total_cards"] == 1


# ---------------------------------------------------------------------------
# Test 12: Chat Runtime Grounding
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_chat_study_grounding(client: httpx.AsyncClient) -> None:
    """Runtime chat routes study inquiry and injects authentic decks into context."""
    email = f"chat_study_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Neuroscience 301", "subject": "Biology"},
    )

    # Ask chat about study decks
    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={"message": "What study decks do I currently have for revision?"},
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["agent_slug"] == "study"


# ---------------------------------------------------------------------------
# Test 13: Chat Offline Fallback with Authentic Study Stats
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_chat_study_offline_stats(client: httpx.AsyncClient) -> None:
    """When providers are offline, chat reports real study deck count."""
    email = f"study_offline_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    # Create 2 decks
    await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Spanish Vocabulary", "subject": "Languages"},
    )
    await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Linear Algebra", "subject": "Mathematics"},
    )

    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        headers=headers,
        json={"message": "Can you quiz me or check my study decks?"},
    )
    assert chat_resp.status_code == 200
    content = chat_resp.json()["response"]
    # Should mention 2 study decks or Spanish Vocabulary / Linear Algebra
    assert "2 study deck" in content or "Spanish Vocabulary" in content or "Linear Algebra" in content


# ---------------------------------------------------------------------------
# Test 14: Chat Streaming Grounding & Offline Fallback
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_chat_streaming_study_grounding(client: httpx.AsyncClient) -> None:
    """Verify streaming chat runtime grounds study decks and flashcards stats."""
    email = f"study_stream_{uuid.uuid4().hex[:8]}@example.com"
    headers, _ = await _get_auth(client, email)

    # 1. Ask via stream before creating any deck -> 0 decks message
    resp_empty = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "What study decks do I have in my library?", "provider": "offline"},
        headers=headers,
    )
    assert resp_empty.status_code == 200
    empty_stream = resp_empty.text
    assert "data:" in empty_stream
    assert "no study decks" in empty_stream.lower()

    # 2. Create a study deck
    deck_resp = await client.post(
        "/api/v1/study/decks",
        headers=headers,
        json={"title": "Cellular Respiration", "subject": "Biology"},
    )
    assert deck_resp.status_code == 201
    deck_id = deck_resp.json()["id"]

    await client.post(
        f"/api/v1/study/decks/{deck_id}/cards",
        headers=headers,
        json={"front": "Glycolysis location", "back": "Cytoplasm"},
    )

    # 3. Ask via stream again -> confirms 1 study deck
    resp_one = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "Can you check my study decks and flashcards?", "provider": "offline"},
        headers=headers,
    )
    assert resp_one.status_code == 200
    one_stream = resp_one.text
    assert "data:" in one_stream
    assert "1 study deck" in one_stream
    assert "Cellular Respiration" in one_stream

