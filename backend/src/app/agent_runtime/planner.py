"""Agent Runtime Planner for ROXY-AI 2.0.

Decomposes high-level user objectives into sequential operational steps
with dynamic tool discovery from the Central Tool Registry.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool

log = structlog.get_logger()


class AgentPlanner:
    """Plans and decomposes tasks into executable milestones and tool dispatches."""

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()

    async def create_plan(
        self,
        objective: str,
        context: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Formulate a step-by-step execution plan for an objective."""
        ctx = context or {}
        discovered_tools = self._tool_registry.discover_for_task(objective, user_id=user_id)
        tool_ids = {t.id: t for t in discovered_tools}

        # Attempt deterministic planning first for guaranteed precision
        deterministic_plan = self._deterministic_decomposition(objective, tool_ids, ctx)
        if deterministic_plan:
            return deterministic_plan

        # Fallback to general tool-backed plan
        return self._build_default_plan(objective, discovered_tools, ctx)

    def _deterministic_decomposition(
        self,
        objective: str,
        available_tools: dict[str, AgentTool],
        ctx: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        """Parse structured goals using pattern matching for math, search, email, schedule, and multi-step combinations."""
        text = objective.strip()
        lower = text.lower()

        # Multi-step: Search AND Email
        if ("search" in lower or "find" in lower or "look up" in lower) and ("email" in lower or "mail" in lower or "send" in lower):
            # Extract email recipient if present
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
            to_addr = email_match.group(0) if email_match else "recipient@example.com"

            # Clean query for search
            q = re.sub(r"(?i)and\s+(?:then\s+)?(?:email|send).*$", "", text).strip()
            q = re.sub(r"(?i)^(?:please\s+)?(?:search(?:\s+for)?|find|look up)\s+", "", q).strip()
            if not q:
                q = objective

            return [
                {
                    "step_number": 1,
                    "description": f"Search the web for '{q}'",
                    "tool_id": "system_web_search",
                    "tool_input": {"query": q, "max_results": 5},
                    "depends_on": [],
                },
                {
                    "step_number": 2,
                    "description": f"Send compiled search results to {to_addr}",
                    "tool_id": "system_email_send",
                    "tool_input": {
                        "to": to_addr,
                        "subject": f"Research Summary: {q}",
                        "body": f"Here are the verified research results for '{q}'.",
                    },
                    "depends_on": [1],
                },
            ]

        # Multi-step: Calculate AND Store Memory
        if ("calculate" in lower or "compute" in lower or "math" in lower) and ("remember" in lower or "save" in lower or "store" in lower):
            math_match = re.search(r"[\d\s\+\-\*\/\^\(\)\.]+", text)
            expr = math_match.group(0).strip() if math_match else "10 * 5"
            return [
                {
                    "step_number": 1,
                    "description": f"Calculate expression '{expr}'",
                    "tool_id": "system_calculator",
                    "tool_input": {"expression": expr},
                    "depends_on": [],
                },
                {
                    "step_number": 2,
                    "description": "Store calculated result in memory",
                    "tool_id": "system_memory_store",
                    "tool_input": {"key": "calculation_result", "value": f"Result of {expr}"},
                    "depends_on": [1],
                },
            ]

        # Single-intent: Email send
        if lower.startswith("email ") or lower.startswith("send email") or "send an email" in lower:
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
            to_addr = email_match.group(0) if email_match else "user@example.com"
            subject = "Notification from ROXY Assistant"
            body = text
            sub_match = re.search(r"subject\s*[:\"']\s*([^\"'\n]+)", text, re.IGNORECASE)
            if sub_match:
                subject = sub_match.group(1).strip()
            return [
                {
                    "step_number": 1,
                    "description": f"Dispatch email to {to_addr}",
                    "tool_id": "system_email_send",
                    "tool_input": {"to": to_addr, "subject": subject, "body": body},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calculator / Math
        if lower.startswith("calculate ") or lower.startswith("what is ") and any(op in text for op in ["+", "-", "*", "/", "^"]):
            expr = re.sub(r"(?i)^(?:calculate|what is|compute)\s+", "", text).replace("?", "").strip()
            if "system_calculator" in available_tools or self._tool_registry.get("system_calculator"):
                return [
                    {
                        "step_number": 1,
                        "description": f"Evaluate arithmetic expression '{expr}'",
                        "tool_id": "system_calculator",
                        "tool_input": {"expression": expr},
                        "depends_on": [],
                    }
                ]

        # Single-intent: Web search
        if lower.startswith("search ") or lower.startswith("search for ") or lower.startswith("google ") or lower.startswith("find out "):
            q = re.sub(r"(?i)^(?:search(?:\s+for)?|google|find out)\s+", "", text).strip()
            return [
                {
                    "step_number": 1,
                    "description": f"Search web sources for '{q}'",
                    "tool_id": "system_web_search",
                    "tool_input": {"query": q, "max_results": 5},
                    "depends_on": [],
                }
            ]

        # Single-intent: Schedule job / reminder
        if lower.startswith("schedule ") or lower.startswith("remind me ") or "set a reminder" in lower:
            return [
                {
                    "step_number": 1,
                    "description": f"Schedule task or reminder for '{text}'",
                    "tool_id": "system_schedule_job",
                    "tool_input": {"title": text, "when": "specified time"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Safe Python code runner
        if lower.startswith("run python") or lower.startswith("execute python") or lower.startswith("python:"):
            code = re.sub(r"(?i)^(?:run python|execute python|python:)\s*", "", text).strip()
            return [
                {
                    "step_number": 1,
                    "description": "Execute sandboxed Python script",
                    "tool_id": "system_python_runner",
                    "tool_input": {"code": code, "language": "python"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Vault / Knowledge search
        if (
            lower.startswith("vault search")
            or lower.startswith("search vault")
            or "in my vault" in lower
            or "in knowledge base" in lower
            or "search documents" in lower
        ):
            q = re.sub(
                r"(?i)^(?:vault search|search vault|search documents(?: for)?|find in vault)\s*",
                "",
                text,
            ).strip()
            if not q:
                q = text
            tool_id = (
                "vault_search"
                if "vault_search" in available_tools or self._tool_registry.get("vault_search")
                else "system_document_query"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Search Knowledge Vault for '{q}'",
                    "tool_id": tool_id,
                    "tool_input": {"query": q, "top_k": 5},
                    "depends_on": [],
                }
            ]

        return None

    def _build_default_plan(
        self,
        objective: str,
        discovered_tools: list[AgentTool],
        ctx: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Construct fallback step plan matching best candidate tools."""
        if not discovered_tools:
            return [
                {
                    "step_number": 1,
                    "description": f"Analyze objective: {objective}",
                    "tool_id": None,
                    "tool_input": {"objective": objective},
                    "depends_on": [],
                }
            ]

        primary_tool = discovered_tools[0]
        # Construct input from objective
        first_input: dict[str, Any] = {}
        if "query" in primary_tool.input_schema.get("properties", {}):
            first_input["query"] = objective
        elif "expression" in primary_tool.input_schema.get("properties", {}):
            first_input["expression"] = objective
        elif "code" in primary_tool.input_schema.get("properties", {}):
            first_input["code"] = objective
        else:
            first_input = {"input": objective}

        return [
            {
                "step_number": 1,
                "description": f"Execute {primary_tool.name} for: {objective[:60]}",
                "tool_id": primary_tool.id,
                "tool_input": first_input,
                "depends_on": [],
            }
        ]
