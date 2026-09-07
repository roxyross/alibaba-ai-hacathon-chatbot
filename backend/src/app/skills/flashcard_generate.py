"""flashcard_generate skill — generate flashcards from source material.

Uses the AI gateway to extract key facts and create Q&A cards.
"""

from __future__ import annotations

import re
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    Flashcard,
    FlashcardGenerateRequest,
    FlashcardGenerateResponse,
)


log = structlog.get_logger()

# System prompt for flashcard generation
SYSTEM_PROMPT = (
    "You are a flashcard generation assistant. Given source material, generate clear, "
    "accurate flashcards. Each card has a front (question/term) and back (answer/definition). "
    "Follow these rules:\n"
    "1. One concept per card\n"
    "2. Specific, unambiguous answers\n"
    "3. Don't give away the answer in the question\n"
    "4. Use the difficulty level to set vocabulary and depth\n"
    "Output ONLY valid JSON: {\"cards\": [{\"front\": \"...\", \"back\": \"...\", \"tags\": [\"...\"]}]}"
)


class FlashcardGenerateSkill(SkillExecutor[FlashcardGenerateRequest, FlashcardGenerateResponse]):
    slug = "flashcard_generate"

    async def execute(self, input_data: FlashcardGenerateRequest) -> FlashcardGenerateResponse:
        source = input_data.source
        count = input_data.count
        level = input_data.level or "intermediate"
        fmt = input_data.format or "basic"

        prompt = (
            f"Generate exactly {count} flashcards at {level} level from the following material.\n"
            f"Format: {fmt}.\n"
            f"Output only JSON with no markdown.\n\n"
            f"Material:\n{source[:6000]}\n\n"
            f"Output JSON:"
        )

        try:
            result = await _call_ai(prompt, SYSTEM_PROMPT)
            cards = _parse_cards(result, count)
            summary = _summarize_source(source)
            return FlashcardGenerateResponse(
                cards=cards,
                count=len(cards),
                source_summary=summary,
                level=level,
            )
        except Exception as exc:
            log.error("flashcard_generate.failed", error=str(exc))
            return FlashcardGenerateResponse(
                cards=[],
                count=0,
                source_summary=_summarize_source(source),
                level=level,
            )


def _summarize_source(text: str) -> str:
    """One-line summary of source material."""
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:120] + ("..." if len(clean) > 120 else "")


def _parse_cards(raw: str, max_count: int) -> list[Flashcard]:
    """Parse JSON cards from AI response."""
    try:
        # Try to extract JSON block
        m = re.search(r"\{[\s\S]*\"cards\"\s*:\s*\[[\s\S]*\]", raw)
        if not m:
            # Try plain array
            m = re.search(r"\[[\s\S]*\]", raw)
        if m:
            import json
            data = json.loads(m.group(0))
            cards_raw = data if isinstance(data, list) else data.get("cards", [])
            return [
                Flashcard(
                    front=c.get("front", ""),
                    back=c.get("back", ""),
                    tags=c.get("tags", []),
                )
                for c in cards_raw[:max_count]
                if c.get("front") and c.get("back")
            ]
    except Exception:
        pass
    return []


async def _call_ai(prompt: str, system: str) -> str:
    """Call the AI gateway for text generation."""
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
        task_type="flashcard_generation",
        stream=False,
        temperature=0.7,
        max_tokens=2048,
    )
    response = await router.route(req)
    return response.content if hasattr(response, "content") else str(response)


def get_executor() -> FlashcardGenerateSkill:
    return FlashcardGenerateSkill()
