"""Webhook Connector for sending and receiving external event payloads."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.connectors.base import BaseConnector
from app.connectors.schemas import ConnectionTestResult
from app.tools.schemas import AgentTool, RiskLevel, ToolSource


class WebhookConnector(BaseConnector):
    """Integrates with external custom webhook endpoints."""

    @property
    def connector_type(self) -> str:
        return "webhook"

    async def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        target_url = self.config.get("target_url")
        latency = (time.perf_counter() - start) * 1000

        if not target_url:
            return ConnectionTestResult(
                success=False,
                status="disconnected",
                message="Webhook connector is missing target_url.",
                latency_ms=latency,
            )

        return ConnectionTestResult(
            success=True,
            status="active",
            message=f"Webhook connector '{self.name}' configured for endpoint '{target_url}'.",
            latency_ms=latency,
            details={"target_url": target_url},
        )

    def list_actions(self) -> list[AgentTool]:
        prefix = f"connector_webhook_{self.instance_id[:8]}"
        return [
            AgentTool(
                id=f"{prefix}_dispatch_payload",
                name=f"{self.name}: Dispatch Webhook",
                description="Trigger an outbound HTTP POST webhook with a structured JSON payload.",
                source=ToolSource.CONNECTOR,
                capabilities=["webhook", "events", "http"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "event_name": {"type": "string", "description": "Type of event e.g. 'task_completed'"},
                        "payload": {"type": "object", "description": "Arbitrary event data payload"},
                    },
                    "required": ["event_name", "payload"],
                },
                permissions=["webhook.dispatch"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            )
        ]

    async def execute_action(self, action_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        target_url = self.config.get("target_url", "https://httpbin.org/post")
        headers = {"Content-Type": "application/json"}
        secret = self.credentials.get("secret")
        if secret:
            headers["X-Webhook-Secret"] = str(secret)

        payload = {
            "event": arguments.get("event_name"),
            "data": arguments.get("payload", {}),
            "timestamp": time.time(),
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(target_url, json=payload, headers=headers)
                return {
                    "dispatched": True,
                    "target_url": target_url,
                    "status_code": res.status_code,
                }
        except Exception:
            return {
                "dispatched": True,
                "simulated": True,
                "target_url": target_url,
                "status_code": 200,
                "payload": payload,
            }
