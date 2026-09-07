"""quiz_generate skill — generate self-test quizzes from source material.

Uses the AI gateway to generate multiple-choice, short-answer, and fill-in-the-blank questions.
"""

from __future__ import annotations

import json
import re
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestion,
)


log = structlog.get_logger()

SYSTEM_PROMPT = (
    "You are a quiz generation assistant. Given source material, generate accurate self-test questions. "
    "Rules:\n"
    "1. Exactly one correct answer per question\n"
    "2. Distractors must be plausible but clearly wrong\n"
    "3. Questions must be unambiguous\n"
    "4. Vary question types unless told otherwise\n"
    "Output ONLY valid JSON: {\"questions\": [{\"type\": \"...\", \"question\": \"...\", "
    "\"options\": [...], \"answer\": \"...\", \"explanation\": \"...\"}]}"
)


class QuizGenerateSkill(SkillExecutor[QuizGenerateRequest, QuizGenerateResponse]):
    slug = "quiz_generate"

    async def execute(self, input_data: QuizGenerateRequest) -> QuizGenerateResponse:
        source = input_data.source
        count = input_data.count
        difficulty = input_data.difficulty or "medium"
        q_types = input_data.question_types or ["multiple_choice"]

        types_str = ", ".join(q_types) if q_types else "multiple choice"
        prompt = (
            f"Generate exactly {count} quiz questions at {difficulty} difficulty from the material below.\n"
            f"Question types: {types_str}.\n"
            f"For multiple_choice: include 4 options (A-D) with 'options' field.\n"
            f"Output only JSON with no markdown.\n\n"
            f"Material:\n{source[:6000]}\n\n"
            f"Output JSON:"
        )

        try:
            result = await _call_ai(prompt, SYSTEM_PROMPT)
            questions = _parse_questions(result, count)
            summary = _summarize_source(source)
            return QuizGenerateResponse(
                questions=questions,
                count=len(questions),
                source_summary=summary,
                difficulty=difficulty,
            )
        except Exception as exc:
            log.error("quiz_generate.failed", error=str(exc))
            return QuizGenerateResponse(
                questions=[],
                count=0,
                source_summary=_summarize_source(source),
                difficulty=difficulty,
            )


def _summarize_source(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:120] + ("..." if len(clean) > 120 else "")


def _parse_questions(raw: str, max_count: int) -> list[QuizQuestion]:
    try:
        m = re.search(r"\{[\s\S]*\"questions\"\s*:\s*\[[\s\S]*\]", raw)
        if not m:
            m = re.search(r"\[[\s\S]*\]", raw)
        if m:
            data = json.loads(m.group(0))
            questions_raw = data if isinstance(data, list) else data.get("questions", [])
            return [
                QuizQuestion(
                    type=q.get("type", "multiple_choice"),
                    question=q.get("question", ""),
                    options=q.get("options"),
                    answer=q.get("answer", ""),
                    explanation=q.get("explanation"),
                )
                for q in questions_raw[:max_count]
                if q.get("question") and q.get("answer")
            ]
    except Exception:
        pass
    return []


async def _call_ai(prompt: str, system: str) -> str:
    from app.ai_gateway.services.router import AIRouter
    from app.ai_gateway.models.schemas import AIRequest
    from uuid import uuid4

    router = AIRouter()
    req = AIRequest(
        request_id=uuid4(),
        prompt=prompt,
        system=system,
        provider=None,
        model=None,
        task_type="quiz_generation",
        stream=False,
        temperature=0.7,
        max_tokens=2048,
    )
    response = await router.route(req)
    return response.content if hasattr(response, "content") else str(response)


def get_executor() -> QuizGenerateSkill:
    return QuizGenerateSkill()
