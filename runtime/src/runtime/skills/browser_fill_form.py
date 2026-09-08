"""browser_fill_form skill — real Playwright form fill and submit.

Per the PR 4 plan: real implementation fills forms and optionally submits
using Playwright. This skill is sensitive (requires user confirmation before
submission). The skill itself does NOT enforce confirmation — that is done
by the AgentExecutor's sensitive-skill gate (spec §3.3).

Requires: `playwright` package. Falls back to a clear stub when not installed.
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


async def browser_fill_form(
    url: str,
    fields: dict[str, str],
    submit: bool = False,
    screenshot: bool = True,
    timeout_seconds: int = 60,
    *,
    user_id: str,
) -> SkillResult:
    """Fill form fields on a URL and optionally submit.

    Args:
        url: The URL containing the form to fill.
        fields: Dict of CSS selector -> value to fill.
            e.g. {"#email": "alice@example.com", "#password": "secret123"}
        submit: If True, submit the form after filling. Default False.
            Note: The caller (Browser Agent / Coordinator) must obtain
            explicit user confirmation before setting submit=True.
        screenshot: If True, take a screenshot after filling (before submit).
        timeout_seconds: Timeout for navigation and each action.
        user_id: for audit logging.

    Returns:
        SkillResult with the form fill result and screenshot path.
    """
    log.info(
        "browser_fill_form.invoked",
        user_id=user_id,
        url=url,
        field_count=len(fields),
        submit=submit,
    )

    if not url or not url.strip():
        return SkillResult(ok=False, data=None, error="url cannot be empty")

    if not url.startswith(("http://", "https://")):
        return SkillResult(ok=False, data=None, error=f"Invalid URL: '{url}'")

    if not fields:
        return SkillResult(ok=False, data=None, error="fields cannot be empty")

    ready, err_msg = await _ensure_playwright()
    if not ready:
        return SkillResult(
            ok=True,
            data={
                "url": url,
                "fields_filled": list(fields.keys()),
                "submitted": False,
                "screenshot_path": None,
                "result": {
                    "title": "[Playwright not ready]",
                    "text": f"[STUB] {err_msg or 'Playwright not installed'}",
                },
            },
            warning=(
                f"browser_fill_form is running in stub mode.\n{err_msg or PLAYWRIGHT_INSTALL_CMD}"
            ),
        )

    async_playwright, PlaywrightTimeout = _import_playwright()

    screenshot_dir = Path(os.environ.get("SCREENSHOT_DIR", "/tmp/runtime-screenshots"))
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path: str | None = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            # Navigate to the form
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)

            # Fill each field
            filled: list[str] = []
            errors: list[str] = []

            for selector, value in fields.items():
                try:
                    # Check if it's a textarea or select
                    tag = await page.eval_on_selector(
                        selector,
                        "el => el.tagName.toLowerCase()",
                    )
                    match tag:
                        case "select":
                            await page.select_option(selector, value)
                        case "textarea":
                            await page.fill(selector, value)
                        case "input":
                            # Detect input type
                            input_type = await page.eval_on_selector(
                                selector,
                                "el => el.type.toLowerCase()",
                            )
                            if input_type in ("checkbox", "radio"):
                                if value.lower() in ("true", "1", "yes", "on"):
                                    await page.check(selector)
                                else:
                                    await page.uncheck(selector)
                            else:
                                await page.fill(selector, value)
                        case _:
                            await page.fill(selector, value)

                    filled.append(selector)
                    log.info("browser_fill_form.field_filled", selector=selector, user_id=user_id)

                except PlaywrightTimeout:
                    errors.append(f"Timeout filling '{selector}'")
                except Exception as exc:
                    errors.append(f"Error on '{selector}': {exc}")

            # Screenshot after fill (before submit)
            if screenshot:
                ss_name = f"form-fill-{uuid.uuid4().hex[:8]}.png"
                screenshot_path = str(screenshot_dir / ss_name)
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                except Exception as exc:
                    log.warning("browser_fill_form.screenshot.failed", error=str(exc))
                    screenshot_path = None

            # Submit if requested
            submitted = False
            result_text = ""
            if submit:
                try:
                    # Try to find and click the submit button
                    submit_selectors = [
                        'button[type="submit"]',
                        'input[type="submit"]',
                        "button[type=submit]",
                        "[type=submit]",
                        "form button:last-of-type",
                    ]
                    submitted_btn = None
                    for sel in submit_selectors:
                        el = await page.query_selector(sel)
                        if el:
                            submitted_btn = sel
                            break

                    if submitted_btn:
                        await page.click(submitted_btn, timeout=10000)
                        submitted = True
                        # Wait a moment for the form to process
                        await asyncio.sleep(1.0)
                        result_text = await page.inner_text("body")[:500]
                    else:
                        errors.append("No submit button found in form")

                except PlaywrightTimeout:
                    errors.append("Submit button click timed out")
                except Exception as exc:
                    errors.append(f"Submit error: {exc}")

            final_state = {
                "url": page.url,
                "title": await page.title(),
                "text_excerpt": result_text or ((await page.inner_text("body"))[:500] if await page.query_selector("body") else ""),
            }

            await browser.close()

        log.info(
            "browser_fill_form.done",
            user_id=user_id,
            url=url,
            filled_count=len(filled),
            submitted=submit,
        )

        return SkillResult(
            ok=True,
            data={
                "url": url,
                "fields_filled": filled,
                "field_errors": errors if errors else None,
                "submitted": submitted,
                "screenshot_path": screenshot_path,
                "result": final_state,
            },
        )

    except PlaywrightTimeout as exc:
        log.error("browser_fill_form.timeout", url=url, user_id=user_id)
        return SkillResult(
            ok=False,
            data=None,
            error=f"Form page load timed out after {timeout_seconds}s",
        )
    except Exception as exc:  # noqa: BLE001
        log.error("browser_fill_form.error", url=url, user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(ok=False, data=None, error=f"Form fill error: {exc}")
