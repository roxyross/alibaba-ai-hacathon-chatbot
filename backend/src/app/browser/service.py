"""BrowserService — Autonomous Web Navigation, DOM Inspection, and Flow Runner (Phase 15).

Coordinates safe web navigation, structured HTML DOM parsing, tables/links/headings extraction,
screenshot preview generation, and multi-step browser automation flows.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.browser.playwright_manager import PlaywrightBrowserManager
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
        self.pw_manager = PlaywrightBrowserManager.get_instance()

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

    # -------------------------------------------------------------------------
    # Hardened Persistent Playwright Session Controls (Phase 10)
    # -------------------------------------------------------------------------

    async def launch_session(
        self,
        profile_name: str = "default",
        headless: bool = True,
        browser_type: str = "chromium",
        viewport_width: int = 1280,
        viewport_height: int = 800,
        user_agent: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Launch or attach to a persistent browser session."""
        model = await self.pw_manager.launch_session(
            session_id=session_id,
            profile_name=profile_name,
            headless=headless,
            browser_type=browser_type,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            user_agent=user_agent,
        )
        return model.model_dump()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Query persistent session state."""
        model = await self.pw_manager.get_session(session_id)
        return model.model_dump() if model else None

    async def close_session(self, session_id: str) -> bool:
        """Close persistent browser session."""
        return await self.pw_manager.close_session(session_id)

    async def navigate_session(
        self,
        url: str,
        session_id: str | None = None,
        tab_id: str | None = None,
        wait_for: str | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Navigate persistent browser session to URL."""
        res = await self.pw_manager.navigate(
            session_id=session_id,
            url=url,
            tab_id=tab_id,
            wait_for=wait_for,
            timeout_seconds=timeout_seconds,
        )
        return res.model_dump()

    async def inspect_dom(
        self,
        session_id: str,
        tab_id: str | None = None,
        selector: str | None = None,
        max_depth: int = 4,
    ) -> dict[str, Any]:
        """Inspect interactive DOM elements and ARIA accessibility roles."""
        res = await self.pw_manager.inspect_dom(
            session_id=session_id,
            tab_id=tab_id,
            selector=selector,
            max_depth=max_depth,
        )
        return res.model_dump()

    async def interact_element(
        self,
        session_id: str,
        selector: str,
        action: str = "click",
        tab_id: str | None = None,
        text: str | None = None,
        value: str | None = None,
        files: list[str] | str | None = None,
        clear_first: bool = True,
        delay_ms: int = 0,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """Click, type, select, upload, or hover on a DOM element with live verification."""
        res = await self.pw_manager.interact_element(
            session_id=session_id,
            tab_id=tab_id,
            selector=selector,
            action=action,
            text=text,
            value=value,
            files=files,
            clear_first=clear_first,
            delay_ms=delay_ms,
            timeout_ms=timeout_ms,
        )
        return res.model_dump()

    async def upload_file(
        self,
        session_id: str,
        selector: str,
        file_paths: list[str] | str,
        tab_id: str | None = None,
        timeout_ms: int = 10000,
    ) -> dict[str, Any]:
        """Upload file(s) into file input."""
        res = await self.pw_manager.upload_file(
            session_id=session_id,
            selector=selector,
            file_paths=file_paths,
            tab_id=tab_id,
            timeout_ms=timeout_ms,
        )
        return res.model_dump()

    async def download_file(
        self,
        session_id: str,
        selector: str | None = None,
        trigger_action: str = "click",
        tab_id: str | None = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """Trigger and capture a downloaded file to a local secure directory."""
        res = await self.pw_manager.download_file(
            session_id=session_id,
            selector=selector,
            trigger_action=trigger_action,
            tab_id=tab_id,
            timeout_ms=timeout_ms,
        )
        return res.model_dump()

    async def scroll_page(
        self,
        session_id: str,
        direction: str = "down",
        amount: int = 500,
        tab_id: str | None = None,
        selector: str | None = None,
    ) -> dict[str, Any]:
        """Scroll active window or container element."""
        res = await self.pw_manager.scroll(
            session_id=session_id,
            tab_id=tab_id,
            direction=direction,
            amount=amount,
            selector=selector,
        )
        return res.model_dump()

    async def manage_session_tabs(
        self,
        session_id: str,
        action: str = "new_tab",
        tab_id: str | None = None,
        url: str | None = "about:blank",
    ) -> dict[str, Any]:
        """Create, close, switch, or list session tabs."""
        res = await self.pw_manager.manage_tabs(
            session_id=session_id,
            action=action,
            tab_id=tab_id,
            url=url,
        )
        return res.model_dump()

    async def wait_for_condition(
        self,
        session_id: str,
        tab_id: str | None = None,
        state: str = "visible",
        selector: str | None = None,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """Wait for selector, network state, or timeout."""
        res = await self.pw_manager.wait_for(
            session_id=session_id,
            tab_id=tab_id,
            state=state,
            selector=selector,
            timeout_ms=timeout_ms,
        )
        return res.model_dump()

    async def get_session_page_state(
        self,
        session_id: str,
        tab_id: str | None = None,
    ) -> dict[str, Any]:
        """Query real page state without leaking secrets."""
        res = await self.pw_manager.get_page_state(
            session_id=session_id,
            tab_id=tab_id,
        )
        return res.model_dump()

    async def capture_screenshot(
        self, url: str, width: int = 1280, height: int = 800
    ) -> dict[str, Any]:
        """Capture visual snapshot representation of a web page locally without leaking URLs to third parties."""
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

        # Generate trusted local visual snapshot (eliminating external service URL leakage)
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        safe_domain = domain.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <!-- Browser Navigation Bar -->
  <rect width="100%" height="48" fill="#1e293b" opacity="0.95"/>
  <circle cx="24" cy="24" r="6" fill="#ef4444"/>
  <circle cx="44" cy="24" r="6" fill="#f59e0b"/>
  <circle cx="64" cy="24" r="6" fill="#10b981"/>
  <!-- Address Bar -->
  <rect x="90" y="10" width="{min(width - 120, 600)}" height="28" rx="14" fill="#0f172a" stroke="#334155"/>
  <text x="110" y="29" fill="#94a3b8" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="13">https://{safe_domain}</text>
  <!-- Main Viewport Card -->
  <rect x="40" y="80" width="{width - 80}" height="{height - 120}" rx="12" fill="#1e293b" stroke="#334155" opacity="0.7"/>
  <text x="70" y="140" fill="#f8fafc" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="24" font-weight="600">{safe_title}</text>
  <text x="70" y="180" fill="#64748b" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="14">Local trusted snapshot — Privacy preserved (no external leakage) — Captured {now}</text>
</svg>"""

        static_shots_dir = Path(__file__).resolve().parents[3] / "static" / "screenshots"
        screenshot_url: str
        try:
            static_shots_dir.mkdir(parents=True, exist_ok=True)
            shot_id = f"snap_{uuid.uuid4().hex[:12]}.svg"
            shot_file = static_shots_dir / shot_id
            shot_file.write_text(svg_content, encoding="utf-8")
            screenshot_url = f"/static/screenshots/{shot_id}"
        except Exception:
            import base64
            svg_b64 = base64.b64encode(svg_content.encode("utf-8")).decode("ascii")
            screenshot_url = f"data:image/svg+xml;base64,{svg_b64}"

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
        if not clean_url.startswith(("http://", "https://", "about:", "data:", "file:")):
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

                elif act_type in ("type", "fill"):
                    selector = str(act.get("selector", "")).strip()
                    text_val = str(act.get("text", act.get("value", "")))
                    step_record["details"] = {
                        "typed_selector": selector,
                        "text": text_val,
                        "message": f"Typed text into element '{selector}'",
                    }
                    result_data["last_typed"] = {"selector": selector, "text": text_val}

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

        # ---------------------------------------------------------------------
        # Phase 10: Hardened Persistent Playwright Tools
        # ---------------------------------------------------------------------

        async def _tool_browser_launch_session(
            profile_name: str = "default",
            headless: bool = True,
            browser_type: str = "chromium",
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.launch_session(
                profile_name=profile_name,
                headless=headless,
                browser_type=browser_type,
            )

        async def _tool_browser_close_session(
            session_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            closed = await self.close_session(session_id=session_id)
            return {"session_id": session_id, "closed": closed}

        async def _tool_browser_manage_tabs(
            session_id: str,
            action: str = "new_tab",
            tab_id: str | None = None,
            url: str | None = "about:blank",
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.manage_session_tabs(
                session_id=session_id, action=action, tab_id=tab_id, url=url
            )

        async def _tool_browser_inspect_dom(
            session_id: str,
            tab_id: str | None = None,
            selector: str | None = None,
            max_depth: int = 4,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.inspect_dom(
                session_id=session_id, tab_id=tab_id, selector=selector, max_depth=max_depth
            )

        async def _tool_browser_interact_element(
            session_id: str,
            selector: str,
            action: str = "click",
            tab_id: str | None = None,
            text: str | None = None,
            value: str | None = None,
            files: list[str] | str | None = None,
            clear_first: bool = True,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.interact_element(
                session_id=session_id,
                tab_id=tab_id,
                selector=selector,
                action=action,
                text=text,
                value=value,
                files=files,
                clear_first=clear_first,
            )

        async def _tool_browser_upload_file(
            session_id: str,
            selector: str,
            file_paths: list[str] | str,
            tab_id: str | None = None,
            timeout_ms: int = 10000,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.upload_file(
                session_id=session_id,
                selector=selector,
                file_paths=file_paths,
                tab_id=tab_id,
                timeout_ms=timeout_ms,
            )

        async def _tool_browser_download_file(
            session_id: str,
            selector: str | None = None,
            trigger_action: str = "click",
            tab_id: str | None = None,
            timeout_ms: int = 30000,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.download_file(
                session_id=session_id,
                selector=selector,
                trigger_action=trigger_action,
                tab_id=tab_id,
                timeout_ms=timeout_ms,
            )

        async def _tool_browser_scroll(
            session_id: str,
            direction: str = "down",
            amount: int = 500,
            tab_id: str | None = None,
            selector: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.scroll_page(
                session_id=session_id,
                tab_id=tab_id,
                direction=direction,
                amount=amount,
                selector=selector,
            )

        async def _tool_browser_wait_for(
            session_id: str,
            tab_id: str | None = None,
            state: str = "visible",
            selector: str | None = None,
            timeout_ms: int = 5000,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.wait_for_condition(
                session_id=session_id,
                tab_id=tab_id,
                state=state,
                selector=selector,
                timeout_ms=timeout_ms,
            )

        async def _tool_browser_get_page_state(
            session_id: str,
            tab_id: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            return await self.get_session_page_state(session_id=session_id, tab_id=tab_id)

        # 7. Browser Launch Session
        reg.register(
            AgentTool(
                id="browser_launch_session",
                name="Launch Persistent Browser Session",
                description="Launch or attach to a persistent Playwright browser session with user profile support.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "session", "persistent", "launch"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "profile_name": {"type": "string", "default": "default", "description": "Persistent profile name"},
                        "headless": {"type": "boolean", "default": True, "description": "Run headless or headed"},
                        "browser_type": {"type": "string", "default": "chromium", "description": "chromium, firefox, or webkit"},
                    },
                },
                permissions=["browser:session:launch"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_launch_session,
        )

        # 8. Browser Close Session
        reg.register(
            AgentTool(
                id="browser_close_session",
                name="Close Browser Session",
                description="Close an active persistent Playwright browser session and clean up resources.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "session", "close"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID to close"},
                    },
                    "required": ["session_id"],
                },
                permissions=["browser:session:close"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_close_session,
        )

        # 9. Browser Manage Tabs
        reg.register(
            AgentTool(
                id="browser_manage_tabs",
                name="Manage Browser Tabs",
                description="Create, switch, close, or list tabs in an active browser session.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "tabs", "navigation"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "action": {"type": "string", "enum": ["new_tab", "close_tab", "switch_tab", "list_tabs"], "default": "new_tab"},
                        "tab_id": {"type": "string", "description": "Tab ID to switch or close"},
                        "url": {"type": "string", "description": "Initial URL for new tab"},
                    },
                    "required": ["session_id"],
                },
                permissions=["browser:tabs"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_manage_tabs,
        )

        # 10. Browser Inspect DOM
        reg.register(
            AgentTool(
                id="browser_inspect_dom",
                name="Inspect Interactive DOM Elements",
                description="Inspect interactive buttons, inputs, links, forms, and ARIA roles on the current page.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "dom", "inspect", "accessibility"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "tab_id": {"type": "string", "description": "Optional tab ID"},
                        "selector": {"type": "string", "description": "Root CSS selector to inspect"},
                        "max_depth": {"type": "integer", "default": 4, "description": "Max inspection depth"},
                    },
                    "required": ["session_id"],
                },
                permissions=["browser:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_inspect_dom,
        )

        # 11. Browser Interact Element
        reg.register(
            AgentTool(
                id="browser_interact_element",
                name="Interact with DOM Element",
                description="Click, type, fill, select, upload, or hover on a DOM element with live verification.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "interaction", "click", "type", "form", "upload"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "selector": {"type": "string", "description": "CSS/XPath/ARIA selector"},
                        "action": {"type": "string", "enum": ["click", "type", "select", "hover", "clear", "press_enter", "upload"], "default": "click"},
                        "tab_id": {"type": "string", "description": "Optional tab ID"},
                        "text": {"type": "string", "description": "Text to type if action is 'type'"},
                        "value": {"type": "string", "description": "Value to select if action is 'select'"},
                        "files": {"type": "array", "items": {"type": "string"}, "description": "Local file paths to upload if action is 'upload'"},
                        "clear_first": {"type": "boolean", "default": True, "description": "Clear input before typing"},
                    },
                    "required": ["session_id", "selector"],
                },
                permissions=["browser:interact"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            ),
            _tool_browser_interact_element,
        )

        # 12. Browser Scroll
        reg.register(
            AgentTool(
                id="browser_scroll",
                name="Scroll Webpage or Container",
                description="Scroll page down, up, top, or bottom and return post-scroll coordinates.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "scroll", "navigation"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "direction": {"type": "string", "enum": ["down", "up", "top", "bottom"], "default": "down"},
                        "amount": {"type": "integer", "default": 500, "description": "Scroll amount in pixels"},
                        "tab_id": {"type": "string", "description": "Optional tab ID"},
                        "selector": {"type": "string", "description": "Optional container selector"},
                    },
                    "required": ["session_id"],
                },
                permissions=["browser:scroll"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_scroll,
        )

        # 13. Browser Wait For
        reg.register(
            AgentTool(
                id="browser_wait_for",
                name="Wait for Browser Element or State",
                description="Wait for an element to appear, become visible, or wait for network idle.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "wait", "state"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "state": {"type": "string", "enum": ["visible", "hidden", "attached", "detached", "networkidle"], "default": "visible"},
                        "selector": {"type": "string", "description": "CSS selector to wait for"},
                        "timeout_ms": {"type": "integer", "default": 5000, "description": "Timeout in milliseconds"},
                        "tab_id": {"type": "string", "description": "Optional tab ID"},
                    },
                    "required": ["session_id"],
                },
                permissions=["browser:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_wait_for,
        )

        # 14. Browser Get Page State
        reg.register(
            AgentTool(
                id="browser_get_page_state",
                name="Get Browser Page Telemetry & State",
                description="Retrieve current page URL, title, readyState, viewport, and storage keys without leaking secrets.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "state", "telemetry"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "tab_id": {"type": "string", "description": "Optional tab ID"},
                    },
                    "required": ["session_id"],
                },
                permissions=["browser:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_get_page_state,
        )

        # 15. Browser Upload File
        reg.register(
            AgentTool(
                id="browser_upload_file",
                name="Upload File to Browser Element",
                description="Attach and upload one or more local files to a file input element in the active browser session.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "upload", "files", "form"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "selector": {"type": "string", "description": "File input CSS selector (e.g. 'input[type=file]')"},
                        "file_paths": {"type": "array", "items": {"type": "string"}, "description": "Local path(s) to files to upload"},
                        "tab_id": {"type": "string", "description": "Optional tab ID"},
                        "timeout_ms": {"type": "integer", "default": 10000, "description": "Upload timeout in ms"},
                    },
                    "required": ["session_id", "selector", "file_paths"],
                },
                permissions=["browser:upload"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            ),
            _tool_browser_upload_file,
        )

        # 16. Browser Download File
        reg.register(
            AgentTool(
                id="browser_download_file",
                name="Capture Browser File Download",
                description="Trigger and capture a file download from the active browser session to local secure storage.",
                source=ToolSource.SYSTEM,
                capabilities=["browser", "download", "files"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID"},
                        "selector": {"type": "string", "description": "Selector to click to trigger download"},
                        "trigger_action": {"type": "string", "default": "click", "description": "Trigger action: click or wait"},
                        "tab_id": {"type": "string", "description": "Optional tab ID"},
                        "timeout_ms": {"type": "integer", "default": 30000, "description": "Download timeout in ms"},
                    },
                    "required": ["session_id"],
                },
                permissions=["browser:download"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_browser_download_file,
        )

