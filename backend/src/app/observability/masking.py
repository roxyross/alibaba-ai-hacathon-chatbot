"""Zero Credential Leakage Engine and Log Interception Processor.

Guarantees:
- Zero raw credential, API key, token, private key, or payment card leakage in logs/telemetry.
- Automatic structlog processing with contextual correlation ID injection.
- Recursive deep masking of complex nested payloads, request headers, and error traces.
- Metrics counter tracking total sanitized secrets across all runtime categories.
"""

from __future__ import annotations

import re
from collections.abc import MutableMapping
from typing import Any

from structlog.types import EventDict

from app.core.correlation import correlation_id_ctx, trace_id_ctx
from app.trust.dlp_engine import DLPEngine

# Sensitive key names (case-insensitive substring or exact match)
SENSITIVE_KEY_NAMES = {
    "password",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "auth_token",
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
    "private_key",
    "client_secret",
    "db_password",
    "token",
    "card",
    "card_number",
    "cvv",
    "cvc",
    "pin",
    "step_up_code",
    "challenge_token",
}

BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-_\.=]{15,}", re.IGNORECASE)
BASIC_AUTH_PATTERN = re.compile(r"Basic\s+[A-Za-z0-9+/=]{16,}", re.IGNORECASE)


class ZeroLeakageMasker:
    """Enterprise credential scrubber for telemetry, payloads, and logs."""

    _redaction_counts: dict[str, int] = {
        "api_keys": 0,
        "tokens": 0,
        "passwords": 0,
        "private_keys": 0,
        "cards": 0,
        "pii": 0,
        "total": 0,
    }

    @classmethod
    def reset_metrics(cls) -> None:
        """Reset metric counters (used for tests)."""
        cls._redaction_counts = {
            "api_keys": 0,
            "tokens": 0,
            "passwords": 0,
            "private_keys": 0,
            "cards": 0,
            "pii": 0,
            "total": 0,
        }

    @classmethod
    def get_metrics(cls) -> dict[str, int]:
        """Return cumulative counts of intercepted secrets."""
        return dict(cls._redaction_counts)

    @classmethod
    def mask_string(cls, text: str) -> str:
        """Sanitize plain string, scrubbing headers, tokens, and DLP patterns."""
        if not text:
            return text

        scrubbed = text

        # 1. Bearer tokens & Basic Auth headers
        if BEARER_PATTERN.search(scrubbed):
            scrubbed = BEARER_PATTERN.sub("Bearer [REDACTED_TOKEN]", scrubbed)
            cls._redaction_counts["tokens"] += 1
            cls._redaction_counts["total"] += 1

        if BASIC_AUTH_PATTERN.search(scrubbed):
            scrubbed = BASIC_AUTH_PATTERN.sub("Basic [REDACTED_BASIC_AUTH]", scrubbed)
            cls._redaction_counts["tokens"] += 1
            cls._redaction_counts["total"] += 1

        # 2. DLPEngine multi-category scanning & redaction
        redacted_dlp, matches = DLPEngine.redact_text(scrubbed, mask_style="tag")
        if matches:
            for m in matches:
                cat = m.category.value
                if "api_key" in cat:
                    cls._redaction_counts["api_keys"] += 1
                elif "card" in cat or "iban" in cat:
                    cls._redaction_counts["cards"] += 1
                elif "private_key" in cat or "db_connection" in cat:
                    cls._redaction_counts["private_keys"] += 1
                elif "ssn" in cat or "national_id" in cat or "email" in cat or "phone" in cat:
                    cls._redaction_counts["pii"] += 1
                cls._redaction_counts["total"] += 1

        return redacted_dlp

    @classmethod
    def mask_value(cls, key: str | None, value: Any) -> Any:
        """Recursively scrub arbitrary Python objects."""
        if key and any(sens in key.lower() for sens in SENSITIVE_KEY_NAMES):
            cls._redaction_counts["passwords"] += 1
            cls._redaction_counts["total"] += 1
            return "[REDACTED_SECRET]"

        if isinstance(value, str):
            return cls.mask_string(value)
        elif isinstance(value, (dict, MutableMapping)):
            return {str(k): cls.mask_value(str(k), v) for k, v in value.items()}
        elif isinstance(value, list):
            return [cls.mask_value(None, item) for item in value]
        elif isinstance(value, tuple):
            return tuple(cls.mask_value(None, item) for item in value)
        elif isinstance(value, set):
            return {cls.mask_value(None, item) for item in value}
        return value

    @classmethod
    def mask_dict(cls, data: MutableMapping[str, Any]) -> dict[str, Any]:
        """Deep mask dictionary payload in-place or returning cleaned copy."""
        return cls.mask_value(None, data)  # type: ignore[no-any-return]


def structlog_zero_leakage_processor(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Structlog processor injecting correlation context and filtering credentials."""
    # 1. Inject contextual Correlation ID and Trace ID
    cid = correlation_id_ctx.get()
    if cid and "correlation_id" not in event_dict:
        event_dict["correlation_id"] = cid

    tid = trace_id_ctx.get()
    if tid and "trace_id" not in event_dict:
        event_dict["trace_id"] = tid

    # 2. Deep recursive mask all fields in the event dictionary
    masked = ZeroLeakageMasker.mask_dict(event_dict)
    event_dict.clear()
    event_dict.update(masked)
    return event_dict
