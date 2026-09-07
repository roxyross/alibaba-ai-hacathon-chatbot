"""browser_navigate skill — fetch a URL and return a content preview.

Uses httpx for simple HTML pages; falls back to Playwright for JS-heavy SPAs,
banking sites, and other JavaScript-rendered content.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Annotated

import httpx
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    BrowserNavigateRequest,
    BrowserNavigateResponse,
)


log = structlog.get_logger()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class BrowserNavigateSkill(SkillExecutor[BrowserNavigateRequest, BrowserNavigateResponse]):
    slug = "browser_navigate"

    async def execute(self, input_data: BrowserNavigateRequest) -> BrowserNavigateResponse:
        url = input_data.url.strip()
        timeout = input_data.timeout_seconds

        if input_data.js_enabled:
            return await self._playwright_navigate(url, timeout, input_data.wait_for)
        return await self._httpx_navigate(url, timeout, input_data.wait_for)

    async def _httpx_navigate(
        self, url: str, timeout: int, wait_for: str | None
    ) -> BrowserNavigateResponse:
        """Simple HTTP fetch — fast but no JS rendering."""
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(timeout, connect=10.0),
                headers=_HEADERS,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            final_url = str(resp.url)
            content_type = resp.headers.get("content-type", "")
            html = resp.text

            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else None

            preview = self._strip_tags(html)
            preview = re.sub(r"\s+", " ", preview).strip()[:2000]

            if "text/html" not in content_type.lower():
                preview = resp.text[:2000]

            return BrowserNavigateResponse(
                url=url,
                title=title,
                final_url=final_url,
                content_preview=preview,
                success=True,
                error=None,
            )

        except httpx.TimeoutException:
            return BrowserNavigateResponse(
                url=url, title=None, final_url=url,
                content_preview="", success=False, error=f"Timeout after {timeout}s",
            )
        except Exception as exc:
            log.error("browser_navigate.httpx_failed", url=url, error=str(exc))
            return BrowserNavigateResponse(
                url=url, title=None, final_url=url,
                content_preview="", success=False, error=str(exc),
            )

    async def _playwright_navigate(
        self, url: str, timeout: int, wait_for: str | None
    ) -> BrowserNavigateResponse:
        """Full browser with Playwright — renders JS-heavy pages."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.warning("browser_navigate.playwright_not_installed", url=url)
            return BrowserNavigateResponse(
                url=url, title=None, final_url=url,
                content_preview="",
                success=False,
                error=(
                    "Playwright is not installed. "
                    "Install with: pip install playwright && playwright install chromium. "
                    "Falling back to httpx for this request."
                ),
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

                final_url = page.url

                # Wait for a specific selector if provided
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=timeout * 1000)
                    except Exception:
                        pass  # Non-fatal; proceed with whatever loaded

                title = await page.title()
                html = await page.content()

                preview = self._strip_tags(html)
                preview = re.sub(r"\s+", " ", preview).strip()[:2000]

                await browser.close()

                return BrowserNavigateResponse(
                    url=url,
                    title=title,
                    final_url=final_url,
                    content_preview=preview,
                    success=True,
                    error=None,
                )

        except Exception as exc:
            log.error("browser_navigate.playwright_failed", url=url, error=str(exc))
            return BrowserNavigateResponse(
                url=url, title=None, final_url=url,
                content_preview="", success=False, error=str(exc),
            )

    @staticmethod
    def _strip_tags(html: str) -> str:
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        return text.strip()


def get_executor() -> BrowserNavigateSkill:
    return BrowserNavigateSkill()
