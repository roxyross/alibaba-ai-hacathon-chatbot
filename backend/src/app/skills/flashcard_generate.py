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
    import json
    cleaned = raw.strip()
    # Strip markdown code fences if present
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()

    try:
        data = json.loads(cleaned)
        cards_raw = data if isinstance(data, list) else data.get("cards", [])
        cards = [
            Flashcard(
                front=str(c.get("front", "")).strip(),
                back=str(c.get("back", "")).strip(),
                tags=c.get("tags", []) if isinstance(c.get("tags"), list) else [],
            )
            for c in cards_raw[:max_count]
            if c.get("front") and c.get("back")
        ]
        if cards:
            return cards
    except Exception:
        pass

    try:
        m = re.search(r"\{[\s\S]*\"cards\"\s*:\s*\[[\s\S]*?\]\s*\}", cleaned)
        if m:
            data = json.loads(m.group(0))
            cards_raw = data.get("cards", [])
            cards = [
                Flashcard(
                    front=str(c.get("front", "")).strip(),
                    back=str(c.get("back", "")).strip(),
                    tags=c.get("tags", []) if isinstance(c.get("tags"), list) else [],
                )
                for c in cards_raw[:max_count]
                if c.get("front") and c.get("back")
            ]
            if cards:
                return cards
    except Exception:
        pass

    # Fallback: Q&A line regex matching
    cards = []
    qa_blocks = re.findall(
        r"(?:(?:Question|Front|Q):\s*(.+?))\s*(?:(?:Answer|Back|A):\s*(.+?))(?=(?:Question|Front|Q):|$)",
        cleaned,
        re.IGNORECASE | re.DOTALL,
    )
    for q, a in qa_blocks:
        if q.strip() and a.strip():
            cards.append(Flashcard(front=q.strip(), back=a.strip(), tags=["study"]))
            if len(cards) >= max_count:
                break
    return cards


async def _call_ai(prompt: str, system: str) -> str:
    """Call the AI gateway for text generation."""
    from app.ai_gateway.services.router import AIRouter
    from app.ai_gateway.models.schemas import AIRequest, Message, MessageRole, TaskType
    from uuid import uuid4

    router = AIRouter()
    req = AIRequest(
        request_id=uuid4(),
        messages=[
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=prompt),
        ],
        provider=None,
        model=None,
        task_type=TaskType.GENERAL,
        stream=False,
        temperature=0.7,
        max_tokens=2048,
    )
    response = await router.route(req)
    return response.content if hasattr(response, "content") else str(response)


def get_executor() -> FlashcardGenerateSkill:
    return FlashcardGenerateSkill()
