"""code_explain skill — delegates to the AI gateway with a code-explanation prompt.

Per PR 2/3 plan: this is a stub that calls the gateway with a
specialized code-explanation system prompt.
"""

from __future__ import annotations

from typing import Any

import structlog

from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_CODE_EXPLAIN_SYSTEM_PROMPT = """You are an expert code explanation assistant. Given a code snippet, you explain:
1. What the code does (high-level summary)
2. How it does it (key logic flow)
3. Any notable patterns, techniques, or potential issues

Be concise but complete. Match your explanation depth to the user's stated level.
Quote relevant lines of code in your explanation.

Output format:
## Summary
[one-paragraph summary]

## Key Logic
[explanation of the main logic, with quoted code lines where helpful]

## Notes
[anything notable: patterns, potential issues, alternative approaches]"""


async def code_explain(
    code: str,
    language: str,
    level: str = "auto",
    *,
    user_id: str,
    _gateway: Any = None,
) -> SkillResult:
    """Explain a code snippet.

    Args:
        code: the source code to explain
        language: e.g. python, typescript, rust
        level: "line-by-line", "summary", or "auto" (you decide)
        user_id: for audit logging
        _gateway: GatewayClient injected by the skill executor

    Returns:
        SkillResult with 'explanation' (str) in data
    """
    log.info(
        "code_explain.invoked",
        user_id=user_id,
        language=language,
        code_length=len(code),
    )

    from runtime.infrastructure.gateway_client import GatewayClient
    gateway = _gateway or GatewayClient()

    level_instruction = {
        "line-by-line": "Explain each line or block in sequence.",
        "summary": "Give a concise high-level summary only.",
        "auto": "Choose the most appropriate level based on the code complexity.",
    }.get(level, "Choose the most appropriate level based on the code complexity.")

    user_message = f"""Explain this {language} code:

```{language}
{code}
```

Explanation level: {level_instruction}

Provide your explanation now."""

    try:
        reply = await gateway.chat(
            system_prompt=_CODE_EXPLAIN_SYSTEM_PROMPT,
            user_message=user_message,
        )
        return SkillResult(
            ok=True,
            data={
                "explanation": reply.response,
                "language": language,
                "level": level,
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.error("code_explain.failed", user_id=user_id, error=str(exc))
        return SkillResult(ok=False, data=None, error=f"Code explanation failed: {exc}")
