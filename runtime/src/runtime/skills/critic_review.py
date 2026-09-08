"""critic_review skill — structured critical analysis of text, code, plans, or decisions.

Uses the AI gateway to generate a structured critique. The skill delegates to
the gateway with a criteria-driven evaluation prompt that outputs a JSON object
containing the overall verdict, strengths, weaknesses, minor issues, missing
perspectives, and summary.

Supports content types: text, code, plan, decision, research.
Supports depth levels: quick, standard, deep.
"""

from __future__ import annotations

import json
import re
import structlog

from runtime.infrastructure.gateway_client import GatewayClient
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_CONTENT_TYPES = {"text", "code", "plan", "decision", "research"}
_DEPTH_LEVELS = {"quick", "standard", "deep"}
_DEFAULT_CRITERIA = ["logic", "evidence", "clarity", "completeness"]

_CRITERIA_DESCRIPTIONS = {
    "logic": "Are the arguments internally consistent? Are there logical fallacies?",
    "evidence": "Are claims supported by credible evidence? Are sources cited?",
    "clarity": "Is the writing clear and unambiguous? Can a reader act on this without confusion?",
    "completeness": "Are key aspects of the topic addressed? Are counterarguments considered?",
    "feasibility": "Can this plan be executed given available resources and constraints?",
    "risk": "Are risks identified, quantified, and mitigated?",
    "correctness": "Is the code correct, free of bugs, and does it handle edge cases?",
    "readability": "Is the code readable, well-documented, and following conventions?",
}

_CRITERIA_FOR_TYPE: dict[str, list[str]] = {
    "text": ["logic", "evidence", "clarity", "completeness"],
    "code": ["correctness", "readability", "logic"],
    "plan": ["feasibility", "risk", "logic", "completeness"],
    "decision": ["logic", "evidence", "risk", "completeness"],
    "research": ["evidence", "logic", "clarity", "completeness"],
}

_SYSTEM_PROMPT = """You are a rigorous critical evaluator. Given a piece of content and evaluation criteria, you produce a structured critical review in JSON format.

Output ONLY valid JSON matching this schema:
{
  "verdict": "strong | adequate | weak | flawed",
  "overall": "one-sentence assessment of the content",
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": [
    {
      "name": "name of weakness",
      "evidence": "specific quote, line, or data point demonstrating the weakness",
      "why_it_matters": "consequence of this weakness",
      "suggested_fix": "how to address it (or null)"
    }
  ],
  "minor_issues": ["minor issue 1", "minor issue 2"],
  "missing_perspectives": ["perspective 1", "perspective 2"],
  "summary": "2-3 sentence actionable takeaway"
}

Rules:
- Be direct. Do not soften critique with excessive hedging.
- Distinguish fatal flaws from polish issues. Fatal flaws mean the thing fails its goal.
- Do not fabricate weaknesses that are not present.
- Verdict: strong (no fatal flaws, many strengths), adequate (some weaknesses but no fatal flaws), weak (fatal flaws or many weaknesses), flawed (does not achieve its stated goal).
- For depth=quick: return max 3 weaknesses, omit minor_issues and missing_perspectives.
- For depth=deep: add second_order_effects and alternatives_considered fields.
"""

_QUICK_SYSTEM_PROMPT = """You are a critical evaluator. Provide a quick structured critique in JSON:

{
  "verdict": "strong | adequate | weak | flawed",
  "overall": "one-sentence assessment",
  "strengths": ["s1", "s2", "s3"],
  "weaknesses": [
    {"name": "weakness name", "evidence": "specific evidence", "why_it_matters": "consequence", "suggested_fix": "fix (or null)"}
  ],
  "summary": "2-3 sentence takeaway"
}

Be direct. Output ONLY JSON."""


