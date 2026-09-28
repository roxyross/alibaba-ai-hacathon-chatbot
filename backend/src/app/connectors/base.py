"""Base Connector abstract class for external services in ROXY-AI 2.0."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.connectors.schemas import ConnectionTestResult
from app.tools.schemas import AgentTool


class BaseConnector(ABC):
    """Abstract interface that all external service connectors must implement."""

    def __init__(self, instance_id: str, name: str, config: dict[str, Any], credentials: dict[str, Any]) -> None:
        self.instance_id = instance_id
        self.name = name
        self.config = config
        self.credentials = credentials

    @property
    @abstractmethod
    def connector_type(self) -> str:
        """The identifier type of this connector, e.g. 'google', 'github'."""
        pass

    @abstractmethod
    async def test_connection(self) -> ConnectionTestResult:
        """Ping the external service or validate credentials to verify connectivity."""
        pass

    @abstractmethod
    def list_actions(self) -> list[AgentTool]:
        """Expose executable capabilities as AgentTools for the Tool Registry."""
        pass

    @abstractmethod
    async def execute_action(self, action_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a concrete action against the external service API."""
        pass
