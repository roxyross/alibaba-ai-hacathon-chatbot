"""Agent registry: a read-only map from slug to AgentDef.

Built once at startup. Internal agents (per spec §3.10) are loaded
but excluded from the routable index. The registry is the single
source of truth for "which agents exist" and "which can be routed".
"""

from __future__ import annotations

from runtime.agents.loader import discover_agents
from runtime.config import settings
from runtime.domain.agent import AgentDef


class AgentRegistry:
    """Index of all loaded agents, partitioned into routable + internal."""

    def __init__(self, agents: list[AgentDef]) -> None:
        self._all: dict[str, AgentDef] = {a.slug: a for a in agents}
        self._routable: dict[str, AgentDef] = {
            a.slug: a for a in agents if a.routable
        }

    def get(self, slug: str) -> AgentDef | None:
        return self._all.get(slug)

    def routable(self) -> list[AgentDef]:
        """Agents the Coordinator may route user queries to."""
        return list(self._routable.values())

    def all(self) -> list[AgentDef]:
        """All loaded agents, including internal ones."""
        return list(self._all.values())

    def __contains__(self, slug: object) -> bool:
        return isinstance(slug, str) and slug in self._all

    def __len__(self) -> int:
        return len(self._all)

    def __repr__(self) -> str:
        return (
            f"AgentRegistry(total={len(self._all)}, "
            f"routable={len(self._routable)}, "
            f"internal={len(self._all) - len(self._routable)})"
        )


def build_registry() -> AgentRegistry:
    """Build the registry from the configured agents directory."""
    agents = discover_agents(settings.resolve_agents_dir())
    return AgentRegistry(agents)
