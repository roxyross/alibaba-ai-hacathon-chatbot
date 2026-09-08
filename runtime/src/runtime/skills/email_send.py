"""email_send skill — send a Gmail via the backend's OAuth proxy, or directly.

This is a **sensitive** skill (spec §3.3). The SecurityGate must review
the action AND the user must explicitly confirm before this skill executes.
The AgentExecutor enforces this by stopping the skill loop and returning a
confirmation request to the Coordinator when it detects email_send.

This skill is called by the Coordinator after user confirmation is obtained.

Strategy:
  1. Try the backend's Gmail proxy at POST /api/v1/email/send.
  2. If that fails (404, unreachable), fall back to direct Gmail API call
     using the user's refresh token from the backend's token store.
  3. If neither works, return a clear error with remediation steps.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone

import httpx
import structlog

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_EMAIL_PROXY_PATH = "/api/v1/email/send"
_GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def _build_gmail_mime(
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> str:
    """Build a RFC 2822 MIME message, then base64-url encode it for the Gmail API."""
    import email.utils
    import uuid

    msg_id = uuid.uuid4().hex
    now = email.utils.formatdate(localtime=True)
    headers = [
        ("From", "me"),
        ("To", to),
        ("Subject", subject),
        ("Date", now),
        ("Message-ID", f"<{msg_id}@{settings.gmail_client_id or 'runtime'}>"),
    ]
    if cc:
        headers.append(("Cc", ", ".join(cc)))
    if bcc:
        headers.append(("Bcc", ", ".join(bcc)))

    lines = [f"{k}: {v}" for k, v in headers]
    lines.append("")
    lines.append(body)

    raw = "\r\n".join(lines).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


async def _get_access_token_from_backend(user_id: str) -> str | None:
    """Ask the backend for a fresh Gmail access token for the given user."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.backend_base_url}/api/v1/calendar/token",
                headers={"Authorization": f"Bearer {user_id}"},
            )
            if resp.is_success:
                data = resp.json()
                if isinstance(data, dict):
                    token = data.get("access_token")
                    if isinstance(token, str):
                        return token
    except httpx.HTTPError:
        pass
    return None


async def _send_via_gmail_api(access_token: str, to: str, subject: str, body: str,
                               cc: list[str] | None, bcc: list[str] | None) -> tuple[bool, str | None, str | None]:
    """Send directly via Gmail API. Returns (ok, message_id or None, error or None)."""
    mime = _build_gmail_mime(to, subject, body, cc, bcc)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = json.dumps({"raw": mime})

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _GMAIL_SEND_URL,
                headers=headers,
                content=payload,
            )
        if resp.is_success:
            data = resp.json()
            msg_id = data.get("id") if isinstance(data, dict) else None
            return True, str(msg_id) if msg_id is not None else None, None
        if resp.status_code == 401:
            return False, None, "Gmail access token expired. Please reconnect your Google account in Settings."
        if resp.status_code == 403:
            return False, None, "Gmail access denied. Check your Google account permissions."
        return False, None, f"Gmail API error: {resp.status_code}"
    except httpx.HTTPError as exc:
        return False, None, f"Failed to reach Gmail API: {exc}"


async def email_send(
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Send an email.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: Optional list of CC email addresses.
        bcc: Optional list of BCC email addresses.
        user_id: for audit logging.

    Returns:
        SkillResult with send confirmation metadata.
    """
    log.info(
        "email_send.invoked",
        user_id=user_id,
        to=to,
        subject=subject[:80],
    )

    # Validate inputs
    if not to or not to.strip():
        return SkillResult(ok=False, data=None, error="Recipient (to) is required")

    to = to.strip()
    if not _is_valid_email(to):
        return SkillResult(ok=False, data=None, error=f"Invalid recipient email address: '{to}'")

    if not subject or not subject.strip():
        return SkillResult(ok=False, data=None, error="Subject is required")

    if not body or not body.strip():
        return SkillResult(ok=False, data=None, error="Body is required")

    if len(body) > 100_000:
        return SkillResult(
            ok=False,
            data=None,
            error="Email body exceeds 100,000 characters. Please shorten it.",
        )

    if cc:
        invalid_cc = [e for e in cc if not _is_valid_email(e.strip())]
        if invalid_cc:
            return SkillResult(
                ok=False,
                data=None,
                error=f"Invalid CC email addresses: {invalid_cc}",
            )

    # ---- Strategy 1: Backend Gmail proxy ---------------------------------
    proxy_payload = {
        "to": to,
        "subject": subject.strip(),
        "body": body.strip(),
        "cc": [e.strip() for e in (cc or [])],
        "bcc": [e.strip() for e in (bcc or [])],
        "confirm": True,
    }

    try:
        backend_url = f"{settings.backend_base_url}{_EMAIL_PROXY_PATH}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                backend_url,
                json=proxy_payload,
                headers={"Authorization": f"Bearer {user_id}"},
            )

        if resp.status_code == 401:
            return SkillResult(
                ok=False,
                data=None,
                error="Gmail not connected. Please connect your Google account in Settings to send emails.",
            )

        if resp.status_code == 403:
            return SkillResult(
                ok=False,
                data=None,
                error="Gmail access denied. Please check your Google account permissions in Settings.",
            )

        if resp.status_code == 404:
            # Backend proxy not implemented yet — fall through to direct Gmail API
            log.info("email_send.backend_proxy_not_found", user_id=user_id)

        elif not resp.is_success:
            return SkillResult(
                ok=False,
                data=None,
                error=f"Email send failed: {resp.status_code} {resp.text[:200]}",
            )

        else:
            data = resp.json()
            log.info(
                "email_send.sent_via_proxy",
                user_id=user_id,
                to=to,
                message_id=data.get("message_id"),
            )
            return SkillResult(
                ok=True,
                data={
                    "sent": True,
                    "message_id": data.get("message_id"),
                    "to": to,
                    "subject": subject.strip(),
                },
            )

    except httpx.HTTPError:
        # Network error — fall through to direct Gmail API
        log.info("email_send.backend_unreachable_using_direct", user_id=user_id)

    # ---- Strategy 2: Direct Gmail API -----------------------------------
    access_token = await _get_access_token_from_backend(user_id)
    if not access_token:
        return SkillResult(
            ok=False,
            data=None,
            error=(
                "Email service is not configured. The backend's Gmail proxy is unavailable "
                "and no Gmail access token could be retrieved. "
                "Please connect your Google account in Settings."
            ),
        )

    ok, message_id, error = await _send_via_gmail_api(
        access_token, to, subject.strip(), body.strip(),
        [e.strip() for e in (cc or [])],
        [e.strip() for e in (bcc or [])],
    )

    if ok:
        log.info("email_send.sent_via_gmail_api", user_id=user_id, to=to, message_id=message_id)
        return SkillResult(
            ok=True,
            data={
                "sent": True,
                "message_id": message_id,
                "to": to,
                "subject": subject.strip(),
            },
        )

    log.error("email_send.failed", user_id=user_id, to=to, error=error)
    return SkillResult(ok=False, data=None, error=error)
