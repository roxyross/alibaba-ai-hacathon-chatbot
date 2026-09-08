"""Agent executor with skill invocation loop.

Given an agent definition, the user's query, and a user context,
produce the agent's reply. The executor runs a skill loop:

  1. Call the gateway with the agent's system prompt + user message
  2. If the response contains a [SKILL: name]...[/SKILL] block,
     parse the skill name and JSON inputs
  3. Invoke the skill via SkillExecutor
  4. Feed the skill result back to the gateway as a new user message
  5. Repeat until no more skill blocks (max 5 iterations)

Each iteration consumes time from the shared specialist budget (spec §3.2).
The loop is transparent to the Coordinator — it returns a single
AgentExecutionResult when the agent has no more skill calls.

The executor detects sensitive skills (spec §3.3: email_send,
browser_fill_form) and surfaces confirmation requirements in the
result so the Coordinator can present a plain-language confirmation
before the skill is executed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog

from runtime.domain.agent import AgentDef
from runtime.infrastructure.gateway_client import GatewayClient
from runtime.skills.executor import SkillExecutor, SkillResult

log = structlog.get_logger()

# Sensitive skills per spec §3.3 — require explicit user confirmation before execution.
SENSITIVE_SKILLS: frozenset[str] = frozenset({"email_send", "browser_fill_form"})

# Max skill-loop iterations to prevent infinite loops
MAX_SKILL_LOOP_ITERATIONS = 5

# Pattern to match skill invocation blocks in agent responses.
# Format:
#   [SKILL: code_generate]
#   { "task": "...", "language": "python" }
#   [/SKILL]
_SKILL_BLOCK_RE = re.compile(
    r"\[SKILL:\s*(\w+)\s*\]\s*\n(.*?)\n\s*\[/SKILL\]",
    re.DOTALL,
)


@dataclass(frozen=True)
class AgentExecutionResult:
    response: str
    citations: list[str]
    next_actions: list[str]
    # Set when the loop encountered a sensitive skill that needs
    # user confirmation before execution (spec §3.3).
    needs_sensitive_confirmation: bool = False
    pending_sensitive_skill: str | None = None  # slug of the skill awaiting confirmation
    pending_sensitive_inputs: dict | None = None  # inputs for that skill


@dataclass
class AgentExecutor:
    """Runs an agent with a skill-invocation loop."""

    gateway: GatewayClient
    _skill_executor: SkillExecutor | None = field(default=None, repr=False)
    _security_gate: "SecurityGate | None" = field(default=None, repr=False)

    def set_skill_executor(self, skill_executor: SkillExecutor) -> None:
        """Inject the SkillExecutor (called by main.py after construction)."""
        self._skill_executor = skill_executor

    def set_security_gate(self, gate: "SecurityGate") -> None:
        """Inject the SecurityGate (called by main.py after construction)."""
        self._security_gate = gate

    async def execute(
        self,
        agent: AgentDef,
        query: str,
        *,
        user_id: str,
        session_id: str | None = None,
        bearer_token: str | None = None,
    ) -> AgentExecutionResult:
        """Run the agent on the query, invoking skills as needed.

        `bearer_token` is forwarded to the gateway so it can attribute
        the call to the user.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": query},
        ]

        skill_calls = 0
        citations: list[str] = []
        next_actions: list[str] = []
        last_response = ""

        for iteration in range(MAX_SKILL_LOOP_ITERATIONS):
            reply = await self.gateway.chat_multi(
                messages=messages,
                bearer_token=bearer_token,
            )
            last_response = reply.response

            skill_blocks = list(_SKILL_BLOCK_RE.finditer(reply.response))

            if not skill_blocks:
                # No more skill calls — this is the final answer
                messages.append({"role": "assistant", "content": reply.response})
                break

            # Remove skill blocks from the assistant's response, keeping the
            # surrounding explanation text (the agent may have said something
            # before/after the skill call)
            clean_response = _SKILL_BLOCK_RE.sub("", reply.response).strip()
            if clean_response:
                messages.append({"role": "assistant", "content": clean_response})

            # Invoke each skill block in order
            for match in skill_blocks:
                skill_slug = match.group(1)
                raw_inputs = match.group(2).strip()

                # Parse JSON inputs (skill defines the contract)
                try:
                    inputs = json.loads(raw_inputs) if raw_inputs else {}
                except json.JSONDecodeError as exc:
                    log.warning(
                        "executor.skill_loop.json_error",
                        skill=skill_slug,
                        user_id=user_id,
                        error=str(exc),
                    )
                    skill_result_text = (
                        f"[Skill '{skill_slug}' invocation error: "
                        f"invalid JSON inputs — {exc}]"
                    )
                else:
                    skill_result, needs_confirm = await self._invoke_skill(
                        skill_slug, inputs, user_id=user_id
                    )
                    skill_result_text = self._skill_result_to_text(skill_result)

                    # Sensitive skill detected — stop the loop and return a
                    # confirmation request to the Coordinator (spec §3.3)
                    if needs_confirm:
                        return AgentExecutionResult(
                            response=(
                                f"This action requires your confirmation: "
                                f"'{skill_slug}' — {skill_result.data.get('message', 'please confirm.')}"
                            ),
                            citations=[],
                            next_actions=[
                                f"Confirm: run {skill_slug}",
                                f"Cancel: skip {skill_slug}",
                            ],
                            needs_sensitive_confirmation=True,
                            pending_sensitive_skill=skill_slug,
                            pending_sensitive_inputs=inputs,
                        )

                    # Collect citations and next_actions from the first skill pass
                    if iteration == 0 and isinstance(skill_result.data, dict):
                        if "citations" in skill_result.data:
                            citations.extend(skill_result.data["citations"])
                        if "next_actions" in skill_result.data:
                            next_actions.extend(skill_result.data["next_actions"])

                # Add the skill result as a user turn so the agent can reason about it
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"[SKILL RESULT for '{skill_slug}']:\n"
                            f"{skill_result_text}\n"
                            f"[/SKILL RESULT]"
                        ),
                    }
                )
                skill_calls += 1

            log.info(
                "executor.skill_loop.iteration",
                iteration=iteration + 1,
                skill_calls=skill_calls,
                user_id=user_id,
                agent=agent.slug,
            )

        else:
            # Exceeded MAX_SKILL_LOOP_ITERATIONS
            log.warning(
                "executor.skill_loop.max_iterations",
                agent=agent.slug,
                user_id=user_id,
                skill_calls=skill_calls,
            )

        return AgentExecutionResult(
            response=last_response,
            citations=list(citations),
            next_actions=list(next_actions),
        )

    async def _invoke_skill(
        self, skill_slug: str, inputs: dict, *, user_id: str
    ) -> tuple[SkillResult, bool]:
        """Invoke a skill via the registered SkillExecutor.

        Returns (result, needs_confirmation). If the skill is sensitive
        (spec §3.3), runs the security-privacy agent gate first,
        then returns a confirmation request with the security verdict.
        """
        if self._skill_executor is None:
            return (
                SkillResult(
                    ok=False,
                    data=None,
                    error=(
                        "Skill executor not configured. "
                        "Ensure SkillExecutor was set via set_skill_executor()."
                    ),
                ),
                False,
            )

        # Sensitive skill: run security gate before confirmation
        if skill_slug in SENSITIVE_SKILLS:
            log.info(
                "executor.sensitive_skill.detected",
                skill=skill_slug,
                user_id=user_id,
            )
            # Run the security-privacy agent gate
            security_verdict = "caution"
            security_warning = ""
            if self._security_gate is not None:
                try:
                    result = await self._security_gate.review(
                        skill_slug=skill_slug,
                        inputs=inputs,
                        user_id=user_id,
                    )
                    security_verdict = result.verdict.value
                    security_warning = result.warning
                except Exception as exc:
                    log.warning(
                        "executor.security_gate.error",
                        skill=skill_slug,
                        user_id=user_id,
                        error=str(exc),
                    )
                    security_verdict = "caution"
                    security_warning = f"Security review failed: {exc}"

            return (
                SkillResult(
                    ok=True,
                    data={
                        "skill_slug": skill_slug,
                        "inputs": inputs,
                        "security_verdict": security_verdict,
                        "security_warning": security_warning,
                        "message": (
                            f"'{skill_slug}' is a sensitive skill. "
                            f"Security review: **{security_verdict.upper()}**"
                            + (f" — {security_warning}" if security_warning else "")
                            + " User confirmation is required before execution."
                        ),
                    },
                ),
                True,  # needs_confirmation
            )

        result = await self._skill_executor.invoke(
            skill_slug,
            inputs=inputs,
            user_id=user_id,
        )
        return result, False

    @staticmethod
    def _skill_result_to_text(result: SkillResult) -> str:
        """Convert a SkillResult to text for the conversation."""
        if result.error:
            return f"[ERROR] {result.error}"
        if result.warning:
            return f"{result.warning}\n\nResult:\n{json.dumps(result.data, indent=2)}"
        return json.dumps(result.data, indent=2)
