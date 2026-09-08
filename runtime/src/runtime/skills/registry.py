"""Skill registry: a read-only map from slug to SkillDef.

Like AgentRegistry, built once at startup. Sensitive and internal
skills are loaded but partitioned.
"""

from __future__ import annotations

from runtime.config import settings
from runtime.domain.skill import SkillDef
from runtime.skills.loader import discover_skills


class SkillRegistry:
    def __init__(self, skills: list[SkillDef]) -> None:
        self._all: dict[str, SkillDef] = {s.slug: s for s in skills}

    def get(self, slug: str) -> SkillDef | None:
        return self._all.get(slug)

    def all(self) -> list[SkillDef]:
        return list(self._all.values())

    def user_callable(self) -> list[SkillDef]:
        """Skills a non-internal agent may invoke."""
        return [s for s in self._all.values() if s.callable_by_user]

    def __contains__(self, slug: object) -> bool:
        return isinstance(slug, str) and slug in self._all

    def __len__(self) -> int:
        return len(self._all)

    def __repr__(self) -> str:
        sensitive = sum(1 for s in self._all.values() if s.sensitive)
        internal = sum(1 for s in self._all.values() if s.internal)
        return (
            f"SkillRegistry(total={len(self._all)}, "
            f"sensitive={sensitive}, internal={internal})"
        )


def build_registry() -> SkillRegistry:
    return SkillRegistry(discover_skills(settings.resolve_skills_dir()))
