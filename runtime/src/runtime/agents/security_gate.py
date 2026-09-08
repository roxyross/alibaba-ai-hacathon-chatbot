"""Security & Privacy gate — invokes the security-privacy agent before sensitive skills.

This module provides a `SecurityGate` that the Coordinator calls before any
sensitive skill (email_send, browser_fill_form) executes. It invokes the
security-privacy internal agent with the proposed action and returns a verdict
(clear / caution / block) plus a plain-language warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

from runtime.agents.executor import AgentExecutor
from runtime.agents.registry import AgentRegistry
from runtime.infrastructure.gateway_client import GatewayClient

log = structlog.get_logger()


class RiskVerdict(str, Enum):
    CLEAR = "clear"      # Proceed without concern
    CAUTION = "caution"  # Proceed with a warning
    BLOCK = "block"      # Do not proceed


@dataclass(frozen=True)
class SecurityGateResult:
    verdict: RiskVerdict
    warning: str
    recommendation: str | None  # Narrower alternative if caution/block


_PROMPT_TEMPLATE = """\
You are the Security & Privacy Agent — the runtime's last line of defense before a consequential action runs.

A user has requested the following action:
- Skill: {skill_slug}
- Inputs: {inputs}

Review this action for:
1. **Data exposure** — Is sensitive personal, financial, or credentials data being sent outside the system?
2. **Irreversibility** — Can this action be undone? Is a destructive or permanent change being made?
3. **Scope creep** — Is the action asking for more than it needs?
4. **Third-party impact** — Does this affect other people or systems beyond the user?
5. **Financial cost** — Does this trigger a paid API call or service?
6. **Legal exposure** — Does this involve publishing, legal statements, or contractual commitments?

Respond ONLY with a JSON object:
{{{{
  "verdict": "clear" | "caution" | "block",
  "warning": "A single plain-language sentence describing the risk, or empty string if clear.",
  "recommendation": "A narrower alternative action that achieves the goal with less risk, or null if clear."
}}}}

Be precise. When in doubt, err toward "caution" with a clear warning.
"""


class SecurityGate:
    """Pre-execution security reviewer using the internal security-privacy agent."""

    def __init__(
        self,
        registry: AgentRegistry,
        executor: AgentExecutor,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._agent_slug = "security-privacy"

    async def review(
        self,
        skill_slug: str,
        inputs: dict[str, Any],
        *,
        user_id: str,
        bearer_token: str | None = None,
    ) -> SecurityGateResult:
        """Review a proposed sensitive action and return a verdict.

        Calls the security-privacy internal agent via the Gateway.
        Falls back to a conservative 'caution' verdict on any error.
        """
        agent = self._registry.get(self._agent_slug)
        if agent is None:
            log.warning("security_gate.agent_not_found", slug=self._agent_slug)
            return SecurityGateResult(
                verdict=RiskVerdict.CAUTION,
                warning="Security review agent is not loaded. Treating as caution.",
                recommendation=None,
            )

        prompt = _PROMPT_TEMPLATE.format(
            skill_slug=skill_slug,
            inputs=_fmt_inputs(inputs),
        )

        try:
            messages = [
                {"role": "system", "content": agent.system_prompt},
                {"role": "user", "content": prompt},
            ]
            reply = await self._executor.gateway.chat_multi(
                messages=messages,
                bearer_token=bearer_token,
            )
            result = _parse_verdict(reply.response)
            log.info(
                "security_gate.reviewed",
                user_id=user_id,
                skill=skill_slug,
                verdict=result.verdict.value,
            )
            return result

        except Exception as exc:
            log.error(
                "security_gate.error",
                user_id=user_id,
                skill=skill_slug,
                error=str(exc),
            )
            return SecurityGateResult(
                verdict=RiskVerdict.CAUTION,
                warning=f"Security review failed: {exc}. Treating as caution.",
                recommendation=None,
            )


def _fmt_inputs(inputs: dict[str, Any]) -> str:
    """Format inputs for the prompt, redacting sensitive values."""
    import json
    safe: dict[str, Any] = {}
    SENSITIVE_KEYS = frozenset({
        "password", "secret", "token", "api_key", "apikey",
        "authorization", "credential", "pin", "ssn", "credit_card",
    })
    for k, v in inputs.items():
        if any(sk in k.lower() for sk in SENSITIVE_KEYS):
            safe[k] = "[REDACTED]"
        else:
            safe[k] = v
    return json.dumps(safe, indent=2)


def _parse_verdict(text: str) -> SecurityGateResult:
    """Parse the JSON verdict from the security-privacy agent response."""
    import json, re
    # Extract JSON from the response (agent may wrap in backticks)
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        # Fallback: conservative
        return SecurityGateResult(
            verdict=RiskVerdict.CAUTION,
            warning="Could not parse security verdict. Treating as caution.",
            recommendation=None,
        )
    try:
        data = json.loads(match.group(0))
        verdict_str = data.get("verdict", "caution")
        try:
            verdict = RiskVerdict(verdict_str.lower())
        except ValueError:
            verdict = RiskVerdict.CAUTION
        return SecurityGateResult(
            verdict=verdict,
            warning=data.get("warning", ""),
            recommendation=data.get("recommendation"),
        )
    except json.JSONDecodeError:
        return SecurityGateResult(
            verdict=RiskVerdict.CAUTION,
            warning="Could not parse security verdict JSON. Treating as caution.",
            recommendation=None,
        )
