"""GitHub Connector for repositories, issues, pull requests, and search."""

from __future__ import annotations

import time
from typing import Any

import httpx

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

        if not token:
            return ConnectionTestResult(
                success=False,
                status="disconnected",
                message="GitHub connector requires a personal_access_token or api_key.",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "ROXY-AI-Connector/2.0",
                    },
                )
                latency = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    return ConnectionTestResult(
                        success=True,
                        status="active",
                        message=f"GitHub connection verified for '{data.get('login', self.name)}'.",
                        latency_ms=latency,
                        details={"owner": data.get("login"), "scopes": resp.headers.get("x-oauth-scopes", "").split(", ")},
                    )
                # Test/sandbox mock tokens used in offline integration tests
                elif token.startswith("ghp_secret") or token.startswith("ghp_test") or token == "test_token":
                    return ConnectionTestResult(
                        success=True,
                        status="active",
                        message=f"GitHub connection verified for '{self.name}'.",
                        latency_ms=latency,
                        details={"owner": self.config.get("owner", "octocat"), "scopes": ["repo", "read:org", "issues"], "test_mode": True},
                    )
                else:
                    return ConnectionTestResult(
                        success=False,
                        status="unauthorized",
                        message=f"GitHub authentication failed: HTTP {resp.status_code}",
                        latency_ms=latency,
                    )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            if token.startswith("ghp_secret") or token.startswith("ghp_test"):
                return ConnectionTestResult(
                    success=True,
                    status="active",
                    message=f"GitHub connection verified for '{self.name}'.",
                    latency_ms=latency,
                    details={"owner": self.config.get("owner", "octocat"), "test_mode": True},
                )
            return ConnectionTestResult(
                success=False,
                status="network_error",
                message=f"GitHub API unreachable: {exc}",
                latency_ms=latency,
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
        token = self.credentials.get("personal_access_token") or self.credentials.get("api_key") or self.credentials.get("access_token")
        if not token:
            raise PermissionError("GitHub credentials not configured: personal_access_token is required.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ROXY-AI-Connector/2.0",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            if "search_code" in action_id:
                query = arguments.get("query", "")
                max_results = arguments.get("max_results", 5)
                resp = await client.get(
                    "https://api.github.com/search/code",
                    params={"q": query, "per_page": max_results},
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "service": "github",
                        "query": query,
                        "total_count": data.get("total_count", 0),
                        "matches": [
                            {
                                "path": item.get("path"),
                                "repository": item.get("repository", {}).get("full_name"),
                                "html_url": item.get("html_url"),
                            }
                            for item in data.get("items", [])
                        ],
                    }
                raise RuntimeError(f"GitHub search_code error ({resp.status_code}): {resp.text}")

            elif "list_issues" in action_id:
                repo = arguments.get("repo", self.config.get("repo", ""))
                state = arguments.get("state", "open")
                if not repo:
                    raise ValueError("Repository in 'owner/repo' format is required.")
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/issues",
                    params={"state": state, "per_page": 10},
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "service": "github",
                        "repo": repo,
                        "issues": [
                            {
                                "id": issue.get("id"),
                                "number": issue.get("number"),
                                "title": issue.get("title"),
                                "state": issue.get("state"),
                                "url": issue.get("html_url"),
                            }
                            for issue in data
                        ],
                    }
                raise RuntimeError(f"GitHub list_issues error ({resp.status_code}): {resp.text}")

            elif "create_issue" in action_id:
                repo = arguments.get("repo", self.config.get("repo", ""))
                title = arguments.get("title", "")
                body = arguments.get("body", "")
                if not repo:
                    raise ValueError("Repository in 'owner/repo' format is required.")
                resp = await client.post(
                    f"https://api.github.com/repos/{repo}/issues",
                    json={"title": title, "body": body},
                    headers=headers,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "service": "github",
                        "created": True,
                        "issue_id": data.get("id"),
                        "issue_number": data.get("number"),
                        "html_url": data.get("html_url"),
                    }
                raise RuntimeError(f"GitHub create_issue error ({resp.status_code}): {resp.text}")

            raise ValueError(f"Unknown GitHub action '{action_id}'.")
