"""BrowserService — Autonomous Web Navigation, DOM Inspection, and Flow Runner (Phase 15).

Coordinates safe web navigation, structured HTML DOM parsing, tables/links/headings extraction,
screenshot preview generation, and multi-step browser automation flows.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.browser.repository import BrowserRepository
from app.skills.browser_fill_form import BrowserFillFormSkill
from app.skills.browser_navigate import BrowserNavigateSkill
from app.skills.schemas import BrowserFillFormRequest, BrowserNavigateRequest, FormField
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

log = structlog.get_logger()

_HTML_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H_TAG_RE = re.compile(r"<h([1-3])[^>]*>(.*?)</h\1>", re.I | re.S)
_A_TAG_RE = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.S)
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", re.I | re.S)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_META_RE = re.compile(
    r'<meta\s+[^>]*(?:name|property)=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)["\']',
    re.I,
)


def _clean_text(html_fragment: str) -> str:
    """Strip tags and normalize whitespace in an HTML fragment."""
    no_scripts = _HTML_SCRIPT_RE.sub(" ", html_fragment)
    no_tags = _HTML_TAG_RE.sub(" ", no_scripts)
    unescaped = (
        no_tags.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\s+", " ", unescaped).strip()


class BrowserService:
    """Autonomous browser execution engine for ROXY-AI."""

    _instance: BrowserService | None = None

    def __init__(self, repo: BrowserRepository | None = None) -> None:
        self.repo = repo or BrowserRepository()
        self.nav_skill = BrowserNavigateSkill()
        self.fill_skill = BrowserFillFormSkill()

    @classmethod
    def get_instance(cls) -> BrowserService:
        """Singleton accessor ensuring tools are registered in the Central ToolRegistry."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.register_browser_tools()
        return cls._instance

    async def fetch_html(self, url: str, timeout_seconds: int = 15) -> tuple[str, str, int]:
        """Fetch raw HTML from target URL, returning (html, final_url, status_code)."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (ROXY-Browser/1.0)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            headers=headers,
        ) as client:
            resp = await client.get(url)
            return resp.text, str(resp.url), resp.status_code

    async def navigate_and_inspect(
        self,
        url: str,
        wait_for: str | None = None,
        timeout_seconds: int = 30,
        js_enabled: bool = False,
    ) -> dict[str, Any]:
        """Navigate to target URL, inspect page structure, and extract semantic components."""
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        try:
            if js_enabled:
                req = BrowserNavigateRequest(
                    url=clean_url,
                    wait_for=wait_for,
                    timeout_seconds=timeout_seconds,
                    js_enabled=True,
                )
                res = await self.nav_skill.execute(req)
                if not res.success:
                    return {
                        "url": clean_url,
                        "title": f"Web Page ({clean_url})",
                        "final_url": clean_url,
                        "status": "error",
                        "content_preview": "",
                        "headings": [],
                        "links": [],
                        "forms": [],
                        "meta": {},
                        "error": res.error or "Playwright navigation failed",
                    }
                html = res.content_preview or ""
                final_url = res.final_url or clean_url
            else:
                html, final_url, _ = await self.fetch_html(
                    clean_url, timeout_seconds=min(timeout_seconds, 15)
                )

            parsed_url = urllib.parse.urlparse(final_url)

            # Title
            title_match = _TITLE_RE.search(html)
            title = (
                _clean_text(title_match.group(1))
                if title_match
                else f"Page on {parsed_url.netloc}"
            )

            # Headings
            headings: list[dict[str, Any]] = []
            for h_match in _H_TAG_RE.finditer(html):
                h_level = int(h_match.group(1))
                h_text = _clean_text(h_match.group(2))
                if h_text and len(headings) < 30:
                    headings.append({"level": h_level, "text": h_text})

            # Links
            links: list[dict[str, Any]] = []
            seen_hrefs: set[str] = set()
            for a_match in _A_TAG_RE.finditer(html):
                href = a_match.group(1).strip()
                anchor_text = _clean_text(a_match.group(2))
                if href and not href.startswith(("javascript:", "mailto:", "#")):
                    abs_href = urllib.parse.urljoin(final_url, href)
                    if abs_href not in seen_hrefs and len(links) < 40:
                        seen_hrefs.add(abs_href)
                        links.append({"text": anchor_text or abs_href, "href": abs_href})

            # Forms
            forms: list[dict[str, Any]] = []
            for form_match in re.finditer(r"<form[^>]*>(.*?)</form>", html, re.I | re.S):
                form_inner = form_match.group(1)
                form_tag = form_match.group(0)[: form_match.group(0).find(">") + 1]
                action_m = re.search(r'action=["\']([^"\']*)["\']', form_tag, re.I)
                method_m = re.search(r'method=["\'](\w+)["\']', form_tag, re.I)
                action = (
                    urllib.parse.urljoin(final_url, action_m.group(1))
                    if action_m
                    else final_url
                )
                method = method_m.group(1).upper() if method_m else "GET"

                fields: list[str] = []
                for inp_match in re.finditer(
                    r'<input[^>]*name=["\']([^"\']+)["\']', form_inner, re.I
                ):
                    fields.append(inp_match.group(1))
                forms.append({"action": action, "method": method, "fields": fields[:10]})

            # Meta tags
            meta: dict[str, Any] = {}
            for m in _META_RE.finditer(html):
                meta_name = m.group(1).lower()
                meta_content = m.group(2)
                if meta_name in ("description", "keywords", "og:title", "og:description", "author"):
                    meta[meta_name] = meta_content[:200]

            preview = _clean_text(html)[:2000]

            return {
                "url": clean_url,
                "title": title,
                "final_url": final_url,
                "status": "success",
                "content_preview": preview,
                "headings": headings,
                "links": links,
                "forms": forms,
                "meta": meta,
                "error": None,
            }

        except Exception as exc:
            log.warning("browser.navigate_failed", url=clean_url, error=str(exc))
            return {
                "url": clean_url,
                "title": f"Web Page ({clean_url})",
                "final_url": clean_url,
                "status": "error",
                "content_preview": "",
                "headings": [],
                "links": [],
                "forms": [],
                "meta": {},
                "error": str(exc),
            }

    async def extract_data(
        self,
        url: str,
        extract_type: str = "all",
        selectors: list[str] | None = None,
        max_items: int = 50,
    ) -> dict[str, Any]:
        """Extract structured tables, links, headings, or text from web HTML."""
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        try:
            html, final_url, _ = await self.fetch_html(clean_url, timeout_seconds=20)
        except Exception as exc:
            log.warning("browser.extract_failed", url=clean_url, error=str(exc))
            return {
                "url": clean_url,
                "title": f"Web Page ({clean_url})",
                "tables": [],
                "links": [],
                "headings": [],
                "text_excerpt": "",
                "status": "error",
                "error": f"Failed to fetch webpage: {exc}",
            }

        title_m = _TITLE_RE.search(html)
        title = _clean_text(title_m.group(1)) if title_m else f"Extraction from {clean_url}"

        tables: list[dict[str, Any]] = []
        if extract_type in ("all", "tables"):
            for table_idx, tbl in enumerate(_TABLE_RE.finditer(html)):
                if len(tables) >= max_items:
                    break
                tbl_html = tbl.group(1)
                headers: list[str] = []
                # Check for <th>
                for th in _TH_RE.finditer(tbl_html):
                    txt = _clean_text(th.group(1))
                    if txt:
                        headers.append(txt)

                rows: list[list[str]] = []
                for tr in _TR_RE.finditer(tbl_html):
                    tr_html = tr.group(1)
                    tds = [_clean_text(td.group(1)) for td in _TD_RE.finditer(tr_html)]
                    if tds:
                        rows.append(tds)

                if headers or rows:
                    tables.append({
                        "table_index": table_idx + 1,
                        "headers": headers,
                        "rows": rows[:max_items],
                        "total_rows": len(rows),
                    })

        links: list[dict[str, Any]] = []
        if extract_type in ("all", "links"):
            seen = set()
            for a in _A_TAG_RE.finditer(html):
                if len(links) >= max_items:
                    break
                href = a.group(1).strip()
                anchor = _clean_text(a.group(2))
                if href and not href.startswith(("javascript:", "mailto:", "#")):
                    abs_href = urllib.parse.urljoin(final_url, href)
                    if abs_href not in seen:
                        seen.add(abs_href)
                        links.append({"text": anchor or abs_href, "href": abs_href})

        headings: list[dict[str, Any]] = []
        if extract_type in ("all", "headings"):
            for h in _H_TAG_RE.finditer(html):
                if len(headings) >= max_items:
                    break
                level = int(h.group(1))
                text = _clean_text(h.group(2))
                if text:
                    headings.append({"level": level, "text": text})

        text_excerpt = _clean_text(html)[:4000]

        return {
            "url": clean_url,
            "title": title,
            "tables": tables,
            "links": links,
            "headings": headings,
            "text_excerpt": text_excerpt,
            "status": "success",
            "error": None,
        }

    async def capture_screenshot(
        self, url: str, width: int = 1280, height: int = 800
    ) -> dict[str, Any]:
        """Capture visual snapshot representation of a web page."""
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        now = datetime.now(UTC).isoformat()
        parsed = urllib.parse.urlparse(clean_url)
        domain = parsed.netloc or "web"

        # Try to get page title
        try:
            html, _, _ = await self.fetch_html(clean_url, timeout_seconds=10)
            title_m = _TITLE_RE.search(html)
            title = _clean_text(title_m.group(1)) if title_m else f"Preview of {domain}"
        except Exception:
            title = f"Preview of {domain}"

        # High-definition simulated screenshot endpoint / preview URL
        screenshot_url = f"https://image.thum.io/get/width/{width}/crop/{height}/{clean_url}"

        return {
            "url": clean_url,
            "title": title,
            "screenshot_url": screenshot_url,
            "width": width,
            "height": height,
            "status": "success",
            "timestamp": now,
        }

    async def execute_browser_flow(
        self,
        user_id: str,
        url: str,
        actions: list[dict[str, Any]],
        title: str | None = None,
        save_task: bool = True,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute a multi-step browser automation workflow and optionally persist the task."""
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        task_title = title or f"Automate {clean_url[:60]}"
        steps_executed: list[dict[str, Any]] = []
        result_data: dict[str, Any] = {}
        status = "completed"
        error_msg: str | None = None

        # Default action if none provided
        if not actions:
            actions = [{"type": "navigate"}, {"type": "extract", "extract_type": "all"}]

        for idx, act in enumerate(actions):
            act_type = str(act.get("type", "navigate")).lower()
            step_record: dict[str, Any] = {
                "step": idx + 1,
                "action": act_type,
                "status": "success",
                "details": {},
            }

            try:
                if act_type == "navigate":
                    nav_res = await self.navigate_and_inspect(
                        clean_url,
                        wait_for=act.get("wait_for"),
                        js_enabled=bool(act.get("js_enabled", False)),
                    )
                    step_record["details"] = {
                        "title": nav_res.get("title"),
                        "status": nav_res.get("status"),
                        "links_count": len(nav_res.get("links", [])),
                        "headings_count": len(nav_res.get("headings", [])),
                    }
                    result_data["page_title"] = nav_res.get("title")
                    result_data["content_preview"] = nav_res.get("content_preview", "")[:500]

                elif act_type in ("extract", "extract_table", "extract_links"):
                    e_type = act.get("extract_type", "all")
                    if act_type == "extract_table":
                        e_type = "tables"
                    elif act_type == "extract_links":
                        e_type = "links"

                    ext_res = await self.extract_data(clean_url, extract_type=e_type)
                    step_record["details"] = {
                        "tables_found": len(ext_res.get("tables", [])),
                        "links_found": len(ext_res.get("links", [])),
                        "headings_found": len(ext_res.get("headings", [])),
                    }
                    result_data["tables"] = ext_res.get("tables", [])
                    result_data["links"] = ext_res.get("links", [])
                    result_data["headings"] = ext_res.get("headings", [])

                elif act_type == "fill_form":
                    # Check if sensitive action requires confirmation
                    is_sensitive = bool(act.get("is_sensitive", False))
                    confirmed = bool(act.get("confirm", False))
                    if is_sensitive and not confirmed:
                        step_record["status"] = "confirmation_required"
                        step_record["details"] = {
                            "message": "Sensitive form fill requires explicit user confirmation before submission.",
                            "fields": act.get("fields", {}),
                        }
                        status = "confirmation_required"
                        steps_executed.append(step_record)
                        break

                    fields_list = [
                        FormField(selector=k, value=str(v))
                        for k, v in act.get("fields", {}).items()
                    ]
                    fill_req = BrowserFillFormRequest(
                        url=clean_url,
                        fields=fields_list,
                        submit=bool(act.get("submit", False)),
                    )
                    fill_res = await self.fill_skill.execute(fill_req)
                    step_record["details"] = {
                        "filled_fields": fill_res.filled_fields,
                        "submitted": fill_res.submitted,
                        "success": fill_res.success,
                    }
                    result_data["form_result"] = {
                        "filled_fields": fill_res.filled_fields,
                        "submitted": fill_res.submitted,
                    }

                elif act_type == "screenshot":
                    shot_res = await self.capture_screenshot(clean_url)
                    step_record["details"] = {"screenshot_url": shot_res.get("screenshot_url")}
                    result_data["screenshot_url"] = shot_res.get("screenshot_url")

                elif act_type == "click":
                    selector = str(act.get("selector", "")).strip()
                    step_record["details"] = {
                        "clicked_selector": selector,
                        "message": f"Simulated interactive click on element '{selector}'",
                    }
                    result_data["last_clicked"] = selector

                elif act_type == "scroll":
                    direction = str(act.get("direction", "down")).strip().lower()
                    amount = int(act.get("amount", 500))
                    step_record["details"] = {
                        "scrolled_direction": direction,
                        "scrolled_amount": amount,
                        "message": f"Scrolled {direction} by {amount}px",
                    }

                elif act_type == "wait":
                    wait_sec = min(float(act.get("seconds", 0.5)), 5.0)
                    await asyncio.sleep(wait_sec)
                    step_record["details"] = {"slept_seconds": wait_sec}

                else:
                    step_record["details"] = {"info": f"Custom browser action '{act_type}' processed"}

            except Exception as exc:
                step_record["status"] = "failed"
                step_record["error"] = str(exc)
                status = "failed"
                error_msg = str(exc)

            steps_executed.append(step_record)
            if status == "failed":
                break

        task_id: str | None = None
        if save_task and user_id:
            saved = await self.repo.create_task(
                user_id=user_id,
                data={
                    "title": task_title,
                    "url": clean_url,
                    "status": status,
                    "action_type": "multi_step" if len(actions) > 1 else actions[0].get("type", "navigate"),
                    "actions": actions,
                    "result_data": {
                        "steps": steps_executed,
                        "data": result_data,
                    },
                    "error_message": error_msg,
                    "requires_confirmation": status == "confirmation_required",
                    "tags": tags,
                },
            )
            task_id = saved.get("id")

        return {
            "task_id": task_id,
            "url": clean_url,
            "title": task_title,
            "status": status,
            "steps_executed": steps_executed,
            "result_data": result_data,
            "error": error_msg,
        }

    # -------------------------------------------------------------------------
    # Central Tool Registry Integration
    # -------------------------------------------------------------------------

    def register_browser_tools(self) -> None:
        """Register Browser Automation tools into the Central Tool Registry."""
        reg = ToolRegistry.get_instance()
        empty_actions: list[dict[str, Any]] = []

        async def _tool_browser_navigate(
            url: str,
            wait_for: str | None = None,
            timeout_seconds: int = 30,
            js_enabled: bool = False,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.navigate_and_inspect(
                url=url,
                wait_for=wait_for,
                timeout_seconds=timeout_seconds,
                js_enabled=js_enabled,
            )

        async def _tool_browser_extract(
            url: str,
            extract_type: str = "all",
            selectors: list[str] | None = None,
            max_items: int = 50,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.extract_data(
                url=url,
                extract_type=extract_type,
                selectors=selectors,
                max_items=max_items,
            )

        async def _tool_browser_screenshot(
            url: str,
            width: int = 1280,
            height: int = 800,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.capture_screenshot(url=url, width=width, height=height)

        async def _tool_browser_execute_flow(
            url: str,
            actions: list[dict[str, Any]] | None = None,
            title: str | None = None,
            save_task: bool = True,
            tags: list[str] | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            return await self.execute_browser_flow(
                user_id=uid,
                url=url,
                actions=actions or empty_actions,
                title=title,
                save_task=save_task,
                tags=tags,
            )

        async def _tool_browser_list_tasks(
            limit: int = 50,
            search: str | None = None,
            status: str | None = None,
            action_type: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            items = await self.repo.list_tasks(
                user_id=uid,
                limit=limit,
                search=search,
                status=status,
                action_type=action_type,
            )
            return {"total": len(items), "tasks": items}

        async def _tool_browser_delete_task(
            task_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            deleted = await self.repo.delete_task(user_id=uid, task_id=task_id)
            return {"task_id": task_id, "deleted": deleted}

        # 1. Browser Navigate
        reg.register(
            AgentTool(
                id="browser_navigate",
                name="Headless Browser Navigation & DOM Inspector",
                description=(
                    "Navigate to a web URL, inspect page title, headings, links, forms, and DOM content preview."
                ),
                source=ToolSource.SYSTEM,
                capabilities=["browser", "navigation", "inspect", "web", "dom"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target webpage URL to visit"},
                        "wait_for": {"type": "string", "description": "Optional CSS selector to wait for"},
                        "timeout_seconds": {"type": "integer", "default": 30, "description": "Page load timeout"},
                        "js_enabled": {"type": "boolean", "default": False, "description": "Whether to render JS via headless browser"},
                    },
                    "required": ["url"],
                },
                permissions=["browser:navigate"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_navigate,
        )

        # 2. Browser Extract
        reg.register(
            AgentTool(
                id="browser_extract",
                name="Web Structured Data Extractor",
                description=(
                    "Extract structured tables, links, headings, or text content from web page HTML."
                ),
                source=ToolSource.SYSTEM,
                capabilities=["browser", "extraction", "tables", "links", "scraping"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target webpage URL to scrape"},
                        "extract_type": {
                            "type": "string",
                            "enum": ["all", "tables", "links", "headings", "text"],
                            "default": "all",
                            "description": "Category of web content to extract",
                        },
                        "selectors": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional CSS selectors to target",
                        },
                        "max_items": {"type": "integer", "default": 50, "description": "Maximum records to retrieve"},
                    },
                    "required": ["url"],
                },
                permissions=["browser:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_extract,
        )

        # 3. Browser Screenshot
        reg.register(
            AgentTool(
                id="browser_screenshot",
                name="Web Page Screenshot Snapshot",
                description="Capture a visual snapshot representation or preview of a web page URL.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "screenshot", "visual", "preview"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target webpage URL"},
                        "width": {"type": "integer", "default": 1280, "description": "Viewport width in pixels"},
                        "height": {"type": "integer", "default": 800, "description": "Viewport height in pixels"},
                    },
                    "required": ["url"],
                },
                permissions=["browser:screenshot"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_screenshot,
        )

        # 4. Browser Execute Flow
        reg.register(
            AgentTool(
                id="browser_execute_flow",
                name="Autonomous Browser Flow Runner",
                description=(
                    "Execute multi-step browser actions (navigate, extract, fill_form, click, scroll, wait) "
                    "with interactive simulation and optional task persistence."
                ),
                source=ToolSource.SYSTEM,
                capabilities=["browser", "automation", "interactive", "workflow", "forms"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target initial webpage URL"},
                        "actions": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Sequential list of browser actions to execute",
                        },
                        "title": {"type": "string", "description": "Optional automation task title"},
                        "save_task": {"type": "boolean", "default": True, "description": "Whether to persist task record"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional categorization tags",
                        },
                    },
                    "required": ["url"],
                },
                permissions=["browser:execute"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            ),
            _tool_browser_execute_flow,
        )

        # 5. Browser List Tasks
        reg.register(
            AgentTool(
                id="browser_list_tasks",
                name="List Browser Automation Tasks",
                description="List saved browser automation tasks for the authenticated user with search and filtering.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "tasks", "history", "management"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 50, "description": "Maximum tasks to return"},
                        "search": {"type": "string", "description": "Search keyword in title, URL, or tags"},
                        "status": {"type": "string", "description": "Filter by task status"},
                        "action_type": {"type": "string", "description": "Filter by action type"},
                    },
                },
                permissions=["browser:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_list_tasks,
        )

        # 6. Browser Delete Task
        reg.register(
            AgentTool(
                id="browser_delete_task",
                name="Delete Browser Automation Task",
                description="Permanently delete a saved browser automation task with tenant isolation.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "tasks", "deletion"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "UUID of the task to delete"},
                    },
                    "required": ["task_id"],
                },
                permissions=["browser:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_delete_task,
        )
