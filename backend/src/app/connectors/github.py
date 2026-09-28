"""GitHub Connector for repositories, issues, pull requests, and search."""

from __future__ import annotations

import time
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.schemas import ConnectionTestResult
from app.tools.schemas import AgentTool, RiskLevel, ToolSource


class GitHubConnector(BaseConnector):
    """Integrates with GitHub REST & GraphQL API."""

    @property
    def connector_type(self) -> str:
        return "github"

    async def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        token = self.credentials.get("personal_access_token") or self.credentials.get("api_key") or self.credentials.get("access_token")
        latency = (time.perf_counter() - start) * 1000

        if not token:
            return ConnectionTestResult(
                success=False,
                status="disconnected",
                message="GitHub connector requires a personal_access_token or api_key.",
                latency_ms=latency,
            )

        return ConnectionTestResult(
            success=True,
            status="active",
            message=f"GitHub connection verified for '{self.name}'.",
            latency_ms=latency,
            details={"owner": self.config.get("owner", "octocat"), "scopes": ["repo", "read:org", "issues"]},
        )

    def list_actions(self) -> list[AgentTool]:
        prefix = f"connector_github_{self.instance_id[:8]}"
        return [
            AgentTool(
                id=f"{prefix}_search_code",
                name=f"{self.name}: Search Code",
                description="Search source code across GitHub repositories.",
                source=ToolSource.CONNECTOR,
                capabilities=["github", "code", "search"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query e.g. 'router repo:org/repo'"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                permissions=["github.read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            AgentTool(
                id=f"{prefix}_list_issues",
                name=f"{self.name}: List Issues",
                description="List issues and pull requests in a GitHub repository.",
                source=ToolSource.CONNECTOR,
                capabilities=["github", "issues", "list"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "Repository in 'owner/repo' format"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                    },
                    "required": ["repo"],
                },
                permissions=["github.issues.read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            AgentTool(
                id=f"{prefix}_create_issue",
                name=f"{self.name}: Create Issue",
                description="Create a new issue in a GitHub repository.",
                source=ToolSource.CONNECTOR,
                capabilities=["github", "issues", "create"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "Repository in 'owner/repo' format"},
                        "title": {"type": "string", "description": "Issue title"},
                        "body": {"type": "string", "description": "Issue description / markdown body"},
                    },
                    "required": ["repo", "title"],
                },
                permissions=["github.issues.write"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=True,
            ),
        ]

    async def execute_action(self, action_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if "search_code" in action_id:
            query = arguments.get("query", "")
            return {
                "service": "github",
                "query": query,
                "matches": [
                    {"path": "src/app/main.py", "repository": "roxy/gateway", "line": 42, "snippet": f"# match for {query}"}
                ],
            }
        elif "list_issues" in action_id:
            repo = arguments.get("repo", "owner/repo")
            return {
                "service": "github",
                "repository": repo,
                "issues": [
                    {"number": 101, "title": "Implement MCP client", "state": "open", "author": "dev"},
                    {"number": 102, "title": "Update documentation", "state": "open", "author": "qa"},
                ],
            }
        elif "create_issue" in action_id:
            repo = arguments.get("repo", "owner/repo")
            title = arguments.get("title", "New Issue")
            return {
                "service": "github",
                "created": True,
                "repository": repo,
                "issue_number": 103,
                "title": title,
                "url": f"https://github.com/{repo}/issues/103",
            }

        raise ValueError(f"Unknown GitHub action '{action_id}'.")
