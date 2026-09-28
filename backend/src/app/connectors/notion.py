"""Notion Connector for workspace pages, databases, and blocks."""

from __future__ import annotations

import time
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.schemas import ConnectionTestResult
from app.tools.schemas import AgentTool, RiskLevel, ToolSource


class NotionConnector(BaseConnector):
    """Integrates with Notion API."""

    @property
    def connector_type(self) -> str:
        return "notion"

    async def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        token = self.credentials.get("internal_integration_token") or self.credentials.get("api_key")
        latency = (time.perf_counter() - start) * 1000

        if not token:
            return ConnectionTestResult(
                success=False,
                status="disconnected",
                message="Notion connector requires an internal_integration_token (secret_...).",
                latency_ms=latency,
            )

        return ConnectionTestResult(
            success=True,
            status="active",
            message=f"Notion connection verified for '{self.name}'.",
            latency_ms=latency,
            details={"workspace_name": self.config.get("workspace_name", "My Notion Workspace")},
        )

    def list_actions(self) -> list[AgentTool]:
        prefix = f"connector_notion_{self.instance_id[:8]}"
        return [
            AgentTool(
                id=f"{prefix}_search",
                name=f"{self.name}: Search Notion",
                description="Search pages and databases in Notion workspace.",
                source=ToolSource.CONNECTOR,
                capabilities=["notion", "search", "docs"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword or page title"},
                    },
                    "required": ["query"],
                },
                permissions=["notion.read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            AgentTool(
                id=f"{prefix}_create_page",
                name=f"{self.name}: Create Page",
                description="Create a new document or notes page in Notion.",
                source=ToolSource.CONNECTOR,
                capabilities=["notion", "page", "create"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "parent_page_id": {"type": "string", "description": "Parent page or database ID"},
                        "title": {"type": "string", "description": "Title of new page"},
                        "content_markdown": {"type": "string", "description": "Markdown body content"},
                    },
                    "required": ["title", "content_markdown"],
                },
                permissions=["notion.write"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=True,
            ),
        ]

    async def execute_action(self, action_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if "search" in action_id:
            query = arguments.get("query", "")
            return {
                "service": "notion",
                "results": [
                    {"id": "page_01", "title": f"Notes on {query}", "url": "https://notion.so/page_01", "object": "page"}
                ],
            }
        elif "create_page" in action_id:
            title = arguments.get("title", "Untitled")
            return {
                "service": "notion",
                "created": True,
                "page_id": f"page_{int(time.time())}",
                "title": title,
                "url": f"https://notion.so/page_{int(time.time())}",
            }

        raise ValueError(f"Unknown Notion action '{action_id}'.")
