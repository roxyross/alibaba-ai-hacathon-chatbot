"""Domain events emitted during agent execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    AGENT_HANDS_OFF = "agent_hands_off"
    SKILL_INVOKED = "skill_invoked"
    SKILL_COMPLETED = "skill_completed"
    SKILL_FAILED = "skill_failed"
    ROUTING_DECIDED = "routing_decided"
    SENSITIVE_CONFIRMATION = "sensitive_confirmation"


@dataclass(frozen=True)
class AgentHandoffEvent:
    """Emitted when the Coordinator hands off to a specialist agent."""
    timestamp: datetime
    from_agent: str | None  # None = Coordinator
    to_agent: str
    query: str
    decision_reason: str | None = None


@dataclass(frozen=True)
class SkillInvokedEvent:
    """Emitted when an agent invokes a skill."""
    timestamp: datetime
    agent_slug: str
    skill_slug: str
    inputs: dict | None = None


@dataclass(frozen=True)
class SkillCompletedEvent:
    """Emitted when a skill finishes successfully."""
    timestamp: datetime
    skill_slug: str
    output_summary: str | None = None
    latency_ms: int | None = None


@dataclass(frozen=True)
class SkillFailedEvent:
    """Emitted when a skill raises an exception."""
    timestamp: datetime
    skill_slug: str
    error: str
