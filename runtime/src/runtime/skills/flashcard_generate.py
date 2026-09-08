"""flashcard_generate skill — LLM-driven flashcard generation.

Per the PR 3 plan: real implementation uses the AI gateway to generate
quality flashcards from source material. Cards are generated using the
gateway's LLM with a structured JSON-output prompt.

Quality bar (per spec §3.8):
  - One concept per card
  - Specific, unambiguous answer
  - No answer in the question
  - Accurate to source material
"""

from __future__ import annotations

import json
import re
import structlog
import uuid

from runtime.infrastructure.gateway_client import GatewayClient
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_FLASHcard_SYSTEM = """You are an expert educator. Generate flashcards from the provided source material.

Output ONLY valid JSON (no markdown, no explanation):
{
  "cards": [
    {
      "front": "question or term (clear, specific, no answer in question)",
      "back": "answer or definition",
      "source_ref": "brief citation to the source material",
      "tags": ["tag1", "tag2"]
    }
  ],
  "quality_report": {
    "total_generated": N,
    "passed": N,
    "dropped": N,
    "notes": ["why cards were dropped if any"]
  }
}

Quality rules:
- One concept per card
- Question is specific and unambiguous
- Answer does not appear in the question
- Cards are grounded in the provided source material
- Drop any card where you are uncertain about the answer
- Maximum 5 cards unless the source is very rich content
- Tags should be 1-3 words max
"""

async def flashcard_generate(
    source: str,
    count: int = 20,
    level: str = "intermediate",
    format: str = "qa",
    existing_deck_id: str | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Generate flashcards from source material using the AI gateway.

    Args:
        source: The source material text to generate flashcards from.
        count: Desired number of cards (default 20).
        level: "beginner" | "intermediate" | "expert" — affects vocabulary depth.
        format: "qa" (question-answer) or "term-def" (term-definition).
        existing_deck_id: If provided, adds to an existing deck.
        user_id: for audit logging.

    Returns:
        SkillResult with the generated deck of flashcards.
    """
    log.info(
        "flashcard_generate.invoked",
        user_id=user_id,
        source_len=len(source),
        count=count,
        level=level,
        format=format,
    )

    if not source or not source.strip():
        return SkillResult(ok=False, data=None, error="source material cannot be empty")

    deck_id = existing_deck_id or str(uuid.uuid4())
    max_cards = min(max(5, count), 30)

    user_message = f"""Generate {max_cards} flashcards from this source material.

Level: {level}
Format: {format}

Source material:
{source[:3000]}

Output JSON now."""

    gateway = GatewayClient()

    try:
        reply = await gateway.chat(
            system_prompt=_FLASHcard_SYSTEM,
            user_message=user_message,
        )

        # Parse JSON from response
        try:
            data = json.loads(reply.response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            json_match = re.search(r"\{[\s\S]*\}", reply.response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                return SkillResult(
                    ok=False,
                    data=None,
                    error="flashcard_generate failed to parse LLM response as JSON. "
                    "This is a stub — please provide shorter or clearer source material.",
                )

        cards = data.get("cards", [])
        quality_report = data.get("quality_report", {})

        # Validate cards
        valid_cards = []
        for card in cards:
            if not card.get("front") or not card.get("back"):
                continue
            if card["front"] == card["back"]:
                continue
            valid_cards.append({
                "front": card["front"].strip(),
                "back": card["back"].strip(),
                "source_ref": card.get("source_ref", ""),
                "tags": card.get("tags", []),
            })

        log.info(
            "flashcard_generate.done",
            user_id=user_id,
            deck_id=deck_id,
            cards_generated=len(valid_cards),
            passed=quality_report.get("passed", 0),
        )

        return SkillResult(
            ok=True,
            data={
                "deck_id": deck_id,
                "cards": valid_cards,
                "quality_report": quality_report,
            },
        )

    except Exception as exc:  # noqa: BLE001
        log.error("flashcard_generate.error", user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(
            ok=False,
            data=None,
            error=f"Flashcard generation failed: {exc}",
        )
