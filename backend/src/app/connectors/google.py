"""Google Workspace Connector for Gmail, Google Calendar, and Drive."""

from __future__ import annotations

import time
from typing import Any

from app.connectors.base import BaseConnector
from app.connectors.schemas import ConnectionTestResult
from app.tools.schemas import AgentTool, RiskLevel, ToolSource


class GoogleWorkspaceConnector(BaseConnector):
    """Integrates with Google Workspace APIs (Gmail, Calendar, Drive)."""

    @property
    def connector_type(self) -> str:
        return "google"

    async def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        token = self.credentials.get("access_token") or self.credentials.get("api_key")
        latency = (time.perf_counter() - start) * 1000

        if not token:
            return ConnectionTestResult(
                success=False,
                status="disconnected",
                message="Google Workspace connector is missing access_token or api_key.",
                latency_ms=latency,
            )

        # In production this queries userinfo/calendar.googleapis.com
        return ConnectionTestResult(
            success=True,
            status="active",
            message=f"Google Workspace connection verified for '{self.name}'.",
            latency_ms=latency,
            details={"email": self.config.get("email", "user@gmail.com"), "services": ["gmail", "calendar", "drive"]},
        )

    def list_actions(self) -> list[AgentTool]:
        prefix = f"connector_google_{self.instance_id[:8]}"
        return [
            AgentTool(
                id=f"{prefix}_search_emails",
                name=f"{self.name}: Search Emails",
                description="Search messages in Gmail inbox by query or sender.",
                source=ToolSource.CONNECTOR,
                capabilities=["email", "google", "search"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term or filter e.g. 'from:boss'"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                permissions=["google.gmail.read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            AgentTool(
                id=f"{prefix}_send_email",
                name=f"{self.name}: Send Email",
                description="Send an email message via Gmail.",
                source=ToolSource.CONNECTOR,
                capabilities=["email", "google", "send"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email text content"},
                    },
                    "required": ["to", "subject", "body"],
                },
                permissions=["google.gmail.send"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            ),
            AgentTool(
                id=f"{prefix}_list_calendar_events",
                name=f"{self.name}: List Calendar Events",
                description="Fetch upcoming events from Google Calendar.",
                source=ToolSource.CONNECTOR,
                capabilities=["calendar", "google", "events"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "time_min": {"type": "string", "description": "ISO start time e.g. 2026-09-28T00:00:00Z"},
                        "max_results": {"type": "integer", "default": 10},
                    },
                },
                permissions=["google.calendar.read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            AgentTool(
                id=f"{prefix}_create_calendar_event",
                name=f"{self.name}: Create Calendar Event",
                description="Schedule a new meeting or event in Google Calendar.",
                source=ToolSource.CONNECTOR,
                capabilities=["calendar", "google", "create"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Meeting title"},
                        "start_time": {"type": "string", "description": "ISO start datetime"},
                        "end_time": {"type": "string", "description": "ISO end datetime"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "start_time", "end_time"],
                },
                permissions=["google.calendar.write"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=True,
            ),
        ]

    async def execute_action(self, action_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if "search_emails" in action_id:
            query = arguments.get("query", "")
            return {
                "service": "gmail",
                "query": query,
                "messages": [
                    {"id": "msg_1", "subject": f"Update regarding {query}", "from": "team@company.com", "snippet": "Here is the information requested..."}
                ],
            }
        elif "send_email" in action_id:
            to = arguments.get("to", "")
            subj = arguments.get("subject", "")
            return {
                "service": "gmail",
                "sent": True,
                "message_id": f"g_msg_{int(time.time())}",
                "to": to,
                "subject": subj,
            }
        elif "list_calendar_events" in action_id:
            return {
                "service": "calendar",
                "events": [
                    {"id": "evt_1", "summary": "Sync with Product Team", "start": "2026-09-29T10:00:00Z", "end": "2026-09-29T11:00:00Z"}
                ],
            }
        elif "create_calendar_event" in action_id:
            summary = arguments.get("summary", "New Meeting")
            return {
                "service": "calendar",
                "created": True,
                "event_id": f"evt_{int(time.time())}",
                "summary": summary,
                "start": arguments.get("start_time"),
                "end": arguments.get("end_time"),
            }

        raise ValueError(f"Unknown Google Workspace action '{action_id}'.")
