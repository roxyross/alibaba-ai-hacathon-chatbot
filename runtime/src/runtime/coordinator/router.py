"""Coordinator router.

Takes a user query + classification verdict, hands off to the right
specialist's executor, and returns a typed result. Handles
uncertain-classification re-prompts (spec §3.1), per-specialist
timeouts (spec §3.2), and specialist crashes (spec §10.2).

The router does NOT execute skills itself; that is the executor's
job. The router is the seam between classification and execution.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from runtime.agents.executor import AgentExecutionResult, AgentExecutor
from runtime.agents.registry import AgentRegistry
from runtime.config import settings
from runtime.coordinator.classifier import Classification, Classifier
from runtime.coordinator.timeout import SpecialistTimeout, with_specialist_budget

if TYPE_CHECKING:
    from runtime.agents.security_gate import SecurityGate, SecurityGateResult

log = structlog.get_logger()


@dataclass(frozen=True)
class CoordinatorResult:
    """The Coordinator's reply to the user-facing API layer."""

    # True if classification was uncertain. The API layer surfaces a
    # clarification prompt; the user is not routed to a specialist.
    needs_clarification: bool

    # The agent that handled the request, when `needs_clarification` is False.
    agent_slug: str | None

    # The agent's reply text.
    response: str | None

    # Citations the agent returned (e.g. URLs for research).
    citations: list[str]

    # If the agent's response was timeout, crash, sensitive_confirmation, or normal.
    status: str  # "ok" | "timeout" | "error" | "agent_disabled" | "uncertain" | "sensitive_confirmation"

    # Suggested follow-up actions (e.g. "try a different specialist").
    next_actions: list[str]

    # Set when status == "sensitive_confirmation" — the skill that needs confirmation.
    pending_sensitive_skill: str | None = None
    # Inputs for the pending sensitive skill.
    pending_sensitive_inputs: dict[str, Any] | None = None


