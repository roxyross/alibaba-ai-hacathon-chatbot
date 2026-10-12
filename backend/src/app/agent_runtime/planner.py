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
        if (
            (
                lower.startswith("search ")
                or lower.startswith("search for ")
                or lower.startswith("google ")
                or lower.startswith("find out ")
            )
            and not (
                lower.startswith("search vault")
                or lower.startswith("search knowledge vault")
                or lower.startswith("search in vault")
                or lower.startswith("search in knowledge vault")
                or lower.startswith("search my vault")
            )
        ):
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

        # Single-intent & Multi-step: Workspace Coding & Terminal / Test Workflows
        if any(w in lower for w in ["run test", "run pytest", "execute tests", "test project", "test suite"]):
            target_path = ""
            m_path = re.search(r"(?:tests?/|test_)\w+\.py", text)
            if m_path:
                target_path = m_path.group(0)
            return [
                {
                    "step_number": 1,
                    "description": f"Execute project test suite ({target_path or 'all tests'})",
                    "tool_id": "project_test_run",
                    "tool_input": {"project_path": ".", "test_path": target_path},
                    "depends_on": [],
                }
            ]

        if lower.startswith("run terminal") or lower.startswith("exec command") or lower.startswith("terminal:"):
            cmd = re.sub(r"(?i)^(?:run terminal(?: command)?|exec command|terminal:)\s*", "", text).strip()
            return [
                {
                    "step_number": 1,
                    "description": f"Execute sandboxed terminal command '{cmd}'",
                    "tool_id": "terminal_run",
                    "tool_input": {"command": cmd, "cwd": "."},
                    "depends_on": [],
                }
            ]

        if "git status" in lower or "git diff" in lower or "git commit" in lower:
            if "diff" in lower:
                return [
                    {
                        "step_number": 1,
                        "description": "Inspect Git unified diff for workspace modifications",
                        "tool_id": "git_diff",
                        "tool_input": {"repo_path": "."},
                        "depends_on": [],
                    }
                ]
            if "commit" in lower:
                m_msg = re.search(r"['\"]([^'\"]+)['\"]", text)
                msg_val = m_msg.group(1) if m_msg else "Update project files via Roxy Coding Agent"
                return [
                    {
                        "step_number": 1,
                        "description": f"Create Git commit: '{msg_val}'",
                        "tool_id": "git_commit",
                        "tool_input": {"message": msg_val, "repo_path": ".", "add_all": True},
                        "depends_on": [],
                    }
                ]
            return [
                {
                    "step_number": 1,
                    "description": "Inspect Git source control status of workspace",
                    "tool_id": "git_status",
                    "tool_input": {"repo_path": "."},
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
            (
                lower.startswith("take screenshot of ")
                or lower.startswith("take a screenshot of ")
                or lower.startswith("screenshot ")
                or lower.startswith("capture screenshot of ")
                or lower.startswith("capture preview of ")
            )
            and not any(w in lower for w in ["desktop", "my screen", "my desktop", "computer", "display", "pc"])
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
            or "my credits" in lower
            or "ai credits" in lower
            or "check credits" in lower
            or "check my credits" in lower
            or "wallet balance" in lower
            or "my token usage" in lower
            or "token usage" in lower
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

        # Single-intent: Personal Finance - Financial Summary & Net Worth
        if (
            "financial summary" in lower
            or "finance summary" in lower
            or "my finances" in lower
            or "show my finances" in lower
            or "net worth" in lower
            or "what is my net worth" in lower
            or "how much money do i have" in lower
            or "my spending summary" in lower
            or "spending overview" in lower
            or "spending burn rate" in lower
            or lower.startswith("show finances")
            or lower.startswith("view finances")
        ):
            tool_id = (
                "finance_get_summary"
                if "finance_get_summary" in tools or self._tool_registry.get("finance_get_summary")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Calculate total net worth, dual-currency balances, and monthly spending burn rate",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Personal Finance - List Accounts
        if (
            "my bank accounts" in lower
            or "my accounts" in lower
            or "list accounts" in lower
            or "show accounts" in lower
            or "bank accounts" in lower
            or "connected accounts" in lower
            or "list my bank accounts" in lower
            or "list financial accounts" in lower
            or lower.startswith("show bank accounts")
            or lower.startswith("view bank accounts")
        ):
            tool_id = (
                "finance_list_accounts"
                if "finance_list_accounts" in tools or self._tool_registry.get("finance_list_accounts")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Retrieve list of all connected financial and bank accounts",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Personal Finance - Disconnect / Delete Account (requires confirmation)
        if (
            lower.startswith("delete account ")
            or lower.startswith("remove account ")
            or lower.startswith("disconnect account ")
            or lower.startswith("delete bank account ")
            or lower.startswith("disconnect bank account ")
        ):
            acc_id = re.sub(
                r"(?i)^(?:delete|remove|disconnect)\s+(?:bank\s+)?account\s*",
                "",
                text,
            ).strip().strip("'\"")
            tool_id = (
                "finance_delete_account"
                if "finance_delete_account" in tools or self._tool_registry.get("finance_delete_account")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Disconnect financial account '{acc_id}' and purge ledger (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"account_id": acc_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Personal Finance - Get Account Details
        if (
            lower.startswith("get account ")
            or lower.startswith("show account ")
            or lower.startswith("view account ")
            or "account details for " in lower
            or "account details " in lower
        ):
            acc_id = re.sub(
                r"(?i)^(?:get\s+account|show\s+account|view\s+account|account\s+details(?:\s+for)?)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if acc_id:
                tool_id = (
                    "finance_get_account"
                    if "finance_get_account" in tools or self._tool_registry.get("finance_get_account")
                    else "system_memory_retrieve"
                )
                return [
                    {
                        "step_number": 1,
                        "description": f"Retrieve details and recent transactions for account '{acc_id}'",
                        "tool_id": tool_id,
                        "tool_input": {"account_id": acc_id},
                        "depends_on": [],
                    }
                ]

        # Single-intent: Personal Finance - Record / Log Transaction or Expense
        if (
            lower.startswith("record expense ")
            or lower.startswith("record transaction ")
            or lower.startswith("log expense ")
            or lower.startswith("log transaction ")
            or lower.startswith("add expense ")
            or lower.startswith("add transaction ")
            or lower.startswith("track expense ")
        ):
            clean_cmd = re.sub(r"(?i)^(?:record|log|add|track)\s+(?:expense|transaction)\s*", "", text).strip()
            amt_match = re.search(r"(\$|rs\.?|pkr)?\s*([0-9]+(?:\.[0-9]+)?)\s*(usd|pkr|dollars|rupees)?", clean_cmd, re.I)
            amount_val = 0.0
            currency = "USD"
            if amt_match:
                amount_val = float(amt_match.group(2))
                raw_curr = (amt_match.group(1) or amt_match.group(3) or "").lower()
                if "rs" in raw_curr or "pkr" in raw_curr or "rupee" in raw_curr:
                    currency = "PKR"

            cat_match = re.search(r"(?:for|category|under)\s+([a-zA-Z0-9_\-]+)", clean_cmd, re.I)
            category = cat_match.group(1).lower() if cat_match else "general"

            tool_id = (
                "finance_record_transaction"
                if "finance_record_transaction" in tools or self._tool_registry.get("finance_record_transaction")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Record transaction of {amount_val} {currency} under '{category}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "account_id": "acc_default",
                        "description": clean_cmd,
                        "amount_usd": amount_val if currency == "USD" else round(amount_val / 280.0, 2),
                        "amount_pkr": round(amount_val * 280.0, 2) if currency == "USD" else amount_val,
                        "category": category,
                        "transaction_type": "debit",
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Personal Finance - List Transactions / Expense History
        if (
            "list transactions" in lower
            or "show transactions" in lower
            or "recent transactions" in lower
            or "my transactions" in lower
            or "recent expenses" in lower
            or "show spending" in lower
            or "spending history" in lower
            or "expense history" in lower
            or "show expense ledger" in lower
            or "transaction history" in lower
            or lower.startswith("show transactions")
            or lower.startswith("view transactions")
        ):
            tool_id = (
                "finance_list_transactions"
                if "finance_list_transactions" in tools or self._tool_registry.get("finance_list_transactions")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Retrieve financial transaction history and spending ledger",
                    "tool_id": tool_id,
                    "tool_input": {"limit": 50},
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

        # Single-intent: Cowork Workspace - Delete Artifact (requires confirmation)
        if (
            lower.startswith("delete artifact ")
            or lower.startswith("remove artifact ")
            or "delete cowork artifact" in lower
        ):
            artifact_id = re.sub(
                r"(?i)^(?:delete\s+(?:cowork\s+)?artifact|remove\s+(?:cowork\s+)?artifact)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not artifact_id:
                artifact_id = ctx_dict.get("artifact_id", "art_1")
            tool_id = (
                "cowork_delete_artifact"
                if "cowork_delete_artifact" in tools or self._tool_registry.get("cowork_delete_artifact")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Delete artifact '{artifact_id}' from workspace (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"artifact_id": artifact_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Cowork Workspace - Render Diagram
        if (
            lower.startswith("render diagram ")
            or lower.startswith("create diagram ")
            or lower.startswith("generate diagram ")
            or lower.startswith("generate mermaid diagram ")
            or lower.startswith("draw architecture diagram ")
            or "render architecture diagram" in lower
            or "render mermaid diagram" in lower
        ):
            clean_title = re.sub(
                r"(?i)^(?:render\s+(?:architecture\s+|mermaid\s+)?diagram|create\s+(?:architecture\s+|mermaid\s+)?diagram|generate\s+(?:architecture\s+|mermaid\s+)?diagram|draw\s+architecture\s+diagram)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not clean_title:
                clean_title = "System Architecture Diagram"
            diag_type = "svg" if ("svg" in lower or "vector" in lower) else "mermaid"
            tool_id = (
                "cowork_render_diagram"
                if "cowork_render_diagram" in tools or self._tool_registry.get("cowork_render_diagram")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Generate {diag_type} diagram '{clean_title[:40]}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "title": clean_title,
                        "diagram_type": diag_type,
                        "description": text,
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Cowork Workspace - Refine Artifact with AI
        if (
            lower.startswith("refine artifact ")
            or lower.startswith("revise artifact ")
            or lower.startswith("improve artifact ")
            or lower.startswith("refine document ")
            or lower.startswith("revise document ")
            or "refine artifact with ai" in lower
        ):
            target_match = re.search(r"(?:art[-_][a-zA-Z0-9]+|[a-zA-Z0-9_\-]+)", re.sub(r"(?i)^(?:refine|revise|improve)\s+(?:artifact|document)\s*", "", text).strip())
            art_id = target_match.group(0) if target_match else (ctx_dict.get("artifact_id", "art_1"))
            instruction = text
            tool_id = (
                "cowork_refine_artifact"
                if "cowork_refine_artifact" in tools or self._tool_registry.get("cowork_refine_artifact")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Refine artifact '{art_id}' using AI iterative assistant",
                    "tool_id": tool_id,
                    "tool_input": {
                        "artifact_id": art_id,
                        "instruction": instruction,
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Cowork Workspace - Update Artifact
        if (
            lower.startswith("update artifact ")
            or lower.startswith("edit artifact ")
            or lower.startswith("modify artifact ")
        ):
            target_match = re.search(r"(?:art[-_][a-zA-Z0-9]+|[a-zA-Z0-9_\-]+)", re.sub(r"(?i)^(?:update|edit|modify)\s+artifact\s*", "", text).strip())
            art_id = target_match.group(0) if target_match else (ctx_dict.get("artifact_id", "art_1"))
            tool_id = (
                "cowork_update_artifact"
                if "cowork_update_artifact" in tools or self._tool_registry.get("cowork_update_artifact")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Update content and metadata for artifact '{art_id}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "artifact_id": art_id,
                        "change_summary": text,
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Cowork Workspace - View / Inspect Artifact
        if (
            lower.startswith("view artifact ")
            or lower.startswith("get artifact ")
            or lower.startswith("inspect artifact ")
            or lower.startswith("artifact details for ")
            or "artifact details" in lower
        ):
            art_id = re.sub(
                r"(?i)^(?:view\s+artifact|get\s+artifact|inspect\s+artifact|artifact\s+details(?:\s+for)?)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not art_id or art_id.lower() == "artifact details":
                art_id = ctx_dict.get("artifact_id", "art_1")
            tool_id = (
                "cowork_get_artifact"
                if "cowork_get_artifact" in tools or self._tool_registry.get("cowork_get_artifact")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Retrieve details and versions for artifact '{art_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"artifact_id": art_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Cowork Workspace - List Artifacts
        if (
            "list artifacts" in lower
            or "show artifacts" in lower
            or "view artifacts" in lower
            or "my artifacts" in lower
            or "workspace artifacts" in lower
            or "cowork artifacts" in lower
            or "all artifacts" in lower
            or lower.startswith("artifacts")
        ):
            tool_id = (
                "cowork_list_artifacts"
                if "cowork_list_artifacts" in tools or self._tool_registry.get("cowork_list_artifacts")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List all cowork workspace artifacts and current versions",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Cowork Workspace - Create Artifact / Document / Report
        if (
            lower.startswith("create artifact ")
            or lower.startswith("new artifact ")
            or lower.startswith("create document ")
            or lower.startswith("draft document ")
            or lower.startswith("generate report ")
            or lower.startswith("create code artifact ")
            or "create a new artifact" in lower
            or "generate document" in lower
        ):
            clean_title = re.sub(
                r"(?i)^(?:create\s+(?:a\s+)?(?:new\s+)?artifact|new\s+artifact|create\s+(?:a\s+)?document|draft\s+document|generate\s+report|create\s+code\s+artifact|generate\s+document)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not clean_title:
                clean_title = "Workspace Artifact"
            art_type = "markdown"
            if "code" in lower or "python" in lower or "script" in lower:
                art_type = "code"
            elif "diagram" in lower or "mermaid" in lower:
                art_type = "mermaid"
            elif "svg" in lower:
                art_type = "svg"

            tool_id = (
                "cowork_create_artifact"
                if "cowork_create_artifact" in tools or self._tool_registry.get("cowork_create_artifact")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Create {art_type} artifact '{clean_title[:40]}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "title": clean_title,
                        "artifact_type": art_type,
                        "content": f"# {clean_title}\n\nGenerated by Cowork Task Workspace.",
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Device Agent - Close / Terminate Application (destructive - requires confirmation)
        if (
            lower.startswith("close app ")
            or lower.startswith("kill app ")
            or lower.startswith("terminate app ")
            or lower.startswith("close application ")
            or lower.startswith("kill process ")
            or lower.startswith("terminate process ")
            or lower.startswith("stop app ")
            or "terminate running application" in lower
        ):
            target_app = re.sub(
                r"(?i)^(?:close\s+(?:app|application)?|kill\s+(?:app|application|process)?|terminate\s+(?:app|application|process)?|stop\s+app)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not target_app:
                target_app = ctx_dict.get("app_name", "app")
            tool_id = (
                "device_close_app"
                if "device_close_app" in tools or self._tool_registry.get("device_close_app")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Terminate application '{target_app}' (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"app_name": target_app, "force": "force" in lower or "kill" in lower},
                    "depends_on": [],
                }
            ]

        # Single-intent: Device Agent - Capture Screen / Screenshot
        if (
            "screenshot" in lower
            or "screen capture" in lower
            or "capture screen" in lower
            or "grab screen" in lower
            or "capture desktop" in lower
            or "take a screenshot" in lower
            or "take screenshot" in lower
        ):
            tool_id = (
                "device_capture_screen"
                if "device_capture_screen" in tools or self._tool_registry.get("device_capture_screen")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Capture a live screenshot of the user's desktop display",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Device Agent - Focus Application Window
        if (
            lower.startswith("focus app ")
            or lower.startswith("focus window ")
            or lower.startswith("focus ")
            or "bring to front" in lower
            or "switch to window" in lower
        ):
            target_app = re.sub(
                r"(?i)^(?:focus\s+(?:app|window)?|switch\s+to\s+window)\s*",
                "",
                text,
            )
            target_app = re.sub(r"(?i)\s+to\s+(?:the\s+)?front.*$", "", target_app).strip().strip("'\"")
            if not target_app:
                target_app = ctx_dict.get("app_name", "app")
            tool_id = (
                "device_focus_app"
                if "device_focus_app" in tools or self._tool_registry.get("device_focus_app")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Bring window for '{target_app}' to the foreground",
                    "tool_id": tool_id,
                    "tool_input": {"app_name": target_app},
                    "depends_on": [],
                }
            ]

        # Single-intent: Multi-Device Fleet Summary & Inventory
        if (
            "devices are online" in lower
            or "list my devices" in lower
            or "list devices" in lower
            or "show my fleet" in lower
            or "show fleet" in lower
            or "fleet summary" in lower
            or "status of my devices" in lower
            or "my connected devices" in lower
        ):
            tool_id = (
                "device_fleet_summary"
                if "device_fleet_summary" in tools or self._tool_registry.get("device_fleet_summary")
                else "device_list_apps"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Query multi-device fleet health and application inventory",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Media Playback & App Control on Multi-Device Fleet
        if lower.startswith("play ") and (" on " in lower or " in " in lower or len(lower.split()) >= 2):
            try:
                from app.device.intent_parser import DeviceIntentParser, DeviceIntentType
                parsed_intent = DeviceIntentParser.parse(text)
                if parsed_intent.intent_type == DeviceIntentType.APP_CONTROL:
                    tool_id = (
                        "device_fleet_execute"
                        if "device_fleet_execute" in tools or self._tool_registry.get("device_fleet_execute")
                        else "device_orchestrate_app_control"
                    )
                    return [
                        {
                            "step_number": 1,
                            "description": f"Execute '{parsed_intent.capability}' for '{parsed_intent.application}' across fleet (target: {parsed_intent.target_device_hint or 'auto'})",
                            "tool_id": tool_id,
                            "tool_input": {
                                "application": parsed_intent.application,
                                "capability": parsed_intent.capability,
                                "parameters": parsed_intent.parameters,
                                "preferred_device_id": parsed_intent.target_device_hint,
                                "allow_failover": True,
                            },
                            "depends_on": [],
                        }
                    ]
            except Exception:
                pass

        # Single-intent: Device Agent - List Installed & Running Apps
        if (
            "list apps" in lower
            or "list installed apps" in lower
            or "show my apps" in lower
            or "what apps are installed" in lower
            or "running applications" in lower
            or "installed applications" in lower
            or "show installed applications" in lower
            or lower.startswith("apps on my computer")
        ):
            detected_category = "all"
            for cat in ["browser", "development", "productivity", "media", "utilities"]:
                if cat in lower:
                    detected_category = cat
                    break
            tool_id = (
                "device_list_apps"
                if "device_list_apps" in tools or self._tool_registry.get("device_list_apps")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"List installed and running applications (category: {detected_category})",
                    "tool_id": tool_id,
                    "tool_input": {"category": detected_category},
                    "depends_on": [],
                }
            ]

        # Single-intent: Device Agent - Open / Launch Application
        if (
            lower.startswith("open app ")
            or lower.startswith("launch app ")
            or lower.startswith("start app ")
            or lower.startswith("open application ")
            or lower.startswith("launch application ")
            or lower.startswith("start application ")
            or lower.startswith("open ")
            or lower.startswith("launch ")
            or lower.startswith("start ")
        ):
            target_app = re.sub(
                r"(?i)^(?:open\s+(?:app|application)?|launch\s+(?:app|application)?|start\s+(?:app|application)?)\s*",
                "",
                text,
            ).strip().strip("'\"")
            # Filter out non-app phrases
            non_app_words = [
                "project", "task", "file", "diagram", "artifact", "document",
                "report", "calendar", "meeting", "event", "session", "chat",
                "p2p", "webrtc", "stream", "continuity", "handover",
            ]
            if (
                target_app
                and not any(w in target_app.lower() for w in ("p2p", "webrtc", "stream", "session", "handover"))
                and not any(target_app.lower().startswith(w) for w in non_app_words)
            ):
                tool_id = (
                    "device_open_app"
                    if "device_open_app" in tools or self._tool_registry.get("device_open_app")
                    else "system_memory_store"
                )
                return [
                    {
                        "step_number": 1,
                        "description": f"Launch desktop application '{target_app}'",
                        "tool_id": tool_id,
                        "tool_input": {"app_name": target_app, "arguments": []},
                        "depends_on": [],
                    }
                ]

        # Single-intent: Knowledge Vault - Delete Document (destructive - requires confirmation)
        if (
            lower.startswith("delete vault document ")
            or lower.startswith("remove vault document ")
            or lower.startswith("delete document from vault ")
            or "delete from knowledge vault" in lower
        ):
            doc_id = re.sub(
                r"(?i)^(?:delete\s+vault\s+document|remove\s+vault\s+document|delete\s+document\s+from\s+vault|delete\s+from\s+knowledge\s+vault)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not doc_id:
                doc_id = ctx_dict.get("document_id", "doc_1")
            tool_id = (
                "vault_delete_document"
                if "vault_delete_document" in tools or self._tool_registry.get("vault_delete_document")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Delete document '{doc_id}' from Knowledge Vault (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"document_id": doc_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Knowledge Vault - Store Knowledge / Save Note
        if (
            lower.startswith("save note in vault")
            or lower.startswith("save note to vault")
            or lower.startswith("store note in vault")
            or lower.startswith("store in vault")
            or lower.startswith("add to vault")
            or lower.startswith("store knowledge")
            or lower.startswith("save in knowledge vault")
            or lower.startswith("save note in knowledge vault")
        ):
            clean_content = re.sub(
                r"(?i)^(?:save\s+note\s+(?:in|to)\s+(?:knowledge\s+)?vault|store\s+(?:note\s+)?in\s+vault|add\s+to\s+vault|store\s+knowledge|save\s+in\s+knowledge\s+vault)[:\s]*",
                "",
                text,
            ).strip()
            title = clean_content[:30].strip() if clean_content else "Knowledge Note"
            tool_id = (
                "vault_store_knowledge"
                if "vault_store_knowledge" in tools or self._tool_registry.get("vault_store_knowledge")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Store knowledge record '{title}' in Knowledge Vault",
                    "tool_id": tool_id,
                    "tool_input": {"title": title, "content": clean_content or text, "folder": "Notes"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Knowledge Vault - Read / Inspect Document
        if (
            lower.startswith("read vault document ")
            or lower.startswith("inspect vault document ")
            or lower.startswith("view vault document ")
            or lower.startswith("get vault document ")
        ):
            doc_id = re.sub(
                r"(?i)^(?:read|inspect|view|get)\s+vault\s+document\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not doc_id:
                doc_id = ctx_dict.get("document_id", "doc_1")
            tool_id = (
                "vault_read_document"
                if "vault_read_document" in tools or self._tool_registry.get("vault_read_document")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Retrieve and read Knowledge Vault document '{doc_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"document_id": doc_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Knowledge Vault - List Documents
        if (
            "list vault documents" in lower
            or "show vault documents" in lower
            or "view vault documents" in lower
            or "my knowledge vault" in lower
            or "list knowledge vault" in lower
            or "vault documents" in lower
            or lower.startswith("list vault")
            or lower.startswith("show vault")
        ):
            tool_id = (
                "vault_list_documents"
                if "vault_list_documents" in tools or self._tool_registry.get("vault_list_documents")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List documents and folders indexed in the Knowledge Vault",
                    "tool_id": tool_id,
                    "tool_input": {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Knowledge Vault - Search / RAG
        if (
            lower.startswith("search vault for ")
            or lower.startswith("search knowledge vault for ")
            or lower.startswith("search vault ")
            or lower.startswith("query vault ")
            or lower.startswith("find in vault ")
            or "search my vault" in lower
            or "search in knowledge vault" in lower
        ):
            q = re.sub(
                r"(?i)^(?:search\s+(?:knowledge\s+)?vault(?:\s+for)?|query\s+vault|find\s+in\s+vault)\s*",
                "",
                text,
            ).strip()
            tool_id = (
                "vault_search"
                if "vault_search" in tools or self._tool_registry.get("vault_search")
                else "system_document_query"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Perform semantic vector search in Knowledge Vault for '{q}'",
                    "tool_id": tool_id,
                    "tool_input": {"query": q, "top_k": 5},
                    "depends_on": [],
                }
            ]

        # ---------------------------------------------------------------------
        # Phase 7: Projects, Tasks, Automations & Workflow Scheduler
        # ---------------------------------------------------------------------

        # Single-intent: Workspace Hub - Delete Project (destructive - requires confirmation)
        if (
            lower.startswith("delete project ")
            or lower.startswith("remove project ")
            or lower.startswith("delete workspace project ")
            or "delete project" in lower
        ):
            proj_id = re.sub(
                r"(?i)^(?:delete\s+(?:workspace\s+)?project|remove\s+(?:workspace\s+)?project)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not proj_id:
                proj_id = ctx_dict.get("project_id", "proj_1")
            tool_id = (
                "workspace_delete_project"
                if "workspace_delete_project" in tools or self._tool_registry.get("workspace_delete_project")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Delete workspace project '{proj_id}' (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Create Task in Project
        if (
            lower.startswith("create task ")
            or lower.startswith("add task ")
            or "create task in project" in lower
            or "add task to project" in lower
        ):
            task_title = text
            proj_id = ctx_dict.get("project_id", "default_proj")
            m = re.search(r"(?i)(?:create|add)\s+task\s+['\"]?(.+?)['\"]?\s+(?:in|to)\s+project\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", text)
            if m:
                task_title = m.group(1).strip()
                proj_id = m.group(2).strip()
            else:
                task_title = re.sub(r"(?i)^(?:create\s+task|add\s+task)\s*", "", text).strip()
            tool_id = (
                "workspace_create_task"
                if "workspace_create_task" in tools or self._tool_registry.get("workspace_create_task")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Add task '{task_title}' to workspace project '{proj_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id, "title": task_title, "status": "todo", "priority": "medium"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Update Task Status
        if (
            lower.startswith("update task ")
            or lower.startswith("mark task ")
            or lower.startswith("complete task ")
        ):
            status = "done" if ("complete" in lower or "done" in lower) else "in_progress"
            task_id = re.sub(r"(?i)^(?:update\s+task|mark\s+task|complete\s+task)\s*", "", text)
            task_id = re.sub(r"(?i)\s+(?:as\s+)?(?:done|complete|in_progress|todo)\s*$", "", task_id).strip().strip("'\"")
            proj_id = ctx_dict.get("project_id", "default_proj")
            tool_id = (
                "workspace_update_task"
                if "workspace_update_task" in tools or self._tool_registry.get("workspace_update_task")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Update workspace task '{task_id}' status to '{status}'",
                    "tool_id": tool_id,
                    "tool_input": {"project_id": proj_id, "task_id": task_id, "status": status},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - Create Project
        if (
            lower.startswith("create project ")
            or lower.startswith("new project ")
            or lower.startswith("create workspace project ")
            or lower.startswith("start project ")
        ):
            name = re.sub(r"(?i)^(?:create\s+(?:workspace\s+)?project|new\s+project|start\s+project)\s*", "", text).strip().strip("'\"")
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
                    "tool_input": {"name": name, "description": f"Project {name}", "status": "active"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Workspace Hub - List Projects
        if (
            "list projects" in lower
            or "show projects" in lower
            or "my projects" in lower
            or "workspace projects" in lower
            or lower.startswith("list workspace")
            or lower.startswith("show workspace")
        ):
            tool_id = (
                "workspace_list_projects"
                if "workspace_list_projects" in tools or self._tool_registry.get("workspace_list_projects")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List workspace projects, milestones, and task counts",
                    "tool_id": tool_id,
                    "tool_input": {"status": "all"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Delete Event (destructive - requires confirmation)
        if (
            lower.startswith("delete calendar event ")
            or lower.startswith("cancel calendar event ")
            or lower.startswith("delete event ")
            or lower.startswith("cancel event ")
        ):
            event_id = re.sub(
                r"(?i)^(?:delete\s+calendar\s+event|cancel\s+calendar\s+event|delete\s+event|cancel\s+event)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not event_id:
                event_id = ctx_dict.get("event_id", "event_1")
            tool_id = (
                "calendar_delete_event"
                if "calendar_delete_event" in tools or self._tool_registry.get("calendar_delete_event")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Delete calendar event '{event_id}' (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"event_id": event_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Schedule Meeting / Event
        if (
            lower.startswith("schedule meeting")
            or lower.startswith("schedule event")
            or lower.startswith("schedule a meeting")
            or lower.startswith("schedule an event")
            or lower.startswith("schedule call")
            or lower.startswith("book meeting")
            or lower.startswith("set up meeting")
        ):
            tool_id = (
                "calendar_create_event"
                if "calendar_create_event" in tools or self._tool_registry.get("calendar_create_event")
                else "system_schedule_job"
            )
            from app.calendar.service import CalendarService
            parsed = CalendarService.get_instance().parse_event_from_prompt(text)
            return [
                {
                    "step_number": 1,
                    "description": f"Schedule calendar event '{parsed['title']}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "title": parsed["title"],
                        "start_time": parsed["start_time"],
                        "end_time": parsed["end_time"],
                        "category": parsed.get("category", "meeting"),
                        "location": parsed.get("location"),
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Calendar - Upcoming Events
        if (
            "upcoming events" in lower
            or "upcoming meetings" in lower
            or "what's next on my calendar" in lower
            or "what is on my calendar" in lower
            or lower.startswith("calendar upcoming")
        ):
            tool_id = (
                "calendar_get_upcoming"
                if "calendar_get_upcoming" in tools or self._tool_registry.get("calendar_get_upcoming")
                else "system_schedule_job"
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

        # Single-intent: Calendar - List Events
        if (
            "list calendar events" in lower
            or "show calendar events" in lower
            or "show my calendar" in lower
            or "view calendar" in lower
        ):
            tool_id = (
                "calendar_list_events"
                if "calendar_list_events" in tools or self._tool_registry.get("calendar_list_events")
                else "system_schedule_job"
            )
            return [
                {
                    "step_number": 1,
                    "description": "List scheduled calendar events",
                    "tool_id": tool_id,
                    "tool_input": {"limit": 50},
                    "depends_on": [],
                }
            ]

        # Single-intent: Scheduled Jobs - Delete Job (destructive - requires confirmation)
        if (
            lower.startswith("delete scheduled job ")
            or lower.startswith("delete automation ")
            or lower.startswith("remove scheduled job ")
            or lower.startswith("delete job ")
        ):
            job_id = re.sub(
                r"(?i)^(?:delete\s+scheduled\s+job|delete\s+automation|remove\s+scheduled\s+job|delete\s+job)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not job_id:
                job_id = ctx_dict.get("job_id", "job_1")
            tool_id = (
                "scheduler_delete_job"
                if "scheduler_delete_job" in tools or self._tool_registry.get("scheduler_delete_job")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Delete scheduled job '{job_id}' (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"job_id": job_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Scheduled Jobs - Run Job Now
        if (
            lower.startswith("run job ")
            or lower.startswith("run scheduled job ")
            or lower.startswith("execute scheduled job ")
            or lower.startswith("trigger job ")
        ):
            job_id = re.sub(
                r"(?i)^(?:run\s+scheduled\s+job|execute\s+scheduled\s+job|run\s+job|trigger\s+job)\s*",
                "",
                text,
            )
            job_id = re.sub(r"(?i)\s+now$", "", job_id).strip().strip("'\"")
            if not job_id:
                job_id = ctx_dict.get("job_id", "job_1")
            tool_id = (
                "scheduler_run_job_now"
                if "scheduler_run_job_now" in tools or self._tool_registry.get("scheduler_run_job_now")
                else "system_schedule_job"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Immediately execute scheduled job '{job_id}'",
                    "tool_id": tool_id,
                    "tool_input": {"job_id": job_id},
                    "depends_on": [],
                }
            ]

        # Single-intent: Scheduled Jobs - Pause or Resume Job
        if (
            lower.startswith("pause scheduled job ")
            or lower.startswith("pause job ")
            or lower.startswith("resume scheduled job ")
            or lower.startswith("resume job ")
        ):
            status = "Pause" if "pause" in lower else "Active"
            job_id = re.sub(
                r"(?i)^(?:pause\s+scheduled\s+job|pause\s+job|resume\s+scheduled\s+job|resume\s+job)\s*",
                "",
                text,
            ).strip().strip("'\"")
            if not job_id:
                job_id = ctx_dict.get("job_id", "job_1")
            tool_id = (
                "scheduler_update_job_status"
                if "scheduler_update_job_status" in tools or self._tool_registry.get("scheduler_update_job_status")
                else "system_schedule_job"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Update scheduled job '{job_id}' status to '{status}'",
                    "tool_id": tool_id,
                    "tool_input": {"job_id": job_id, "status": status},
                    "depends_on": [],
                }
            ]

        # Single-intent: Scheduled Jobs - List Jobs / Automations
        if (
            "list scheduled jobs" in lower
            or "show scheduled jobs" in lower
            or "list automations" in lower
            or "show automations" in lower
            or "list scheduled tasks" in lower
            or "my scheduled jobs" in lower
        ):
            tool_id = (
                "scheduler_list_jobs"
                if "scheduler_list_jobs" in tools or self._tool_registry.get("scheduler_list_jobs")
                else "system_schedule_job"
            )
        # ---------------------------------------------------------------------
        # Phase 10: Zia Tutor AI (Adaptive Personalized Learning Engine)
        # ---------------------------------------------------------------------

        # Single-intent: Zia Tutor - Reset Study Progress (destructive - requires confirmation)
        if (
            lower.startswith("reset study progress")
            or lower.startswith("reset progress for deck ")
            or lower.startswith("reset deck ")
            or lower.startswith("delete study deck ")
            or lower.startswith("delete deck ")
            or "reset my study progress" in lower
        ):
            deck_id = None
            delete_deck = "delete" in lower
            m = re.search(r"(?:deck\s+)?([a-zA-Z0-9_\-]+)$", text)
            if m and not lower.endswith("study progress") and not lower.endswith("my study progress"):
                deck_id = m.group(1).strip()
            if not deck_id:
                deck_id = ctx_dict.get("deck_id")

            tool_id = (
                "tutor_reset_progress"
                if "tutor_reset_progress" in tools or self._tool_registry.get("tutor_reset_progress")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"{'Delete' if delete_deck else 'Reset'} study progress{' for deck ' + deck_id if deck_id else ''} back to Leitner Box 1 (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {"deck_id": deck_id, "delete_deck": delete_deck},
                    "depends_on": [],
                }
            ]

        # Single-intent: Zia Tutor - Create Study Plan / Curriculum
        if (
            lower.startswith("create study plan for ")
            or lower.startswith("generate study plan for ")
            or lower.startswith("make a study plan for ")
            or lower.startswith("study plan for ")
            or lower.startswith("curriculum for ")
            or lower.startswith("create curriculum for ")
            or ("study plan" in lower and ("create" in lower or "generate" in lower or "build" in lower))
        ):
            topic = re.sub(
                r"(?i)^(?:create\s+(?:a\s+)?study\s+plan\s+(?:for\s+)?|generate\s+(?:a\s+)?study\s+plan\s+(?:for\s+)?|make\s+a\s+study\s+plan\s+(?:for\s+)?|study\s+plan\s+for\s+|curriculum\s+for\s+|create\s+curriculum\s+for\s+)",
                "",
                text,
            ).strip().strip("'\"")
            if not topic or "study plan" in topic.lower():
                topic = re.sub(r"(?i)(?:create|generate|build|make)\s+(?:a\s+)?study\s+plan\s*(?:for\s*)?", "", text).strip()
            if not topic:
                topic = "General Knowledge"

            tool_id = (
                "tutor_create_study_plan"
                if "tutor_create_study_plan" in tools or self._tool_registry.get("tutor_create_study_plan")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Generate adaptive study plan and initial deck for '{topic}'",
                    "tool_id": tool_id,
                    "tool_input": {"topic": topic, "difficulty": "intermediate", "target_days": 7},
                    "depends_on": [],
                }
            ]

        # Single-intent: Zia Tutor - Generate Practice Quiz
        if (
            lower.startswith("generate quiz on ")
            or lower.startswith("create quiz on ")
            or lower.startswith("generate quiz for ")
            or lower.startswith("create quiz for ")
            or lower.startswith("quiz me on ")
            or lower.startswith("practice quiz on ")
            or lower.startswith("quiz on ")
            or "generate quiz" in lower
            or "practice quiz" in lower
        ):
            topic = re.sub(
                r"(?i)^(?:generate\s+(?:a\s+)?quiz\s+(?:on|for)\s+|create\s+(?:a\s+)?quiz\s+(?:on|for)\s+|quiz\s+me\s+on\s+|practice\s+quiz\s+(?:on|for)\s+|quiz\s+on\s+)",
                "",
                text,
            ).strip().strip("'\"")
            if not topic:
                topic = "General Subject"

            tool_id = (
                "tutor_generate_quiz"
                if "tutor_generate_quiz" in tools or self._tool_registry.get("tutor_generate_quiz")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Generate practice quiz questions on '{topic}'",
                    "tool_id": tool_id,
                    "tool_input": {"topic": topic, "count": 5, "difficulty": "medium"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Zia Tutor - Create Flashcards
        if (
            lower.startswith("create flashcards for ")
            or lower.startswith("generate flashcards for ")
            or lower.startswith("make flashcards for ")
            or lower.startswith("flashcards for ")
            or "create flashcards" in lower
            or "generate flashcards" in lower
        ):
            topic = re.sub(
                r"(?i)^(?:create\s+flashcards\s+(?:for\s+)?|generate\s+flashcards\s+(?:for\s+)?|make\s+flashcards\s+(?:for\s+)?|flashcards\s+for\s+)",
                "",
                text,
            ).strip().strip("'\"")
            if not topic:
                topic = "Study Notes"

            tool_id = (
                "tutor_create_flashcards"
                if "tutor_create_flashcards" in tools or self._tool_registry.get("tutor_create_flashcards")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Generate active-recall flashcards for '{topic}'",
                    "tool_id": tool_id,
                    "tool_input": {"topic": topic, "count": 5, "level": "intermediate"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Zia Tutor - Topic Mastery & Learning Progress
        if (
            "topic mastery" in lower
            or "study mastery" in lower
            or "my study progress" in lower
            or "learning progress" in lower
            or "study stats" in lower
            or "show study stats" in lower
            or "what is my mastery" in lower
            or lower.startswith("mastery on ")
            or lower.startswith("mastery for ")
        ):
            topic = None
            m = re.search(r"(?:mastery\s+(?:on|for)\s+)(.+)$", text, re.I)
            if m:
                topic = m.group(1).strip()
            tool_id = (
                "tutor_get_topic_mastery"
                if "tutor_get_topic_mastery" in tools or self._tool_registry.get("tutor_get_topic_mastery")
                else "system_memory_retrieve"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Retrieve topic mastery and study progress{' for ' + topic if topic else ''}",
                    "tool_id": tool_id,
                    "tool_input": {"topic": topic} if topic else {},
                    "depends_on": [],
                }
            ]

        # Single-intent: Zia Tutor - Evaluate Answer / Review Flashcard
        if (
            lower.startswith("evaluate answer")
            or lower.startswith("review card ")
            or lower.startswith("tutor evaluate")
        ):
            is_correct = "incorrect" not in lower and "wrong" not in lower
            card_id = None
            m = re.search(r"(?:card\s+)?([a-zA-Z0-9_\-]+)$", text)
            if m and not lower.endswith("evaluate answer"):
                card_id = m.group(1).strip()
            if not card_id:
                card_id = ctx_dict.get("card_id")

            tool_id = (
                "tutor_evaluate_answer"
                if "tutor_evaluate_answer" in tools or self._tool_registry.get("tutor_evaluate_answer")
                else "system_memory_store"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Evaluate answer and update Leitner progression{' for card ' + card_id if card_id else ''}",
                    "tool_id": tool_id,
                    "tool_input": {"is_correct": is_correct, "card_id": card_id, "user_answer": text},
                    "depends_on": [],
                }
            ]

        # ---------------------------------------------------------------------
        # Phase 11: Cross-Device Continuity, P2P WebRTC & Matter IoT Layer
        # ---------------------------------------------------------------------

        # Single-intent: Cross-Device Session Handover
        if (
            lower.startswith("handover session to ")
            or lower.startswith("handover to ")
            or lower.startswith("transfer chat to ")
            or lower.startswith("transfer session to ")
            or lower.startswith("transfer this session to ")
            or ("transfer" in lower and "to" in lower)
            or ("handover" in lower and "to" in lower)
            or lower.startswith("continue this on ")
            or lower.startswith("continue chat on ")
            or (lower.startswith("switch to ") and any(w in lower for w in ("device", "phone", "macbook", "laptop", "desktop", "tablet", "ipad", "iphone")))
        ):
            target_dev = re.sub(
                r"(?i)^(?:handover\s+(?:(?:this\s+)?session\s+)?to\s+|transfer\s+(?:(?:this\s+)?chat|(?:this\s+)?session)?\s*(?:to\s*)?|continue\s+(?:this|chat)\s+on\s+|switch\s+to\s+)",
                "",
                text,
            ).strip().strip("'\"")
            target_dev = re.sub(r"^(?:my|the)\s+", "", target_dev, flags=re.I).strip()
            if not target_dev:
                target_dev = "Companion Device"

            tool_id = (
                "device_fleet_handover"
                if "device_fleet_handover" in tools or self._tool_registry.get("device_fleet_handover")
                else ("device_handover_session" if "device_handover_session" in tools or self._tool_registry.get("device_handover_session") else "device_list_apps")
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Transfer active session and context to '{target_dev}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "target_device_id": target_dev,
                        "application": "session",
                        "capability": "resume_task",
                        "session_id": str(ctx_dict.get("session_id", "active_session")),
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: P2P WebRTC Peer Signaling
        if (
            lower.startswith("start p2p stream with ")
            or lower.startswith("start webrtc with ")
            or lower.startswith("initiate webrtc with ")
            or lower.startswith("webrtc connection to ")
            or "p2p stream" in lower
            or "webrtc connection" in lower
        ):
            target_peer = re.sub(
                r"(?i)^(?:start\s+(?:p2p\s+stream|webrtc)\s+with\s+|initiate\s+webrtc\s+with\s+|webrtc\s+connection\s+to\s+)",
                "",
                text,
            ).strip().strip("'\"")
            if not target_peer or target_peer.lower() in ("p2p stream", "webrtc"):
                target_peer = "Target Device"

            tool_id = (
                "webrtc_signal_exchange"
                if "webrtc_signal_exchange" in tools or self._tool_registry.get("webrtc_signal_exchange")
                else "device_list_apps"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Initiate WebRTC P2P signaling connection with '{target_peer}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "target_device_id": target_peer,
                        "signal_type": "offer",
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Matter & Zigbee IoT Device Discovery
        if (
            lower.startswith("discover iot devices")
            or lower.startswith("scan for iot devices")
            or lower.startswith("scan for smart home devices")
            or lower.startswith("discover matter devices")
            or lower.startswith("discover smart home devices")
            or "discover smart devices" in lower
            or "find smart home devices" in lower
            or "scan smart home" in lower
            or "list smart devices" in lower
            or "list iot devices" in lower
        ):
            tool_id = (
                "iot_discover_devices"
                if "iot_discover_devices" in tools or self._tool_registry.get("iot_discover_devices")
                else "device_list_apps"
            )
            return [
                {
                    "step_number": 1,
                    "description": "Scan and discover connected Matter & Zigbee IoT devices",
                    "tool_id": tool_id,
                    "tool_input": {"protocol": "all", "device_type": "all"},
                    "depends_on": [],
                }
            ]

        # Single-intent: Smart Lock Control (Security / Destructive - requires confirmation!)
        if (
            (lower.startswith("unlock ") and any(w in lower for w in ("door", "lock", "gate")))
            or (lower.startswith("lock ") and any(w in lower for w in ("door", "lock", "gate")))
            or "unlock front door" in lower
            or "lock front door" in lower
            or "disarm front door lock" in lower
            or "unlock door" in lower
            or "lock door" in lower
        ):
            is_unlock = any(w in lower for w in ("unlock", "disarm", "open"))
            action = "unlock" if is_unlock else "lock"

            lock_name = "Front Door Smart Lock"
            if "garage" in lower:
                lock_name = "Garage Door Lock"
            elif "back door" in lower:
                lock_name = "Back Door Lock"

            tool_id = (
                "iot_lock_control"
                if "iot_lock_control" in tools or self._tool_registry.get("iot_lock_control")
                else "device_close_app"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"{action.capitalize()} smart security perimeter '{lock_name}' (requires user confirmation)",
                    "tool_id": tool_id,
                    "tool_input": {
                        "device_name": lock_name,
                        "action": action,
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Matter & Zigbee IoT Appliance Control
        if (
            lower.startswith("turn on ")
            or lower.startswith("turn off ")
            or lower.startswith("switch on ")
            or lower.startswith("switch off ")
            or lower.startswith("toggle ")
            or lower.startswith("set thermostat to ")
            or lower.startswith("set temperature to ")
            or lower.startswith("set brightness to ")
            or ("thermostat" in lower and ("set" in lower or "change" in lower or "heat" in lower or "cool" in lower))
        ):
            command = "toggle"
            parameters: dict[str, Any] = {}

            if lower.startswith("turn on ") or lower.startswith("switch on "):
                command = "turn_on"
                dev_name = re.sub(r"(?i)^(?:turn|switch)\s+on\s+", "", text).strip().strip("'\"")
            elif lower.startswith("turn off ") or lower.startswith("switch off "):
                command = "turn_off"
                dev_name = re.sub(r"(?i)^(?:turn|switch)\s+off\s+", "", text).strip().strip("'\"")
            elif lower.startswith("toggle "):
                command = "toggle"
                dev_name = re.sub(r"(?i)^toggle\s+", "", text).strip().strip("'\"")
            elif "thermostat" in lower or "temperature" in lower:
                command = "set_temperature"
                dev_name = "Office Thermostat"
                temp_match = re.search(r"(\d+(?:\.\d+)?)", text)
                if temp_match:
                    parameters["temperature"] = float(temp_match.group(1))
            elif "brightness" in lower:
                command = "set_brightness"
                dev_name = "Living Room Main Light"
                b_match = re.search(r"(\d+)%?", text)
                if b_match:
                    parameters["brightness"] = int(b_match.group(1))
            else:
                dev_name = text

            if not dev_name:
                dev_name = "Living Room Main Light"

            tool_id = (
                "iot_control_device"
                if "iot_control_device" in tools or self._tool_registry.get("iot_control_device")
                else "device_open_app"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Send command '{command}' to IoT device '{dev_name}'",
                    "tool_id": tool_id,
                    "tool_input": {
                        "device_name": dev_name,
                        "command": command,
                        "parameters": parameters,
                    },
                    "depends_on": [],
                }
            ]

        # Single-intent: Matter & Zigbee IoT Telemetry / State Query
        if (
            (lower.startswith("check ") and any(w in lower for w in ("temperature", "thermostat", "light", "plug", "sensor", "status", "lock")))
            or (lower.startswith("is the ") and any(w in lower for w in ("on", "off", "open", "locked")))
            or lower.startswith("get status of ")
            or lower.startswith("status of ")
            or "what is the temperature" in lower
            or "check smart home" in lower
        ):
            dev_name = "Office Thermostat" if ("temperature" in lower or "thermostat" in lower) else "Living Room Main Light"
            if "plug" in lower:
                dev_name = "Kitchen Smart Plug"
            elif "sensor" in lower or "motion" in lower:
                dev_name = "Hallway Motion Sensor"
            elif "lock" in lower or "door" in lower:
                dev_name = "Front Door Smart Lock"

            tool_id = (
                "iot_get_device_state"
                if "iot_get_device_state" in tools or self._tool_registry.get("iot_get_device_state")
                else "device_list_apps"
            )
            return [
                {
                    "step_number": 1,
                    "description": f"Query real-time state and telemetry for '{dev_name}'",
                    "tool_id": tool_id,
                    "tool_input": {"device_name": dev_name},
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
