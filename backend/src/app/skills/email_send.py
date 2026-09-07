"""email_send skill — send an email via Gmail API (OAuth2) or SMTP.

Sensitive — requires explicit user confirmation before dispatch.

Supports two modes:
1. Gmail API (primary) — uses the user's stored OAuth2 access token.
   Requires: user has connected Gmail via /auth/oauth/google with gmail.send scope.
2. SMTP fallback — uses SMTP credentials from env vars.
   Requires: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM.
"""

from __future__ import annotations

import base64
import json
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import EmailPolicy

import httpx
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import EmailSendRequest, EmailSendResponse


log = structlog.get_logger()

# OAuth2 tokens are stored at this path (encrypted at rest in production)
_OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "gmail_tokens.json"
)


class EmailSendSkill(SkillExecutor[EmailSendRequest, EmailSendResponse]):
    slug = "email_send"

    async def execute(self, input_data: EmailSendRequest) -> EmailSendResponse:
        # Pre-send confirmation gate — reject if not confirmed
        if not input_data.confirm:
            return EmailSendResponse(
                success=False,
                delivery_status="not_sent",
                error="Confirmation not received. Set confirm: true to dispatch.",
            )

        # Build the email
        msg = EmailMessage(policy=EmailPolicy(max_line_length=0, encodeutf8=False))
        msg["To"] = input_data.to
        msg["Subject"] = input_data.subject
        if input_data.cc:
            msg["Cc"] = ", ".join(input_data.cc)
        if input_data.bcc:
            msg["Bcc"] = ", ".join(input_data.bcc)
        msg.set_content(input_data.body)

        raw_bytes = msg.as_bytes()

        # Try Gmail API first, fall back to SMTP
        if self._has_gmail_oauth():
            return await self._send_via_gmail_api(input_data, raw_bytes)
        elif self._has_smtp_config():
            return self._send_via_smtp(input_data, raw_bytes)
        else:
            return EmailSendResponse(
                success=False,
                delivery_status="not_sent",
                error=(
                    "Email sending is not configured. "
                    "Set Gmail OAuth2 credentials (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
                    "GMAIL_REDIRECT_URI) or SMTP credentials (SMTP_HOST, SMTP_PORT, "
                    "SMTP_USER, SMTP_PASS, SMTP_FROM) in backend/.env."
                ),
            )

    # -------------------------------------------------------------------------
    # Gmail API (OAuth2)
    # -------------------------------------------------------------------------

    def _has_gmail_oauth(self) -> bool:
        return bool(
            os.environ.get("GMAIL_CLIENT_ID")
            and os.environ.get("GMAIL_CLIENT_SECRET")
        )

    def _load_user_token(self, user_id: str) -> str | None:
        """Load the stored OAuth2 access token for a user, if present."""
        token_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", f"gmail_token_{user_id}.json"
        )
        if not os.path.exists(token_path):
            return None
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Check expiry
            expires_at = data.get("expires_at", 0)
            if datetime.now(timezone.utc).timestamp() >= expires_at - 60:
                # Token expired or about to expire — try refresh
                return self._refresh_token(user_id, data.get("refresh_token"))
            return data.get("access_token")
        except Exception:
            return None

    def _refresh_token(self, user_id: str, refresh_token: str | None) -> str | None:
        if not refresh_token:
            return None
        try:
            client_id = os.environ["GMAIL_CLIENT_ID"]
            client_secret = os.environ["GMAIL_CLIENT_SECRET"]
        except KeyError:
            return None

        token_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", f"gmail_token_{user_id}.json"
        )
        import httpx
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        if resp.status_code != 200:
            log.warning("email_send.token_refresh_failed", user_id=user_id)
            return None
        data = resp.json()
        access_token = data.get("access_token")
        # Persist refreshed token
        try:
            with open(token_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "expires_at": datetime.now(timezone.utc).timestamp()
                        + data.get("expires_in", 3600),
                    },
                    f,
                )
        except Exception:
            pass
        return access_token

    async def _send_via_gmail_api(
        self, input_data: EmailSendRequest, raw_bytes: bytes
    ) -> EmailSendResponse:
        user_id = input_data.user_id or "default"
        access_token = self._load_user_token(user_id)

        if not access_token:
            return EmailSendResponse(
                success=False,
                delivery_status="not_sent",
                error=(
                    "Gmail is not connected. "
                    "Visit /settings to connect your Gmail account for sending."
                ),
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Encode as base64url (Gmail API requirement)
                b64 = base64.urlsafe_b64encode(raw_bytes).decode()
                # Remove padding to satisfy Gmail API
                b64 = b64.rstrip("=")

                resp = await client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json={"raw": b64},
                )

            if resp.status_code == 401:
                # Token revoked — clear stored token
                token_path = os.path.join(
                    os.path.dirname(__file__), "..", "..", "..", "data",
                    f"gmail_token_{user_id}.json",
                )
                try:
                    os.remove(token_path)
                except Exception:
                    pass
                return EmailSendResponse(
                    success=False,
                    delivery_status="not_sent",
                    error="Gmail access token was revoked. Reconnect Gmail in settings.",
                )

            if resp.status_code != 200:
                log.error("email_send.gmail_api_failed", status=resp.status_code, body=resp.text[:300])
                return EmailSendResponse(
                    success=False,
                    delivery_status="failed",
                    error=f"Gmail API error {resp.status_code}: {resp.text[:200]}",
                )

            data = resp.json()
            message_id = data.get("id", "")
            return EmailSendResponse(
                success=True,
                delivery_status="sent",
                message_id=message_id,
                sent_at=datetime.now(timezone.utc).isoformat(),
            )

        except httpx.TimeoutException:
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error="Gmail API request timed out.",
            )
        except Exception as exc:
            log.error("email_send.gmail_api_error", error=str(exc))
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error=f"Email send failed: {exc}",
            )

    # -------------------------------------------------------------------------
    # SMTP fallback
    # -------------------------------------------------------------------------

    def _has_smtp_config(self) -> bool:
        return all(
            bool(os.environ.get(k))
            for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "SMTP_FROM")
        )

    def _send_via_smtp(
        self, input_data: EmailSendRequest, raw_bytes: bytes
    ) -> EmailSendResponse:
        try:
            host = os.environ["SMTP_HOST"]
            port = int(os.environ.get("SMTP_PORT", "587"))
            user = os.environ["SMTP_USER"]
            password = os.environ["SMTP_PASS"]
            from_addr = os.environ["SMTP_FROM"]

            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls()
                server.login(user, password)
                server.sendmail(from_addr, [input_data.to], raw_bytes)

            log.info("email_send.smtp_success", to=input_data.to)
            return EmailSendResponse(
                success=True,
                delivery_status="sent",
                message_id=f"smtp-{datetime.now().timestamp()}",
                sent_at=datetime.now(timezone.utc).isoformat(),
            )

        except smtplib.SMTPAuthenticationError:
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error="SMTP authentication failed. Check SMTP_USER and SMTP_PASS.",
            )
        except smtplib.SMTPException as exc:
            log.error("email_send.smtp_error", error=str(exc))
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error=f"SMTP error: {exc}",
            )
        except Exception as exc:
            log.error("email_send.smtp_error", error=str(exc))
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error=f"Email send failed: {exc}",
            )


def get_executor() -> EmailSendSkill:
    return EmailSendSkill()
