"""browser_navigate skill — real Playwright browser automation.

Per the PR 4 plan: real implementation drives a Playwright browser
to navigate pages, perform actions, and extract data.

Requires: `playwright` package (`pip install playwright && playwright install chromium`).
If Playwright is not installed, returns a clear stub with setup instructions.
"""

from __future__ import annotations

import asyncio
import os
import structlog
import uuid
from pathlib import Path

from runtime.skills._playwright import _ensure_playwright, PLAYWRIGHT_INSTALL_CMD
from runtime.skills.executor import SkillResult

log = structlog.get_logger()


# Lazy import — only resolved when Playwright is confirmed available.
def _import_playwright():
    from playwright.async_api import async_playwright
    from playwright.async_api import TimeoutError as PlaywrightTimeout
    return async_playwright, PlaywrightTimeout


async def browser_navigate(
    url: str,
    actions: list[dict] | None = None,
    timeout_seconds: int = 60,
    extract_selectors: dict | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Navigate a URL and optionally perform actions using Playwright.

    Args:
        url: The URL to navigate to.
        actions: Optional list of actions to perform after navigation.
            Each action is a dict: {"type": "click|fill|wait|press|screenshot", "selector": "...", "value": "..."}
        timeout_seconds: Page load timeout (default 60s).
        extract_selectors: Optional dict of name -> CSS selector to extract.
            e.g. {"title": "h1", "price": ".price"}
        user_id: for audit logging.

    Returns:
        SkillResult with pages visited, extractions, screenshot paths, and final page state.
    """
    log.info(
        "browser_navigate.invoked",
        user_id=user_id,
        url=url,
        action_count=len(actions) if actions else 0,
        timeout_seconds=timeout_seconds,
    )

    if not url or not url.strip():
        return SkillResult(ok=False, data=None, error="url cannot be empty")

    if not url.startswith(("http://", "https://")):
        return SkillResult(ok=False, data=None, error=f"Invalid URL: '{url}'. Must start with http:// or https://")

    ready, err_msg = await _ensure_playwright()
    if not ready:
        return SkillResult(
            ok=True,
            data={
                "pages_visited": [url],
                "extractions": [
                    {
                        "action": "navigate",
                        "extracted": {
                            "title": "[Playwright not ready]",
                            "text": f"[STUB] {err_msg}",
                            "links": [],
                            "tables": [],
                        },
                    }
                ],
                "screenshot_paths": [],
                "final_state": {
                    "url": url,
                    "title": "[Playwright not ready]",
                    "text_excerpt": err_msg or "Install Playwright to enable browser automation.",
                },
            },
            warning=(
                f"browser_navigate is running in stub mode.\n{err_msg or PLAYWRIGHT_INSTALL_CMD}"
            ),
        )

    # Real Playwright implementation
    async_playwright, PlaywrightTimeout = _import_playwright()

    pages_visited = [url]
    extractions: list[dict] = []
    screenshot_paths: list[str] = []

    # Screenshots directory
    screenshot_dir = Path(os.environ.get("SCREENSHOT_DIR", "/tmp/runtime-screenshots"))
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # Enable request/response logging for debugging
            async def handle_console(msg):
                # Log errors only
                if msg.type == "error":
                    log.warning("browser.console.error", url=url, text=msg.text)

            page.on("console", handle_console)

            # Navigate
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            pages_visited.append(page.url)

            # Take initial screenshot
            screenshot_path = str(screenshot_dir / f"{uuid.uuid4().hex[:8]}.png")
            try:
                await page.screenshot(path=screenshot_path, full_page=False)
                screenshot_paths.append(screenshot_path)
            except Exception as exc:
                log.warning("browser.screenshot.failed", url=url, error=str(exc))

            extraction: dict = {
                "action": "navigate",
                "extracted": {},
            }

            # Extract requested selectors
            if extract_selectors:
                for name, selector in extract_selectors.items():
                    try:
                        if name == "title":
                            val = await page.title()
                        else:
                            val = await page.eval_on_selector(selector, "el => el.innerText")
                        extraction["extracted"][name] = val
                    except Exception as exc:
                        extraction["extracted"][name] = f"[Error: {exc}]"

            # Extract general page info
            try:
                extraction["extracted"]["title"] = await page.title()
            except Exception:
                pass

            try:
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.slice(0, 20).map(el => ({text: el.innerText.trim().slice(0, 80), href: el.href}))",
                )
                extraction["extracted"]["links"] = links
            except Exception:
                extraction["extracted"]["links"] = []

            extractions.append(extraction)

            # Perform actions
            if actions:
                for action_def in actions:
                    action_type = action_def.get("type")
                    selector = action_def.get("selector", "")
                    value = action_def.get("value", "")

                    if not selector:
                        log.warning("browser.action.no_selector", action_type=action_type)
                        continue

                    try:
                        match action_type:
                            case "click":
                                await page.click(selector, timeout=10000)
                            case "fill":
                                await page.fill(selector, str(value))
                            case "type":
                                await page.type(selector, str(value))
                            case "wait":
                                await asyncio.sleep(float(value))
                            case "wait_for_selector":
                                await page.wait_for_selector(selector, timeout=10000)
                            case "press":
                                await page.press(selector, str(value))
                            case "screenshot":
                                action_ss = str(screenshot_dir / f"{uuid.uuid4().hex[:8]}.png")
                                await page.screenshot(path=action_ss, full_page=False)
                                screenshot_paths.append(action_ss)
                            case "navigate":
                                await page.goto(str(value), wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                                pages_visited.append(page.url)
                            case _:
                                log.warning("browser.unknown_action", action_type=action_type)

                        log.info("browser.action.done", action_type=action_type, selector=selector)

                    except PlaywrightTimeout:
                        log.warning("browser.action.timeout", action_type=action_type, selector=selector)
                    except Exception as exc:
                        log.warning("browser.action.error", action_type=action_type, selector=selector, error=str(exc))

            # Final state
            final_state = {
                "url": page.url,
                "title": await page.title(),
                "text_excerpt": (await page.inner_text("body"))[:500] if await page.query_selector("body") else "",
            }

            await browser.close()

        log.info(
            "browser_navigate.done",
            user_id=user_id,
            url=url,
            pages_visited=len(pages_visited),
            extractions=len(extractions),
            screenshots=len(screenshot_paths),
        )

        return SkillResult(
            ok=True,
            data={
                "pages_visited": pages_visited,
                "extractions": extractions,
                "screenshot_paths": screenshot_paths,
                "final_state": final_state,
            },
        )

    except PlaywrightTimeout as exc:
        log.error("browser_navigate.timeout", url=url, user_id=user_id, error=str(exc))
        return SkillResult(
            ok=False,
            data=None,
            error=f"Page load timed out after {timeout_seconds}s: {url}",
        )
    except Exception as exc:  # noqa: BLE001
        log.error("browser_navigate.error", url=url, user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(
            ok=False,
            data=None,
            error=f"Browser automation error: {exc}",
        )
