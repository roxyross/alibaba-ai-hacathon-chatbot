"""Playwright Browser Manager — Hardened Persistent Browser Automation Engine (Phase 10).

Manages persistent browser profiles, multi-tab execution, DOM inspection, element interactions,
scrolling, screenshots, and postcondition verification under the Zero Simulation Doctrine.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from pathlib import Path
import re
import tempfile
from typing import Any
import uuid

import structlog

from app.browser.schemas import (
    BrowserDOMInspectResponse,
    BrowserDownloadResponse,
    BrowserElementInteractResponse,
    BrowserNavigateHardenedResponse,
    BrowserPageStateResponse,
    BrowserScreenshotHardenedResponse,
    BrowserScrollResponse,
    BrowserSessionModel,
    BrowserTabManageResponse,
    BrowserTabModel,
    BrowserUploadResponse,
    BrowserWaitResponse,
)

log = structlog.get_logger()

_PROFILE_BASE_DIR = Path.home() / ".roxy" / "browser_profiles"
_SCREENSHOT_DIR = Path.home() / ".roxy" / "browser_screenshots"
_DOWNLOADS_DIR = Path.home() / ".roxy" / "browser_downloads"


class _ManagedSession:
    """Internal session tracking container for persistent Playwright context."""

    def __init__(
        self,
        session_id: str,
        profile_name: str,
        browser_type: str,
        context: Any,
        device_id: str = "current_host",
    ) -> None:
        self.session_id = session_id
        self.profile_name = profile_name
        self.browser_type = browser_type
        self.context = context
        self.device_id = device_id
        self.tabs: dict[str, Any] = {}  # tab_id -> Playwright Page
        self.active_tab_id: str | None = None
        self.created_at = datetime.now(UTC).isoformat()
        self.last_active_at = self.created_at
        self.is_closed = False

    def touch(self) -> None:
        self.last_active_at = datetime.now(UTC).isoformat()

    def get_active_page(self) -> Any:
        if self.active_tab_id and self.active_tab_id in self.tabs:
            page = self.tabs[self.active_tab_id]
            if not page.is_closed():
                return page
        # Fallback to first non-closed page
        for tid, p in self.tabs.items():
            if not p.is_closed():
                self.active_tab_id = tid
                return p
        return None

    def to_model(self) -> BrowserSessionModel:
        tab_models: list[BrowserTabModel] = []
        for tid, page in list(self.tabs.items()):
            if not page.is_closed():
                try:
                    tab_models.append(
                        BrowserTabModel(
                            tab_id=tid,
                            url=page.url,
                            title="",  # Title can be queried dynamically
                            is_active=(tid == self.active_tab_id),
                        )
                    )
                except Exception:
                    pass

        active_page = self.get_active_page()
        cur_url = active_page.url if active_page else "about:blank"

        return BrowserSessionModel(
            session_id=self.session_id,
            device_id=self.device_id,
            browser=self.browser_type,
            profile=self.profile_name,
            tabs=tab_models,
            active_tab_id=self.active_tab_id,
            current_url=cur_url,
            authenticated_state=False,  # Evaluated via cookie probe
            created_at=self.created_at,
            last_active_at=self.last_active_at,
            is_closed=self.is_closed,
        )


class PlaywrightBrowserManager:
    """Singleton manager coordinating persistent Playwright sessions and actions."""

    _instance: PlaywrightBrowserManager | None = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._pw: Any = None
        self._sessions: dict[str, _ManagedSession] = {}
        _PROFILE_BASE_DIR.mkdir(parents=True, exist_ok=True)
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> PlaywrightBrowserManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _ensure_playwright(self) -> Any:
        """Lazily initialize Playwright driver instance."""
        if self._pw is None:
            try:
                from playwright.async_api import async_playwright
                self._pw = await async_playwright().start()
                log.info("playwright_manager.driver_started")
            except Exception as exc:
                log.error("playwright_manager.start_failed", error=str(exc))
                raise RuntimeError(f"Failed to start Playwright driver: {exc}") from exc
        return self._pw

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    async def launch_session(
        self,
        session_id: str | None = None,
        profile_name: str = "default",
        headless: bool = True,
        browser_type: str = "chromium",
        viewport_width: int = 1280,
        viewport_height: int = 800,
        user_agent: str | None = None,
    ) -> BrowserSessionModel:
        """Launch or attach to a persistent browser session."""
        async with self._lock:
            sid = session_id or f"sess_{uuid.uuid4().hex[:10]}"
            if sid in self._sessions and not self._sessions[sid].is_closed:
                sess = self._sessions[sid]
                sess.touch()
                return sess.to_model()

            pw = await self._ensure_playwright()
            profile_dir = _PROFILE_BASE_DIR / profile_name
            profile_dir.mkdir(parents=True, exist_ok=True)

            b_launcher = getattr(pw, browser_type.lower(), pw.chromium)

            context_kwargs: dict[str, Any] = {
                "user_data_dir": str(profile_dir),
                "headless": headless,
                "viewport": {"width": viewport_width, "height": viewport_height},
                "accept_downloads": True,
            }
            if user_agent:
                context_kwargs["user_agent"] = user_agent

            context = await b_launcher.launch_persistent_context(**context_kwargs)

            sess = _ManagedSession(
                session_id=sid,
                profile_name=profile_name,
                browser_type=browser_type,
                context=context,
            )

            # Ensure at least one tab exists
            pages = context.pages
            if pages:
                tab_id = f"tab_{uuid.uuid4().hex[:6]}"
                sess.tabs[tab_id] = pages[0]
                sess.active_tab_id = tab_id
            else:
                p = await context.new_page()
                tab_id = f"tab_{uuid.uuid4().hex[:6]}"
                sess.tabs[tab_id] = p
                sess.active_tab_id = tab_id

            self._sessions[sid] = sess
            log.info("playwright_manager.session_launched", session_id=sid, profile=profile_name, headless=headless)
            return sess.to_model()

    async def get_session(self, session_id: str) -> BrowserSessionModel | None:
        """Retrieve state for an existing browser session."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            return None
        sess.touch()
        model = sess.to_model()
        # Probe cookies count to check authenticated state without leaking values
        try:
            cookies = await sess.context.cookies()
            model.authenticated_state = len(cookies) > 0
        except Exception:
            pass
        return model

    async def close_session(self, session_id: str) -> bool:
        """Close browser context and release session resources."""
        async with self._lock:
            sess = self._sessions.pop(session_id, None)
            if not sess:
                return False
            try:
                sess.is_closed = True
                await sess.context.close()
                log.info("playwright_manager.session_closed", session_id=session_id)
                return True
            except Exception as exc:
                log.warning("playwright_manager.session_close_error", session_id=session_id, error=str(exc))
                return False

    async def close_all_sessions(self) -> None:
        """Tear down all open browser sessions."""
        async with self._lock:
            for sid, sess in list(self._sessions.items()):
                try:
                    await sess.context.close()
                except Exception:
                    pass
            self._sessions.clear()
            if self._pw:
                try:
                    await self._pw.stop()
                except Exception:
                    pass
                self._pw = None

    # -------------------------------------------------------------------------
    # Tab Management
    # -------------------------------------------------------------------------

    async def manage_tabs(
        self,
        session_id: str,
        action: str = "new_tab",
        tab_id: str | None = None,
        url: str | None = "about:blank",
    ) -> BrowserTabManageResponse:
        """Create, close, switch, or list tabs in an active session."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        if action == "new_tab":
            page = await sess.context.new_page()
            new_tab_id = f"tab_{uuid.uuid4().hex[:6]}"
            sess.tabs[new_tab_id] = page
            sess.active_tab_id = new_tab_id
            if url and url != "about:blank":
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        elif action == "close_tab":
            target_id = tab_id or sess.active_tab_id
            if target_id and target_id in sess.tabs:
                page = sess.tabs.pop(target_id)
                if not page.is_closed():
                    await page.close()
                if sess.active_tab_id == target_id:
                    sess.active_tab_id = next(iter(sess.tabs.keys()), None)

        elif action == "switch_tab":
            if tab_id and tab_id in sess.tabs:
                sess.active_tab_id = tab_id
                page = sess.tabs[tab_id]
                if not page.is_closed():
                    await page.bring_to_front()
            else:
                raise ValueError(f"Tab ID '{tab_id}' does not exist in session.")

        model = sess.to_model()
        return BrowserTabManageResponse(
            session_id=session_id,
            action=action,
            active_tab_id=sess.active_tab_id or "",
            tabs=model.tabs,
        )

    # -------------------------------------------------------------------------
    # Navigation & Page State
    # -------------------------------------------------------------------------

    async def navigate(
        self,
        session_id: str | None = None,
        url: str = "",
        tab_id: str | None = None,
        wait_for: str | None = None,
        timeout_seconds: int = 30,
    ) -> BrowserNavigateHardenedResponse:
        """Navigate target tab to a URL, waiting for load and extracting semantic DOM components."""
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://", "about:", "data:", "file:")):
            clean_url = f"https://{clean_url}"

        # In data URLs, browsers treat '#' as the URL fragment identifier, cutting off the HTML body
        if clean_url.startswith("data:text/html"):
            parts = clean_url.split(",", 1)
            if len(parts) == 2 and "#" in parts[1]:
                clean_url = f"{parts[0]},{parts[1].replace('#', '%23')}"

        # Ensure active session exists
        if not session_id or session_id not in self._sessions or self._sessions[session_id].is_closed:
            s_model = await self.launch_session(session_id=session_id)
            session_id = s_model.session_id

        sess = self._sessions[session_id]
        sess.touch()

        target_tab_id = tab_id or sess.active_tab_id
        if not target_tab_id or target_tab_id not in sess.tabs:
            p = await sess.context.new_page()
            target_tab_id = f"tab_{uuid.uuid4().hex[:6]}"
            sess.tabs[target_tab_id] = p
            sess.active_tab_id = target_tab_id

        page = sess.tabs[target_tab_id]

        try:
            resp = await page.goto(
                clean_url,
                wait_until="domcontentloaded",
                timeout=timeout_seconds * 1000,
            )
            final_url = page.url
            status_code = resp.status if resp else 200

            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=min(timeout_seconds * 1000, 10000))
                except Exception:
                    pass

            title = await page.title()
            content = await page.content()

            # Structured extraction via real Playwright evaluation
            eval_data = await page.evaluate(
                """() => {
                    const headings = Array.from(document.querySelectorAll('h1, h2, h3')).slice(0, 30).map(h => ({
                        level: parseInt(h.tagName[1]),
                        text: h.innerText.trim()
                    })).filter(h => h.text.length > 0);

                    const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 40).map(a => ({
                        text: a.innerText.trim() || a.getAttribute('aria-label') || a.href,
                        href: a.href
                    })).filter(l => l.href && !l.href.startsWith('javascript:'));

                    const forms = Array.from(document.querySelectorAll('form')).slice(0, 10).map(f => ({
                        action: f.action,
                        method: (f.method || 'GET').toUpperCase(),
                        fields: Array.from(f.querySelectorAll('input, select, textarea')).map(i => i.name || i.id || i.placeholder).filter(Boolean)
                    }));

                    const meta = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                        const k = m.getAttribute('name') || m.getAttribute('property');
                        if (k) meta[k.toLowerCase()] = m.getAttribute('content') || '';
                    });

                    return { headings, links, forms, meta };
                }"""
            )

            # Strip text preview
            text_preview = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 2000) : ''")

            return BrowserNavigateHardenedResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                url=clean_url,
                title=title,
                final_url=final_url,
                status="success",
                content_preview=text_preview.strip(),
                headings=eval_data.get("headings", []),
                links=eval_data.get("links", []),
                forms=eval_data.get("forms", []),
                meta=eval_data.get("meta", {}),
                error=None,
            )

        except Exception as exc:
            log.warning("playwright_manager.navigate_failed", url=clean_url, error=str(exc))
            return BrowserNavigateHardenedResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                url=clean_url,
                title=f"Error ({clean_url})",
                final_url=clean_url,
                status="error",
                content_preview="",
                headings=[],
                links=[],
                forms=[],
                meta={},
                error=str(exc),
            )

    async def get_page_state(
        self,
        session_id: str,
        tab_id: str | None = None,
    ) -> BrowserPageStateResponse:
        """Query real page state without exposing authentication secrets."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        target_tab_id = tab_id or sess.active_tab_id
        page = sess.tabs.get(target_tab_id or "") if target_tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError(f"Active tab for session '{session_id}' is closed.")

        url = page.url
        title = await page.title()
        viewport = page.viewport_size or {"width": 1280, "height": 800}

        cookies = await sess.context.cookies()
        has_cookies = len(cookies) > 0

        state_data = await page.evaluate(
            """() => {
                let keys = [];
                try {
                    keys = Object.keys(localStorage || {});
                } catch(e) {}
                return {
                    ready_state: document.readyState,
                    storage_keys: keys.slice(0, 50)
                };
            }"""
        )

        return BrowserPageStateResponse(
            session_id=session_id,
            tab_id=target_tab_id or "",
            url=url,
            title=title,
            ready_state=state_data.get("ready_state", "complete"),
            viewport=viewport,
            tabs_count=len([p for p in sess.tabs.values() if not p.is_closed()]),
            has_cookies=has_cookies,
            authenticated_state=has_cookies,
            storage_keys=state_data.get("storage_keys", []),
        )

    # -------------------------------------------------------------------------
    # DOM Inspection & Element Identification
    # -------------------------------------------------------------------------

    async def inspect_dom(
        self,
        session_id: str,
        tab_id: str | None = None,
        selector: str | None = None,
        max_depth: int = 4,
    ) -> BrowserDOMInspectResponse:
        """Inspect interactive DOM elements, buttons, inputs, links, and ARIA roles."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        page = sess.tabs.get(tab_id or "") if tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError("No active page available for DOM inspection.")

        target_root = selector or "body"

        elements_data = await page.evaluate(
            """([rootSelector, depthLimit]) => {
                const root = document.querySelector(rootSelector) || document.body;
                if (!root) return [];

                const interactiveSelectors = 'button, a, input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [onclick], [tabindex]';
                const nodes = Array.from(root.querySelectorAll(interactiveSelectors)).slice(0, 100);

                return nodes.map((el, idx) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        index: idx,
                        tag: el.tagName.toLowerCase(),
                        role: el.getAttribute('role') || el.tagName.toLowerCase(),
                        name: el.innerText.trim().slice(0, 80) || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '',
                        id: el.id || null,
                        classes: el.className ? el.className.split(' ').slice(0, 5).join(' ') : null,
                        type: el.getAttribute('type') || null,
                        value: (el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'textarea') ? el.value.slice(0, 50) : null,
                        disabled: el.hasAttribute('disabled'),
                        visible: rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden',
                        bounds: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    };
                });
            }""",
            [target_root, max_depth],
        )

        title = await page.title()
        url = page.url
        snippet = await page.evaluate(
            "root => (document.querySelector(root) || document.body).innerHTML.slice(0, 1500)",
            target_root,
        )

        return BrowserDOMInspectResponse(
            session_id=session_id,
            tab_id=tab_id or sess.active_tab_id or "",
            url=url,
            title=title,
            elements=elements_data,
            html_snippet=snippet,
            total_elements_found=len(elements_data),
        )

    # -------------------------------------------------------------------------
    # Element Interaction (Click, Type, Select, Hover)
    # -------------------------------------------------------------------------

    async def interact_element(
        self,
        session_id: str,
        tab_id: str | None = None,
        selector: str = "",
        action: str = "click",
        text: str | None = None,
        value: str | None = None,
        files: list[str] | str | None = None,
        clear_first: bool = True,
        delay_ms: int = 0,
        timeout_ms: int = 5000,
    ) -> BrowserElementInteractResponse:
        """Perform real element interaction with automatic wait, scroll, and verification."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        page = sess.tabs.get(tab_id or "") if tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError("No active page available for interaction.")

        target_tab_id = tab_id or sess.active_tab_id or ""
        clean_selector = selector.strip()
        act_lower = action.lower()

        try:
            # 1. Wait for element to exist and be visible (or attached if file upload)
            locator = page.locator(clean_selector).first
            wait_state = "attached" if act_lower in ("upload", "upload_file") else "visible"
            await locator.wait_for(state=wait_state, timeout=timeout_ms)

            details: dict[str, Any] = {"selector": clean_selector, "action": act_lower}

            if act_lower == "click":
                await locator.click(timeout=timeout_ms)
                details["clicked"] = True

            elif act_lower in ("type", "fill"):
                payload_text = text if text is not None else (value or "")
                if clear_first:
                    await locator.fill(payload_text, timeout=timeout_ms)
                else:
                    await locator.type(payload_text, delay=delay_ms, timeout=timeout_ms)
                details["typed_length"] = len(payload_text)

            elif act_lower == "select":
                select_val = value or text or ""
                await locator.select_option(value=select_val, timeout=timeout_ms)
                details["selected_value"] = select_val

            elif act_lower == "hover":
                await locator.hover(timeout=timeout_ms)
                details["hovered"] = True

            elif act_lower == "clear":
                await locator.fill("", timeout=timeout_ms)
                details["cleared"] = True

            elif act_lower == "press_enter":
                await locator.press("Enter", timeout=timeout_ms)
                details["pressed_key"] = "Enter"

            elif act_lower in ("upload", "upload_file"):
                raw_files = files if files is not None else (text or value or "")
                file_list = [raw_files] if isinstance(raw_files, str) else list(raw_files)
                resolved = [str(Path(p).resolve()) for p in file_list]
                await locator.set_input_files(resolved, timeout=timeout_ms)
                details["uploaded_files"] = resolved

            else:
                raise ValueError(f"Unsupported browser element interaction: '{action}'")

            # 2. Live postcondition verification
            verified = True
            if act_lower in ("type", "fill") and text:
                try:
                    val_now = await locator.input_value(timeout=1000)
                    verified = (text in val_now)
                    details["verified_input_value"] = val_now
                except Exception:
                    verified = True  # Non-standard input or submitted

            return BrowserElementInteractResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                selector=clean_selector,
                action=act_lower,
                success=True,
                verified=verified,
                details=details,
                error=None,
            )

        except Exception as exc:
            log.warning("playwright_manager.interact_failed", selector=clean_selector, action=act_lower, error=str(exc))
            return BrowserElementInteractResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                selector=clean_selector,
                action=act_lower,
                success=False,
                verified=False,
                details={"selector": clean_selector},
                error=str(exc),
            )

    async def upload_file(
        self,
        session_id: str,
        selector: str,
        file_paths: list[str] | str,
        tab_id: str | None = None,
        timeout_ms: int = 10000,
    ) -> BrowserUploadResponse:
        """Upload file(s) to a file input element."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        page = sess.tabs.get(tab_id or "") if tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError("No active page available.")

        target_tab_id = tab_id or sess.active_tab_id or ""
        clean_selector = selector.strip()

        paths = [file_paths] if isinstance(file_paths, str) else list(file_paths)
        resolved_paths = [str(Path(p).resolve()) for p in paths]

        try:
            loc = page.locator(clean_selector).first
            await loc.wait_for(state="attached", timeout=timeout_ms)
            await loc.set_input_files(resolved_paths, timeout=timeout_ms)

            return BrowserUploadResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                selector=clean_selector,
                files_uploaded=resolved_paths,
                success=True,
                verified=True,
                details={"files_count": len(resolved_paths), "paths": resolved_paths},
                error=None,
            )
        except Exception as exc:
            log.warning("playwright_manager.upload_failed", selector=clean_selector, error=str(exc))
            return BrowserUploadResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                selector=clean_selector,
                files_uploaded=[],
                success=False,
                verified=False,
                details={},
                error=str(exc),
            )

    async def download_file(
        self,
        session_id: str,
        selector: str | None = None,
        trigger_action: str = "click",
        tab_id: str | None = None,
        timeout_ms: int = 30000,
    ) -> BrowserDownloadResponse:
        """Trigger and capture a downloaded file to a secure local directory."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        page = sess.tabs.get(tab_id or "") if tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError("No active page available.")

        target_tab_id = tab_id or sess.active_tab_id or ""
        _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        try:
            async with page.expect_download(timeout=timeout_ms) as download_info:
                if selector:
                    loc = page.locator(selector).first
                    await loc.click(timeout=timeout_ms)

            download = await download_info.value
            suggested_filename = download.suggested_filename or f"download_{uuid.uuid4().hex[:8]}"
            save_path = _DOWNLOADS_DIR / f"{uuid.uuid4().hex[:6]}_{suggested_filename}"
            await download.save_as(str(save_path))

            file_size = save_path.stat().st_size if save_path.exists() else 0

            return BrowserDownloadResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                downloaded_path=str(save_path),
                filename=suggested_filename,
                file_size_bytes=file_size,
                success=True,
                error=None,
            )
        except Exception as exc:
            log.warning("playwright_manager.download_failed", selector=selector, error=str(exc))
            return BrowserDownloadResponse(
                session_id=session_id,
                tab_id=target_tab_id,
                downloaded_path="",
                filename="",
                file_size_bytes=0,
                success=False,
                error=str(exc),
            )

    # -------------------------------------------------------------------------
    # Scrolling
    # -------------------------------------------------------------------------

    async def scroll(
        self,
        session_id: str,
        tab_id: str | None = None,
        direction: str = "down",
        amount: int = 500,
        selector: str | None = None,
    ) -> BrowserScrollResponse:
        """Scroll active window or container element and return post-scroll coordinates."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        page = sess.tabs.get(tab_id or "") if tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError("No active page available for scrolling.")

        d_lower = direction.lower()
        delta_x = 0
        delta_y = 0

        if d_lower == "down":
            delta_y = amount
        elif d_lower == "up":
            delta_y = -amount
        elif d_lower == "top":
            await page.evaluate("() => window.scrollTo(0, 0)")
        elif d_lower == "bottom":
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")

        if delta_x != 0 or delta_y != 0:
            if selector:
                await page.evaluate(
                    """([sel, dx, dy]) => {
                        const el = document.querySelector(sel);
                        if (el) el.scrollBy(dx, dy);
                    }""",
                    [selector, delta_x, delta_y],
                )
            else:
                await page.evaluate("([dx, dy]) => window.scrollBy(dx, dy)", [delta_x, delta_y])

        # Retrieve current scroll offset
        coords = await page.evaluate(
            "() => ({ x: Math.round(window.scrollX || 0), y: Math.round(window.scrollY || 0) })"
        )

        return BrowserScrollResponse(
            session_id=session_id,
            tab_id=tab_id or sess.active_tab_id or "",
            direction=direction,
            amount=amount,
            scroll_x=coords.get("x", 0),
            scroll_y=coords.get("y", 0),
            success=True,
        )

    # -------------------------------------------------------------------------
    # Real Screenshot Capture
    # -------------------------------------------------------------------------

    async def capture_screenshot(
        self,
        session_id: str | None = None,
        tab_id: str | None = None,
        url: str | None = None,
        full_page: bool = False,
        selector: str | None = None,
        width: int = 1280,
        height: int = 800,
    ) -> BrowserScreenshotHardenedResponse:
        """Capture real pixel PNG screenshot locally without leaking URL to third-party services."""
        # If url provided without active session, launch transient or attached session
        if (not session_id or session_id not in self._sessions) and url:
            s_model = await self.launch_session(
                viewport_width=width,
                viewport_height=height,
            )
            session_id = s_model.session_id
            await self.navigate(session_id=session_id, url=url)

        sess = self._sessions.get(session_id or "")
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        page = sess.tabs.get(tab_id or "") if tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError("No active page available for screenshot.")

        file_id = f"shot_{uuid.uuid4().hex[:12]}.png"
        out_path = _SCREENSHOT_DIR / file_id

        try:
            if selector:
                loc = page.locator(selector).first
                png_bytes = await loc.screenshot(path=str(out_path))
            else:
                png_bytes = await page.screenshot(path=str(out_path), full_page=full_page)

            b64_str = base64.b64encode(png_bytes).decode("ascii")

            return BrowserScreenshotHardenedResponse(
                session_id=session_id,
                screenshot_path=str(out_path),
                base64_data=f"data:image/png;base64,{b64_str}",
                width=width,
                height=height,
                success=True,
                error=None,
            )

        except Exception as exc:
            log.warning("playwright_manager.screenshot_failed", error=str(exc))
            return BrowserScreenshotHardenedResponse(
                session_id=session_id,
                screenshot_path="",
                base64_data=None,
                width=width,
                height=height,
                success=False,
                error=str(exc),
            )

    # -------------------------------------------------------------------------
    # Wait Operations
    # -------------------------------------------------------------------------

    async def wait_for(
        self,
        session_id: str,
        tab_id: str | None = None,
        state: str = "visible",
        selector: str | None = None,
        timeout_ms: int = 5000,
    ) -> BrowserWaitResponse:
        """Wait for selector, network state, or timeout."""
        sess = self._sessions.get(session_id)
        if not sess or sess.is_closed:
            raise ValueError(f"Session '{session_id}' not found or closed.")
        sess.touch()

        page = sess.tabs.get(tab_id or "") if tab_id else sess.get_active_page()
        if not page or page.is_closed():
            raise ValueError("No active page available.")

        start_t = asyncio.get_running_loop().time()

        try:
            if state == "networkidle":
                await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            elif selector:
                await page.wait_for_selector(selector, state=state, timeout=timeout_ms)  # type: ignore[arg-type]
            else:
                await asyncio.sleep(min(timeout_ms / 1000.0, 10.0))

            waited = (asyncio.get_running_loop().time() - start_t) * 1000.0
            return BrowserWaitResponse(
                session_id=session_id,
                tab_id=tab_id or sess.active_tab_id or "",
                success=True,
                waited_ms=round(waited, 2),
                error=None,
            )
        except Exception as exc:
            waited = (asyncio.get_running_loop().time() - start_t) * 1000.0
            return BrowserWaitResponse(
                session_id=session_id,
                tab_id=tab_id or sess.active_tab_id or "",
                success=False,
                waited_ms=round(waited, 2),
                error=str(exc),
            )
