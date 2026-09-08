"""task_breakdown skill — LLM-based task decomposition.

Per PR 3 plan: delegates to the AI gateway with a structured
planning prompt that returns a JSON plan.
"""

from __future__ import annotations

import json

import structlog

from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_TASK_BREAKDOWN_SYSTEM_PROMPT = """You are an expert planner. Given a user goal, you break it into an ordered list of subtasks.

You must output ONLY valid JSON (no markdown, no explanation outside the JSON):
{
  "plan": [
    {
      "step": 1,
      "name": "short descriptive name",
      "owner": "agent-slug",
      "goal": "what success looks like",
      "depends_on": [],
      "decision_point": false
    }
  ],
  "decision_points": [],
  "risks": ["risk 1", "risk 2"],
  "estimated_total": "human-readable estimate"
}

Agent slugs to choose from: research, files, coding, planner, automation, study, voice, browser, security-privacy, coordinator.
- research: web searches, fact-checking, literature review
- files: RAG over uploaded documents
- coding: code generation, debugging, refactoring
- planner: decomposing goals, planning
- automation: scheduling recurring jobs
- study: flashcards, quizzes, summarization
- voice: voice sessions
- browser: web navigation, form filling
- security-privacy: reviewing sensitive actions
- coordinator: general questions, routing

Rules:
- `depends_on` is a list of prior step numbers this step waits for
- `decision_point: true` marks a step where the user must choose before proceeding
- Steps that can run in parallel should have no depends_on overlap
- Cap the plan at the horizon limit
- If the goal is too vague to plan, output {"error": "goal is too vague - please clarify: <question>"}

Output ONLY the JSON object. No markdown fences, no text before or after."""


async def task_breakdown(
    goal: str,
    context: str | None = None,
    horizon: str = "normal",
    *,
    user_id: str,
    _gateway=None,
) -> SkillResult:
    """Break a user goal into an ordered subtask plan.

    Args:
        goal: what the user wants to achieve
        context: constraints, prior state, relevant history
        horizon: "quick" (≤3 steps), "normal" (≤10), "phased" (multi-session)
        user_id: for audit logging
        _gateway: GatewayClient injected by the skill executor

    Returns:
        SkillResult with 'plan' (list), 'decision_points' (list), 'risks' (list),
        'estimated_total' (str)
    """
    log.info(
        "task_breakdown.invoked",
        user_id=user_id,
        goal=goal[:80],
        horizon=horizon,
    )

    from runtime.infrastructure.gateway_client import GatewayClient
    gateway = _gateway or GatewayClient()

    horizon_limit = {"quick": 3, "normal": 10, "phased": 30}.get(horizon, 10)

    context_block = f"\n\nContext:\n{context}" if context else ""
    user_message = f"""Break this goal into a plan (max {horizon_limit} steps):

Goal: {goal}{context_block}

Horizon: {horizon}

Output the plan as JSON now."""

    try:
        reply = await gateway.chat(
            system_prompt=_TASK_BREAKDOWN_SYSTEM_PROMPT,
            user_message=user_message,
        )
        # Try to parse the response as JSON
        try:
            data = json.loads(reply.response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r"\{[\s\S]*\}", reply.response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                return SkillResult(
                    ok=False,
                    data=None,
                    error="task_breakdown failed to parse the LLM response as JSON. "
                    "This is a stub — a real implementation would handle this better.",
                )

        if "error" in data:
            return SkillResult(ok=False, data=data, error=data["error"])

        return SkillResult(ok=True, data=data)
    except Exception as exc:  # noqa: BLE001
        log.error("task_breakdown.failed", user_id=user_id, error=str(exc))
        return SkillResult(ok=False, data=None, error=f"Task breakdown failed: {exc}")
