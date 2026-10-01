"""Phase 10 Master Integration Test Suite: Zia Tutor AI (Adaptive Personalized Learning Engine).

Verifies:
1. Tool discovery: All 6 tutor tools registered in Central ToolRegistry with correct risk levels and confirmation gates.
2. Adaptive study plan: Tool execution creates milestone curriculum and initializes active study deck.
3. Leitner spaced repetition: 5-box intervals, box advancement on correct, reset to box 1 on incorrect, and mastery recomputation.
4. Socratic tutoring: tutor_evaluate_answer generates pedagogical feedback and updates active recall state.
5. Interactive quizzes: Practice quiz generation, submission scoring, and historical persistence.
6. Topic mastery metrics: Deck-level and holistic stats tracking Leitner distribution and cards due for review.
7. Destructive progress reset: Action Center confirmation gating on tutor_reset_progress (RiskLevel.HIGH, requires_confirmation=True).
8. AgentPlanner intent routing: Deterministic routing for study plans, quizzes, flashcards, mastery, and resets.
9. Strict multi-tenant anti-IDOR isolation across decks, cards, quizzes, and mastery metrics.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.agent_runtime.planner import AgentPlanner
from app.main import app
from app.study.repository import StudyRepository, clear_in_memory_stores
from app.study.schemas import QuizSubmitRequest
from app.study.service import StudyService
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel, ToolExecutionRequest


@pytest.fixture(autouse=True)
def _reset_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_in_memory_stores()
    # Re-register tutor tools in registry
    StudyService.get_instance().register_tutor_tools()

    # Fast deterministic fallback mode (avoids external network timeouts)
    from app.ai_gateway.services.router import AIRouter

    async def _mock_route(*args: object, **kwargs: object) -> None:
        raise RuntimeError("AI test fallback mode")

    monkeypatch.setattr(AIRouter, "route", _mock_route)


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
# Test 1: Tool Discovery & Confirmation Gates in Central ToolRegistry
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_tool_discovery_and_confirmation_gates() -> None:
    """Verify all 6 Zia Tutor tools are registered with precise risk levels and confirmation gates."""
    registry = ToolRegistry.get_instance()
    StudyService.get_instance().register_tutor_tools(registry)

    expected_tools = {
        "tutor_create_study_plan": (RiskLevel.LOW, False),
        "tutor_generate_quiz": (RiskLevel.LOW, False),
        "tutor_evaluate_answer": (RiskLevel.LOW, False),
        "tutor_create_flashcards": (RiskLevel.LOW, False),
        "tutor_get_topic_mastery": (RiskLevel.LOW, False),
        "tutor_reset_progress": (RiskLevel.HIGH, True),
    }

    for tool_id, (expected_risk, expected_confirmation) in expected_tools.items():
        tool = registry.get(tool_id)
        assert tool is not None, f"Tool '{tool_id}' must be registered in ToolRegistry"
        assert tool.risk_level == expected_risk, f"Tool '{tool_id}' risk level mismatch"
        assert tool.requires_confirmation is expected_confirmation, (
            f"Tool '{tool_id}' confirmation mismatch: expected {expected_confirmation}"
        )
        assert "study" in tool.capabilities or "tutor" in tool.capabilities


# ---------------------------------------------------------------------------
# Test 2: Adaptive Study Plan Creation Tool Execution
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_create_study_plan_tool_execution() -> None:
    """Verify tutor_create_study_plan creates a multi-day milestone curriculum and initial deck."""
    registry = ToolRegistry.get_instance()
    user_id = f"user_study_plan_{uuid.uuid4().hex[:8]}"

    res = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_create_study_plan",
            arguments={"topic": "Distributed Consensus", "difficulty": "advanced", "target_days": 10},
            user_id=user_id,
        )
    )
    assert res.success is True
    result = res.output

    assert result["topic"] == "Distributed Consensus"
    assert result["difficulty"] == "advanced"
    assert result["target_days"] == 10
    assert result["cards_created"] >= 5
    assert len(result["milestones"]) >= 3
    assert result["deck_id"] is not None

    # Verify the deck was persisted and belongs to user
    repo = StudyRepository()
    deck = await repo.get_deck(user_id, result["deck_id"])
    assert deck is not None
    assert deck["title"] == "Study Plan: Distributed Consensus"
    assert deck["card_count"] >= 5


# ---------------------------------------------------------------------------
# Test 3: Leitner Spaced Repetition Mechanics (5-Box Progression & Reset)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_leitner_spaced_repetition_progression() -> None:
    """Verify card advancement through Leitner boxes on correct reviews and reset to Box 1 on error."""
    repo = StudyRepository()
    user_id = f"user_leitner_{uuid.uuid4().hex[:8]}"

    # Create deck and card
    deck = await repo.create_deck(user_id=user_id, title="Raft Algorithm")
    deck_id = deck["id"]
    card = await repo.create_card(
        user_id=user_id,
        deck_id=deck_id,
        front="What is a Leader Election in Raft?",
        back="Process where candidate nodes request votes when heartbeat times out.",
    )
    assert card is not None
    card_id = card["id"]
    assert card["box"] == 1

    # Initial deck mastery should be 0.0% (all in Box 1)
    deck_before = await repo.get_deck(user_id, deck_id)
    assert deck_before is not None
    assert deck_before["mastery_percentage"] == 0.0

    # 1. First correct review: Advances to Box 2 (weight: 0.25 -> 25% mastery)
    rev1 = await repo.record_card_review(user_id, card_id, is_correct=True)
    assert rev1 is not None
    assert rev1["box"] == 2
    assert rev1["review_count"] == 1
    assert rev1["correct_count"] == 1

    deck_after1 = await repo.get_deck(user_id, deck_id)
    assert deck_after1 is not None
    assert deck_after1["mastery_percentage"] == 25.0

    # 2. Second correct review: Advances to Box 3 (weight: 0.50 -> 50% mastery)
    rev2 = await repo.record_card_review(user_id, card_id, is_correct=True)
    assert rev2 is not None
    assert rev2["box"] == 3
    assert rev2["correct_count"] == 2

    deck_after2 = await repo.get_deck(user_id, deck_id)
    assert deck_after2 is not None
    assert deck_after2["mastery_percentage"] == 50.0

    # 3. Third correct review: Advances to Box 4 (weight: 0.75 -> 75% mastery)
    rev3 = await repo.record_card_review(user_id, card_id, is_correct=True)
    assert rev3 is not None
    assert rev3["box"] == 4

    deck_after3 = await repo.get_deck(user_id, deck_id)
    assert deck_after3 is not None
    assert deck_after3["mastery_percentage"] == 75.0

    # 4. Fourth correct review: Advances to Box 5 (weight: 1.0 -> 100% mastery)
    rev4 = await repo.record_card_review(user_id, card_id, is_correct=True)
    assert rev4 is not None
    assert rev4["box"] == 5

    deck_after4 = await repo.get_deck(user_id, deck_id)
    assert deck_after4 is not None
    assert deck_after4["mastery_percentage"] == 100.0

    # 5. Incorrect review: Resets back to Box 1 immediately (mastery drops to 0.0%)
    rev5 = await repo.record_card_review(user_id, card_id, is_correct=False)
    assert rev5 is not None
    assert rev5["box"] == 1
    assert rev5["review_count"] == 5
    assert rev5["correct_count"] == 4  # Did not increment on fail

    deck_after5 = await repo.get_deck(user_id, deck_id)
    assert deck_after5 is not None
    assert deck_after5["mastery_percentage"] == 0.0


# ---------------------------------------------------------------------------
# Test 4: Socratic Evaluation Tool Execution
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_evaluate_answer_tool_socratic_coaching() -> None:
    """Verify tutor_evaluate_answer provides Socratic feedback and advances Leitner state."""
    registry = ToolRegistry.get_instance()
    repo = StudyRepository()
    user_id = f"user_socratic_{uuid.uuid4().hex[:8]}"

    deck = await repo.create_deck(user_id=user_id, title="Database Normalization")
    assert deck is not None
    card = await repo.create_card(
        user_id=user_id,
        deck_id=deck["id"],
        front="What constitutes Third Normal Form (3NF)?",
        back="It is in 2NF and all transitive dependencies are eliminated.",
    )
    assert card is not None
    card_id = card["id"]

    # 1. Correct evaluation
    res_correct = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_evaluate_answer",
            arguments={
                "is_correct": True,
                "card_id": card_id,
                "user_answer": "No transitive functional dependencies on non-prime attributes.",
            },
            user_id=user_id,
        )
    )
    assert res_correct.success is True
    eval_correct = res_correct.output

    assert eval_correct["is_correct"] is True
    assert eval_correct["new_box"] == 2
    assert "Advancing to Leitner Box 2" in eval_correct["socratic_feedback"]
    assert "transitive" in eval_correct["socratic_feedback"].lower()

    # 2. Incorrect evaluation
    res_incorrect = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_evaluate_answer",
            arguments={
                "is_correct": False,
                "card_id": card_id,
                "user_answer": "Tables have foreign keys only.",
            },
            user_id=user_id,
        )
    )
    assert res_incorrect.success is True
    eval_incorrect = res_incorrect.output

    assert eval_incorrect["is_correct"] is False
    assert eval_incorrect["new_box"] == 1
    assert "Card reset to Leitner Box 1" in eval_incorrect["socratic_feedback"]


# ---------------------------------------------------------------------------
# Test 5: Interactive Quiz Generation and Session Scoring
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_generate_quiz_and_scoring() -> None:
    """Verify tutor_generate_quiz creates questions and submit_quiz computes percentage score."""
    registry = ToolRegistry.get_instance()
    service = StudyService.get_instance()
    user_id = f"user_quiz_{uuid.uuid4().hex[:8]}"

    # Generate quiz via tool
    res_quiz = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_generate_quiz",
            arguments={"topic": "Asynchronous Programming", "count": 4, "difficulty": "hard"},
            user_id=user_id,
        )
    )
    assert res_quiz.success is True
    quiz_res = res_quiz.output

    assert quiz_res["topic"] == "Asynchronous Programming"
    assert quiz_res["count"] == 4
    assert len(quiz_res["questions"]) == 4

    questions = quiz_res["questions"]
    for q in questions:
        assert len(q["options"]) >= 2
        assert "explanation" in q
        assert 0 <= q["correct_index"] < len(q["options"])

    # Submit answers: answer 3 correctly, 1 incorrectly
    user_answers = {
        "0": questions[0]["correct_index"],
        "1": questions[1]["correct_index"],
        "2": questions[2]["correct_index"],
        "3": (questions[3]["correct_index"] + 1) % len(questions[3]["options"]),  # Wrong
    }

    sub_req = QuizSubmitRequest(
        topic="Asynchronous Programming",
        questions=questions,
        user_answers=user_answers,
        title="Async Event Loop Quiz",
    )
    session_res = await service.submit_quiz(user_id=user_id, request=sub_req)

    assert session_res.score == 3
    assert session_res.total_questions == 4
    assert session_res.score_percentage == 75.0
    assert session_res.passed is True  # 75% >= 70%


# ---------------------------------------------------------------------------
# Test 6: Topic Mastery Metrics Tool Execution
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_get_topic_mastery_tool_execution() -> None:
    """Verify tutor_get_topic_mastery reports both deck-specific and holistic user metrics."""
    registry = ToolRegistry.get_instance()
    repo = StudyRepository()
    user_id = f"user_mastery_{uuid.uuid4().hex[:8]}"

    # Create 2 decks
    deck1 = await repo.create_deck(user_id=user_id, title="Kubernetes Primers", subject="DevOps")
    deck2 = await repo.create_deck(user_id=user_id, title="Docker Fundamentals", subject="DevOps")
    assert deck1 is not None
    assert deck2 is not None

    # Add card to deck1 and advance it to box 3
    c1 = await repo.create_card(user_id, deck1["id"], front="What is a Pod?", back="Atomic unit")
    assert c1 is not None
    await repo.record_card_review(user_id, c1["id"], is_correct=True)
    await repo.record_card_review(user_id, c1["id"], is_correct=True)

    # Add card to deck2
    await repo.create_card(user_id, deck2["id"], front="What is an Image?", back="Read-only template")

    # 1. Deck-specific mastery
    res_deck1 = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_get_topic_mastery",
            arguments={"deck_id": deck1["id"]},
            user_id=user_id,
        )
    )
    assert res_deck1.success is True
    deck1_mastery = res_deck1.output
    assert deck1_mastery["deck_id"] == deck1["id"]
    assert deck1_mastery["mastery_percentage"] == 50.0  # Box 3 = 50%
    assert deck1_mastery["leitner_boxes"][3] == 1

    # 2. Holistic topic mastery
    res_holistic = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_get_topic_mastery",
            arguments={"topic": "DevOps"},
            user_id=user_id,
        )
    )
    assert res_holistic.success is True
    holistic = res_holistic.output
    assert holistic["overall_stats"]["total_decks"] == 2
    assert holistic["overall_stats"]["total_cards"] == 2
    assert len(holistic["matching_decks"]) == 2


# ---------------------------------------------------------------------------
# Test 7: Destructive Progress Reset & Confirmation Gating
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_reset_progress_destructive_confirmation() -> None:
    """Verify tutor_reset_progress resets card boxes to 1 and enforces confirmation requirement."""
    registry = ToolRegistry.get_instance()
    repo = StudyRepository()
    user_id = f"user_reset_{uuid.uuid4().hex[:8]}"

    # Verify confirmation gate
    tool = registry.get("tutor_reset_progress")
    assert tool is not None
    assert tool.requires_confirmation is True
    assert tool.risk_level == RiskLevel.HIGH

    # Create deck, advance cards
    deck = await repo.create_deck(user_id=user_id, title="Cryptography")
    assert deck is not None
    c1 = await repo.create_card(user_id, deck["id"], front="What is RSA?", back="Public key cipher")
    c2 = await repo.create_card(user_id, deck["id"], front="What is AES?", back="Symmetric block cipher")
    assert c1 is not None
    assert c2 is not None
    await repo.record_card_review(user_id, c1["id"], is_correct=True)
    await repo.record_card_review(user_id, c2["id"], is_correct=True)

    # Deck mastery should be 25% (both in box 2)
    deck_mid = await repo.get_deck(user_id, deck["id"])
    assert deck_mid is not None
    assert deck_mid["mastery_percentage"] == 25.0

    # Execute reset via tool
    res_reset = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_reset_progress",
            arguments={"deck_id": deck["id"], "delete_deck": False},
            user_id=user_id,
        )
    )
    assert res_reset.success is True
    reset_res = res_reset.output
    assert reset_res["success"] is True
    assert reset_res["cards_reset"] == 2
    assert reset_res["mastery_percentage"] == 0.0

    # Verify cards are back to Box 1
    card1_after = await repo.get_card(user_id, c1["id"])
    card2_after = await repo.get_card(user_id, c2["id"])
    assert card1_after is not None
    assert card2_after is not None
    assert card1_after["box"] == 1
    assert card2_after["box"] == 1

    deck_after = await repo.get_deck(user_id, deck["id"])
    assert deck_after is not None
    assert deck_after["mastery_percentage"] == 0.0

    # Test delete_deck option
    res_del = await registry.execute(
        ToolExecutionRequest(
            tool_id="tutor_reset_progress",
            arguments={"deck_id": deck["id"], "delete_deck": True},
            user_id=user_id,
        )
    )
    assert res_del.success is True
    delete_res = res_del.output
    assert delete_res["deleted"] is True
    assert await repo.get_deck(user_id, deck["id"]) is None
    assert await repo.get_card(user_id, c1["id"]) is None


# ---------------------------------------------------------------------------
# Test 8: AgentPlanner Deterministic Intent Routing for Zia Tutor
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_zia_tutor_intent_routing() -> None:
    """Verify AgentPlanner parses natural language learning prompts into precise tutor tool calls."""
    planner = AgentPlanner()

    # 1. Create study plan intent
    plan1 = await planner.create_plan("create study plan for Microservices Architecture")
    assert len(plan1) >= 1
    assert plan1[0]["tool_id"] == "tutor_create_study_plan"
    assert "Microservices Architecture" in plan1[0]["tool_input"]["topic"]

    # 2. Practice quiz intent
    plan2 = await planner.create_plan("quiz me on Graph Neural Networks")
    assert len(plan2) >= 1
    assert plan2[0]["tool_id"] == "tutor_generate_quiz"
    assert "Graph Neural Networks" in plan2[0]["tool_input"]["topic"]

    # 3. Create flashcards intent
    plan3 = await planner.create_plan("create flashcards for Compiler Design")
    assert len(plan3) >= 1
    assert plan3[0]["tool_id"] == "tutor_create_flashcards"
    assert "Compiler Design" in plan3[0]["tool_input"]["topic"]

    # 4. Topic mastery intent
    plan4 = await planner.create_plan("topic mastery on Distributed Systems")
    assert len(plan4) >= 1
    assert plan4[0]["tool_id"] == "tutor_get_topic_mastery"

    # 5. Reset study progress intent
    plan5 = await planner.create_plan("reset study progress for deck deck_k8s_101")
    assert len(plan5) >= 1
    assert plan5[0]["tool_id"] == "tutor_reset_progress"
    assert plan5[0]["tool_input"]["deck_id"] == "deck_k8s_101"

    # 6. Evaluate answer intent
    plan6 = await planner.create_plan("evaluate answer for card card_456")
    assert len(plan6) >= 1
    assert plan6[0]["tool_id"] == "tutor_evaluate_answer"


# ---------------------------------------------------------------------------
# Test 9: Multi-Tenant Anti-IDOR Boundary Isolation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_multi_tenant_anti_idor_isolation(client: httpx.AsyncClient) -> None:
    """Verify strict tenant isolation: User B cannot access, mutate, or reset User A's study data."""
    headers_a, user_a_id = await _get_auth(client, f"tutor_a_{uuid.uuid4().hex[:8]}@example.com")
    headers_b, user_b_id = await _get_auth(client, f"tutor_b_{uuid.uuid4().hex[:8]}@example.com")

    # User A creates a deck and card via API
    deck_resp = await client.post(
        "/api/v1/study/decks",
        json={"title": "User A Private Study Deck", "subject": "Confidential Research"},
        headers=headers_a,
    )
    assert deck_resp.status_code == 201
    deck_a_id = deck_resp.json()["id"]

    card_resp = await client.post(
        f"/api/v1/study/decks/{deck_a_id}/cards",
        json={"front": "Private Question A", "back": "Private Answer A"},
        headers=headers_a,
    )
    assert card_resp.status_code == 201
    card_a_id = card_resp.json()["id"]

    # User B attempts to access User A's deck -> 404 Not Found
    get_deck_b = await client.get(f"/api/v1/study/decks/{deck_a_id}", headers=headers_b)
    assert get_deck_b.status_code == 404

    # User B attempts to list cards of User A's deck -> 404 Not Found
    list_cards_b = await client.get(f"/api/v1/study/decks/{deck_a_id}/cards", headers=headers_b)
    assert list_cards_b.status_code == 404

    # User B attempts to access User A's card directly -> 404 Not Found
    get_card_b = await client.get(f"/api/v1/study/cards/{card_a_id}", headers=headers_b)
    assert get_card_b.status_code == 404

    # User B attempts to submit review for User A's card -> 404 Not Found
    review_b = await client.post(
        f"/api/v1/study/cards/{card_a_id}/review",
        json={"is_correct": True},
        headers=headers_b,
    )
    assert review_b.status_code == 404

    # User B attempts to delete User A's deck -> 404 Not Found
    del_deck_b = await client.delete(f"/api/v1/study/decks/{deck_a_id}", headers=headers_b)
    assert del_deck_b.status_code == 404

    # Verify User A's deck and card are completely intact
    verify_a = await client.get(f"/api/v1/study/decks/{deck_a_id}", headers=headers_a)
    assert verify_a.status_code == 200
    assert verify_a.json()["title"] == "User A Private Study Deck"

    # User B's study stats must reflect zero decks
    stats_b = await client.get("/api/v1/study/stats", headers=headers_b)
    assert stats_b.status_code == 200
    assert stats_b.json()["total_decks"] == 0
    assert stats_b.json()["total_cards"] == 0
