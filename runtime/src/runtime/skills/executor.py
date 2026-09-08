"""Skill executor dispatcher with Pydantic input validation.

The executor looks up a Python function for the skill slug in a registry.
If the skill has a registered input schema (a Pydantic model), the incoming
inputs are validated against it BEFORE the function is called — converting
LLM-emitted strings to correct types and surfacing a clean `SkillResult` error
(rather than a raw TypeError) when validation fails.

Per spec §3.10: "Skills that don't have a registered implementation ... return
a clear 'not yet implemented' error rather than a 500."
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import structlog
from pydantic import BaseModel, ValidationError

from runtime.domain.skill import SkillDef

log = structlog.get_logger()

SkillImpl = Callable[..., Awaitable["SkillResult"]]


@dataclass
class SkillResult:
    ok: bool
    data: object
    error: str | None = None
    warning: str | None = None  # shown to the user alongside the data


class SkillNotRegistered(Exception):
    """Raised when a skill is invoked that has no implementation."""


@dataclass
class SkillSpec:
    """A registered skill: its implementation function + optional Pydantic input schema."""

    impl: SkillImpl
    # Optional Pydantic model used to validate `inputs` before calling `impl`.
    # If None, inputs are passed through unchecked (for internal-only skills).
    input_model: type[BaseModel] | None = None


class SkillExecutor:
    """Registry + dispatcher for skill implementations.

    Skills are registered with `register(slug, fn, input_model=None)`.
    The optional `input_model` is a Pydantic model that validates the
    skill's inputs before the function is called — preventing raw TypeError
    leaks from malformed LLM tool-call arguments.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillSpec] = {}

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register(
        self,
        slug: str,
        fn: SkillImpl,
        input_model: type[BaseModel] | None = None,
    ) -> None:
        """Register a skill implementation with an optional Pydantic input schema.

        Args:
            slug: Canonical skill name, e.g. "web_search".
            fn: Async function with signature `(..., *, user_id: str) -> SkillResult`.
            input_model: Optional Pydantic model (subclass of BaseModel) whose fields
                define the skill's expected inputs. If provided, inputs dict will be
                validated before `fn` is called. If None, inputs are passed through
                unchecked (use for internal-only skills called programmatically).
        """
        self._skills[slug] = SkillSpec(impl=fn, input_model=input_model)
        log.debug("skill.registered", slug=slug, has_schema=input_model is not None)

    def is_registered(self, slug: str) -> bool:
        return slug in self._skills

    # -------------------------------------------------------------------------
    # Dispatch
    # -------------------------------------------------------------------------

    async def invoke(
        self,
        skill: SkillDef | str,
        *,
        inputs: dict,
        user_id: str,
    ) -> SkillResult:
        """Invoke a skill by SkillDef or by slug string.

        If the skill has a registered input schema, the inputs dict is validated
        against it BEFORE calling the implementation. Validation errors return a
        clean ``SkillResult(ok=False)`` with a readable message — never a raw
        TypeError back to the LLM loop.

        Args:
            skill: SkillDef from the registry or a slug string.
            inputs: Raw dict of inputs from the LLM tool-call JSON.
            user_id: Required by all skill implementations for audit logging.

        Returns:
            SkillResult with the skill's response data or a clean error.
        """
        slug = skill.slug if isinstance(skill, SkillDef) else skill
        spec = self._skills.get(slug)

        if spec is None:
            log.warning("skill.not_implemented", slug=slug, user_id=user_id)
            return SkillResult(
                ok=False,
                data=None,
                error=(
                    f"Skill '{slug}' is not implemented yet. "
                    "This is a PR 2 stub; the real implementation lands in PR 3."
                ),
            )

        # ---- Pydantic validation before calling --------------------------------
        if spec.input_model is not None:
            try:
                validated = spec.input_model.model_validate(inputs)
                # Convert back to dict for the skill function (model_validate returns a model)
                kwargs = validated.model_dump()
            except ValidationError as exc:
                # Surface a clean, readable error — not a raw TypeError
                field_errors = "; ".join(
                    f"{e['loc']}: {e['msg']}" for e in exc.errors()
                )
                log.warning(
                    "skill.input_validation_failed",
                    slug=slug,
                    user_id=user_id,
                    errors=field_errors,
                )
                return SkillResult(
                    ok=False,
                    data=None,
                    error=f"Invalid inputs for '{slug}': {field_errors}",
                )
        else:
            # No schema registered — pass inputs through unchecked (internal skills)
            kwargs = dict(inputs)

        # ---- Call the implementation ------------------------------------------
        try:
            return await spec.impl(**kwargs, user_id=user_id)
        except Exception as exc:  # noqa: BLE001 — surface skill errors cleanly
            log.error(
                "skill.execution.failed",
                slug=slug,
                user_id=user_id,
                error=str(exc),
                exc_info=True,
            )
            return SkillResult(ok=False, data=None, error=f"Skill failed: {exc}")
