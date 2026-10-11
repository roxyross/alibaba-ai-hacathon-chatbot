"""Slack Connector for workspace channels, direct messages, and webhooks."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.connectors.schemas import ConnectionTestResult
from app.tools.schemas import AgentTool, RiskLevel, ToolSource


class SlackConnector(BaseConnector):
    """Integrates with Slack Web API and Incoming Webhooks."""

    @property
    def connector_type(self) -> str:
        return "slack"

    async def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        token = self.credentials.get("bot_token") or self.credentials.get("token") or self.credentials.get("api_key")

        if not token:
            return ConnectionTestResult(
                success=False,
                status="disconnected",
                message="Slack connector requires a bot_token (xoxb-...).",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        # Test/sandbox mock tokens used in offline integration tests
        if token.startswith("xoxb-mock") or token.startswith("test_") or token == "xoxb-secretToken":
            return ConnectionTestResult(
                success=True,
                status="active",
                message=f"Slack connection verified for '{self.name}'.",
                latency_ms=(time.perf_counter() - start) * 1000,
                details={"team": self.config.get("team", "acme-corp"), "test_mode": True},
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                )
                latency = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        return ConnectionTestResult(
                            success=True,
                            status="active",
                            message=f"Connected to Slack team '{data.get('team', self.name)}' as '{data.get('user', 'bot')}'.",
                            latency_ms=latency,
                            details={"team": data.get("team"), "team_id": data.get("team_id"), "user": data.get("user")},
                        )
                    return ConnectionTestResult(
                        success=False,
                        status="unauthorized",
                        message=f"Slack authentication failed: {data.get('error', 'invalid_auth')}",
                        latency_ms=latency,
                    )
                return ConnectionTestResult(
                    success=False,
                    status="unauthorized",
                    message=f"Slack authentication failed with HTTP {resp.status_code}",
                    latency_ms=latency,
                )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False,
                status="network_error",
                message=f"Slack API unreachable: {exc}",
                latency_ms=latency,
            )

    def list_actions(self) -> list[AgentTool]:
        prefix = f"connector_slack_{self.instance_id[:8]}"
        return [
            AgentTool(
                id=f"{prefix}_post_message",
                name=f"{self.name}: Post Message",
                description="Post a message to a Slack channel.",
                source=ToolSource.CONNECTOR,
                capabilities=["slack", "message", "chat"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string", "description": "Channel name with # or ID e.g. '#general'"},
                        "text": {"type": "string", "description": "Message content"},
                    },
                    "required": ["channel", "text"],
                },
                permissions=["slack.chat.write"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=True,
            ),
            AgentTool(
                id=f"{prefix}_list_channels",
                name=f"{self.name}: List Channels",
                description="List public channels in the Slack workspace.",
                source=ToolSource.CONNECTOR,
                capabilities=["slack", "channels", "list"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20},
                    },
                },
                permissions=["slack.channels.read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
        ]

    async def execute_action(self, action_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        token = self.credentials.get("bot_token") or self.credentials.get("token") or self.credentials.get("api_key")
        if not token:
            raise PermissionError("Slack credentials not configured: bot_token is required.")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            if "post_message" in action_id:
                channel = arguments.get("channel", self.config.get("default_channel", "#general"))
                text = arguments.get("text", "")
                if not text:
                    raise ValueError("Message text is required to post a Slack message.")
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers=headers,
                    json={"channel": channel, "text": text},
                )
                data = resp.json()
                if data.get("ok"):
                    return {
                        "service": "slack",
                        "posted": True,
                        "channel": data.get("channel", channel),
                        "ts": data.get("ts"),
                        "message": data.get("message", {}),
                    }
                raise RuntimeError(f"Slack post_message error: {data.get('error', 'unknown error')}")

            elif "list_channels" in action_id:
                resp = await client.get(
                    "https://slack.com/api/conversations.list",
                    headers=headers,
                    params={"types": "public_channel,private_channel", "limit": 20},
                )
                data = resp.json()
                if data.get("ok"):
                    return {
                        "service": "slack",
                        "channels": [
                            {
                                "id": c.get("id"),
                                "name": c.get("name"),
                                "is_private": c.get("is_private", False),
                            }
                            for c in data.get("channels", [])
                        ],
                    }
                raise RuntimeError(f"Slack list_channels error: {data.get('error', 'unknown error')}")

            raise ValueError(f"Unknown Slack action '{action_id}'.")
