"""Study & Learning Studio Service (Phase 16).

Coordinates AI flashcard generation, quiz construction, spaced repetition scheduling,
and study deck mastery evaluation.
"""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

import structlog

from app.study.repository import StudyRepository
from app.study.schemas import (
    GeneratedCard,
    GenerateFlashcardsRequest,
    GenerateFlashcardsResponse,
    GenerateQuizRequest,
    GenerateQuizResponse,
    QuizQuestion,
    QuizSessionResponse,
    QuizSubmitRequest,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

log = structlog.get_logger()


# System prompts adhering to .claude/agents/study.md
FLASHCARD_SYSTEM_PROMPT = (
    "You are an expert Study Agent. Generate clear, accurate flashcards from the provided material.\n"
    "Quality bar rules:\n"
    "1. One concept per card.\n"
    "2. Clear, unambiguous answers on the back.\n"
    "3. Never give away the answer in the question.\n"
    "4. Add an optional concise explanation or memory hook.\n"
    "Output ONLY valid JSON matching this exact structure: "
    "{\"cards\": [{\"front\": \"...\", \"back\": \"...\", \"explanation\": \"...\", \"tags\": [\"...\"]}]}"
)

QUIZ_SYSTEM_PROMPT = (
    "You are an expert Study Agent. Generate challenging, educational multiple-choice quiz questions.\n"
    "Quality bar rules:\n"
    "1. Exactly 4 options per question.\n"
    "2. Plausible distractors (wrong answers must be reasonable, not absurd).\n"
    "3. Unambiguous correct answer with 0-based index.\n"
    "4. Detailed pedagogical explanation.\n"
    "Output ONLY valid JSON matching this exact structure: "
    "{\"questions\": [{\"question\": \"...\", \"options\": [\"A\", \"B\", \"C\", \"D\"], \"correct_index\": 0, \"explanation\": \"...\"}]}"
)


class StudyService:
    """Service for Study Studio operations."""

    _instance: ClassVar[StudyService | None] = None

    def __init__(self, repository: StudyRepository | None = None) -> None:
        self.repo = repository or StudyRepository()

    @classmethod
    def get_instance(cls, repository: StudyRepository | None = None) -> StudyService:
        """Get or initialize singleton instance of StudyService."""
        if cls._instance is None:
            cls._instance = cls(repository=repository)
        return cls._instance

    async def generate_flashcards(
        self, user_id: str, request: GenerateFlashcardsRequest
    ) -> GenerateFlashcardsResponse:
        """Generate structured flashcards using AI with deterministic fallback."""
        topic = request.topic.strip()
        count = max(1, min(25, request.count))
        level = request.level or "intermediate"
        source = (request.source_text or "").strip()

        cards: list[GeneratedCard] = []

        # Attempt AI generation via AI Gateway
        try:
            from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole, TaskType
            from app.ai_gateway.services.router import AIRouter

            user_prompt = (
                f"Topic: {topic}\n"
                f"Difficulty Level: {level}\n"
                f"Target Card Count: {count}\n"
            )
            if source:
                user_prompt += f"Source Material:\n{source[:4000]}\n"
            user_prompt += f"\nGenerate exactly {count} flashcards adhering to the system rules. Output JSON only."

            router = AIRouter()
            chat_req = AIRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=FLASHCARD_SYSTEM_PROMPT),
                    Message(role=MessageRole.USER, content=user_prompt),
                ],
                task_type=TaskType.GENERAL,
                temperature=0.3,
                user_id=user_id,
            )
            chat_resp = await router.route(chat_req)
            resp_text = (chat_resp.content or "").strip()

            cards = self._parse_generated_cards(resp_text, count, topic)
        except Exception as exc:
            log.warning("study_service.ai_flashcard_failed", error=str(exc))

        # Fallback if AI was unavailable or produced empty cards
        if not cards:
            cards = self._fallback_generate_cards(topic, source, count, level)

        # Optional auto-save to deck
        saved_deck_id = request.save_to_deck_id
        deck_title = None

        if request.new_deck_title:
            new_deck = await self.repo.create_deck(
                user_id=user_id,
                title=request.new_deck_title.strip(),
                description=f"Generated deck on {topic}",
                subject=topic[:30],
                tags=[topic, level],
            )
            saved_deck_id = new_deck["id"]
            deck_title = new_deck["title"]
        elif saved_deck_id:
            existing = await self.repo.get_deck(user_id, saved_deck_id)
            if existing:
                deck_title = existing["title"]

        if saved_deck_id:
            for c in cards:
                await self.repo.create_card(
                    user_id=user_id,
                    deck_id=saved_deck_id,
                    front=c.front,
                    back=c.back,
                    explanation=c.explanation,
                    level=level,
                )

        return GenerateFlashcardsResponse(
            topic=topic,
            count=len(cards),
            level=level,
            cards=cards,
            deck_id=saved_deck_id,
            deck_title=deck_title,
        )

    async def generate_quiz(
        self, user_id: str, request: GenerateQuizRequest
    ) -> GenerateQuizResponse:
        """Generate interactive practice quiz with options and explanations."""
        topic = request.topic.strip()
        count = max(1, min(20, request.count))
        difficulty = request.difficulty or "medium"
        source = (request.source_text or "").strip()

        # If deck_id provided and no source, gather deck cards as context
        if request.deck_id and not source:
            deck_cards = await self.repo.list_cards_for_deck(user_id, request.deck_id, limit=50)
            if deck_cards:
                source = "\n".join(
                    f"Q: {c.get('front', '')} | A: {c.get('back', '')}" for c in deck_cards
                )

        questions: list[QuizQuestion] = []

        # Attempt AI generation
        try:
            from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole, TaskType
            from app.ai_gateway.services.router import AIRouter

            user_prompt = (
                f"Topic: {topic}\n"
                f"Difficulty: {difficulty}\n"
                f"Number of Questions: {count}\n"
            )
            if source:
                user_prompt += f"Study Context:\n{source[:4000]}\n"
            user_prompt += f"\nGenerate exactly {count} multiple-choice questions. Output JSON only."

            router = AIRouter()
            chat_req = AIRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=QUIZ_SYSTEM_PROMPT),
                    Message(role=MessageRole.USER, content=user_prompt),
                ],
                task_type=TaskType.GENERAL,
                temperature=0.3,
                user_id=user_id,
            )
            chat_resp = await router.route(chat_req)
            resp_text = (chat_resp.content or "").strip()

            questions = self._parse_quiz_questions(resp_text, count, topic)
        except Exception as exc:
            log.warning("study_service.ai_quiz_failed", error=str(exc))

        # Fallback if AI was unavailable
        if not questions:
            questions = self._fallback_generate_quiz(topic, source, count, difficulty)

        return GenerateQuizResponse(
            topic=topic,
            count=len(questions),
            difficulty=difficulty,
            questions=questions,
        )

    async def submit_quiz(
        self, user_id: str, request: QuizSubmitRequest
    ) -> QuizSessionResponse:
        """Evaluate quiz answers, compute percentage score, and persist session."""
        questions = request.questions
        user_answers = request.user_answers
        total_q = len(questions)

        score = 0
        for idx, q in enumerate(questions):
            ans_key = str(idx)
            correct_idx = q.get("correct_index", 0)
            if ans_key in user_answers and user_answers[ans_key] == correct_idx:
                score += 1

        quiz_dict = await self.repo.create_quiz_session(
            user_id=user_id,
            topic=request.topic,
            questions=questions,
            user_answers=user_answers,
            score=score,
            total_questions=total_q,
            title=request.title,
            difficulty=request.difficulty,
            deck_id=request.deck_id,
        )

        return QuizSessionResponse(**quiz_dict)

    # ---------------------------------------------------------------------------
    # Internal Parsers & Fallback Generators
    # ---------------------------------------------------------------------------

    def _parse_generated_cards(
        self, raw_text: str, target_count: int, topic: str
    ) -> list[GeneratedCard]:
        """Extract and validate JSON cards from AI response."""
        json_match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group(1))
            raw_cards = data.get("cards") or []
            results: list[GeneratedCard] = []
            for c in raw_cards[:target_count]:
                front = str(c.get("front") or "").strip()
                back = str(c.get("back") or "").strip()
                if front and back:
                    results.append(
                        GeneratedCard(
                            front=front,
                            back=back,
                            explanation=c.get("explanation"),
                            tags=c.get("tags") or [topic],
                        )
                    )
            return results
        except Exception:
            return []

    def _parse_quiz_questions(
        self, raw_text: str, target_count: int, _topic: str
    ) -> list[QuizQuestion]:
        """Extract and validate quiz questions from AI response."""
        json_match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group(1))
            raw_questions = data.get("questions") or []
            results: list[QuizQuestion] = []
            for q in raw_questions[:target_count]:
                question = str(q.get("question") or "").strip()
                options = [str(opt).strip() for opt in q.get("options", []) if str(opt).strip()]
                correct_idx = int(q.get("correct_index", 0))
                expl = str(q.get("explanation") or "").strip()
                if question and len(options) >= 2:
                    results.append(
                        QuizQuestion(
                            question=question,
                            options=options,
                            correct_index=min(max(0, correct_idx), len(options) - 1),
                            explanation=expl or f"Option {correct_idx + 1} is the correct answer.",
                        )
                    )
            return results
        except Exception:
            return []

    def _fallback_generate_cards(
        self, topic: str, source: str, count: int, _level: str
    ) -> list[GeneratedCard]:
        """Deterministic knowledge generator for flashcards when AI is offline."""
        cards: list[GeneratedCard] = []

        # If source text has bullet points or sentences, parse them
        if source:
            lines = [
                line.strip().lstrip("-*•1234567890.) ")
                for line in source.splitlines()
                if line.strip()
            ]
            for line in lines:
                if ":" in line:
                    parts = line.split(":", 1)
                    cards.append(
                        GeneratedCard(
                            front=f"What is {parts[0].strip()}?",
                            back=parts[1].strip(),
                            explanation=f"Key concept from {topic} study notes.",
                            tags=[topic],
                        )
                    )
                elif " is " in line:
                    parts = line.split(" is ", 1)
                    cards.append(
                        GeneratedCard(
                            front=f"What is {parts[0].strip()}?",
                            back=f"It is {parts[1].strip()}",
                            explanation=f"Definition from {topic} study notes.",
                            tags=[topic],
                        )
                    )
                if len(cards) >= count:
                    break

        # Standard domain cards if source was short or missing
        templates = [
            (
                f"What is the primary definition of {topic}?",
                f"{topic} encompasses the fundamental principles, mechanisms, and core methodologies in its respective field.",
                f"Core foundation of {topic}.",
            ),
            (
                f"What are the essential components or characteristics of {topic}?",
                "Key components include structured architecture, input-output transformations, and systematic workflows.",
                f"Architectural building block for {topic}.",
            ),
            (
                f"What is a standard best practice when applying {topic}?",
                "Follow modular design, continuous verification, and robust boundary constraint validation.",
                f"Best practice recommendation for {topic}.",
            ),
            (
                f"How does {topic} address failure states or edge cases?",
                "Through defensive validation, graceful degradation fallbacks, and comprehensive exception logging.",
                f"Reliability principle for {topic}.",
            ),
            (
                f"Why is {topic} critical in modern technical systems?",
                "It optimizes operational efficiency, reduces manual overhead, and enhances systemic scalability.",
                f"Systemic impact of {topic}.",
            ),
        ]

        while len(cards) < count:
            idx = len(cards) % len(templates)
            tpl = templates[idx]
            suffix = f" (Part {len(cards) + 1})" if len(cards) >= len(templates) else ""
            cards.append(
                GeneratedCard(
                    front=tpl[0] + suffix,
                    back=tpl[1],
                    explanation=tpl[2],
                    tags=[topic],
                )
            )

        return cards[:count]

    def _fallback_generate_quiz(
        self, topic: str, source: str, count: int, _difficulty: str
    ) -> list[QuizQuestion]:
        """Deterministic generator for multiple-choice quiz questions."""
        questions: list[QuizQuestion] = []

        q_templates = [
            {
                "question": f"Which of the following best defines the primary purpose of {topic}?",
                "options": [
                    f"To provide systematic structure, predictable execution, and reliable outcomes for {topic}.",
                    "To generate unverified synthetic artifacts without validation.",
                    "To bypass standard security constraints and credential isolation.",
                    "To execute arbitrary unmonitored background subprocesses.",
                ],
                "correct_index": 0,
                "explanation": f"The primary goal of {topic} is reliable, structured, and predictable execution.",
            },
            {
                "question": f"When evaluating {topic}, what is considered an essential operational best practice?",
                "options": [
                    "Disabling all error logging and silent retry policies.",
                    "Implementing defensive input validation and multi-tenant security barriers.",
                    "Hardcoding static credentials directly into client interfaces.",
                    "Ignoring state persistence and relying entirely on ephemeral storage.",
                ],
                "correct_index": 1,
                "explanation": "Defensive input validation and tenant boundary isolation are fundamental best practices.",
            },
            {
                "question": f"In the context of spaced repetition and active recall in {topic}, how should errors be handled?",
                "options": [
                    "Discarding the card permanently from the study schedule.",
                    "Resetting the concept to Box 1 for immediate short-interval review.",
                    "Marking the card as mastered and skipping future evaluations.",
                    "Archiving the deck without updating review timestamps.",
                ],
                "correct_index": 1,
                "explanation": "In Leitner spaced repetition, missed cards return to Box 1 for reinforcement.",
            },
            {
                "question": f"What is the primary benefit of decomposing complex {topic} concepts into flashcards?",
                "options": [
                    "It ensures one distinct concept per card, promoting focused active recall.",
                    "It inflates the total question count without enhancing comprehension.",
                    "It eliminates the need for any conceptual verification.",
                    "It obfuscates the underlying subject matter definitions.",
                ],
                "correct_index": 0,
                "explanation": "Single-concept flashcards maximize memory retention by isolating atomic ideas.",
            },
            {
                "question": f"How does structured mastery tracking improve retention for {topic}?",
                "options": [
                    "By hiding review dates and scheduling cards randomly.",
                    "By quantifying mastery percentage and prioritizing cards that are due for review.",
                    "By preventing users from taking self-assessment quizzes.",
                    "By enforcing identical review intervals regardless of user performance.",
                ],
                "correct_index": 1,
                "explanation": "Mastery tracking dynamically prioritizes items that are due or need reinforcement.",
            },
        ]

        while len(questions) < count:
            idx = len(questions) % len(q_templates)
            tpl = q_templates[idx]
            suffix = f" [Question {len(questions) + 1}]" if len(questions) >= len(q_templates) else ""
            q_text = str(tpl["question"]) + suffix
            raw_opts = tpl["options"]
            opt_list = [str(o) for o in raw_opts] if isinstance(raw_opts, (list, tuple)) else []
            c_idx = int(str(tpl["correct_index"]))
            expl = str(tpl["explanation"])
            questions.append(
                QuizQuestion(
                    question=q_text,
                    options=opt_list,
                    correct_index=c_idx,
                    explanation=expl,
                )
            )

        return questions[:count]

    # ---------------------------------------------------------------------------
    # Zia Tutor Domain Methods (Phase 10)
    # ---------------------------------------------------------------------------

    async def create_study_plan(
        self,
        user_id: str,
        topic: str,
        difficulty: str = "intermediate",
        target_days: int = 7,
    ) -> dict[str, Any]:
        """Generate structured curriculum milestones and establish an active study deck."""
        clean_topic = topic.strip()
        days = max(1, min(30, target_days))

        milestones = [
            {
                "day": 1,
                "title": f"Foundational Principles of {clean_topic}",
                "focus": "Core terminology, atomic concepts, and theoretical overview.",
                "activities": ["Review concept flashcards", "Complete diagnostic quiz"],
            },
            {
                "day": min(2, days),
                "title": "Structural Mechanics & Architecture",
                "focus": "Component relationships, data flow, and standard operation patterns.",
                "activities": ["Socratic dialogue review", "Active recall drills"],
            },
            {
                "day": min(3, days),
                "title": "Implementation Patterns & Best Practices",
                "focus": "Defensive workflows, modular decomposition, and boundary verification.",
                "activities": ["Flashcard Leitner review (Box 2/3)", "Application practice"],
            },
            {
                "day": min(5, days),
                "title": "Edge Cases, Error Handling & Optimization",
                "focus": "Fault tolerance, performance bottlenecks, and real-world diagnostics.",
                "activities": ["Scenario-based quizzes", "Targeted reinforcement"],
            },
            {
                "day": days,
                "title": "Comprehensive Mastery & Capstone Evaluation",
                "focus": "Full curriculum synthesis and retention assessment.",
                "activities": ["Comprehensive final quiz", "Long-term Leitner Box 5 graduation"],
            },
        ]

        seen_days: set[int] = set()
        deduped_milestones: list[dict[str, Any]] = []
        for m in milestones:
            if m["day"] not in seen_days and m["day"] <= days:
                seen_days.add(m["day"])
                deduped_milestones.append(m)

        deck = await self.repo.create_deck(
            user_id=user_id,
            title=f"Study Plan: {clean_topic}",
            description=f"{days}-day adaptive curriculum covering {clean_topic} ({difficulty} level).",
            subject=clean_topic[:30],
            tags=[clean_topic, difficulty, "curriculum"],
        )
        deck_id = deck["id"]

        gen_resp = await self.generate_flashcards(
            user_id=user_id,
            request=GenerateFlashcardsRequest(
                topic=clean_topic,
                count=5,
                level=difficulty,
                save_to_deck_id=deck_id,
            ),
        )

        return {
            "topic": clean_topic,
            "difficulty": difficulty,
            "target_days": days,
            "deck_id": deck_id,
            "deck_title": deck["title"],
            "cards_created": gen_resp.count,
            "milestones": deduped_milestones,
            "summary": f"Generated {days}-day study plan for '{clean_topic}' with {gen_resp.count} flashcards in deck '{deck['title']}'.",
        }

    async def evaluate_answer(
        self,
        user_id: str,
        card_id: str | None = None,
        is_correct: bool = True,
        user_answer: str | None = None,
        question: str | None = None,
        expected_answer: str | None = None,
    ) -> dict[str, Any]:
        """Socratic evaluation of a learner's answer with Leitner spaced repetition progression."""
        card_info = None
        new_box = 1
        next_review_at = None

        if card_id:
            updated_card = await self.repo.record_card_review(
                user_id=user_id, card_id=card_id, is_correct=is_correct
            )
            if updated_card:
                card_info = updated_card
                new_box = updated_card.get("box", 1)
                next_review_at = updated_card.get("next_review_at")
                if not question:
                    question = updated_card.get("front")
                if not expected_answer:
                    expected_answer = updated_card.get("back")

        if is_correct:
            socratic_feedback = (
                f"Excellent grasp! You accurately identified: '{user_answer or expected_answer or 'the core concept'}'. "
                f"Notice how this connects to the broader systemic principles. "
                f"Advancing to Leitner Box {new_box}."
            )
        else:
            socratic_feedback = (
                f"Not quite, but let's break it down together. Consider: '{question or 'the key premise'}'. "
                f"What fundamental mechanism drives this rather than '{user_answer or 'the current guess'}'? "
                f"Card reset to Leitner Box 1 for rapid review."
            )

        return {
            "is_correct": is_correct,
            "card_id": card_id,
            "new_box": new_box,
            "next_review_at": next_review_at,
            "socratic_feedback": socratic_feedback,
            "card": card_info,
            "summary": f"Answer evaluated as {'correct' if is_correct else 'incorrect'}. Leitner box is now {new_box}.",
        }

    async def get_topic_mastery(
        self,
        user_id: str,
        deck_id: str | None = None,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve topic mastery metrics, cards due, and Leitner progression."""
        if deck_id:
            deck = await self.repo.get_deck(user_id=user_id, deck_id=deck_id)
            if not deck:
                return {"user_id": user_id, "found": False, "error": f"Deck '{deck_id}' not found."}
            cards = await self.repo.list_cards_for_deck(user_id=user_id, deck_id=deck_id, limit=200)
            box_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for c in cards:
                box_counts[c.get("box", 1)] = box_counts.get(c.get("box", 1), 0) + 1
            return {
                "user_id": user_id,
                "deck_id": deck_id,
                "title": deck["title"],
                "subject": deck.get("subject", "General"),
                "mastery_percentage": deck.get("mastery_percentage", 0.0),
                "total_cards": len(cards),
                "leitner_boxes": box_counts,
                "summary": f"Deck '{deck['title']}' is at {deck.get('mastery_percentage', 0.0)}% mastery with {len(cards)} cards.",
            }

        stats = await self.repo.get_study_stats(user_id=user_id)
        decks = await self.repo.list_decks(user_id=user_id, query=topic, limit=20)
        return {
            "user_id": user_id,
            "overall_stats": stats,
            "filtered_topic": topic,
            "matching_decks": [
                {
                    "id": d["id"],
                    "title": d["title"],
                    "subject": d.get("subject", "General"),
                    "mastery_percentage": d.get("mastery_percentage", 0.0),
                    "card_count": d.get("card_count", 0),
                }
                for d in decks
            ],
            "summary": f"Overall mastery: {stats.get('average_mastery', 0.0)}% across {stats.get('total_decks', 0)} decks with {stats.get('cards_due_for_review', 0)} cards due for review.",
        }

    async def reset_progress(
        self,
        user_id: str,
        deck_id: str | None = None,
        delete_deck: bool = False,
    ) -> dict[str, Any]:
        """Destructive mutation: Reset card Leitner review progress or delete deck entirely."""
        if delete_deck and deck_id:
            success = await self.repo.delete_deck(user_id=user_id, deck_id=deck_id)
            return {
                "user_id": user_id,
                "deck_id": deck_id,
                "deleted": success,
                "action": "delete_deck",
                "summary": f"Study deck '{deck_id}' and all associated flashcards have been deleted.",
            }

        result = await self.repo.reset_progress(user_id=user_id, deck_id=deck_id)
        result["action"] = "reset_boxes"
        return result

    # ---------------------------------------------------------------------------
    # Central Tool Registry Integration (Phase 10: Zia Tutor AI)
    # ---------------------------------------------------------------------------

    def register_tutor_tools(self, registry: ToolRegistry | None = None) -> None:
        """Register all Zia Tutor AI tools into the Central Tool Registry."""
        reg = registry or ToolRegistry.get_instance()

        # 1. tutor_create_study_plan
        async def _tool_tutor_create_study_plan(
            topic: str,
            difficulty: str = "intermediate",
            target_days: int = 7,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            return await self.create_study_plan(
                user_id=uid,
                topic=topic,
                difficulty=difficulty,
                target_days=target_days,
            )

        reg.register(
            AgentTool(
                id="tutor_create_study_plan",
                name="Create Study Plan",
                description="Generate a personalized adaptive study plan, milestone curriculum, and initial flashcard deck for any topic or skill.",
                source=ToolSource.SYSTEM,
                capabilities=["study", "tutor", "curriculum", "learning_plan"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Subject or skill to learn"},
                        "difficulty": {"type": "string", "description": "Difficulty level: beginner, intermediate, advanced", "default": "intermediate"},
                        "target_days": {"type": "integer", "description": "Duration of study plan in days", "default": 7},
                    },
                    "required": ["topic"],
                },
                permissions=["study:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_tutor_create_study_plan,
        )

        # 2. tutor_generate_quiz
        async def _tool_tutor_generate_quiz(
            topic: str,
            count: int = 5,
            difficulty: str = "medium",
            deck_id: str | None = None,
            source_text: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            resp = await self.generate_quiz(
                user_id=uid,
                request=GenerateQuizRequest(
                    topic=topic,
                    count=count,
                    difficulty=difficulty,
                    deck_id=deck_id,
                    source_text=source_text,
                ),
            )
            return {
                "topic": resp.topic,
                "count": resp.count,
                "difficulty": resp.difficulty,
                "questions": [q.model_dump() for q in resp.questions],
                "summary": f"Generated {resp.count} multiple-choice quiz questions on '{resp.topic}'.",
            }

        reg.register(
            AgentTool(
                id="tutor_generate_quiz",
                name="Generate Practice Quiz",
                description="Generate interactive multiple-choice practice quizzes with pedagogical explanations and distractors.",
                source=ToolSource.SYSTEM,
                capabilities=["study", "tutor", "quiz", "assessment"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Topic or concept to be quizzed on"},
                        "count": {"type": "integer", "description": "Number of questions to generate", "default": 5},
                        "difficulty": {"type": "string", "description": "Difficulty: easy, medium, hard", "default": "medium"},
                        "deck_id": {"type": "string", "description": "Optional study deck ID to ground questions in"},
                        "source_text": {"type": "string", "description": "Optional reference study notes or excerpts"},
                    },
                    "required": ["topic"],
                },
                permissions=["study:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_tutor_generate_quiz,
        )

        # 3. tutor_evaluate_answer
        async def _tool_tutor_evaluate_answer(
            is_correct: bool,
            card_id: str | None = None,
            user_answer: str | None = None,
            question: str | None = None,
            expected_answer: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            return await self.evaluate_answer(
                user_id=uid,
                card_id=card_id,
                is_correct=is_correct,
                user_answer=user_answer,
                question=question,
                expected_answer=expected_answer,
            )

        reg.register(
            AgentTool(
                id="tutor_evaluate_answer",
                name="Evaluate Tutor Answer",
                description="Evaluate a student's answer, provide Socratic feedback, and advance or reset the flashcard's Leitner spaced repetition interval.",
                source=ToolSource.SYSTEM,
                capabilities=["study", "tutor", "evaluate", "socratic", "spaced_repetition"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "is_correct": {"type": "boolean", "description": "Whether the answer was correct"},
                        "card_id": {"type": "string", "description": "Optional flashcard ID being reviewed"},
                        "user_answer": {"type": "string", "description": "The student's submitted response"},
                        "question": {"type": "string", "description": "The prompt or question asked"},
                        "expected_answer": {"type": "string", "description": "The correct answer or definition"},
                    },
                    "required": ["is_correct"],
                },
                permissions=["study:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_tutor_evaluate_answer,
        )

        # 4. tutor_create_flashcards
        async def _tool_tutor_create_flashcards(
            topic: str,
            count: int = 5,
            level: str = "intermediate",
            source_text: str | None = None,
            save_to_deck_id: str | None = None,
            new_deck_title: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            resp = await self.generate_flashcards(
                user_id=uid,
                request=GenerateFlashcardsRequest(
                    topic=topic,
                    count=count,
                    level=level,
                    source_text=source_text,
                    save_to_deck_id=save_to_deck_id,
                    new_deck_title=new_deck_title,
                ),
            )
            return {
                "topic": resp.topic,
                "count": resp.count,
                "level": resp.level,
                "deck_id": resp.deck_id,
                "deck_title": resp.deck_title,
                "cards": [c.model_dump() for c in resp.cards],
                "summary": f"Created {resp.count} flashcards on '{resp.topic}'" + (f" in deck '{resp.deck_title}'." if resp.deck_title else "."),
            }

        reg.register(
            AgentTool(
                id="tutor_create_flashcards",
                name="Create Flashcards",
                description="Generate atomic, active-recall flashcards from study materials, notes, or topics, with optional persistence to a deck.",
                source=ToolSource.SYSTEM,
                capabilities=["study", "tutor", "flashcards", "active_recall"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Subject or topic of the flashcards"},
                        "count": {"type": "integer", "description": "Number of flashcards to generate", "default": 5},
                        "level": {"type": "string", "description": "Difficulty: beginner, intermediate, advanced", "default": "intermediate"},
                        "source_text": {"type": "string", "description": "Optional notes or source material to extract cards from"},
                        "save_to_deck_id": {"type": "string", "description": "Existing deck ID to save cards to"},
                        "new_deck_title": {"type": "string", "description": "Title of new deck to create and save cards in"},
                    },
                    "required": ["topic"],
                },
                permissions=["study:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_tutor_create_flashcards,
        )

        # 5. tutor_get_topic_mastery
        async def _tool_tutor_get_topic_mastery(
            deck_id: str | None = None,
            topic: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            return await self.get_topic_mastery(user_id=uid, deck_id=deck_id, topic=topic)

        reg.register(
            AgentTool(
                id="tutor_get_topic_mastery",
                name="Get Topic Mastery",
                description="Retrieve learning mastery metrics, spaced repetition cards due for review, Leitner box distribution, and overall study progress.",
                source=ToolSource.SYSTEM,
                capabilities=["study", "tutor", "mastery", "progress", "stats"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "deck_id": {"type": "string", "description": "Specific study deck ID to inspect"},
                        "topic": {"type": "string", "description": "Filter mastery by topic keyword"},
                    },
                },
                permissions=["study:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_tutor_get_topic_mastery,
        )

        # 6. tutor_reset_progress (RiskLevel.HIGH, requires_confirmation=True)
        async def _tool_tutor_reset_progress(
            deck_id: str | None = None,
            delete_deck: bool = False,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            return await self.reset_progress(user_id=uid, deck_id=deck_id, delete_deck=delete_deck)

        reg.register(
            AgentTool(
                id="tutor_reset_progress",
                name="Reset Study Progress",
                description="Destructively reset study progress, mastery scores, and card intervals back to Leitner Box 1, or delete a study deck. Requires explicit confirmation.",
                source=ToolSource.SYSTEM,
                capabilities=["study", "tutor", "reset", "delete"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "deck_id": {"type": "string", "description": "Specific study deck to reset or delete"},
                        "delete_deck": {"type": "boolean", "description": "Whether to delete the deck entirely instead of just resetting review boxes", "default": False},
                    },
                },
                permissions=["study:write"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            ),
            _tool_tutor_reset_progress,
        )
