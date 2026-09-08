"""Skill definition domain model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillDef:
    """Immutable skill definition loaded from .claude/skills/<slug>/SKILL.md."""

    slug: str
    description: str
    body: str  # Markdown body = skill contract
    sensitive: bool = False
    internal: bool = False
    requires_confirmation: bool = False

    @property
    def callable_by_user(self) -> bool:
        """Internal skills are NOT callable by user-facing agents."""
        return not self.internal

    @property
    def is_sensitive(self) -> bool:
        """Sensitive skills require explicit user confirmation before dispatch."""
        return self.sensitive or self.requires_confirmation
