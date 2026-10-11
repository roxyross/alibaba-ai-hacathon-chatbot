"""Dedicated CLI Launcher for Safe WhatsApp Web QR Session Onboarding (Phase P2).

Provides guided, interactive browser session enrollment into the dedicated
Playwright profile (~/.roxy/browser_profiles/whatsapp_personal).

Governing Principles (Zero Simulation Doctrine):
1. Non-invasive: Opens only the isolated personal profile directory; never touches
   or exports cookies, tokens, or personal chat databases.
2. User-driven: The human user explicitly scans the QR code with their own phone.
3. Safe for CI: Provides --dry-run and --check-status flags for testing without
   spawning graphical windows in automated environments.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import time
from typing import Any

import structlog

from app.integrations.whatsapp_personal import _PROFILE_BASE_DIR, _WHATSAPP_PROFILE_NAME

log = structlog.get_logger()


def check_profile_status(profile_dir: Path | str | None = None) -> dict[str, Any]:
    """Inspect dedicated browser profile directory without launching browser."""
    target_dir = Path(profile_dir) if profile_dir else _PROFILE_BASE_DIR

    exists = target_dir.exists()
    file_count = 0
    total_bytes = 0

    if exists:
        try:
            items = list(target_dir.iterdir())
            file_count = len(items)
            for item in items:
                if item.is_file():
                    total_bytes += item.stat().st_size
                elif item.is_dir():
                    with_suppressed_errors = False
                    try:
                        total_bytes += sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    except Exception:
                        pass
        except Exception as exc:
            return {
                "exists": True,
                "profile_dir": str(target_dir),
                "profile_name": _WHATSAPP_PROFILE_NAME,
                "status": "INACCESSIBLE",
                "error": str(exc),
                "is_authenticated": False,
            }

    is_authenticated = exists and file_count > 0

    status = "AUTHENTICATED" if is_authenticated else ("EMPTY" if exists else "NOT_CONFIGURED")

    return {
        "exists": exists,
        "profile_dir": str(target_dir),
        "profile_name": _WHATSAPP_PROFILE_NAME,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "status": status,
        "is_authenticated": is_authenticated,
    }


async def launch_whatsapp_web_onboarding(
    profile_dir: Path | str | None = None,
    headless: bool = False,
    timeout_sec: float = 120.0,
    dry_run: bool = False,
    interactive_prompt: bool = True,
) -> dict[str, Any]:
    """Launch Playwright browser context to allow user to scan WhatsApp QR code.

    Args:
        profile_dir: Directory to store browser cookies and local storage.
        headless: If True, run headless (used for CI verification). Default False.
        timeout_sec: Maximum time to wait for QR scan or manual exit.
        dry_run: If True, validates prerequisites and exits immediately without launching browser.
        interactive_prompt: If True, log user guidance on console.
    """
    target_dir = Path(profile_dir) if profile_dir else _PROFILE_BASE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        status_info = check_profile_status(target_dir)
        return {
            "success": True,
            "dry_run": True,
            "profile_dir": str(target_dir),
            "profile_name": _WHATSAPP_PROFILE_NAME,
            "profile_status": status_info["status"],
            "message": "Dry-run check succeeded. Browser profile directory is ready.",
        }

    try:
        from playwright.async_api import async_playwright
    except ImportError as err:
        return {
            "success": False,
            "error": "PLAYWRIGHT_NOT_INSTALLED",
            "message": "Playwright is not installed. Run 'pip install playwright && playwright install chromium'.",
            "details": str(err),
        }

    start_time = time.perf_counter()
    qr_scanned = False
    details: dict[str, Any] = {}

    if interactive_prompt and not headless:
        print("\n" + "=" * 70)
        print("  ROXY-AI — WHATSAPP WEB ONBOARDING LAUNCHER")
        print("=" * 70)
        print(f"  Target Profile: {target_dir}")
        print("  Instructions:")
        print("  1. A dedicated Chrome/Chromium window will open to https://web.whatsapp.com")
        print("  2. Open WhatsApp on your phone -> Settings -> Linked Devices -> Link a Device")
        print("  3. Point your camera at the on-screen QR code.")
        print("  4. Once your chats appear, your session is saved in this isolated profile.")
        print("=" * 70 + "\n")

    async with async_playwright() as p:
        browser_context = None
        try:
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir=str(target_dir),
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-default-browser-check",
                ],
            )

            page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=30000)

            # Poll for authentication signal or timeout
            poll_end = time.perf_counter() + timeout_sec
            while time.perf_counter() < poll_end:
                if headless:
                    # In headless CI mode, don't block for 120s; probe once and exit
                    break

                try:
                    # If chat list container or side pane appears, user has logged in
                    chat_pane = await page.query_selector("#pane-side, div[data-testid='chat-list']")
                    if chat_pane is not None:
                        qr_scanned = True
                        if interactive_prompt:
                            print("\n[INFO] WhatsApp Web chat list detected! Syncing session data to profile...")
                        await asyncio.sleep(4.0)
                        break
                except Exception:
                    pass

                await asyncio.sleep(2.0)

            details["duration_sec"] = round(time.perf_counter() - start_time, 2)
            details["qr_detected_or_scanned"] = qr_scanned

        except Exception as exc:
            return {
                "success": False,
                "error": "BROWSER_LAUNCH_ERROR",
                "message": f"Failed to launch or navigate browser: {exc}",
                "profile_dir": str(target_dir),
            }
        finally:
            if browser_context:
                try:
                    await browser_context.close()
                except Exception:
                    pass

    final_status = check_profile_status(target_dir)
    return {
        "success": True,
        "profile_dir": str(target_dir),
        "qr_scanned": qr_scanned,
        "final_status": final_status["status"],
        "is_authenticated": final_status["is_authenticated"],
        "details": details,
        "message": f"WhatsApp Web session check completed. Status: {final_status['status']}. QR Scanned: {qr_scanned}.",
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for launch_web_profile."""
    parser = argparse.ArgumentParser(
        description="Roxy-AI: Safe WhatsApp Web Browser Profile QR Onboarding Launcher"
    )
    parser.add_argument(
        "--check-status",
        action="store_true",
        help="Inspect status of dedicated profile directory and exit without opening browser.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate profile path and configuration without launching browser.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (for automated testing). Default is False.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout in seconds to wait for QR scan. Default: 120.",
    )
    parser.add_argument(
        "--profile-dir",
        type=str,
        default=None,
        help="Optional custom profile directory path.",
    )

    args = parser.parse_args(argv)

    if args.check_status:
        res = check_profile_status(args.profile_dir)
        print(f"Profile Directory: {res['profile_dir']}")
        print(f"Status: {res['status']}")
        print(f"Authenticated: {res['is_authenticated']}")
        print(f"Files: {res.get('file_count', 0)} (Total bytes: {res.get('total_bytes', 0)})")
        return 0

    result = asyncio.run(
        launch_whatsapp_web_onboarding(
            profile_dir=args.profile_dir,
            headless=args.headless,
            timeout_sec=args.timeout,
            dry_run=args.dry_run,
        )
    )

    if result.get("success"):
        print(f"[SUCCESS] {result.get('message', 'Onboarding completed.')}")
        return 0
    else:
        print(f"[ERROR] {result.get('message', result.get('error'))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
