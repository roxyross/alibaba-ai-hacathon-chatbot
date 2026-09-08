"""code_debug skill — delegates to the AI gateway with a debugging prompt.

Per PR 2/3 plan: this is a stub that calls the gateway with a
specialized debugging/diagnosis system prompt.
"""

from __future__ import annotations

from typing import Any

import structlog

from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_CODE_DEBUG_SYSTEM_PROMPT = """You are an expert debugging assistant. Given a code snippet and an error message (or symptom), you:
1. Reproduce/confirm the bug — identify the exact failure point
2. Form a hypothesis — explain what you think is wrong and why
3. Propose a fix — show the corrected code with a brief explanation
4. Verify — explain how the fix resolves the issue

Be precise. Quote the problematic code lines in your diagnosis.

Output format:
## Bug Identification
[what the bug is, quoting the relevant code lines]

## Root Cause
[why this happens]

## Proposed Fix
```[language]
[fixed code]
```

## Verification
[how to verify the fix works]"""


async def code_debug(
    code: str,
    error_message: str | None = None,
    language: str = "python",
    *,
    user_id: str,
    _gateway: Any = None,
) -> SkillResult:
    """Diagnose and suggest a fix for a bug.

    Args:
        code: the source code with the bug
        error_message: the error text (traceback, stdout, etc.) if available
        language: e.g. python, typescript, rust
        user_id: for audit logging
        _gateway: GatewayClient injected by the skill executor

    Returns:
        SkillResult with 'diagnosis' (str) and 'fix' (str) in data
    """
    log.info(
        "code_debug.invoked",
        user_id=user_id,
        language=language,
        has_error=bool(error_message),
    )

    from runtime.infrastructure.gateway_client import GatewayClient
    gateway = _gateway or GatewayClient()

    error_block = f"\n\nError message:\n```\n{error_message}\n```" if error_message else "\n\n(No specific error message provided — diagnose from code inspection.)"

    user_message = f"""Debug this {language} code:

```{language}
{code}
```
{error_block}

Provide your diagnosis and proposed fix now."""

    try:
        reply = await gateway.chat(
            system_prompt=_CODE_DEBUG_SYSTEM_PROMPT,
            user_message=user_message,
        )
        return SkillResult(
            ok=True,
            data={
                "diagnosis": reply.response,
                "language": language,
                "has_error": bool(error_message),
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.error("code_debug.failed", user_id=user_id, error=str(exc))
        return SkillResult(ok=False, data=None, error=f"Code debug failed: {exc}")
