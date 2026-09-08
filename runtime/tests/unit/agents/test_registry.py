"""Tests for runtime.agents.registry — AgentRegistry."""

from __future__ import annotations

from runtime.agents.loader import AgentDef
from runtime.agents.registry import AgentRegistry


def _agent(slug: str, internal: bool = False) -> AgentDef:
    return AgentDef(
        slug=slug,
        description=f"{slug} agent",
        body=f"# {slug} agent body",
        tools=[],
        internal=internal,
    )


class TestAgentRegistry:
    def setup_method(self) -> None:
        self.agents = [
            _agent("research"),
            _agent("coding"),
            _agent("memory-curator", internal=True),
        ]
        self.registry = AgentRegistry(self.agents)

    def test_get_returns_agent(self) -> None:
        agent = self.registry.get("research")
        assert agent is not None
        assert agent.slug == "research"

    def test_get_returns_none_for_unknown(self) -> None:
        assert self.registry.get("unknown") is None

    def test_routable_excludes_internal(self) -> None:
        routable = self.registry.routable()
        slugs = {a.slug for a in routable}
        assert "research" in slugs
        assert "coding" in slugs
        assert "memory-curator" not in slugs

    def test_all_includes_internal(self) -> None:
        all_slugs = {a.slug for a in self.registry.all()}
        assert "memory-curator" in all_slugs

    def test_len(self) -> None:
        assert len(self.registry) == 3

    def test_contains(self) -> None:
        assert "research" in self.registry
        assert "unknown" not in self.registry

    def test_repr(self) -> None:
        r = repr(self.registry)
        assert "total=3" in r
        assert "routable=2" in r
        assert "internal=1" in r
