"""Agent Runtime Planner for ROXY-AI 2.0.

Decomposes high-level user objectives into sequential operational steps
with dynamic tool discovery from the Central Tool Registry.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
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
        available_tools: dict[str, AgentTool] | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Parse structured goals using pattern matching for math, search, email, schedule, and multi-step combinations."""
        tools = available_tools or {}
        text = objective.strip()
        lower = text.lower()
        ctx_dict: dict[str, Any] = ctx or {}

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
            if "system_calculator" in tools or self._tool_registry.get("system_calculator"):
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
        if (
            (
                lower.startswith("schedule ")
                and not (
                    lower.startswith("schedule meeting")
                    or lower.startswith("schedule event")
                    or lower.startswith("schedule a meeting")
                    or lower.startswith("schedule an event")
                    or lower.startswith("schedule call")
                )
            )
            or lower.startswith("remind me ")
            or "set a reminder" in lower
        ):
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
                if "vault_search" in tools or self._tool_registry.get("vault_search")
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

        # Single-intent: Deep research & autonomous investigation
        if (
            lower.startswith("deep research")
            or lower.startswith("research ")
            or lower.startswith("investigate ")
            or "comprehensive analysis of" in lower
            or "deep investigation on" in lower
            or "conduct research on" in lower
        ):
            q = re.sub(
                r"(?i)^(?:deep research(?:\s+on|\s+into)?|research(?:\s+on|\s+into)?|investigate(?:\s+into)?|conduct research on)\s*",
                "",
                text,
            ).strip()
            if not q:
                q = text
            research_tool_id = (
                "research_deep_investigate"
                if "research_deep_investigate" in tools
                or self._tool_registry.get("research_deep_investigate")
                else "system_web_search"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Conduct autonomous deep research on '{q}'",
                    "tool_id": research_tool_id,
                    "tool_input": {"query": q, "depth": "deep", "save_report": True},
                    "depends_on": [],
                }
            ]

        # Single-intent: Browser screenshot
        if (
            lower.startswith("take screenshot of ")
            or lower.startswith("take a screenshot of ")
            or lower.startswith("screenshot ")
            or lower.startswith("capture screenshot of ")
            or lower.startswith("capture preview of ")
        ):
            target_url = re.sub(
                r"(?i)^(?:take\s+(?:a\s+)?screenshot\s+of|screenshot|capture\s+(?:a\s+)?(?:screenshot|preview)\s+of)\s*",
                "",
                text,
            ).strip()
            if not target_url.startswith(("http://", "https://")):
                target_url = f"https://{target_url}"
            tool_id = (
                "browser_screenshot"
                if "browser_screenshot" in tools or self._tool_registry.get("browser_screenshot")
                else "browser_navigate"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Capture screenshot preview of '{target_url}'",
                    "tool_id": tool_id,
                    "tool_input": {"url": target_url, "width": 1280, "height": 800},
                    "depends_on": [],
                }
            ]

        # Single-intent: Browser extract data / tables / links
        if (
            lower.startswith("extract tables from ")
            or lower.startswith("extract table from ")
            or lower.startswith("extract links from ")
            or lower.startswith("extract data from ")
            or lower.startswith("scrape tables from ")
            or lower.startswith("scrape table from ")
            or lower.startswith("scrape ")
        ):
            target_url = re.sub(
                r"(?i)^(?:extract\s+(?:tables?|links?|data)\s+from|scrape\s+(?:tables?|links?|data\s+from)?)\s*",
                "",
                text,
            ).strip()
            if not target_url.startswith(("http://", "https://")):
                target_url = f"https://{target_url}"
            extract_type = "tables" if "table" in lower else ("links" if "link" in lower else "all")
            tool_id = (
                "browser_extract"
                if "browser_extract" in tools or self._tool_registry.get("browser_extract")
                else "browser_navigate"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Extract {extract_type} from '{target_url}'",
                    "tool_id": tool_id,
                    "tool_input": {"url": target_url, "extract_type": extract_type, "max_items": 50},
                    "depends_on": [],
                }
            ]

        # Single-intent: Browser fill form / automated flow
        if (
            lower.startswith("fill form on ")
            or lower.startswith("fill out form on ")
            or lower.startswith("submit form on ")
            or lower.startswith("automate flow on ")
            or lower.startswith("automate browser on ")
        ):
            target_url = re.sub(
                r"(?i)^(?:fill\s+(?:out\s+)?form\s+on|submit\s+form\s+on|automate\s+(?:flow|browser)\s+on)\s*",
                "",
                text,
            ).strip()
            if not target_url.startswith(("http://", "https://")):
                target_url = f"https://{target_url}"
            tool_id = (
                "browser_execute_flow"
                if "browser_execute_flow" in tools or self._tool_registry.get("browser_execute_flow")
                else "browser_navigate"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Execute automated browser workflow on '{target_url}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "url": target_url,
                        "actions": [{"type": "fill_form", "fields": {}}],
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Browser navigate & inspect DOM
        if (
            lower.startswith("navigate to ")
            or lower.startswith("browse to ")
            or lower.startswith("open website ")
            or lower.startswith("visit website ")
            or lower.startswith("visit ")
            or lower.startswith("go to website ")
            or lower.startswith("inspect website ")
        ):
            target_url = re.sub(
                r"(?i)^(?:navigate\s+to|browse\s+to|open\s+website|visit\s+website|visit|go\s+to\s+website|inspect\s+website)\s*",
                "",
                text,
            ).strip()
            if not target_url.startswith(("http://", "https://")):
                target_url = f"https://{target_url}"
            tool_id = (
                "browser_navigate"
                if "browser_navigate" in tools or self._tool_registry.get("browser_navigate")
                else "system_web_search"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Navigate to '{target_url}' and inspect DOM structure",
                    "tool_id": tool_id,
                    "tool_input": {"url": target_url, "timeout_seconds": 30},
                    "depends_on": [],
                }
            ]

        # Single-intent: Billing credit wallet / balance query
        if (
            "how many credits" in lower
            or "credit balance" in lower
            or "check my wallet" in lower
            or "my wallet" in lower
            or "my ai credits" in lower
            or "check credits" in lower
            or "wallet balance" in lower
            or lower.startswith("show wallet")
            or lower.startswith("view wallet")
        ):
            tool_id = (
                "billing_get_wallet"
                if "billing_get_wallet" in tools or self._tool_registry.get("billing_get_wallet")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Retrieve current AI credit wallet balance and subscription status",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Billing list plans / pricing
        if (
            "pricing plan" in lower
            or "subscription plan" in lower
            or "how much is pro" in lower
            or "how much does pro cost" in lower
            or "compare plans" in lower
            or "list plans" in lower
            or lower.startswith("show plans")
            or lower.startswith("view plans")
            or lower.startswith("what plans")
        ):
            tool_id = (
                "billing_list_plans"
                if "billing_list_plans" in tools or self._tool_registry.get("billing_list_plans")
                else "system_web_search"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List available Roxy-AI subscription plans and top-up packages",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Billing upgrade / subscribe checkout
        if (
            lower.startswith("upgrade to ")
            or lower.startswith("subscribe to ")
            or lower.startswith("buy subscription")
            or lower.startswith("checkout plan")
            or lower.startswith("checkout ")
            or "upgrade my plan" in lower
            or "upgrade to pro" in lower
            or "subscribe to pro" in lower
            or "upgrade to team" in lower
            or "subscribe to team" in lower
        ):
            plan_id = "team" if "team" in lower else "pro"
            curr = "pkr" if "pkr" in lower or "rupee" in lower else "usd"
            tool_id = (
                "billing_create_checkout"
                if "billing_create_checkout" in tools or self._tool_registry.get("billing_create_checkout")
                else "system_web_search"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Generate checkout session for {plan_id.title()} plan in {curr.upper()}",
                    "tool_id": tool_id,
                    "tool_input": {"plan_id": plan_id, "currency": curr},
                    "depends_on": [],
                }
            ]

        # Single-intent: Billing top up credits
        if (
            "top up credits" in lower
            or "topup credits" in lower
            or "buy credits" in lower
            or "purchase credits" in lower
            or "add credits" in lower
            or "buy credit pack" in lower
            or lower.startswith("top up ")
            or lower.startswith("topup ")
        ):
            pack_id = "pack_20" if ("ultra" in lower or "20" in lower) else ("pack_5" if ("starter" in lower or "5" in lower) else "pack_10")
            curr = "pkr" if "pkr" in lower or "rupee" in lower else "usd"
            tool_id = (
                "billing_topup_credits"
                if "billing_topup_credits" in tools or self._tool_registry.get("billing_topup_credits")
                else "system_web_search"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Generate credit top-up checkout for {pack_id} in {curr.upper()}",
                    "tool_id": tool_id,
                    "tool_input": {"pack_id": pack_id, "currency": curr},
                    "depends_on": [],
                }
            ]

        # Single-intent: Billing invoices & billing history
        if (
            "billing history" in lower
            or "my invoices" in lower
            or "show invoices" in lower
            or "view invoices" in lower
            or "payment history" in lower
            or "my receipts" in lower
            or "past payments" in lower
        ):
            tool_id = (
                "billing_get_invoices"
                if "billing_get_invoices" in tools or self._tool_registry.get("billing_get_invoices")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Retrieve billing invoices and payment transaction history",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Billing cancel subscription
        if (
            "cancel my subscription" in lower
            or "cancel subscription" in lower
            or "cancel pro" in lower
            or "stop subscription" in lower
            or "end subscription" in lower
        ):
            tool_id = (
                "billing_cancel_subscription"
                if "billing_cancel_subscription" in tools or self._tool_registry.get("billing_cancel_subscription")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Cancel active subscription at period end (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Delete Project (requires confirmation)
        if (
            lower.startswith("delete project ")
            or lower.startswith("remove project ")
            or "delete workspace project" in lower
        ):
            proj_id = re.sub(r"(?i)^(?:delete\s+(?:workspace\s+)?project|remove\s+(?:workspace\s+)?project)\s*", "", text).strip().strip("'\"")
            tool_id = (
                "workspace_delete_project"
                if "workspace_delete_project" in tools or self._tool_registry.get("workspace_delete_project")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Permanently delete workspace project '{proj_id}' (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Create Task
        if (
            lower.startswith("create task ")
            or lower.startswith("add task ")
            or lower.startswith("new task ")
            or "add a task" in lower
            or "create a task" in lower
        ):
            proj_match = re.search(r"(?i)(?:in|to|for)\s+project\s+([a-zA-Z0-9_\-]+)", text)
            proj_id = proj_match.group(1) if proj_match else (ctx_dict.get("project_id", "default_proj"))
            clean_title = re.sub(r"(?i)^(?:create|add|new)\s+(?:a\s+)?task\s*", "", text)
            clean_title = re.sub(r"(?i)\s+(?:in|to|for)\s+project\s+[a-zA-Z0-9_\-]+.*$", "", clean_title).strip().strip("'\"")
            if not clean_title:
                clean_title = "New Task"
            tool_id = (
                "workspace_create_task"
                if "workspace_create_task" in tools or self._tool_registry.get("workspace_create_task")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Create task '{clean_title}' in project '{proj_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id, "title": clean_title, "status": "todo", "priority": "medium"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Update Task / Complete Task
        if (
            lower.startswith("update task ")
            or lower.startswith("complete task ")
            or lower.startswith("mark task ")
            or "mark task done" in lower
            or "mark task complete" in lower
        ):
            proj_match = re.search(r"(?i)(?:in|for)\s+project\s+([a-zA-Z0-9_\-]+)", text)
            proj_id = proj_match.group(1) if proj_match else (ctx_dict.get("project_id", "default_proj"))
            task_match = re.search(r"(?:task[-_][a-zA-Z0-9]+|[a-zA-Z0-9_\-]+)", re.sub(r"(?i)^(?:update|complete|mark)\s+task\s*", "", text).strip())
            task_id = task_match.group(0) if task_match else "task_1"
            new_status = "done" if ("done" in lower or "complete" in lower or "finish" in lower) else ("in_progress" if "in progress" in lower else "todo")
            tool_id = (
                "workspace_update_task"
                if "workspace_update_task" in tools or self._tool_registry.get("workspace_update_task")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Update task '{task_id}' in project '{proj_id}' to status '{new_status}'",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id, "task_id": task_id, "status": new_status},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Link Document
        if (
            lower.startswith("link document ")
            or lower.startswith("attach document ")
            or "link document to project" in lower
            or "attach document to project" in lower
        ):
            proj_match = re.search(r"(?i)(?:to|in)\s+project\s+([a-zA-Z0-9_\-]+)", text)
            proj_id = proj_match.group(1) if proj_match else (ctx_dict.get("project_id", "default_proj"))
            doc_match = re.search(r"(?:doc[-_][a-zA-Z0-9]+|[a-zA-Z0-9_\-]+)", re.sub(r"(?i)^(?:link|attach)\s+document\s*", "", text).strip())
            doc_id = doc_match.group(0) if doc_match else "doc_1"
            tool_id = (
                "workspace_link_document"
                if "workspace_link_document" in tools or self._tool_registry.get("workspace_link_document")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Link document '{doc_id}' to project '{proj_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id, "document_id": doc_id, "title": f"Document {doc_id}"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Create Project
        if (
            lower.startswith("create project ")
            or lower.startswith("new project ")
            or lower.startswith("add project ")
            or "create a project" in lower
            or "create new project" in lower
        ):
            name = re.sub(r"(?i)^(?:create\s+(?:a\s+)?(?:new\s+)?project|new\s+project|add\s+project)\s*", "", text).strip().strip("'\"")
            if not name:
                name = "New Workspace Project"
            tool_id = (
                "workspace_create_project"
                if "workspace_create_project" in tools or self._tool_registry.get("workspace_create_project")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Create new workspace project '{name}'",
                    "tool_id": tool_id,
                    "tool_input": {"name": name, "description": "", "status": "active"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Project Details
        if (
            lower.startswith("project details for ")
            or lower.startswith("view project ")
            or lower.startswith("get project ")
            or lower.startswith("inspect project ")
            or "project details" in lower
        ):
            proj_id = re.sub(r"(?i)^(?:project\s+details(?:\s+for)?|view\s+project|get\s+project|inspect\s+project)\s*", "", text).strip().strip("'\"")
            if not proj_id or proj_id.lower() == "project details":
                proj_id = ctx_dict.get("project_id", "default_proj")
            tool_id = (
                "workspace_get_project"
                if "workspace_get_project" in tools or self._tool_registry.get("workspace_get_project")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Retrieve details for project '{proj_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - List Projects / Overview
        if (
            "list projects" in lower
            or "my workspace projects" in lower
            or "show projects" in lower
            or "show my projects" in lower
            or "view projects" in lower
            or "workspace projects" in lower
            or "workspace overview" in lower
            or "workspace summary" in lower
            or lower.startswith("projects")
        ):
            tool_id = (
                "workspace_list_projects"
                if "workspace_list_projects" in tools or self._tool_registry.get("workspace_list_projects")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List all workspace projects and summary metrics",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Image Studio - Delete Artwork (requires confirmation)
        if (
            lower.startswith("delete image ")
            or lower.startswith("remove image ")
            or lower.startswith("delete artwork ")
            or "delete generated image" in lower
        ):
            img_id = re.sub(r"(?i)^(?:delete\s+(?:image|artwork)|remove\s+(?:image|artwork))\s*", "", text).strip().strip("'\"")
            tool_id = (
                "image_delete_generation"
                if "image_delete_generation" in tools or self._tool_registry.get("image_delete_generation")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Delete artwork '{img_id}' from gallery (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"image_id": img_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Image Studio - Save / Export to Knowledge Vault
        if (
            lower.startswith("save image to vault")
            or lower.startswith("export image to vault")
            or lower.startswith("export artwork to vault")
            or "save artwork to vault" in lower
            or "export to knowledge vault" in lower
        ):
            img_id = re.sub(r"(?i)^(?:save\s+(?:image|artwork)\s+to\s+vault|export\s+(?:image|artwork)\s+to\s+(?:knowledge\s+)?vault)\s*", "", text).strip().strip("'\"")
            if not img_id:
                img_id = ctx_dict.get("image_id", "default_img")
            tool_id = (
                "image_export_to_vault"
                if "image_export_to_vault" in tools or self._tool_registry.get("image_export_to_vault")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Export artwork '{img_id}' to Knowledge Vault",
                    "tool_id": tool_id,
                    "tool_input": {"image_id": img_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Image Studio - Favorite Artwork
        if (
            lower.startswith("favorite image ")
            or lower.startswith("star image ")
            or "add image to favorites" in lower
        ):
            img_id = re.sub(r"(?i)^(?:favorite\s+image|star\s+image)\s*", "", text).strip().strip("'\"")
            if not img_id:
                img_id = ctx_dict.get("image_id", "default_img")
            tool_id = (
                "image_toggle_favorite"
                if "image_toggle_favorite" in tools or self._tool_registry.get("image_toggle_favorite")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Toggle favorite status on artwork '{img_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"image_id": img_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Image Studio - Enhance Prompt
        if (
            lower.startswith("enhance prompt ")
            or lower.startswith("improve prompt ")
            or lower.startswith("enhance image prompt ")
            or "enhance prompt" in lower
        ):
            clean_p = re.sub(r"(?i)^(?:enhance\s+(?:image\s+)?prompt|improve\s+(?:image\s+)?prompt)\s*", "", text).strip().strip("'\"")
            if not clean_p:
                clean_p = text
            tool_id = (
                "image_enhance_prompt"
                if "image_enhance_prompt" in tools or self._tool_registry.get("image_enhance_prompt")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Enhance image prompt '{clean_p[:40]}'",
                    "tool_id": tool_id,
                    "tool_input": {"prompt": clean_p, "style_preset": "photorealistic"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Image Studio - View / Inspect Artwork
        if (
            lower.startswith("view image ")
            or lower.startswith("inspect image ")
            or lower.startswith("image details for ")
            or lower.startswith("view artwork ")
        ):
            img_id = re.sub(r"(?i)^(?:view\s+image|inspect\s+image|image\s+details(?:\s+for)?|view\s+artwork)\s*", "", text).strip().strip("'\"")
            if not img_id:
                img_id = ctx_dict.get("image_id", "default_img")
            tool_id = (
                "image_get_generation"
                if "image_get_generation" in tools or self._tool_registry.get("image_get_generation")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Retrieve details for artwork '{img_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"image_id": img_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Image Studio - List Gallery
        if (
            "image gallery" in lower
            or "my image gallery" in lower
            or "show my artworks" in lower
            or "view my artworks" in lower
            or "list generated images" in lower
            or "my generated images" in lower
            or lower.startswith("show gallery")
            or lower.startswith("view gallery")
        ):
            tool_id = (
                "image_list_gallery"
                if "image_list_gallery" in tools or self._tool_registry.get("image_list_gallery")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List saved artworks in Image Studio gallery",
                    "tool_id": tool_id,
                    "tool_input": {"favorite_only": "favorite" in lower},
                    "depends_on": [],
                }
            ]

        # Single-intent: Image Studio - Generate Neural Image
        if (
            lower.startswith("generate image ")
            or lower.startswith("create image ")
            or lower.startswith("generate an image ")
            or lower.startswith("create an image ")
            or lower.startswith("draw ")
            or lower.startswith("paint ")
            or lower.startswith("generate picture of ")
            or lower.startswith("create picture of ")
            or lower.startswith("make an image of ")
            or lower.startswith("image of ")
        ):
            detected_style = "photorealistic"
            for st in ["cinematic", "anime", "cyberpunk", "3d_render", "oil_painting", "minimalist", "watercolor", "photorealistic"]:
                if st in lower or st.replace("_", " ") in lower:
                    detected_style = st
                    break

            detected_ratio = "1:1"
            if "16:9" in lower or "widescreen" in lower or "landscape" in lower:
                detected_ratio = "16:9"
            elif "9:16" in lower or "portrait" in lower or "story" in lower:
                detected_ratio = "9:16"

            clean_prompt = re.sub(
                r"(?i)^(?:generate\s+(?:an?\s+)?image(?:\s+of)?|create\s+(?:an?\s+)?image(?:\s+of)?|draw(?:\s+a|\s+an)?|paint(?:\s+a|\s+an)?|generate\s+picture\s+of|create\s+picture\s+of|make\s+an\s+image\s+of|image\s+of)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not clean_prompt:
                clean_prompt = text

            tool_id = (
                "image_generate"
                if "image_generate" in tools or self._tool_registry.get("image_generate")
                else "system_web_search"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Generate neural image for '{clean_prompt[:40]}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "prompt": clean_prompt,
                        "style_preset": detected_style,
                        "aspect_ratio": detected_ratio,
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Delete Event (requires confirmation)
        if (
            lower.startswith("delete calendar event ")
            or lower.startswith("delete event ")
            or lower.startswith("cancel calendar event ")
            or lower.startswith("cancel event ")
            or lower.startswith("remove calendar event ")
            or lower.startswith("remove event ")
            or "delete event" in lower
        ):
            event_id = re.sub(
                r"(?i)^(?:delete|cancel|remove)\s+(?:calendar\s+)?event\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not event_id:
                event_id = ctx_dict.get("event_id", "default_event")
            tool_id = (
                "calendar_delete_event"
                if "calendar_delete_event" in tools or self._tool_registry.get("calendar_delete_event")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Permanently delete calendar event '{event_id}' (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"event_id": event_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Upcoming Events
        if (
            "upcoming events" in lower
            or "upcoming meetings" in lower
            or "upcoming schedule" in lower
            or "what's next on my calendar" in lower
            or "what is next on my calendar" in lower
            or lower.startswith("upcoming events")
        ):
            tool_id = (
                "calendar_get_upcoming"
                if "calendar_get_upcoming" in tools or self._tool_registry.get("calendar_get_upcoming")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Retrieve upcoming calendar events and meetings",
                    "tool_id": tool_id,
                    "tool_input": {"days_ahead": 7},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Parse Prompt
        if (
            lower.startswith("parse event ")
            or lower.startswith("parse schedule ")
            or lower.startswith("parse calendar prompt ")
        ):
            raw_prompt = re.sub(
                r"(?i)^parse\s+(?:event|schedule|calendar\s+prompt)\s*",
                "",
                text,
            ).strip().strip("'\"")
            tool_id = (
                "calendar_parse_prompt"
                if "calendar_parse_prompt" in tools or self._tool_registry.get("calendar_parse_prompt")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Parse natural language event prompt '{raw_prompt[:40]}'",
                    "tool_id": tool_id,
                    "tool_input": {"prompt": raw_prompt},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - View Event Details
        if (
            lower.startswith("view event ")
            or lower.startswith("inspect event ")
            or lower.startswith("event details for ")
            or lower.startswith("get event ")
        ):
            event_id = re.sub(
                r"(?i)^(?:view|inspect|get)\s+event\s*|(?:event\s+details\s+(?:for\s+)?)",
                "",
                text,
            ).strip().strip("'\"")
            if not event_id:
                event_id = ctx_dict.get("event_id", "default_event")
            tool_id = (
                "calendar_get_event"
                if "calendar_get_event" in tools or self._tool_registry.get("calendar_get_event")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Retrieve details for calendar event '{event_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"event_id": event_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Update Event
        if (
            lower.startswith("update event ")
            or lower.startswith("reschedule event ")
            or lower.startswith("edit event ")
            or lower.startswith("update calendar event ")
        ):
            event_id = re.sub(
                r"(?i)^(?:update|reschedule|edit)\s+(?:calendar\s+)?event\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not event_id:
                event_id = ctx_dict.get("event_id", "evt-1")
            tool_id = (
                "calendar_update_event"
                if "calendar_update_event" in tools or self._tool_registry.get("calendar_update_event")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Update calendar event '{event_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"event_id": event_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - List Calendar Events
        if (
            "show calendar" in lower
            or "view calendar" in lower
            or "my calendar" in lower
            or "list calendar events" in lower
            or "list events" in lower
            or "what is on my calendar" in lower
            or "what's on my calendar" in lower
            or "my schedule today" in lower
        ):
            detected_cat = None
            for cat in ["meeting", "hackathon", "deadline", "personal", "reminder"]:
                if cat in lower:
                    detected_cat = cat
                    break
            tool_id = (
                "calendar_list_events"
                if "calendar_list_events" in tools or self._tool_registry.get("calendar_list_events")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List events on user calendar",
                    "tool_id": tool_id,
                    "tool_input": {"category": detected_cat},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Create / Schedule Event
        if (
            lower.startswith("schedule meeting ")
            or lower.startswith("schedule event ")
            or lower.startswith("schedule a meeting ")
            or lower.startswith("schedule an event ")
            or lower.startswith("schedule ")
            or lower.startswith("book meeting ")
            or lower.startswith("create event ")
            or lower.startswith("add event ")
            or lower.startswith("create calendar event ")
        ):
            clean_title = re.sub(
                r"(?i)^(?:schedule\s+(?:a\s+|an\s+)?(?:meeting|event)?|book\s+meeting|create\s+(?:calendar\s+)?event|add\s+event)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not clean_title:
                clean_title = "Scheduled Meeting"
            tool_id = (
                "calendar_create_event"
                if "calendar_create_event" in tools or self._tool_registry.get("calendar_create_event")
                else "system_memory_store"
            )
            start_iso = (datetime.now(UTC) + timedelta(days=1)).replace(hour=14, minute=0, second=0).isoformat()
            return [
                {
                    "step_number": 1,
                    "description": f"Schedule calendar event '{clean_title[:40]}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "title": clean_title,
                        "start_time": start_iso,
                        "category": "meeting",
                    },
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