def _build_user_message(
    content: str,
    content_type: str,
    depth: str,
    criteria: list[str] | None,
) -> str:
    type_criteria = _CRITERIA_FOR_TYPE.get(content_type, _DEFAULT_CRITERIA)
    criteria_list = criteria if criteria else type_criteria
    criteria_str = "\n".join(
        f"  - {c}: {_CRITERIA_DESCRIPTIONS.get(c, c)}"
        for c in criteria_list
    )
    depth_note = ""
    if depth == "quick":
        depth_note = "Give a quick critique: max 3 weaknesses, skip minor_issues and missing_perspectives."
    elif depth == "deep":
        depth_note = "For deep review: also include second_order_effects and alternatives_considered fields."

    return f"""Critique this {content_type}:

--- CONTENT START ---
{content[:8000]}
--- CONTENT END ---

Content type: {content_type}
Critique depth: {depth}
Evaluation criteria:
{criteria_str}

{depth_note}

Output JSON now."""


async def critic_review(
    content: str,
    type: str = "text",
    depth: str = "standard",
    criteria: list[str] | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Provide a structured critical review of text, code, plans, or decisions.

    Args:
        content: The text, code, plan, or decision description to review.
        type: Content type — "text" | "code" | "plan" | "decision" | "research".
        depth: Critique depth — "quick" | "standard" | "deep".
        criteria: Optional list of evaluation criteria to prioritize.
                 Defaults to type-specific criteria.
        user_id: For audit logging.

    Returns:
        SkillResult with the structured critique JSON.
    """
    log.info(
        "critic_review.invoked",
        user_id=user_id,
        type=type,
        depth=depth,
        content_len=len(content),
    )

    if not content or not content.strip():
        return SkillResult(ok=False, data=None, error="content cannot be empty")

    if type not in _CONTENT_TYPES:
        return SkillResult(
            ok=False, data=None,
            error=f"Invalid type '{type}'. Must be one of: {', '.join(sorted(_CONTENT_TYPES))}"
        )

    if depth not in _DEPTH_LEVELS:
        return SkillResult(
            ok=False, data=None,
            error=f"Invalid depth '{depth}'. Must be one of: quick, standard, deep"
        )

    if criteria:
        invalid = [c for c in criteria if c not in _CRITERIA_DESCRIPTIONS]
        if invalid:
            return SkillResult(
                ok=False, data=None,
                error=f"Unknown criteria: {invalid}. Valid: {list(_CRITERIA_DESCRIPTIONS.keys())}"
            )

    system_prompt = _QUICK_SYSTEM_PROMPT if depth == "quick" else _SYSTEM_PROMPT
    user_message = _build_user_message(content, type, depth, criteria)

    gateway = GatewayClient()

    try:
        reply = await gateway.chat(
            system_prompt=system_prompt,
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
                    ok=False, data=None,
                    error="critic_review failed to parse LLM response as JSON. Try providing shorter or clearer content.",
                )

        # Validate verdict
        valid_verdicts = {"strong", "adequate", "weak", "flawed"}
        verdict = data.get("verdict", "adequate")
        if verdict not in valid_verdicts:
            data["verdict"] = "adequate"

        log.info(
            "critic_review.done",
            user_id=user_id,
            verdict=data.get("verdict"),
            weakness_count=len(data.get("weaknesses", [])),
        )

        return SkillResult(
            ok=True,
            data={
                "verdict": data["verdict"],
                "overall": data.get("overall", ""),
                "strengths": data.get("strengths", []),
                "weaknesses": data.get("weaknesses", []),
                "minor_issues": data.get("minor_issues", []) if depth != "quick" else [],
                "missing_perspectives": data.get("missing_perspectives", []) if depth != "quick" else [],
                "second_order_effects": data.get("second_order_effects", []) if depth == "deep" else [],
                "alternatives_considered": data.get("alternatives_considered", []) if depth == "deep" else [],
                "summary": data.get("summary", ""),
                "type": type,
                "depth": depth,
                "criteria_evaluated": criteria or _CRITERIA_FOR_TYPE.get(type, _DEFAULT_CRITERIA),
            },
        )

    except Exception as exc:  # noqa: BLE001
        log.error("critic_review.error", user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(
            ok=False, data=None,
            error=f"Critique generation failed: {exc}"
        )
