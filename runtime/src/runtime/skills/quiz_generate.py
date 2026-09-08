"""quiz_generate skill — LLM-driven quiz generation.

Per the PR 3 plan: real implementation uses the AI gateway to generate
self-test quizzes from source material. Supports MCQ, short-answer, and fill-in-the-blank.
"""

from __future__ import annotations

import json
import re
import structlog
import uuid

from runtime.infrastructure.gateway_client import GatewayClient
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_QUIZ_SYSTEM = """You are an expert educator. Generate a self-test quiz from the provided source material.

Output ONLY valid JSON (no markdown, no explanation):
{
  "questions": [
    {
      "id": "q1",
      "type": "mcq",
      "prompt": "question text, specific and unambiguous",
      "choices": ["correct answer", "distractor A", "distractor B", "distractor C"],
      "answer": 0,
      "source_ref": "brief citation"
    },
    {
      "id": "q2",
      "type": "short_answer",
      "prompt": "short answer question",
      "answer": "expected answer",
      "source_ref": "brief citation"
    },
    {
      "id": "q3",
      "type": "fill_blank",
      "prompt": "The key concept of X is called _____.",
      "answer": "expected term",
      "source_ref": "brief citation"
    }
  ],
  "answer_key": {"q1": 0, "q2": "expected answer", "q3": "expected term"}
}

Quality rules:
- One question tests one concept
- MCQ: exactly 4 choices, exactly 1 correct answer, distractors are plausible
- Short answer: answer is a short phrase or number, not a long sentence
- Fill in the blank: exactly one blank, answer is a single term or short phrase
- Questions are grounded in the provided source material
- Drop any question where you are uncertain
- Max 10 questions total unless the source is very rich
- Mix question types: some MCQ, some short answer, some fill-in-blank
"""


async def quiz_generate(
    source: str,
    count: int = 10,
    types: list[str] | None = None,
    difficulty: str = "medium",
    *,
    user_id: str,
) -> SkillResult:
    """Generate a self-test quiz from source material using the AI gateway.

    Args:
        source: The source material text to generate quiz from.
        count: Desired number of questions (default 10, max 15).
        types: List of question types to include: "mcq", "short_answer", "fill_blank".
               Defaults to all three types.
        difficulty: "easy" | "medium" | "hard".
        user_id: for audit logging.

    Returns:
        SkillResult with the generated quiz.
    """
    log.info(
        "quiz_generate.invoked",
        user_id=user_id,
        source_len=len(source),
        count=count,
        difficulty=difficulty,
        types=types,
    )

    if not source or not source.strip():
        return SkillResult(ok=False, data=None, error="source material cannot be empty")

    quiz_id = str(uuid.uuid4())
    max_questions = min(max(5, count), 15)
    question_types = types or ["mcq", "short_answer", "fill_blank"]

    # Limit to supported types
    supported = {"mcq", "short_answer", "fill_blank"}
    question_types = [t for t in question_types if t in supported]
    if not question_types:
        question_types = ["mcq"]

    user_message = f"""Generate a quiz from this source material.

Difficulty: {difficulty}
Max questions: {max_questions}
Include question types: {", ".join(question_types)}

Source material:
{source[:3000]}

Output JSON now."""

    gateway = GatewayClient()

    try:
        reply = await gateway.chat(
            system_prompt=_QUIZ_SYSTEM,
            user_message=user_message,
        )

        try:
            data = json.loads(reply.response)
        except json.JSONDecodeError:
            json_match = re.search(r"\{[\s\S]*\}", reply.response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                return SkillResult(
                    ok=False,
                    data=None,
                    error="quiz_generate failed to parse LLM response as JSON.",
                )

        questions = data.get("questions", [])
        answer_key = data.get("answer_key", {})

        # Validate and normalize questions
        valid_questions = []
        for q in questions[:max_questions]:
            qtype = q.get("type")
            if qtype not in supported:
                continue
            if not q.get("prompt"):
                continue
            prompt = q["prompt"].strip()
            valid_q = {
                "id": q.get("id", f"q{len(valid_questions)+1}"),
                "type": qtype,
                "prompt": prompt,
                "source_ref": q.get("source_ref", ""),
            }
            if qtype == "mcq":
                choices = q.get("choices", [])
                if len(choices) < 2:
                    continue
                valid_q["choices"] = [str(c) for c in choices]
                valid_q["answer"] = q.get("answer", 0)
            else:
                valid_q["answer"] = q.get("answer", "")
            valid_questions.append(valid_q)

        log.info(
            "quiz_generate.done",
            user_id=user_id,
            quiz_id=quiz_id,
            questions=len(valid_questions),
        )

        return SkillResult(
            ok=True,
            data={
                "quiz_id": quiz_id,
                "questions": valid_questions,
                "answer_key": answer_key,
                "difficulty": difficulty,
            },
        )

    except Exception as exc:  # noqa: BLE001
        log.error("quiz_generate.error", user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(
            ok=False,
            data=None,
            error=f"Quiz generation failed: {exc}",
        )
