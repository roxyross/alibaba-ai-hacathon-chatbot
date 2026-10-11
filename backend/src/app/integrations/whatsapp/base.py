"""Base adapter contract for Universal WhatsApp Integration."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from app.integrations.whatsapp.models import (
    WhatsAppCapability,
    WhatsAppConnectionReport,
    WhatsAppOperationResult,
    WhatsAppRoute,
)


class WhatsAppBaseAdapter(ABC):
    """Abstract base adapter defining the authoritative contract for WhatsApp channels."""

    @property
    @abstractmethod
    def route(self) -> WhatsAppRoute:
        """Route identifier for this adapter."""
        ...

    @abstractmethod
    def get_capabilities(self) -> list[WhatsAppCapability]:
        """List verified capabilities supported by this adapter."""
        ...

    @abstractmethod
    async def get_connection_status(self) -> WhatsAppConnectionReport:
        """Probe session or credentials to determine real-world connection status."""
        ...

    @staticmethod
    def normalize_phone_number(raw_number: str) -> str:
        """Normalize a phone number into strict E.164 format (+[country][national])."""
        if not raw_number:
            raise ValueError("Recipient phone number cannot be empty.")

        clean = re.sub(r"[\s\-\(\)\.]+", "", raw_number.strip())
        if clean.startswith("00"):
            clean = "+" + clean[2:]
        elif not clean.startswith("+"):
            clean = "+" + clean

        if not re.match(r"^\+[1-9]\d{6,14}$", clean):
            raise ValueError(
                f"Invalid phone number format '{clean[:4]}...'. Must follow international E.164 format (+country_code and number)."
            )
        return clean

    @staticmethod
    def redact_phone_number(phone_number: str) -> str:
        """Mask a phone number for safe logging and report inclusion without leaking PII."""
        clean = phone_number.strip()
        if len(clean) <= 6:
            return "+XXXXXXX"
        prefix = clean[:3]
        suffix = clean[-3:]
        return f"{prefix}*****{suffix}"

    def resolve_recipient(self, raw_recipient: str) -> tuple[bool, str, str]:
        """Resolve raw contact string into normalized E.164.

        Returns: (success, normalized_recipient, error_message)
        """
        try:
            norm = self.normalize_phone_number(raw_recipient)
            return True, norm, "OK"
        except ValueError as err:
            return False, "", str(err)

    def prepare_message(self, recipient: str, message: str) -> dict[str, Any]:
        """Prepare outgoing message payload without sending."""
        is_ok, norm, err = self.resolve_recipient(recipient)
        if not is_ok:
            raise ValueError(f"Cannot prepare message: {err}")
        return {
            "recipient_normalized": norm,
            "recipient_redacted": self.redact_phone_number(norm),
            "message_text": message,
            "route": self.route.value,
        }

    @abstractmethod
    async def send_message(
        self,
        user_id: str,
        recipient: str,
        message: str,
        challenge_id: str,
        run_id: str,
    ) -> WhatsAppOperationResult:
        """Execute approved message sending via this adapter."""
        ...

    @abstractmethod
    async def get_message_status(self, operation_id: str) -> WhatsAppOperationResult:
        """Retrieve latest observed message status."""
        ...

    @abstractmethod
    async def cancel_operation(self, operation_id: str) -> bool:
        """Cancel an ongoing or pending operation if technically supported."""
        ...
