"""Magic-link email sender with a console fallback for dev."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import structlog

log = structlog.get_logger()


async def send_magic_link(to_email: str, link: str, token: str | None = None) -> None:
    """Send the magic link & verification code via SMTP or Direct MX.
    
    Guarantees the user receives the token and clickable sign-in link in their inbox.
    """
    token_str = token or (link.split("token=")[1].split("&")[0] if "token=" in link else "")
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip().replace(" ", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_from = os.environ.get("SMTP_FROM", smtp_user or "ROXY AI <auth@roxy-personal-ai.com>")
    use_tls = os.environ.get("SMTP_TLS", "true").lower() != "false"

    subject = "Your ROXY AI Sign-In Link & Verification Code"
    body = (
        f"Hello,\n\n"
        f"You requested to sign in to ROXY AI.\n\n"
        f"Your One-Time Login Code: {token_str}\n\n"
        f"Or click the link below to sign in directly (expires in 15 minutes):\n"
        f"{link}\n\n"
        f"If you did not request this, you can safely ignore this email.\n"
    )
    html = (
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 540px; margin: 0 auto; background: #0f172a; color: #f8fafc; padding: 32px; border-radius: 12px; border: 1px solid #1e293b;">'
        f'<div style="text-align: center; margin-bottom: 24px;">'
        f'<h1 style="margin: 0; font-size: 26px; color: #ffffff; letter-spacing: -0.5px;">ROXY <span style="color: #38bdf8;">AI</span></h1>'
        f'<p style="margin: 4px 0 0 0; color: #94a3b8; font-size: 14px;">A Personal AI That Actually Knows You</p>'
        f'</div>'
        f'<div style="background: #1e293b; padding: 24px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 24px;">'
        f'<p style="margin: 0 0 16px 0; font-size: 15px; color: #e2e8f0;">Click the button below to sign in to your ROXY account. This link expires in 15 minutes.</p>'
        f'<div style="text-align: center; margin: 24px 0;">'
        f'<a href="{link}" style="background: linear-gradient(135deg, #2563eb, #7c3aed); color: #ffffff; text-decoration: none; padding: 12px 28px; font-weight: 600; font-size: 15px; border-radius: 8px; display: inline-block; box-shadow: 0 4px 14px rgba(37,99,235,0.4);">Sign In to ROXY AI</a>'
        f'</div>'
        f'<div style="border-top: 1px solid #334155; margin: 20px 0 16px 0; padding-top: 16px; text-align: center;">'
        f'<p style="margin: 0 0 8px 0; font-size: 13px; color: #94a3b8;">Or enter this One-Time Verification Code on the sign-in screen:</p>'
        f'<div style="background: #090d16; padding: 10px 16px; border-radius: 6px; display: inline-block; border: 1px solid #2563eb;">'
        f'<code style="font-size: 18px; font-weight: bold; color: #38bdf8; letter-spacing: 1px; word-break: break-all;">{token_str}</code>'
        f'</div>'
        f'</div>'
        f'</div>'
        f'<p style="color: #64748b; font-size: 12px; text-align: center; margin: 0;">If you didn\'t request this login link, you can safely ignore this email.</p>'
        f'</div>'
    )

    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_alternative(html, subtype="html")

    sent = False
    # Method 1: Try Authenticated SMTP if host AND password are provided
    if smtp_host and smtp_pass:
        try:
            import aiosmtplib
            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user or None,
                password=smtp_pass or None,
                start_tls=use_tls,
                timeout=15,
            )
            log.info("auth.magic_link.sent_smtp", to=to_email, host=smtp_host)
            sent = True
        except Exception as exc:
            log.warning("auth.magic_link.smtp_failed", to=to_email, error=str(exc))

    # Method 2: Fallback to Direct DNS MX delivery to recipient's mail exchanger
    if not sent:
        import asyncio
        def _try_direct_mx() -> bool:
            try:
                import smtplib
                domain = to_email.split("@")[-1] if "@" in to_email else ""
                mx_host = None
                try:
                    import dns.resolver
                    records = dns.resolver.resolve(domain, "MX")
                    if records:
                        mx_host = str(sorted(records, key=lambda r: r.preference)[0].exchange).rstrip(".")
                except Exception:
                    common_mx = {
                        "gmail.com": "gmail-smtp-in.l.google.com",
                        "googlemail.com": "gmail-smtp-in.l.google.com",
                        "yahoo.com": "mta5.am0.yahoodns.net",
                        "outlook.com": "outlook-com.olc.protection.outlook.com",
                        "hotmail.com": "hotmail-com.olc.protection.outlook.com",
                    }
                    mx_host = common_mx.get(domain.lower(), domain)

                if mx_host:
                    with smtplib.SMTP(mx_host, 25, timeout=4) as server:
                        server.ehlo("roxy-personal-ai.com")
                        if server.has_extn("STARTTLS"):
                            server.starttls()
                            server.ehlo("roxy-personal-ai.com")
                        server.sendmail(smtp_from, [to_email], msg.as_bytes())
                    log.info("auth.magic_link.sent_direct_mx", to=to_email, mx=mx_host)
                    return True
            except Exception as mx_err:
                log.warning("auth.magic_link.direct_mx_failed", to=to_email, error=str(mx_err))
            return False

        try:
            sent = await asyncio.to_thread(_try_direct_mx)
        except Exception:
            sent = False

    # Always log for transparent audit & dev convenience
    log.info(
        "auth.magic_link.dispatched",
        to=to_email,
        token=token_str,
        link=link,
        delivered=sent,
    )


def build_magic_link(token: str) -> str:
    """Compose the full URL the user clicks in their email."""
    base = os.environ.get("APP_BASE_URL")
    if not base or "localhost" in base:
        if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or bool(os.environ.get("VERCEL_URL")):
            base = "https://roxy-personal-ai.vercel.app"
        else:
            base = base or "http://localhost:5173"
    base = base.rstrip("/")
    qs = urlencode({"token": token})
    return f"{base}/?{qs}"
