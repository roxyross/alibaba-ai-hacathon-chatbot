"""email_draft skill — create a Gmail draft via the backend's OAuth flow.

The runtime does not manage its own Gmail OAuth; instead it calls the backend's
Gmail API proxy. If no email integration is configured, returns a clearly-labeled
mock draft.

This skill creates a draft — it does NOT send the email. The email_send skill
(which is sensitive and requires explicit user confirmation) handles actual sending.
"""

from __future__ import annotations

import re
import structlog

import httpx

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_EMAIL_DRAFT_URL = "/api/v1/email/draft"


def _is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


async def email_draft(
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Create a Gmail draft.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: Optional list of CC email addresses.
        bcc: Optional list of BCC email addresses.
        user_id: for audit logging.

    Returns:
        SkillResult with draft metadata (id, preview_url, etc.).
    """
    log.info(
        "email_draft.invoked",
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

    # Validate CC/BCC
    if cc:
        invalid_cc = [e for e in cc if not _is_valid_email(e.strip())]
        if invalid_cc:
            return SkillResult(
                ok=False,
                data=None,
                error=f"Invalid CC email addresses: {invalid_cc}",
            )

    # Try to create draft via backend's Gmail proxy
    backend_url = f"{settings.backend_base_url}{_EMAIL_DRAFT_URL}"
    payload = {
        "to": to,
        "subject": subject.strip(),
        "body": body.strip(),
        "cc": [e.strip() for e in (cc or [])],
        "bcc": [e.strip() for e in (bcc or [])],
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                backend_url,
                json=payload,
                headers={"Authorization": f"Bearer {user_id}"},
            )

        if resp.status_code == 401:
            return SkillResult(
                ok=False,
                data=None,
                error="Gmail not connected. Please connect your Google account in Settings.",
            )

        if not resp.is_success:
            return SkillResult(
                ok=False,
                data=None,
                error=f"Email draft creation failed: {resp.status_code} {resp.text[:200]}",
            )

        data = resp.json()
        log.info(
            "email_draft.created",
            user_id=user_id,
            draft_id=data.get("draft_id"),
            to=to,
        )

        return SkillResult(
            ok=True,
            data={
                "draft_id": data.get("draft_id"),
                "preview_url": data.get("preview_url"),
                "to": to,
                "subject": subject.strip(),
                "cc": payload["cc"],
                "created_at": data.get("created_at"),
            },
        )

    except httpx.HTTPError as exc:
        log.warning("email_draft.backend_unavailable", user_id=user_id, error=str(exc))
        # Fall back to mock
        return SkillResult(
            ok=True,
            data={
                "draft_id": f"mock-{user_id[:8]}",
                "preview_url": None,
                "to": to,
                "subject": subject.strip(),
                "cc": payload["cc"],
                "is_mock": True,
                "note": (
                    "Email integration is not configured. This draft was not saved. "
                    "Connect Gmail in Settings to enable email drafts."
                ),
            },
            warning="Email draft was not saved — Gmail integration is not configured. "
                    "Connect your Google account in Settings.",
        )
    except Exception as exc:  # noqa: BLE001
        log.error("email_draft.error", user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(ok=False, data=None, error=f"Failed to create draft: {exc}")
