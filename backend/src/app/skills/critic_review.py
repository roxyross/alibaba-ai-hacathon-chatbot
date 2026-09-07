"""critic_review skill — structured critical review of text, code, plans, or decisions.

Uses the AI gateway (Gemini primary → Grok fallback) to generate a structured
critique with verdict, strengths, weaknesses, and actionable takeaways.

Depth levels:
  quick  — top 3 strengths / 3 key weaknesses, brief summary
  standard — full structured critique
  deep  — standard + missing perspectives, second-order effects, benchmarking
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
import structlog

from app.ai_gateway.models.schemas import AIRequest, AIResponse, Message, MessageRole
from app.ai_gateway.services.router import AIRouter
from app.skills.base import SkillExecutor
from app.skills.schemas import (
    CriticReviewRequest,
    CriticReviewResponse,
    CriticWeakness,
)

log = structlog.get_logger()

# Fallback base URL for the AI gateway when called from within the backend
_GATEWAY_BASE = os.getenv("AI_GATEWAY_BASE", "http://localhost:8000")


class CriticReviewSkill(SkillExecutor[CriticReviewRequest, CriticReviewResponse]):
    slug = "critic_review"

    def __init__(self) -> None:
        self._router = AIRouter()

    async def execute(self, input_data: CriticReviewRequest) -> CriticReviewResponse:
        content_type = input_data.type.lower()
        depth = input_data.depth.lower()
        criteria = input_data.criteria or ["logic", "evidence", "clarity", "completeness"]

        system_prompt = _build_system_prompt(content_type, depth, criteria)
        user_prompt = _build_user_prompt(input_data.content, content_type, depth)

        try:
            response = await self._call_ai(system_prompt, user_prompt)
            parsed = _parse_critique(response, depth)
            return CriticReviewResponse(
                verdict=parsed.get("verdict", "adequate"),
                overall=parsed.get("overall", ""),
                strengths=parsed.get("strengths", []),
                weaknesses=[CriticWeakness(**w) for w in parsed.get("weaknesses", [])],
                minor_issues=parsed.get("minor_issues", []),
                missing_perspectives=parsed.get("missing_perspectives", []),
                summary=parsed.get("summary", ""),
                depth=depth,
                criteria_evaluated=criteria,
            )
        except Exception as exc:
            log.error("critic_review.failed", error=str(exc))
            return CriticReviewResponse(
                verdict="weak",
                overall="Critique generation failed — see error details.",
                strengths=[],
                weaknesses=[],
                minor_issues=[],
                missing_perspectives=[],
                summary=f"Failed to generate critique: {exc}",
                depth=depth,
                criteria_evaluated=criteria,
            )

    async def _call_ai(self, system: str, user: str) -> str:
        """Call the AI gateway for a structured JSON critique."""
        # Try internal router first (same-process, faster)
        try:
            request = AIRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=system),
                    Message(role=MessageRole.USER, content=user),
                ],
                temperature=0.4,
                max_tokens=2048,
                stream=False,
            )
            response: AIResponse = await self._router.route(request)
            return getattr(response, "content", None) or (response.choices[0].message.content if hasattr(response, "choices") else str(response))
        except Exception as exc:
            log.warning("critic_review.internal_gateway_fallback", error=str(exc))

        # Fallback: HTTP call to the gateway endpoint
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_GATEWAY_BASE}/api/v1/ai/chat",
                json={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 2048,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content") or data.get("response") or (data.get("choices", [{}])[0].get("message", {}).get("content", ""))


def _build_system_prompt(content_type: str, depth: str, criteria: list[str]) -> str:
    criteria_str = ", ".join(criteria)
    depth_instruction = {
        "quick": "Give top 3 strengths and 3 key weaknesses. Keep the summary to 1-2 sentences.",
        "standard": "Provide a full structured critique with all sections.",
        "deep": (
            "Provide a full structured critique. Additionally include missing perspectives, "
            "second-order effects, and benchmarking against known alternatives."
        ),
    }.get(depth, "Provide a standard structured critique.")

    return f"""You are a rigorous, impartial critic reviewing {content_type}.
Evaluate the content against these criteria: {criteria_str}.
{depth_instruction}

Respond ONLY with valid JSON matching this exact schema:
{{
  "verdict": "strong | adequate | weak | flawed",
  "overall": "one-sentence assessment",
  "strengths": ["strength 1", "strength 2", ...],
  "weaknesses": [
    {{"name": "weakness name", "evidence": "quote or data point", "why_it_matters": "consequence", "suggested_fix": "how to fix or null"}}
  ],
  "minor_issues": ["issue 1", "issue 2", ...],
  "missing_perspectives": ["perspective 1", "perspective 2", ...],
  "summary": "2-3 sentence actionable takeaway"
}}

Be specific and cite evidence from the content. Do not invent facts."""


def _build_user_prompt(content: str, content_type: str, depth: str) -> str:
    return f"Review the following {content_type} content:\n\n{content}"


def _parse_critique(raw: str, depth: str) -> dict[str, Any]:
    """Extract JSON from the model response, handling markdown code fences."""
    # Strip markdown code fences
    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first JSON object
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        log.warning("critic_review.parse_failed", raw=raw[:200])
        return {
            "verdict": "weak",
            "overall": raw[:200] if raw else "Could not parse critique.",
            "strengths": [],
            "weaknesses": [],
            "minor_issues": ["Failed to parse structured critique from model response."],
            "missing_perspectives": [],
            "summary": raw[:200] if raw else "No response.",
        }


def get_executor() -> CriticReviewSkill:
    return CriticReviewSkill()
