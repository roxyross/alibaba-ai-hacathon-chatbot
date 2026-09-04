"""Magic-link email sender with a console fallback for dev."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import structlog

log = structlog.get_logger()


async def send_magic_link(to_email: str, link: str) -> None:
    """Send the magic link via SMTP. If SMTP isn't configured, log it instead.

    In dev, copy the printed link from the server console and paste it into
    the browser to complete sign-in.
    """
    smtp_host = os.environ.get("SMTP_HOST")
    if not smtp_host:
        log.info(
            "auth.magic_link.dev_fallback",
            to=to_email,
            link=link,
            message="SMTP not configured. Use this link to sign in.",
        )
        return

    # Lazy import so dev installs without aiosmtplib still boot.
    import aiosmtplib
    from email.message import EmailMessage

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user or "no-reply@roxy.local")
    use_tls = os.environ.get("SMTP_TLS", "true").lower() != "false"

    subject = "Your ROXY sign-in link"
    body = (
        f"Hello,\n\n"
        f"Click the link below to sign in to ROXY. It expires in 15 minutes.\n\n"
        f"{link}\n\n"
        f"If you didn't request this, you can ignore this email.\n"
    )
    html = (
        f"<p>Hello,</p>"
        f"<p>Click the link below to sign in to ROXY. It expires in 15 minutes.</p>"
        f'<p><a href="{link}">Sign in to ROXY</a></p>'
        f"<p>If you didn't request this, you can ignore this email.</p>"
    )

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_pass or None,
            start_tls=use_tls,
        )
        log.info("auth.magic_link.sent", to=to_email)
    except Exception as exc:  # noqa: BLE001 — log and fall back, don't crash auth
        log.error(
            "auth.magic_link.send_failed",
            to=to_email,
            error=str(exc),
            link=link,
            message="Falling back to console log.",
        )


def build_magic_link(token: str) -> str:
    """Compose the full URL the user clicks in their email."""
    base = os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    qs = urlencode({"token": token})
    return f"{base}/auth/callback?{qs}"