class Coordinator:
    def __init__(
        self,
        registry: AgentRegistry,
        classifier: Classifier,
        executor: AgentExecutor,
        security_gate: "SecurityGate | None" = None,
    ) -> None:
        self._registry = registry
        self._classifier = classifier
        self._executor = executor
        self._security_gate = security_gate

    def set_security_gate(self, gate: "SecurityGate") -> None:
        """Inject the SecurityGate after construction (called by main.py)."""
        self._security_gate = gate

    async def handle(
        self,
        query: str,
        *,
        user_id: str,
        session_id: str | None = None,
        bearer_token: str | None = None,
    ) -> CoordinatorResult:
        from runtime.infrastructure.gateway_client import current_bearer_token
        if bearer_token:
            current_bearer_token.set(bearer_token)

        # ---- 1. Classify ---------------------------------------------------
        verdict = self._classifier.classify(query)
        log.info(
            "coordinator.classified",
            user_id=user_id,
            top_score=round(verdict.top_score, 3),
            second_score=round(verdict.second_score, 3),
            agent=verdict.agent_slug,
            uncertain=verdict.uncertain,
            tied=verdict.tied,
        )

        stripped = query.strip()
        if not stripped:
            return CoordinatorResult(
                needs_clarification=True,
                agent_slug="coordinator",
                response="Please enter a message or question so I can assist you.",
                citations=[],
                status="uncertain",
                next_actions=[
                    "Write some code",
                    "Research a topic",
                    "Check my finances",
                    "Schedule a reminder",
                ],
            )

        # Check if query is conversational or a greeting
        GREETING_WORDS = {
            "hello", "hi", "hey", "salam", "assalam", "assalamu", "alaikum",
            "namaste", "hola", "bonjour", "marhaba", "greetings", "howdy",
            "morning", "afternoon", "evening", "kese", "kaise", "kaisa", "hal",
            "sup", "yo", "good", "thanks", "thank", "shukriya", "dhanyawad",
            "help", "madad", "batao", "sunao",
        }
        query_words = set(re.findall(r"\w+", query.lower(), re.UNICODE))
        is_greeting_or_chat = bool(query_words & GREETING_WORDS) or (0 < len(query_words) <= 3) or any(ord(c) > 127 for c in query)

        agent = None
        if verdict.uncertain:
            # If the user is saying hello, greeting, speaking non-English, or having a natural conversation,
            # route to the research agent so the LLM responds conversationally and in the user's language!
            if is_greeting_or_chat or stripped:
                research_agent = self._registry.get("research")
                if research_agent is not None:
                    agent = research_agent
                    log.info("coordinator.routed_to_research", reason="conversational", query=query[:60])

            if agent is None:
                # Re-prompt when intent isn't clear and not conversational
                clarification_msg = (
                    "Hi! I'm ROXY, your personal AI assistant. "
                    "How can I help you today? You can ask me to:\n\n"
                    "- Write, explain, or debug **code**\n"
                    "- **Research** a topic or search the web\n"
                    "- Check your **finances** or bank transactions\n"
                    "- **Schedule** reminders or recurring tasks\n"
                    "- Study, generate quizzes, or ask about your documents"
                )
                return CoordinatorResult(
                    needs_clarification=True,
                    agent_slug="coordinator",
                    response=clarification_msg,
                    citations=[],
                    status="uncertain",
                    next_actions=[
                        "Write some code",
                        "Research a topic",
                        "Check my finances",
                        "Schedule a reminder",
                    ],
                )
        else:
            agent = self._registry.get(verdict.agent_slug) if verdict.agent_slug else None
        if agent is None:
            log.error(
                "coordinator.classifier.invalid_slug",
                slug=verdict.agent_slug,
            )
            return CoordinatorResult(
                needs_clarification=True,
                agent_slug="coordinator",
                response="I couldn't find the right specialist agent for this request. Could you rephrase your question?",
                citations=[],
                status="uncertain",
                next_actions=[
                    "Could you rephrase your question?",
                ],
            )

        # ---- 2. Execute with timeout (spec §3.2) -------------------------
        start = time.monotonic()
        try:
            result: AgentExecutionResult = await with_specialist_budget(
                self._executor.execute(
                    agent,
                    query,
                    user_id=user_id,
                    session_id=session_id,
                    bearer_token=bearer_token,
                ),
                agent_slug=agent.slug,
                budget_seconds=float(settings.specialist_timeout_seconds),
            )
        except SpecialistTimeout as exc:
            elapsed = time.monotonic() - start
            log.warning(
                "coordinator.specialist.timeout",
                agent=agent.slug,
                user_id=user_id,
                elapsed_seconds=round(elapsed, 2),
                budget_seconds=exc.budget,
            )
            return CoordinatorResult(
                needs_clarification=False,
                agent_slug=agent.slug,
                response=(
                    f"The {agent.slug} agent is taking too long. "
                    "Would you like to try again, route to a different agent, "
                    "or have me handle it directly?"
                ),
                citations=[],
                status="timeout",
                next_actions=[
                    "Try again",
                    f"Route to a different agent (e.g. {self._suggest_alternative(agent.slug)})",
                    "Let the Coordinator handle it",
                ],
            )
        except Exception as exc:  # noqa: BLE001 — per spec §10.2, catch all and surface a clean error
            elapsed = time.monotonic() - start
            log.error(
                "coordinator.specialist.crashed",
                agent=agent.slug,
                user_id=user_id,
                elapsed_seconds=round(elapsed, 2),
                error=str(exc),
                exc_info=True,
            )
            return CoordinatorResult(
                needs_clarification=False,
                agent_slug=agent.slug,
                response=(
                    f"The {agent.slug} agent ran into an error. "
                    "Would you like to try again, or route this to a different agent?"
                ),
                citations=[],
                status="error",
                next_actions=[
                    "Try again",
                    f"Route to a different agent (e.g. {self._suggest_alternative(agent.slug)})",
                ],
            )

        elapsed = time.monotonic() - start
        log.info(
            "coordinator.specialist.ok",
            agent=agent.slug,
            user_id=user_id,
            elapsed_seconds=round(elapsed, 2),
        )

        # ---- Sensitive skill gate (spec §3.3) -------------------------------
        if result.needs_sensitive_confirmation:
            skill_slug = result.pending_sensitive_skill or "unknown"
            log.info(
                "coordinator.sensitive_confirmation_required",
                agent=agent.slug,
                skill=skill_slug,
                user_id=user_id,
            )
            # Describe the action in plain language for the confirmation prompt
            inputs = result.pending_sensitive_inputs or {}
            action_description = _sensitive_action_description(skill_slug, inputs)
            return CoordinatorResult(
                needs_clarification=False,
                agent_slug=agent.slug,
                response=(
                    f"⚠️ This action requires your confirmation:\n\n"
                    f"**{action_description}**\n\n"
                    f"Do you want to proceed?"
                ),
                citations=[],
                status="sensitive_confirmation",
                next_actions=[
                    f"Confirm: run {skill_slug}",
                    f"Cancel: skip {skill_slug}",
                ],
                pending_sensitive_skill=skill_slug,
                pending_sensitive_inputs=inputs,
            )

        return CoordinatorResult(
            needs_clarification=False,
            agent_slug=agent.slug,
            response=result.response,
            citations=result.citations,
            status="ok",
            next_actions=result.next_actions,
        )

    def _suggest_alternative(self, current_slug: str) -> str:
        """Pick a different routable agent for the timeout retry."""
        for agent in self._registry.routable():
            if agent.slug != current_slug:
                return agent.slug
        return "another agent"


def _sensitive_action_description(skill_slug: str, inputs: dict[str, Any]) -> str:
    """Return a plain-language description of a sensitive action (spec §3.3)."""
    if skill_slug == "email_send":
        to_addr = inputs.get("to", "unknown")
        subject = inputs.get("subject", "(no subject)")
        return f'Send an email to "{to_addr}" with subject "{subject}"'
    if skill_slug == "browser_fill_form":
        url = inputs.get("url", "unknown URL")
        return f'Fill out and submit a form at "{url}"'
    return f"Run the '{skill_slug}' skill with the provided inputs"


# ---- Security-check endpoint types -------------------------------------------

from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True)
class SecurityCheckRequest:
    skill_slug: str
    inputs: dict[str, Any]
    user_id: str
    bearer_token: str | None = None


async def security_check(
    coord: Coordinator,
    req: SecurityCheckRequest,
) -> dict[str, Any]:
    """Direct security review — calls the security-privacy agent for a proposed action.

    Exposed as POST /api/v1/runtime/security-check.
    Used by agents and for direct security review requests.
    """
    gate = coord._security_gate  # noqa: SLF001 — Coordinator owns the gate
    if gate is None:
        return {
            "verdict": "error",
            "error": "Security gate not configured",
        }

    result = await gate.review(
        skill_slug=req.skill_slug,
        inputs=req.inputs,
        user_id=req.user_id,
        bearer_token=req.bearer_token,
    )
    return {
        "verdict": result.verdict.value,
        "warning": result.warning,
        "recommendation": result.recommendation,
    }
