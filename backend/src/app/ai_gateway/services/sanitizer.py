"""Prompt injection detection and sanitization.

Applies at the domain layer before any provider is called. Two-stage approach:
1. Blocklist — rejects known injection patterns immediately.
2. Structured wrapping — isolates user input in a bounded `user` role message.

Per Spec §5 and Constitution §3.
"""

from __future__ import annotations

import re

from app.ai_gateway.models.schemas import Message, MessageRole


# -----------------------------------------------------------------------------
# Blocklist of known prompt injection patterns
# -----------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # Ignore / discard previous instructions
    re.compile(r"ignore\s+(all\s+)?(previous|prior|earlier)\s+(instructions?|orders?|commands?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|earlier)\s+(instructions?|orders?)", re.IGNORECASE),
    re.compile(r"(forget|clear)\s+(all\s+)?(previous|prior|earlier)?\s*instructions?", re.IGNORECASE),
    # System prompt override / jailbreak
    re.compile(r"(set|change|override|modify)\s+.*system\s+(prompt|instruction|role)", re.IGNORECASE),
    re.compile(r"system\s+prompt\s*[:=]\s*.+", re.IGNORECASE),
    # Role-playing jailbreaks
    re.compile(r"pretend\s+you\s+(are|have\s+been)\s+(an?\s+)?(new|unrestricted)", re.IGNORECASE),
    re.compile(r"(act|behave)\s+as\s+(if|though)\s+(you|ai)\s+(have|has)\s+no\s+restrictions?", re.IGNORECASE),
    re.compile(r"pretend\s+(you|ai)\s+(have|has)\s+no\s+restrictions?", re.IGNORECASE),
    # Amoral / DAN-style
    re.compile(r"\bDAN\b", re.IGNORECASE),  # Do Anything Now jailbreak
    re.compile(r"(you\s+are\s+now|switch\s+to)\s+(an?\s+)?(different|unrestricted|unfiltered)", re.IGNORECASE),
    # Output suppression attempts
    re.compile(r"(do\s+not|don't)\s+(reveal|show|disclose|tell\s+me|explain)", re.IGNORECASE),
    # Privilege escalation
    re.compile(r"(reveal|show|tell)\s+(your|the)\s+(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"(output|print|return)\s+(your|the)\s+(full|complete|entire)\s+(system\s+)?prompt", re.IGNORECASE),
    # Null-byte / binary injection
    re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]"),
]

# Blocklist trigger words for fast-path scanning (pre-regex)
_BLOCKLIST_KEYWORDS: set[str] = {
    "ignore previous",
    "disregard instructions",
    "ignore instructions",
    "system prompt",
    "you are now",
    "do anything now",
    "DAN",
}


class PromptInjectionError(Exception):
    """Raised when user input matches a known injection pattern."""

    def __init__(self, matched_pattern: str, input_snippet: str = "") -> None:
        self.matched_pattern = matched_pattern
        self.input_snippet = input_snippet[:100]
        super().__init__(
            f"Prompt injection detected: pattern {matched_pattern!r} matched. "
            f"Input snippet: {input_snippet[:100]!r}"
        )


class PromptSanitizer:
    """Two-stage prompt injection sanitizer.

    Stage 1 — Blocklist: fast regex scan; raises PromptInjectionError on match.
    Stage 2 — Structured wrapping: wraps user input in a bounded `user` role
               message inside a system-bounded conversation structure.
    """

    def sanitize(self, user_input: str, system_prompt: str = "") -> list[Message]:
        """Sanitize user input and return a structured message list.

        Args:
            user_input: Raw user input string.
            system_prompt: Optional system prompt to prepend.

        Returns:
            A list of Message objects starting with a system message (if provided),
            followed by the sanitized user message.

        Raises:
            PromptInjectionError: if blocklist triggers.
        """
        self._check_blocklist(user_input)

        messages = []

        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))

        # Structured wrapping: user input goes into a bounded user-role message.
        # The input is escaped to prevent breaking out of the user role context.
        wrapped = self._wrap_user_input(user_input)
        messages.append(Message(role=MessageRole.USER, content=wrapped))

        return messages

    def _check_blocklist(self, text: str) -> None:
        """Fast-path keyword scan, then regex pass. Raises PromptInjectionError."""
        lower = text.lower()

        # Fast path: keyword presence check
        for keyword in _BLOCKLIST_KEYWORDS:
            if keyword in lower:
                # Verify with regex before raising
                for pattern in _INJECTION_PATTERNS:
                    if pattern.search(text):
                        raise PromptInjectionError(
                            matched_pattern=pattern.pattern,
                            input_snippet=text,
                        )
                # Keyword hit but no regex match — still check all patterns for safety
                for pattern in _INJECTION_PATTERNS:
                    if pattern.search(text):
                        raise PromptInjectionError(
                            matched_pattern=pattern.pattern,
                            input_snippet=text,
                        )
                return  # keyword hit, no regex match — safe

        # Full regex pass
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                raise PromptInjectionError(
                    matched_pattern=pattern.pattern,
                    input_snippet=text,
                )

    def _wrap_user_input(self, user_input: str) -> str:
        """Escape user input to prevent role-context breakout.

        We wrap the input so that any attempt to inject system-role content
        inside the user message is neutralized by structural role boundaries.
        """
        # Basic escaping: collapse multiple blank lines (which some models use to inject)
        sanitized = re.sub(r"\n{3,}", "\n\n", user_input)
        # Strip null bytes
        sanitized = sanitized.replace("\x00", "")
        return sanitized.strip()
