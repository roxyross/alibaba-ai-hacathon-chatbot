"""code_generate skill — delegates to the AI gateway with a code-gen prompt.

Per PR 2/3 plan: this is a stub that calls the gateway with a
specialized code-generation system prompt. The real implementation
adds linter/type-checker invocation and sandbox execution in later PRs.
"""

from __future__ import annotations

from typing import Any

import structlog

from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_CODE_GEN_SYSTEM_PROMPT = """You are an expert code generation assistant. Generate clean, well-structured code that:
1. Matches the requested language's conventions and style
2. Handles errors gracefully
3. Is minimal and focused on the task
4. Includes docstrings/comments where helpful

Return the generated code in a markdown code block with the language label.
If you cannot generate the code (ambiguous requirements), say what you need clarified.

Output format:
```
[language: python|typescript|rust|...]

[generated code here]
```"""


async def code_generate(
    task: str,
    language: str,
    context_files: list[str] | None = None,
    constraints: list[str] | None = None,
    output_path: str | None = None,
    *,
    user_id: str,
    _gateway: Any = None,
) -> SkillResult:
    """Generate code matching the user's requirements.

    Args:
        task: what the code should do
        language: e.g. python, typescript, rust
        context_files: files to read for style/conventions (not yet wired in PR 2)
        constraints: e.g. "no new deps", "match existing error-handling pattern"
        output_path: if provided, write directly (not yet wired in PR 2)
        user_id: for audit logging
        _gateway: GatewayClient injected by the skill executor

    Returns:
        SkillResult with 'code' (str) and 'language' (str) in data
    """
    log.info(
        "code_generate.invoked",
        user_id=user_id,
        task=task[:80],
        language=language,
    )

    from runtime.infrastructure.gateway_client import GatewayClient
    gateway = _gateway or GatewayClient()

    context_block = ""
    if context_files:
        context_block = f"\n\nContext files to match style from:\n" + "\n".join(f"- {f}" for f in context_files)

    constraints_block = ""
    if constraints:
        constraints_block = f"\n\nConstraints: {', '.join(constraints)}"

    user_message = f"""Generate code for the following task:

Task: {task}
Language: {language}{context_block}{constraints_block}

{('Output path: ' + output_path) if output_path else ''}

Generate the code now."""  # fmt: skip

    try:
        reply = await gateway.chat(
            system_prompt=_CODE_GEN_SYSTEM_PROMPT,
            user_message=user_message,
        )
        return SkillResult(
            ok=True,
            data={
                "code": reply.response,
                "language": language,
                "output_path": output_path,
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.error("code_generate.failed", user_id=user_id, error=str(exc))
        return SkillResult(ok=False, data=None, error=f"Code generation failed: {exc}")
