"""Agent definition domain model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentDef:
    """Immutable agent definition loaded from .claude/agents/<slug>.md"""

    slug: str
    description: str
    body: str  # Markdown body = system prompt
    tools: list[str] = field(default_factory=list)
    sensitive: bool = False
    internal: bool = False

    @property
    def routable(self) -> bool:
        """Internal agents are NOT exposed to the Coordinator's routing."""
        return not self.internal

    @property
    def system_prompt(self) -> str:
        """The full system prompt passed to the AI gateway."""
        return self.body
