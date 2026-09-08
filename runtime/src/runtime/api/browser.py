"""Browser automation API.

Per spec §3.7: The Browser Agent drives a real browser via
browser_navigate (read-only) and browser_fill_form (sensitive).
This module exposes:

  POST /api/v1/runtime/browser/run  — run a browser task
  GET  /api/v1/runtime/browser/sessions  — list active sessions

The stub implementation returns mock results without a live browser.
Real browser automation (Playwright) lands in PR 4.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from runtime.infrastructure.auth import decode_bearer, AuthError
from runtime.skills.browser_navigate import browser_navigate
from runtime.skills.browser_fill_form import browser_fill_form

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/runtime/browser", tags=["browser"])


# ---------------------------------------------------------------------------
# Session state (in-memory; PR 4 moves to DB for multi-worker)
# ---------------------------------------------------------------------------


@dataclass
class BrowserSession:
    """Per-user browser session state."""

    session_id: str
    user_id: str
    started_at: str
    last_url: str | None = None
    cookies: dict = field(default_factory=dict)


_active_sessions: dict[str, BrowserSession] = {}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class NavigateRequest(BaseModel):
    """Run a read-only browser navigation task."""

    url: str
    actions: list[dict[str, Any]] | None = None
    timeout_seconds: int = 60
    extract_selectors: dict[str, str] | None = None
    session_id: str | None = None  # reuse existing session


class FillFormRequest(BaseModel):
    """Run a browser form-fill task (sensitive; requires confirmation)."""

    url: str
    fields: dict[str, str] | None = None
    submit: bool = True
    action: str | None = None
    session_id: str | None = None


class BrowserResult(BaseModel):
    """Result of a browser run."""

    session_id: str
    success: bool
    pages_visited: list[str] | None = None
    extractions: list[dict] | None = None
    final_url: str | None = None
    final_title: str | None = None
    screenshot_paths: list[str] | None = None
    result_page: dict | None = None
    stub: bool = True
    stub_note: str = (
        "This is a stub result. Real browser automation with Playwright "
        "lands in PR 4."
    )
    error: str | None = None


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _get_user_id(authorization: str | None = Header(None)) -> str:
    """Validate JWT and return user_id."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    try:
        ctx = decode_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )
    return ctx.user_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/run",
    response_model=BrowserResult,
    summary="Run a browser automation task",
    description=(
        "Runs a browser navigation or form-fill task. Read-only tasks (navigate) "
        "are executed directly. Sensitive tasks (form-fill) require prior "
        "confirmation via the security gate. Returns a stub result in PR 3; "
        "real Playwright automation lands in PR 4."
    ),
)
async def run_browser_task(
    request: NavigateRequest | FillFormRequest,
    user_id: str = Depends(_get_user_id),
) -> BrowserResult:
    """Run a browser task (navigation or form-fill).

    The request body discriminates by the presence of `fields`:
    - With `fields`: treated as a form-fill (sensitive) task.
    - Without `fields`: treated as a navigation (read-only) task.

    For the stub, both paths return mock results. Real Playwright
    automation lands in PR 4.
    """
    session_id = request.session_id or str(uuid.uuid4())

    # Track or create session
    if session_id not in _active_sessions:
        _active_sessions[session_id] = BrowserSession(
            session_id=session_id,
            user_id=user_id,
            started_at=_iso_now(),
        )
    browser_session = _active_sessions[session_id]

    # Dispatch to skill
    if isinstance(request, FillFormRequest):
        # Sensitive: requires prior user confirmation in production
        # (the executor's gate handles this before this endpoint is called)
        log.info(
            "browser.run.form_fill",
            session_id=session_id,
            user_id=user_id,
            url=request.url,
        )
        result = await browser_fill_form(
            url=request.url,
            fields=request.fields,
            submit=request.submit,
            action=request.action,
            user_id=user_id,
        )
        return BrowserResult(
            session_id=session_id,
            success=result.ok,
            pages_visited=[request.url],
            result_page=result.data.get("result_page") if result.ok else None,
            stub=True,
            stub_note="browser_fill_form is a stub until PR 4.",
            error=result.error,
        )
    else:
        log.info(
            "browser.run.navigate",
            session_id=session_id,
            user_id=user_id,
            url=request.url,
        )
        result = await browser_navigate(
            url=request.url,
            actions=request.actions,
            timeout_seconds=request.timeout_seconds,
            extract_selectors=request.extract_selectors,
            user_id=user_id,
        )

        if result.ok:
            browser_session.last_url = request.url
            return BrowserResult(
                session_id=session_id,
                success=True,
                pages_visited=result.data.get("pages_visited"),
                extractions=result.data.get("extractions"),
                final_url=result.data.get("final_state", {}).get("url"),
                final_title=result.data.get("final_state", {}).get("title"),
                screenshot_paths=result.data.get("screenshot_paths"),
                stub=True,
                stub_note="browser_navigate is a stub until PR 4.",
            )
        else:
            return BrowserResult(
                session_id=session_id,
                success=False,
                error=result.error,
                stub=True,
            )


@router.get(
    "/sessions",
    summary="List active browser sessions",
)
async def list_sessions(
    user_id: str = Depends(_get_user_id),
) -> dict:
    """List active browser sessions for the current user."""
    user_sessions = [
        {
            "session_id": s.session_id,
            "started_at": s.started_at,
            "last_url": s.last_url,
        }
        for s in _active_sessions.values()
        if s.user_id == user_id
    ]
    return {"sessions": user_sessions}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
