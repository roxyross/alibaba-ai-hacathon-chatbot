"""Data Loss Prevention (DLP) Engine — Algorithmic and heuristic scanning and redaction."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

from app.trust.schemas import DLPCategory, DLPMatch, DLPScanResponse


def check_luhn(card_number_str: str) -> bool:
    """Validate payment card number using the Luhn mod-10 checksum."""
    digits = [int(c) for c in card_number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False

    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def check_iban(iban_str: str) -> bool:
    """Validate International Bank Account Number using ISO 7064 mod-97-10."""
    clean = re.sub(r"\s+", "", iban_str).upper()
    if len(clean) < 14 or len(clean) > 34:
        return False
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", clean):
        return False

    # Rearrange: move the first 4 characters to the end
    rearranged = clean[4:] + clean[:4]
    # Replace each letter with two digits (A=10, B=11, ..., Z=35)
    numeric_str = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    try:
        return int(numeric_str) % 97 == 1
    except ValueError:
        return False


def calculate_shannon_entropy(token: str) -> float:
    """Calculate the Shannon entropy of a string (bits per symbol)."""
    if not token:
        return 0.0
    prob_dict: dict[str, int] = {}
    for ch in token:
        prob_dict[ch] = prob_dict.get(ch, 0) + 1
    length = len(token)
    entropy = -sum((count / length) * math.log2(count / length) for count in prob_dict.values())
    return entropy


class DLPEngine:
    """Scans and redacts PII, credentials, financial details, and cryptographic keys."""

    # Pre-compiled regex patterns
    PATTERNS: dict[DLPCategory, list[tuple[re.Pattern[str], str, float]]] = {
        DLPCategory.CREDIT_CARD: [
            (
                re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{13,19}\b"),
                "Payment Card (Visa/Mastercard/Amex/Discover)",
                0.95,
            ),
        ],
        DLPCategory.IBAN: [
            (
                re.compile(r"\b[A-Z]{2}\d{2}[-\s]?(?:[A-Z0-9]{4}[-\s]?){2,7}[A-Z0-9]{1,4}\b"),
                "International Bank Account Number (IBAN)",
                0.90,
            ),
        ],
        DLPCategory.PRIVATE_KEY: [
            (
                re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
                "Cryptographic Private Key (RSA/EC/OpenSSH)",
                1.0,
            ),
        ],
        DLPCategory.API_KEY: [
            (
                re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,}|sk-proj-[a-zA-Z0-9\-_]{30,})\b"),
                "OpenAI API Secret Key",
                0.98,
            ),
            (
                re.compile(r"\bAIzaSy[a-zA-Z0-9\-_]{30,40}\b"),
                "Google Gemini / Cloud API Key",
                0.99,
            ),
            (
                re.compile(r"\bsk-ant-[a-zA-Z0-9\-_]{30,}\b"),
                "Anthropic API Key",
                0.98,
            ),
            (
                re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
                "AWS Access Key ID",
                0.99,
            ),
            (
                re.compile(r"\b(?:sk|pk|rk)_(?:test|live)_[0-9a-zA-Z]{24,}\b"),
                "Stripe API Key",
                0.98,
            ),
            (
                re.compile(r"\b(?:ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{60,})\b"),
                "GitHub Personal Access Token",
                0.99,
            ),
        ],
        DLPCategory.DB_CONNECTION: [
            (
                re.compile(r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|mssql)://[a-zA-Z0-9_.\-]+:[^\s@'\"<>]+@[a-zA-Z0-9_.\-]+(?::\d+)?(?:/[^\s'\"<>]*)?"),
                "Database Connection String with Credentials",
                0.95,
            ),
        ],
        DLPCategory.PASSWORD: [
            (
                re.compile(r"""(?i)\b(?:password|passwd|pwd|secret|api_secret)\s*[:=]\s*["']?([^\s"';,]{6,})["']?"""),
                "Exposed Inline Password / Secret",
                0.85,
            ),
        ],
        DLPCategory.SSN: [
            (
                re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
                "US Social Security Number",
                0.92,
            ),
        ],
        DLPCategory.NATIONAL_ID: [
            (
                re.compile(r"\b\d{5}-\d{7}-\d\b"),
                "Pakistani National Identity Card (CNIC)",
                0.90,
            ),
        ],
        DLPCategory.EMAIL: [
            (
                re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
                "Email Address",
                0.80,
            ),
        ],
        DLPCategory.PHONE: [
            (
                re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
                "Telephone / Mobile Number",
                0.75,
            ),
        ],
    }

    @classmethod
    def scan_text(
        cls,
        text: str,
        categories: Iterable[DLPCategory] | None = None,
        mask_style: str = "tag",
    ) -> list[DLPMatch]:
        """Scan a plain string and return all verified DLP violations with offsets."""
        if not text:
            return []

        active_categories = set(categories) if categories else set(cls.PATTERNS.keys())
        matches: list[DLPMatch] = []

        for cat, rule_list in cls.PATTERNS.items():
            if cat not in active_categories:
                continue

            for pattern, rule_name, base_conf in rule_list:
                for m in pattern.finditer(text):
                    matched_str = m.group(0)
                    start, end = m.start(), m.end()

                    # Specific Algorithmic Checks
                    if cat == DLPCategory.CREDIT_CARD:
                        cleaned = re.sub(r"[-\s]", "", matched_str)
                        if not check_luhn(cleaned):
                            continue  # False positive: fails Luhn

                    elif cat == DLPCategory.IBAN:
                        cleaned = re.sub(r"[-\s]", "", matched_str)
                        if not check_iban(cleaned):
                            continue  # False positive: fails IBAN mod-97

                    elif cat == DLPCategory.PASSWORD:
                        # Extract the inner password value if captured
                        if m.lastindex and m.group(1):
                            matched_str = m.group(1)

                    # Generate masked text
                    if mask_style == "tag":
                        masked = f"[REDACTED_{cat.value.upper()}]"
                    else:
                        if len(matched_str) > 8:
                            masked = matched_str[:2] + ("•" * (len(matched_str) - 6)) + matched_str[-4:]
                        else:
                            masked = "•" * len(matched_str)

                    matches.append(
                        DLPMatch(
                            category=cat,
                            matched_text=matched_str,
                            masked_text=masked,
                            start=start,
                            end=end,
                            confidence=base_conf,
                            rule_name=rule_name,
                        )
                    )

        return cls._resolve_overlapping(matches)

    @classmethod
    def _resolve_overlapping(cls, matches: list[DLPMatch]) -> list[DLPMatch]:
        """Resolve and deduplicate overlapping ranges, prioritizing wider match and higher confidence."""
        if not matches:
            return []

        # Sort primarily by start asc, length desc, confidence desc
        sorted_m = sorted(matches, key=lambda m: (m.start, -(m.end - m.start), -m.confidence))
        resolved: list[DLPMatch] = []

        for m in sorted_m:
            if not resolved:
                resolved.append(m)
                continue

            last = resolved[-1]
            if m.start >= last.end:
                resolved.append(m)
            else:
                # Overlap detected
                m_len = m.end - m.start
                last_len = last.end - last.start
                if m_len > last_len or (m_len == last_len and m.confidence > last.confidence):
                    resolved[-1] = m

        resolved.sort(key=lambda x: x.start)
        return resolved

    @classmethod
    def redact_text(
        cls,
        text: str,
        categories: Iterable[DLPCategory] | None = None,
        mask_style: str = "tag",
    ) -> tuple[str, list[DLPMatch]]:
        """Redact all sensitive entities from text, returning sanitized string and violation list."""
        if not text:
            return "", []

        matches = cls.scan_text(text, categories=categories, mask_style=mask_style)
        if not matches:
            return text, []

        # Replace from end to beginning to preserve character offsets
        redacted = text
        for m in sorted(matches, key=lambda x: x.start, reverse=True):
            redacted = redacted[:m.start] + m.masked_text + redacted[m.end:]

        return redacted, matches

    @classmethod
    def scan_payload(
        cls,
        payload: dict[str, Any],
        categories: Iterable[DLPCategory] | None = None,
        mask_style: str = "tag",
    ) -> DLPScanResponse:
        """Recursively scan and sanitize a JSON-like dictionary payload."""
        all_matches: list[DLPMatch] = []

        def _recursive_sanitize(item: Any) -> Any:
            if isinstance(item, str):
                sanitized, matches = cls.redact_text(item, categories=categories, mask_style=mask_style)
                all_matches.extend(matches)
                return sanitized
            elif isinstance(item, dict):
                return {k: _recursive_sanitize(v) for k, v in item.items()}
            elif isinstance(item, list):
                return [_recursive_sanitize(v) for v in item]
            return item

        sanitized_dict = _recursive_sanitize(payload)
        has_violations = len(all_matches) > 0

        # Recommendation: if credentials/private keys/credit cards found, recommendation is 'block'
        critical_cats = {
            DLPCategory.CREDIT_CARD,
            DLPCategory.PRIVATE_KEY,
            DLPCategory.DB_CONNECTION,
            DLPCategory.API_KEY,
        }
        if any(m.category in critical_cats for m in all_matches):
            rec = "block"
        elif has_violations:
            rec = "warn"
        else:
            rec = "allow"

        return DLPScanResponse(
            has_violations=has_violations,
            total_violations=len(all_matches),
            matches=all_matches,
            sanitized_payload=sanitized_dict,
            action_recommended=rec,
        )
