"""Tests for runtime.agents.loader — parse .md files into AgentDef."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from runtime.agents.loader import (
    AgentLoadError,
    AgentDef,
    discover_agents,
    load_agent,
)

# ---- helpers ---------------------------------------------------------------

def _write_agent(path: Path, name: str, description: str, body: str, **frontmatter: object) -> None:
    """Write a minimal .md agent file with YAML frontmatter."""
    fm_lines = ["---", f"name: {name}", f"description: {description}"]
    for k, v in frontmatter.items():
        fm_lines.append(f"{k}: {v!r}" if not isinstance(v, str) else f"{k}: {v}")
    fm_lines.append("---")
    content = "\n".join(fm_lines) + "\n" + body
    path.write_text(content, encoding="utf-8")


# ---- load_agent -----------------------------------------------------------

class TestLoadAgent:
    def test_parses_valid_file(self, tmp_path: Path) -> None:
        path = tmp_path / "research.md"
        _write_agent(
            path,
            name="research",
            description="Web search and synthesis",
            body="# Research Agent\n\nI answer questions...",
        )
        agent = load_agent(path)
        assert agent.slug == "research"
        assert agent.description == "Web search and synthesis"
        assert agent.body.startswith("# Research Agent")
        assert agent.tools == []
        assert agent.sensitive is False
        assert agent.internal is False

    def test_parses_optional_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "browser.md"
        _write_agent(
            path,
            name="browser",
            description="Browser automation",
            body="I drive a browser...",
            tools=["Read", "Write", "Bash"],
            sensitive=True,
            internal=False,
        )
        agent = load_agent(path)
        assert agent.slug == "browser"
        assert agent.tools == ["Read", "Write", "Bash"]
        assert agent.sensitive is True

    def test_tools_accepts_csv_string(self, tmp_path: Path) -> None:
        path = tmp_path / "coding.md"
        _write_agent(
            path,
            name="coding",
            description="Code generation",
            body="I write code...",
            tools="Read, Write, Glob",
        )
        agent = load_agent(path)
        assert agent.tools == ["Read", "Write", "Glob"]

    def test_missing_name_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\ndescription: something\n---\nbody", encoding="utf-8")
        with pytest.raises(AgentLoadError) as exc_info:
            load_agent(path)
        assert "name" in str(exc_info.value).lower()

    def test_missing_description_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        _write_agent(path, name="test", description="", body="Some body")
        with pytest.raises(AgentLoadError) as exc_info:
            load_agent(path)
        assert "description" in str(exc_info.value).lower()

    def test_empty_body_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        _write_agent(path, name="test", description="Some desc", body="   ")
        with pytest.raises(AgentLoadError) as exc_info:
            load_agent(path)
        assert "body" in str(exc_info.value).lower()

    def test_unparseable_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\nname: test\n  badly: indented: yaml\n---\nbody", encoding="utf-8")
        with pytest.raises(AgentLoadError) as exc_info:
            load_agent(path)
        assert "yaml" in str(exc_info.value).lower()

    def test_internal_flag(self, tmp_path: Path) -> None:
        path = tmp_path / "memory-curator.md"
        _write_agent(
            path,
            name="memory-curator",
            description="Nightly memory pruning",
            body="I clean up memories...",
            internal=True,
        )
        agent = load_agent(path)
        assert agent.internal is True
        assert agent.routable is False  # internal agents are not routable


# ---- discover_agents ------------------------------------------------------

class TestDiscoverAgents:
    def test_loads_all_md_files(self, tmp_path: Path) -> None:
        _write_agent(tmp_path / "research.md", "research", "Web search", "Research body")
        _write_agent(tmp_path / "coding.md", "coding", "Code generation", "Coding body")
        agents = discover_agents(tmp_path)
        slugs = {a.slug for a in agents}
        assert "research" in slugs
        assert "coding" in slugs

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        agents = discover_agents(tmp_path / "nonexistent")
        assert agents == []

    def test_bad_file_logged_not_fatal(self, tmp_path: Path) -> None:
        # One good file, one bad file — bad file is skipped but good file loads
        _write_agent(tmp_path / "good.md", "good", "Good agent", "Good body")
        bad = tmp_path / "bad.md"
        bad.write_text("---\ndescription: missing name\n---\nbody", encoding="utf-8")

        agents = discover_agents(tmp_path)
        assert len(agents) == 1
        assert agents[0].slug == "good"
        # The bad file was skipped (logged to structlog stdout; verified separately)
