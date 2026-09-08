"""Tests for runtime.skills.loader — parse SKILL.md files into SkillDef."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from runtime.skills.loader import (
    SkillLoadError,
    SkillDef,
    discover_skills,
    load_skill,
)


# ---- helpers ---------------------------------------------------------------

def _write_skill(base: Path, slug: str, name: str, description: str, body: str, **fm: object) -> None:
    """Write a skill folder with a SKILL.md file."""
    skill_dir = base / slug
    skill_dir.mkdir()
    fm_lines = ["---", f"name: {name}", f"description: {description}"]
    for k, v in fm.items():
        fm_lines.append(f"{k}: {v!r}" if not isinstance(v, str) else f"{k}: {v}")
    fm_lines.append("---")
    content = "\n".join(fm_lines) + "\n" + body
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


# ---- load_skill -----------------------------------------------------------

class TestLoadSkill:
    def test_parses_valid_file(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "web_search", "web_search", "Issue a web search", "## Purpose\nRun a web search...")
        skill = load_skill(tmp_path / "web_search" / "SKILL.md")
        assert skill.slug == "web_search"
        assert skill.description == "Issue a web search"
        assert skill.body.startswith("## Purpose")
        assert skill.sensitive is False
        assert skill.internal is False

    def test_parses_optional_frontmatter(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "email_send",
            "email_send",
            "Send an email",
            "## Purpose\nSend email...",
            sensitive=True,
            internal=False,
        )
        skill = load_skill(tmp_path / "email_send" / "SKILL.md")
        assert skill.slug == "email_send"
        assert skill.sensitive is True

    def test_internal_flag(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "memory_summarize_prune",
            "memory_summarize_prune",
            "Nightly memory pruning",
            "## Purpose\nPrune memories...",
            internal=True,
        )
        skill = load_skill(tmp_path / "memory_summarize_prune" / "SKILL.md")
        assert skill.internal is True
        assert skill.callable_by_user is False

    def test_missing_name_raises(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        skill_dir.joinpath("SKILL.md").write_text("---\ndescription: x\n---\nbody", encoding="utf-8")
        with pytest.raises(SkillLoadError) as exc_info:
            load_skill(skill_dir / "SKILL.md")
        assert "name" in str(exc_info.value).lower()

    def test_missing_description_raises(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "bad", "bad", "", "body")
        with pytest.raises(SkillLoadError) as exc_info:
            load_skill(tmp_path / "bad" / "SKILL.md")
        assert "description" in str(exc_info.value).lower()

    def test_empty_body_raises(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "bad", "bad", "desc", "   ")
        with pytest.raises(SkillLoadError) as exc_info:
            load_skill(tmp_path / "bad" / "SKILL.md")
        assert "body" in str(exc_info.value).lower()


# ---- discover_skills -------------------------------------------------------

class TestDiscoverSkills:
    def test_loads_all_skill_folders(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "web_search", "web_search", "Issue a web search", "## Purpose")
        _write_skill(tmp_path, "calculator", "calculator", "Run a calculation", "## Purpose")
        skills = discover_skills(tmp_path)
        slugs = {s.slug for s in skills}
        assert "web_search" in slugs
        assert "calculator" in slugs

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        assert discover_skills(tmp_path / "nonexistent") == []

    def test_bad_file_logged_not_fatal(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "good", "good", "Good skill", "## Purpose")
        bad = tmp_path / "bad"
        bad.mkdir()
        bad.joinpath("SKILL.md").write_text("---\nname: bad\ndescription: missing\n---\n", encoding="utf-8")
        skills = discover_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].slug == "good"
        # The bad file was skipped (logged to structlog stdout; verified separately)
