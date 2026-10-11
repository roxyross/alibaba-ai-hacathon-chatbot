"""Secret and credential security handling for ROXY-AI.

Provides encryption-at-rest for sensitive credentials, masking for UI/logs/telemetry,
and recursive sanitization of payloads before model prompt exposure or logging.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any

import structlog

log = structlog.get_logger()

# Sensitive key patterns that must be sanitized from logs and model contexts
SENSITIVE_KEY_PATTERNS = re.compile(
    r"(token|secret|password|passwd|api_key|apikey|authorization|credential|private_key|access_token|refresh_token)",
    re.IGNORECASE,
)


def mask_secret(value: str | None, show_last: int = 4) -> str:
    """Mask a sensitive credential for safe presentation in UI, logs, or telemetry."""
    if not value:
        return ""
    val_str = str(value)
    if len(val_str) <= 6:
        return "••••••••"
    return f"••••••••{val_str[-show_last:]}"


def sanitize_data_for_logging(data: Any, max_depth: int = 10) -> Any:
    """Recursively redact sensitive tokens, passwords, and API keys from arbitrary data structures."""
    if max_depth <= 0:
        return data

    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            if SENSITIVE_KEY_PATTERNS.search(str(k)):
                sanitized[k] = mask_secret(str(v)) if v is not None else None
            else:
                sanitized[k] = sanitize_data_for_logging(v, max_depth - 1)
        return sanitized

    if isinstance(data, list):
        return [sanitize_data_for_logging(item, max_depth - 1) for item in data]

    if isinstance(data, tuple):
        return tuple(sanitize_data_for_logging(item, max_depth - 1) for item in data)

    return data


class SecretStore:
    """Secure encrypted storage abstraction for third-party tokens and credentials."""

    _instance: SecretStore | None = None

    def __init__(self, master_key: str | None = None) -> None:
        raw_key = master_key or os.getenv("SECRET_KEY", "roxy-production-master-secret-key-32b!")
        # Derive 32-byte key
        derived = hashlib.sha256(raw_key.encode("utf-8")).digest()
        self._key_b64 = base64.urlsafe_b64encode(derived)
        self._fernet: Any = None
        try:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(self._key_b64)
        except Exception as exc:
            log.warning("secret_store.fernet_unavailable", error=str(exc))

    @classmethod
    def get_instance(cls) -> SecretStore:
        if cls._instance is None:
            cls._instance = SecretStore()
        return cls._instance

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a secret string into an opaque ciphertext."""
        if not plaintext:
            return ""
        if self._fernet:
            try:
                encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
                return f"enc:{encrypted_bytes.decode('ascii')}"
            except Exception as exc:
                log.error("secret_store.encryption_failed", error=str(exc))
        # Fallback obfuscation if Fernet is not available
        b64 = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
        return f"obf:{b64}"

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext back into the original plaintext secret."""
        if not ciphertext:
            return ""
        if ciphertext.startswith("enc:") and self._fernet:
            try:
                token = ciphertext[4:].encode("ascii")
                return self._fernet.decrypt(token).decode("utf-8")
            except Exception as exc:
                log.error("secret_store.decryption_failed", error=str(exc))
                return ""
        if ciphertext.startswith("obf:"):
            try:
                return base64.b64decode(ciphertext[4:].encode("ascii")).decode("utf-8")
            except Exception:
                return ""
        # If not prefixed with enc: or obf:, assume legacy plaintext
        return ciphertext
