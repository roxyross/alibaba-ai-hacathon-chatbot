"""email_send skill — send an email via Gmail API (OAuth2) or SMTP.

Sensitive — requires explicit user confirmation before dispatch.

Supports two modes:
1. Gmail API (primary) — uses the user's stored OAuth2 access token.
   Requires: user has connected Gmail via /auth/oauth/google with gmail.send scope.
2. SMTP fallback — uses SMTP credentials from env vars.
   Requires: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import contextlib
import hashlib
import json
import os
import smtplib
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

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
        msg = EmailMessage()
        msg["To"] = input_data.to
        msg["Subject"] = input_data.subject
        if input_data.cc:
            msg["Cc"] = ", ".join(input_data.cc)
        if input_data.bcc:
            msg["Bcc"] = ", ".join(input_data.bcc)
        msg.set_content(input_data.body)

        raw_bytes = msg.as_bytes()

        # 1. Direct SMTP credentials provided in request or environment take top priority
        if self._has_direct_smtp(input_data) or self._has_smtp_config():
            return self._send_via_smtp(input_data, msg)

        # 2. If Gmail OAuth credentials exist and a token has been saved, use Gmail API
        user_id = input_data.user_id or "default"
        if self._has_gmail_oauth():
            token = self._load_user_token(user_id)
            if token:
                return await self._send_via_gmail_api(input_data, raw_bytes)

        # 3. Fall back to Direct MX delivery
        mx_res = self._send_via_direct_mx(input_data, msg)
        if mx_res.success:
            return mx_res

        # 4. If direct MX failed or was blocked, return actionable diagnostic message
        return EmailSendResponse(
            success=False,
            delivery_status="not_sent",
            error=(
                "Email delivery is not configured. To send emails: "
                "(1) Sign in with Google with Gmail permissions, or "
                "(2) Add your Gmail App Password to SMTP_PASS in backend/.env for rijjienterprise@gmail.com, or "
                "(3) Enter your Gmail App Password in the Sender Settings in the Send Email panel."
            ),
        )

    # -------------------------------------------------------------------------
    # Gmail API (OAuth2)
    # -------------------------------------------------------------------------

    def _has_gmail_oauth(self) -> bool:
        return bool(
            (os.environ.get("GMAIL_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID"))
            and (os.environ.get("GMAIL_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET"))
        )

    @staticmethod
    def _is_production() -> bool:
        """Detect production environment including Vercel indicators."""
        app_env = os.environ.get("APP_ENV", "").lower()
        env = os.environ.get("ENV", "").lower()
        environment = os.environ.get("ENVIRONMENT", "").lower()
        return (
            app_env in ("production", "prod")
            or env in ("production", "prod")
            or environment in ("production", "prod")
            or bool(os.environ.get("VERCEL"))
            or bool(os.environ.get("VERCEL_ENV"))
            or bool(os.environ.get("VERCEL_URL"))
            or os.environ.get("APP_BASE_URL", "").startswith("https://")
        )

    def _get_cipher(self) -> Any:
        """Resolve Fernet / MultiFernet authenticated encryption cipher for user OAuth token storage.

        Enforces SEC-06:
        - In production: strictly requires a dedicated GMAIL_TOKEN_ENCRYPTION_KEY (>= 32 chars).
        - Rejects known or publicly predictable development keys in production.
        - Fails closed (returns None) if key configuration is missing or insecure in production.
        - Supports MultiFernet key rotation when GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK is configured.
        - In non-production: falls back to dev key for offline unit/local testing with warning.
        """
        is_prod = self._is_production()
        primary_key_str = os.environ.get("GMAIL_TOKEN_ENCRYPTION_KEY", "").strip()

        insecure_keys = {
            "roxy-dev-secret-do-not-use-in-prod",
            "dev-key-do-not-use-in-prod",
            "test_key",
            "default_key",
            "development",
        }

        if is_prod:
            if not primary_key_str or primary_key_str in insecure_keys or len(primary_key_str) < 32:
                log.error(
                    "email_send.missing_or_insecure_production_encryption_key",
                    detail="Production Gmail OAuth token encryption requires a dedicated, strong GMAIL_TOKEN_ENCRYPTION_KEY (minimum 32 characters). Refusing insecure fallback.",
                )
                return None
        elif not primary_key_str:
            master_secret = os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY")
            if not master_secret:
                master_secret = "roxy-dev-secret-do-not-use-in-prod"
            derived = hashlib.sha256(f"roxy-gmail-token-encryption:{master_secret}".encode()).digest()
            primary_key_str = base64.urlsafe_b64encode(derived).decode("utf-8")

        try:
            from cryptography.fernet import Fernet, MultiFernet
            ciphers: list[Fernet] = []

            # 1. Initialize primary Fernet cipher
            try:
                ciphers.append(Fernet(primary_key_str.encode("utf-8")))
            except Exception:
                derived = hashlib.sha256(primary_key_str.encode("utf-8")).digest()
                ciphers.append(Fernet(base64.urlsafe_b64encode(derived)))

            # 2. Support transparent key rotation via GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK
            fallback_key_str = os.environ.get("GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK", "").strip()
            if fallback_key_str and fallback_key_str not in insecure_keys:
                try:
                    ciphers.append(Fernet(fallback_key_str.encode("utf-8")))
                except Exception:
                    derived_fb = hashlib.sha256(fallback_key_str.encode("utf-8")).digest()
                    ciphers.append(Fernet(base64.urlsafe_b64encode(derived_fb)))

            return MultiFernet(ciphers)
        except Exception as exc:
            log.warning("email_send.cipher_init_failed", error=str(exc))
            return None

    def _token_dir(self) -> str:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    def _save_token_to_db(self, user_id: str, container: dict[str, Any]) -> bool:
        """Persist encrypted token envelope into durable PostgreSQL connector_instances table."""
        if not os.environ.get("DATABASE_URL"):
            return False
        try:
            from sqlalchemy import select

            from app.db import get_session_factory
            from app.models.connector import ConnectorInstance

            factory = get_session_factory()
            if factory is None:
                log.error("email_send.db_session_factory_unavailable", user_id=user_id)
                return False

            async def _async_save() -> bool:
                async with factory() as session:
                    stmt = select(ConnectorInstance).where(
                        ConnectorInstance.user_id == user_id,
                        ConnectorInstance.connector_type == "gmail",
                    )
                    res = await session.execute(stmt)
                    existing = res.scalars().first()
                    now = datetime.now(UTC)
                    if existing:
                        existing.encrypted_credentials_json = json.dumps(container)
                        existing.status = "active"
                        existing.updated_at = now
                    else:
                        new_obj = ConnectorInstance(
                            id=str(uuid.uuid4()),
                            user_id=user_id,
                            connector_type="gmail",
                            name="Gmail OAuth",
                            auth_type="oauth2",
                            status="active",
                            config_json="{}",
                            encrypted_credentials_json=json.dumps(container),
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(new_obj)
                    await session.commit()
                    return True

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return bool(pool.submit(asyncio.run, _async_save()).result(timeout=4.0))
        except Exception as exc:
            log.warning("email_send.db_token_save_fallback", user_id=user_id, error=str(exc))
            return False

    def _load_token_from_db(self, user_id: str) -> dict[str, Any] | None:
        """Fetch encrypted token envelope from durable PostgreSQL connector_instances table."""
        if not os.environ.get("DATABASE_URL"):
            return None
        try:
            from sqlalchemy import select

            from app.db import get_session_factory
            from app.models.connector import ConnectorInstance

            factory = get_session_factory()
            if factory is None:
                log.error("email_send.db_session_factory_unavailable", user_id=user_id)
                return None

            async def _async_load() -> dict[str, Any] | None:
                async with factory() as session:
                    stmt = select(ConnectorInstance).where(
                        ConnectorInstance.user_id == user_id,
                        ConnectorInstance.connector_type == "gmail",
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item and item.encrypted_credentials_json:
                        try:
                            data = json.loads(item.encrypted_credentials_json)
                            if isinstance(data, dict):
                                return data
                        except Exception:
                            return None
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _async_load()).result(timeout=4.0)
        except Exception as exc:
            log.warning("email_send.db_token_load_fallback", user_id=user_id, error=str(exc))
            return None

    def _save_encrypted_token(self, user_id: str, payload: dict[str, Any]) -> bool:
        """Save user OAuth2 token payload encrypted at rest into durable storage."""
        cipher = self._get_cipher()
        if not cipher:
            log.error("email_send.save_token_failed_no_cipher", user_id=user_id)
            return False

        payload_to_encrypt = dict(payload)
        payload_to_encrypt["user_id"] = user_id
        payload_bytes = json.dumps(payload_to_encrypt).encode("utf-8")
        encrypted_bytes = cipher.encrypt(payload_bytes)

        container = {
            "encrypted": True,
            "user_id": user_id,
            "ciphertext": encrypted_bytes.decode("utf-8"),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        has_db = bool(os.environ.get("DATABASE_URL"))
        is_prod = self._is_production()

        # Enforce SEC-06 durable persistence rules:
        if is_prod:
            # When running in production, durable database persistence is strictly required.
            if not has_db:
                log.error(
                    "email_send.production_missing_database_url",
                    user_id=user_id,
                    detail="DATABASE_URL not configured in production mode. Refusing to fall back to ephemeral local container storage.",
                )
                return False

            db_saved = self._save_token_to_db(user_id, container)
            if not db_saved:
                log.error(
                    "email_send.durable_db_write_failed",
                    user_id=user_id,
                    detail="Durable database write failed in production mode. Refusing to report successful persistence.",
                )
                return False

            # In production, never write tokens to a local container disk file.
            return True

        # Non-production (development / test) mode:
        if has_db:
            db_saved = self._save_token_to_db(user_id, container)
            if not db_saved:
                log.error(
                    "email_send.durable_db_write_failed",
                    user_id=user_id,
                    detail="Durable database write failed when DATABASE_URL was configured. Refusing to report successful persistence.",
                )
                return False
        elif os.environ.get("REQUIRE_DURABLE_TOKEN_STORE", "false").lower() in ("true", "1"):
            log.error(
                "email_send.missing_database_url_strict",
                user_id=user_id,
                detail="REQUIRE_DURABLE_TOKEN_STORE enforced but DATABASE_URL is missing. Failing closed.",
            )
            return False

        # In development/test mode only, persist to local container disk for offline/test execution
        data_dir = self._token_dir()
        token_path = os.path.join(data_dir, f"gmail_token_{user_id}.json")
        try:
            with open(token_path, "w", encoding="utf-8") as f:
                json.dump(container, f, indent=2)
            with contextlib.suppress(Exception):
                os.chmod(token_path, 0o600)
            return True
        except Exception as exc:
            log.error("email_send.save_encrypted_token_failed", user_id=user_id, error=str(exc))
            # If durable DB was already written successfully, local cache failure is non-fatal
            return has_db

    def _load_user_token_payload(self, user_id: str) -> dict[str, Any] | None:
        """Load and decrypt stored token payload from durable shared database or local disk."""
        is_prod = self._is_production()
        data: Any = None

        # 1. Attempt load from durable shared database (NeonDB PostgreSQL)
        db_data = self._load_token_from_db(user_id)
        if db_data and isinstance(db_data, dict):
            data = db_data

        # 2. Fall back to local file storage only in development/test mode
        if not data and not is_prod:
            data_dir = self._token_dir()
            token_path = os.path.join(data_dir, f"gmail_token_{user_id}.json")
            if not os.path.exists(token_path):
                token_path = os.path.join(data_dir, "gmail_token_default.json")
                if not os.path.exists(token_path):
                    return None

            try:
                with open(token_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as exc:
                log.warning("email_send.load_file_exception", user_id=user_id, error=str(exc))
                return None

        try:
            if isinstance(data, dict) and data.get("encrypted") and "ciphertext" in data:
                cipher = self._get_cipher()
                if not cipher:
                    log.error("email_send.load_token_failed_no_cipher", user_id=user_id)
                    return None
                ciphertext = data["ciphertext"]
                from cryptography.fernet import InvalidToken
                try:
                    decrypted_bytes = cipher.decrypt(ciphertext.encode("utf-8"))
                except InvalidToken:
                    log.warning("email_send.invalid_token_or_tampered_ciphertext", user_id=user_id)
                    return None
                except Exception as exc:
                    log.warning("email_send.decrypt_exception", user_id=user_id, error=str(exc))
                    return None

                decrypted_obj = json.loads(decrypted_bytes.decode("utf-8"))
                if not isinstance(decrypted_obj, dict):
                    return None
                payload: dict[str, Any] = decrypted_obj
                if payload.get("user_id") and payload["user_id"] != user_id:
                    log.error("email_send.cross_user_token_access_blocked", requested=user_id, owner=payload.get("user_id"))
                    return None

                # Transparent key rotation: if fallback key is configured, re-encrypt under primary
                if os.environ.get("GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK"):
                    with contextlib.suppress(Exception):
                        self._save_encrypted_token(user_id, payload)

                return payload
            elif isinstance(data, dict) and "access_token" in data:
                # Auto-migrate legacy unencrypted token in non-production only
                if not self._is_production():
                    self._save_encrypted_token(user_id, data)
                    return data
                log.warning("email_send.unencrypted_legacy_token_rejected_in_production", user_id=user_id)
                return None
            return None
        except Exception as exc:
            log.warning("email_send.load_token_exception", user_id=user_id, error=str(exc))
            return None

    def _load_user_token(self, user_id: str) -> str | None:
        """Load the stored OAuth2 access token for a user, if present."""
        payload = self._load_user_token_payload(user_id)
        if not payload:
            return None
        expires_at = payload.get("expires_at", 0)
        if datetime.now(UTC).timestamp() >= expires_at - 60:
            return self._refresh_token(user_id, payload.get("refresh_token"))
        access_token = payload.get("access_token")
        return str(access_token) if isinstance(access_token, str) else None

    def _refresh_token(self, user_id: str, refresh_token: str | None) -> str | None:
        if not refresh_token:
            return None
        client_id = os.environ.get("GMAIL_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID")
        client_secret = os.environ.get("GMAIL_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None

        try:
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
                log.warning("email_send.token_refresh_failed", user_id=user_id, status=resp.status_code)
                return None
            data = resp.json()
            access_token = data.get("access_token")
            # Persist refreshed token securely encrypted
            saved = self._save_encrypted_token(
                user_id,
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": datetime.now(UTC).timestamp() + data.get("expires_in", 3600),
                },
            )
            if not saved:
                log.error("email_send.token_refresh_persistence_failed", user_id=user_id)
                return None
            return str(access_token) if isinstance(access_token, str) else None
        except Exception as exc:
            log.warning("email_send.refresh_exception", error=str(exc))
            return None

    def _delete_token_from_db(self, user_id: str) -> bool:
        """Remove revoked token from durable PostgreSQL connector_instances table."""
        if not os.environ.get("DATABASE_URL"):
            return False
        try:
            import concurrent.futures

            from sqlalchemy import delete

            from app.db import get_session_factory
            from app.models.connector import ConnectorInstance

            factory = get_session_factory()
            if factory is None:
                return False

            async def _async_delete() -> bool:
                async with factory() as session:
                    stmt = delete(ConnectorInstance).where(
                        ConnectorInstance.user_id == user_id,
                        ConnectorInstance.connector_type == "gmail",
                    )
                    await session.execute(stmt)
                    await session.commit()
                    return True

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return bool(pool.submit(asyncio.run, _async_delete()).result(timeout=4.0))
        except Exception as exc:
            log.warning("email_send.db_token_delete_failed", user_id=user_id, error=str(exc))
            return False

    def _delete_user_token(self, user_id: str) -> None:
        """Remove user OAuth token from database and local storage upon revocation."""
        self._delete_token_from_db(user_id)
        data_dir = self._token_dir()
        token_path = os.path.join(data_dir, f"gmail_token_{user_id}.json")
        with contextlib.suppress(Exception):
            if os.path.exists(token_path):
                os.remove(token_path)

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
                # Token revoked — clear stored token from durable DB and local cache
                self._delete_user_token(user_id)
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
                sent_at=datetime.now(UTC).isoformat(),
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
    # SMTP support (direct credentials or environment variables)
    # -------------------------------------------------------------------------

    def _has_direct_smtp(self, input_data: EmailSendRequest) -> bool:
        return bool(input_data.smtp_user and input_data.smtp_pass)

    def _has_smtp_config(self) -> bool:
        return all(
            bool(os.environ.get(k))
            for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS")
        )

    def _send_via_smtp(
        self, input_data: EmailSendRequest, msg: EmailMessage
    ) -> EmailSendResponse:
        try:
            # Direct credentials take priority over env vars
            user = (input_data.smtp_user or os.environ.get("SMTP_USER", "")).strip()
            password = (input_data.smtp_pass or os.environ.get("SMTP_PASS", "")).strip().replace(" ", "")
            host = (input_data.smtp_host or os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip()
            port = int(input_data.smtp_port or os.environ.get("SMTP_PORT", "587"))
            from_addr = (input_data.smtp_from or os.environ.get("SMTP_FROM") or user).strip()

            if not user or not password:
                return EmailSendResponse(
                    success=False,
                    delivery_status="failed",
                    error="SMTP username and password/app-password are required to send emails.",
                )

            # Ensure From header is set on the email message
            if not msg.get("From"):
                msg["From"] = from_addr

            raw_bytes = msg.as_bytes()
            all_recipients = [input_data.to] + (input_data.cc or []) + (input_data.bcc or [])

            if port == 465:
                # SSL connection
                with smtplib.SMTP_SSL(host, port, timeout=25) as server:
                    server.login(user, password)
                    server.sendmail(from_addr, all_recipients, raw_bytes)
            else:
                # STARTTLS connection (standard for Gmail & port 587)
                with smtplib.SMTP(host, port, timeout=25) as server:
                    server.ehlo()
                    if server.has_extn("STARTTLS"):
                        server.starttls()
                        server.ehlo()
                    server.login(user, password)
                    server.sendmail(from_addr, all_recipients, raw_bytes)

            msg_id = f"smtp_{uuid.uuid4().hex[:12]}"
            log.info("email_send.smtp_success", to=input_data.to, user=user)
            return EmailSendResponse(
                success=True,
                delivery_status="sent",
                message_id=msg_id,
                sent_at=datetime.now(UTC).isoformat(),
            )

        except smtplib.SMTPAuthenticationError as exc:
            log.warning("email_send.smtp_auth_error", error=str(exc))
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error="SMTP authentication failed. If using Gmail, make sure you use a 16-character Google App Password (not your normal Google account password).",
            )
        except smtplib.SMTPConnectError as exc:
            log.error("email_send.smtp_connect_error", error=str(exc))
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error=f"Could not connect to SMTP server {host}:{port}. Check host and port.",
            )
        except smtplib.SMTPException as exc:
            log.error("email_send.smtp_error", error=str(exc))
            err_msg = str(exc)
            if "550" in err_msg and any(w in err_msg.lower() for w in ("limit", "exceeded", "daily", "quota", "user")):
                detail_err = "Email could not be sent because the email provider's daily sending limit was exceeded."
            else:
                detail_err = f"SMTP delivery error: {exc}"
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error=detail_err,
            )
        except Exception as exc:
            log.error("email_send.smtp_unexpected", error=str(exc))
            return EmailSendResponse(
                success=False,
                delivery_status="failed",
                error=f"Email send failed: {exc}",
            )

    def _send_via_direct_mx(
        self, input_data: EmailSendRequest, msg: EmailMessage
    ) -> EmailSendResponse:
        """Attempt direct DNS MX delivery with transparent fallback so emails can be sent to anybody."""
        recipient = input_data.to.strip()
        domain = recipient.split("@")[-1] if "@" in recipient else ""
        from_addr = (os.environ.get("SMTP_FROM") or "roxy-ai@roxy-personal-ai.com").strip()
        if not msg.get("From"):
            msg["From"] = from_addr

        all_recipients = [recipient] + (input_data.cc or []) + (input_data.bcc or [])
        raw_bytes = msg.as_bytes()
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Attempt to resolve MX host via dnspython or socket
        mx_host = None
        try:
            import dns.resolver
            records = dns.resolver.resolve(domain, "MX")
            if records:
                mx_host = str(sorted(records, key=lambda r: r.preference)[0].exchange).rstrip(".")
        except Exception:
            # Fallback to common domain mail servers
            common_mx = {
                "gmail.com": "gmail-smtp-in.l.google.com",
                "googlemail.com": "gmail-smtp-in.l.google.com",
                "yahoo.com": "mta5.am0.yahoodns.net",
                "outlook.com": "outlook-com.olc.protection.outlook.com",
                "hotmail.com": "hotmail-com.olc.protection.outlook.com",
                "live.com": "live-com.olc.protection.outlook.com",
            }
            mx_host = common_mx.get(domain.lower(), domain)

        if mx_host:
            try:
                with smtplib.SMTP(mx_host, 25, timeout=10) as server:
                    server.ehlo("roxy-personal-ai.com")
                    if server.has_extn("STARTTLS"):
                        server.starttls()
                        server.ehlo("roxy-personal-ai.com")
                    server.sendmail(from_addr, all_recipients, raw_bytes)
                log.info("email_send.direct_mx_success", to=recipient, mx=mx_host)
                return EmailSendResponse(
                    success=True,
                    delivery_status="sent",
                    message_id=msg_id,
                    sent_at=datetime.now(UTC).isoformat(),
                )
            except Exception as mx_err:
                log.info("email_send.direct_mx_fallback", to=recipient, mx=mx_host, error=str(mx_err))

        # If direct MX delivery failed or recipient mail server was unreachable
        log.warning("email_send.direct_mx_unreachable", to=recipient, mx=mx_host)
        return EmailSendResponse(
            success=False,
            delivery_status="failed",
            error=(
                f"Direct mail delivery to {domain or recipient} was unreachable or rejected. "
                "Please configure SMTP credentials (e.g. Gmail App Password in Settings) for guaranteed delivery."
            ),
        )


def get_executor() -> EmailSendSkill:
    return EmailSendSkill()
