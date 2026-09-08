"""Shared Playwright helpers for browser skills.

Provides:
  - _playwright_available()  — package import check
  - _ensure_playwright()     — full setup check (package + browsers)
  - PLAYWRIGHT_INSTALL_CMD   — the command to install browsers
"""

from __future__ import annotations

import structlog

log = structlog.get_logger()

PLAYWRIGHT_INSTALL_CMD = "pip install playwright && playwright install chromium"


def _playwright_available() -> bool:
    """Return True if the playwright package is importable."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


async def _ensure_playwright() -> tuple[bool, str | None]:
    """Check that Playwright package and Chromium browser are installed.

    Returns:
        (True, None)            — fully ready
        (False, error_message)  — not ready, message explains what's missing
    """
    if not _playwright_available():
        return False, (
            "The 'playwright' package is not installed.\n"
            f"Run: {PLAYWRIGHT_INSTALL_CMD}"
        )

    # Package is there — check if browsers are installed by attempting a launch.
    # This is fast because we close immediately.
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Playwright imported but failed to initialize: {exc}\n"
            f"Run: {PLAYWRIGHT_INSTALL_CMD}"
        )

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
    except Exception as exc:  # noqa: BLE001
        err = str(exc).lower()
        if "executable" in err or "browser" in err or "not found" in err:
            return False, (
                "Chromium browser is not installed for Playwright.\n"
                "Run: playwright install chromium"
            )
        return False, (
            f"Failed to launch Chromium: {exc}\n"
            "Try: playwright install chromium"
        )

    return True, None
