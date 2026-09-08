"""Parse `.claude/skills/<slug>/SKILL.md` files into SkillDef.

Same parsing approach as the agent loader. A skill is one folder with
one `SKILL.md` file; the folder name is the skill's slug.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import structlog
import yaml

from runtime.domain.skill import SkillDef

log = structlog.get_logger()


class SkillLoadError(Exception):
    """Raised when a skill's SKILL.md cannot be parsed."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def load_skill(path: Path) -> SkillDef:
    """Parse a single SKILL.md.

    `path` is the SKILL.md file. The slug is derived from the
    parent folder's name (which is what the user addresses the
    skill by).
    """
    slug = path.parent.name
    try:
        post = frontmatter.load(path)
    except yaml.YAMLError as exc:
        raise SkillLoadError(path, f"unparseable YAML frontmatter: {exc}") from exc
    except Exception as exc:
        raise SkillLoadError(path, f"could not read file: {exc}") from exc

    metadata = post.metadata or {}
    name = metadata.get("name")
    if not name:
        raise SkillLoadError(path, "missing required frontmatter key 'name'")
    description = metadata.get("description")
    if not description:
        raise SkillLoadError(path, "missing required frontmatter key 'description'")
    sensitive = bool(metadata.get("sensitive", False))
    internal = bool(metadata.get("internal", False))

    body = post.content.strip()
    if not body:
        raise SkillLoadError(path, "empty body — skill needs a contract")

    return SkillDef(
        slug=slug,
        description=description,
        body=body,
        sensitive=sensitive,
        internal=internal,
    )


def discover_skills(skills_dir: Path) -> list[SkillDef]:
    """Load every `<slug>/SKILL.md` in `skills_dir`."""
    if not skills_dir.exists():
        log.warning("skills.dir.missing", path=str(skills_dir))
        return []

    loaded: list[SkillDef] = []
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            skill = load_skill(path)
        except SkillLoadError as exc:
            log.error("skill.load.failed", path=str(exc.path), reason=exc.reason)
            continue
        loaded.append(skill)
        log.info(
            "skill.loaded",
            slug=skill.slug,
            sensitive=skill.sensitive,
            internal=skill.internal,
        )
    return loaded
