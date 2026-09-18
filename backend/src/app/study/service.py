"""Study & Learning Studio Service (Phase 16).

Coordinates AI flashcard generation, quiz construction, spaced repetition scheduling,
and study deck mastery evaluation.
"""

from __future__ import annotations

import json
import re

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

    def __init__(self, repository: StudyRepository | None = None) -> None:
        self.repo = repository or StudyRepository()

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
