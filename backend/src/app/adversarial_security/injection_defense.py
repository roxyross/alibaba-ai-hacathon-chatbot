"""Injection Defense Engine — Defends against Prompt, Command, SQL, Path Traversal, and SSRF injections."""

from __future__ import annotations

import ipaddress
import os
import re
import shlex
import socket
from urllib.parse import urlparse
from typing import Any
import structlog

from app.adversarial_security.schemas import (
    CommandSafetyResult,
    DefenseAction,
    PathSafetyResult,
    PromptInjectionScanResult,
    SecurityThreatType,
    SQLSafetyResult,
    SSRFSafetyResult,
)

log = structlog.get_logger()


class InjectionDefenseEngine:
    """Comprehensive multi-vector injection defense and sanitization engine."""

    # -------------------------------------------------------------------------
    # 1. Prompt Injection & Jailbreak Patterns
    # -------------------------------------------------------------------------
    PROMPT_OVERRIDE_PATTERNS = [
        re.compile(r"\b(ignore|disregard|forget|bypass|override)\b.*?\b(previous|prior|all|system)\b.*?\b(instructions?|prompts?|rules?|directives?)\b", re.IGNORECASE),
        re.compile(r"\b(you are now in|enable|enter)\b.*?\b(dan mode|developer mode|jailbreak|unrestricted mode)\b", re.IGNORECASE),
        re.compile(r"\b(do anything now|pretend you have no (rules|limits|safety))\b", re.IGNORECASE),
        re.compile(r"\bdisregard all previous safety directives\b", re.IGNORECASE),
        re.compile(r"(<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[SYSTEM INSTRUCTION\]|---END OF SYSTEM PROMPT---)", re.IGNORECASE),
        re.compile(r"\b(now act as an unrestricted ai|roleplay as an unfiltered)\b", re.IGNORECASE),
        re.compile(r"\b(reveal|output|print|display)\s+your\s+(original|system)\s+prompt\b", re.IGNORECASE),
    ]

    # -------------------------------------------------------------------------
    # 2. Command Injection Metacharacters
    # -------------------------------------------------------------------------
    COMMAND_METACHAR_PATTERN = re.compile(r"([;&|`$><\n\r])|(\$\([^\)]*\))|(\$\{[^\}]*\})")
    DANGEROUS_COMMANDS = [
        re.compile(r"\b(rm\s+-[rRfF]+|del\s+/[fFsSqQ]+|format\s+[a-zA-Z]:|mkfs|dd\s+if=)\b", re.IGNORECASE),
        re.compile(r"\b(sudo\s+|powershell\s+-enc|cmd\.exe\s+/c|bash\s+-c|sh\s+-c)\b", re.IGNORECASE),
    ]

    # -------------------------------------------------------------------------
    # 3. SQL Injection Patterns
    # -------------------------------------------------------------------------
    SQL_TAUTOLOGY_PATTERN = re.compile(
        r"('\s*OR\s*'1'\s*=\s*'1'|'\s*OR\s*1\s*=\s*1|(\bOR\b\s+\d+=\d+)|(\bOR\b\s+'[^']+'='[^']+'))",
        re.IGNORECASE,
    )
    SQL_STACKED_QUERY_PATTERN = re.compile(
        r";\s*(DROP|TRUNCATE|DELETE|ALTER|CREATE|INSERT|UPDATE)\s+",
        re.IGNORECASE,
    )
    SQL_UNION_PATTERN = re.compile(
        r"\bUNION\s+(ALL\s+)?SELECT\b",
        re.IGNORECASE,
    )
    SQL_COMMENT_PATTERN = re.compile(r"(--|/\*|\*/|#)")
    SQL_TIME_DELAY_PATTERN = re.compile(r"\b(SLEEP\s*\(|WAITFOR\s+DELAY|BENCHMARK\s*\()", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # 4. Path Traversal Patterns
    # -------------------------------------------------------------------------
    TRAVERSAL_REGEX = re.compile(r"(\.\./|\.\.\\|%2e%2e%2f|%2e%2e/|\.\.%2f|\x00)", re.IGNORECASE)

    # -------------------------------------------------------------------------
    # 5. SSRF Blocked Ranges & Hosts
    # -------------------------------------------------------------------------
    CLOUD_METADATA_HOSTS = {
        "169.254.169.254",
        "metadata.google.internal",
        "instance-data",
        "metadata",
    }

    # =========================================================================
    # Prompt Injection Defense
    # =========================================================================

    @classmethod
    def scan_prompt(cls, prompt: str) -> PromptInjectionScanResult:
        """Scan input for prompt injection and jailbreak vectors."""
        detected_patterns: list[str] = []

        for pattern in cls.PROMPT_OVERRIDE_PATTERNS:
            match = pattern.search(prompt)
            if match:
                detected_patterns.append(match.group(0))

        is_injection = len(detected_patterns) > 0
        confidence = min(1.0, 0.4 + (0.3 * len(detected_patterns))) if is_injection else 0.0

        threat_type = None
        defense_action = DefenseAction.ALLOW
        reason = "Prompt validated clean with no adversarial injection patterns."
        sanitized = prompt

        if is_injection:
            threat_type = (
                SecurityThreatType.JAILBREAK
                if any("dan" in p.lower() or "unrestricted" in p.lower() for p in detected_patterns)
                else SecurityThreatType.PROMPT_INJECTION
            )

            if confidence >= 0.7:
                defense_action = DefenseAction.BLOCK
                reason = f"Blocked high-confidence prompt injection attack. Patterns detected: {detected_patterns}"
            else:
                defense_action = DefenseAction.SANITIZE
                reason = f"Sanitized suspicious prompt override sequences. Patterns: {detected_patterns}"
                # Redact matched injection substrings
                for p in detected_patterns:
                    sanitized = sanitized.replace(p, "[REDACTED_INJECTION]")

        return PromptInjectionScanResult(
            prompt=prompt,
            is_injection=is_injection,
            threat_type=threat_type,
            confidence_score=round(confidence, 2),
            detected_patterns=detected_patterns,
            defense_action=defense_action,
            sanitized_prompt=sanitized,
            reason=reason,
        )

    # =========================================================================
    # Command Injection Defense
    # =========================================================================

    @classmethod
    def validate_command(cls, command: str) -> CommandSafetyResult:
        """Inspect shell commands for metacharacter chaining and dangerous binaries."""
        dangerous_metachars: list[str] = []
        tokenized_args: list[str] = []

        # Find dangerous metacharacters
        for match in cls.COMMAND_METACHAR_PATTERN.finditer(command):
            dangerous_metachars.append(match.group(0))

        # Check for dangerous command prefixes
        for pattern in cls.DANGEROUS_COMMANDS:
            cmd_match = pattern.search(command)
            if cmd_match:
                dangerous_metachars.append(cmd_match.group(0))

        # Attempt safe POSIX/Windows tokenization
        try:
            tokenized_args = shlex.split(command, posix=False)
        except Exception:
            tokenized_args = command.split()

        is_safe = len(dangerous_metachars) == 0
        risk_score = 0.0 if is_safe else min(1.0, 0.5 + (0.15 * len(dangerous_metachars)))

        if is_safe:
            defense_action = DefenseAction.ALLOW
            rejection_reason = None
        else:
            defense_action = DefenseAction.BLOCK
            rejection_reason = (
                f"Command injection metacharacters or dangerous invocations detected: {dangerous_metachars}"
            )

        return CommandSafetyResult(
            command=command,
            is_safe=is_safe,
            risk_score=round(risk_score, 2),
            dangerous_metachars=dangerous_metachars,
            tokenized_args=tokenized_args,
            defense_action=defense_action,
            rejection_reason=rejection_reason,
        )

    # =========================================================================
    # SQL Injection Defense
    # =========================================================================

    @classmethod
    def validate_sql(
        cls, query: str, parameters: dict[str, Any] | None = None
    ) -> SQLSafetyResult:
        """Inspect SQL queries for tautologies, stacked statements, union extraction, and parameterization."""
        detected_threats: list[str] = []

        if cls.SQL_TAUTOLOGY_PATTERN.search(query):
            detected_threats.append("SQL Tautology Bypass (' OR '1'='1')")

        if cls.SQL_STACKED_QUERY_PATTERN.search(query):
            detected_threats.append("Stacked Destructive Query ('; DROP/TRUNCATE')")

        if cls.SQL_UNION_PATTERN.search(query):
            detected_threats.append("UNION Data Exfiltration Attack")

        if cls.SQL_TIME_DELAY_PATTERN.search(query):
            detected_threats.append("Blind SQL Time-Delay Injection")

        # Comment injection check when combined with quotes
        if ("'" in query or '"' in query) and cls.SQL_COMMENT_PATTERN.search(query):
            detected_threats.append("Inline Comment Statement Truncation (' --)")

        is_parameterized = True
        # If dynamic query contains raw quotes with variable assignments outside of parameters
        if parameters is None and ("'" in query or '"' in query):
            # Check if this query contains direct variable concatenation patterns
            if re.search(r"=\s*'[^']*'\s*(\bAND\b|\bOR\b|;|$)", query, re.IGNORECASE):
                # Hardcoded values vs parameter placeholders (:param or ?)
                if not re.search(r"(:[a-zA-Z0-9_]+|\?)", query):
                    is_parameterized = False

        is_safe = len(detected_threats) == 0 and is_parameterized

        if is_safe:
            defense_action = DefenseAction.ALLOW
            rejection_reason = None
        else:
            defense_action = DefenseAction.BLOCK
            reasons = list(detected_threats)
            if not is_parameterized:
                reasons.append("Unparameterized SQL string literal detected without bind variables")
            rejection_reason = f"SQL Injection protection triggered: {', '.join(reasons)}"

        return SQLSafetyResult(
            query=query,
            is_safe=is_safe,
            detected_threats=detected_threats,
            is_parameterized=is_parameterized,
            defense_action=defense_action,
            rejection_reason=rejection_reason,
        )

    # =========================================================================
    # Path Traversal Defense
    # =========================================================================

    @classmethod
    def validate_path(
        cls, path: str, base_directory: str = "/workspace/sandbox"
    ) -> PathSafetyResult:
        """Validate that a target path remains strictly confined within its base directory sandbox."""
        if "\x00" in path:
            return PathSafetyResult(
                original_path=path,
                base_directory=base_directory,
                resolved_path=None,
                is_safe=False,
                is_contained=False,
                defense_action=DefenseAction.BLOCK,
                rejection_reason="Null-byte string termination attack detected in file path.",
            )

        if cls.TRAVERSAL_REGEX.search(path):
            return PathSafetyResult(
                original_path=path,
                base_directory=base_directory,
                resolved_path=None,
                is_safe=False,
                is_contained=False,
                defense_action=DefenseAction.BLOCK,
                rejection_reason="Path traversal sequence (../ or URL-encoded dots) detected.",
            )

        # Normalize and resolve absolute paths
        canonical_base = os.path.abspath(base_directory)
        # In multi-platform test, handle relative joining safely
        if os.path.isabs(path):
            candidate_path = os.path.abspath(path)
        else:
            candidate_path = os.path.abspath(os.path.join(canonical_base, path))

        try:
            common = os.path.commonpath([canonical_base, candidate_path])
            is_contained = common == canonical_base
        except ValueError:
            # Different drives on Windows (e.g. C: vs D:)
            is_contained = False

        is_safe = is_contained

        if is_safe:
            defense_action = DefenseAction.ALLOW
            rejection_reason = None
        else:
            defense_action = DefenseAction.BLOCK
            rejection_reason = (
                f"Path traversal escape: '{candidate_path}' is outside sandbox '{canonical_base}'"
            )

        return PathSafetyResult(
            original_path=path,
            base_directory=base_directory,
            resolved_path=candidate_path if is_contained else None,
            is_safe=is_safe,
            is_contained=is_contained,
            defense_action=defense_action,
            rejection_reason=rejection_reason,
        )

    # =========================================================================
    # SSRF & Cloud Metadata Defense
    # =========================================================================

    @classmethod
    def validate_url_ssrf(
        cls, url: str, allowed_schemes: tuple[str, ...] = ("http", "https")
    ) -> SSRFSafetyResult:
        """Inspect outbound URL destination to prevent SSRF and internal cloud metadata access."""
        try:
            parsed = urlparse(url)
        except Exception as e:
            return SSRFSafetyResult(
                url=url,
                is_safe=False,
                scheme="",
                hostname="",
                resolved_ip=None,
                is_private_or_loopback=True,
                is_cloud_metadata=False,
                defense_action=DefenseAction.BLOCK,
                rejection_reason=f"Malformed URL: {e}",
            )

        scheme = (parsed.scheme or "").lower()
        hostname = (parsed.hostname or "").lower()

        if scheme not in allowed_schemes:
            return SSRFSafetyResult(
                url=url,
                is_safe=False,
                scheme=scheme,
                hostname=hostname,
                resolved_ip=None,
                is_private_or_loopback=False,
                is_cloud_metadata=False,
                defense_action=DefenseAction.BLOCK,
                rejection_reason=f"Disallowed URL scheme '{scheme}'. Only {allowed_schemes} are permitted.",
            )

        # Check cloud metadata hostnames
        if hostname in cls.CLOUD_METADATA_HOSTS:
            return SSRFSafetyResult(
                url=url,
                is_safe=False,
                scheme=scheme,
                hostname=hostname,
                resolved_ip=None,
                is_private_or_loopback=True,
                is_cloud_metadata=True,
                defense_action=DefenseAction.BLOCK,
                rejection_reason="Attempted access to Cloud Metadata service (SSRF vector).",
            )

        # Resolve IP address to check for private / loopback IP subnets
        resolved_ip = None
        is_private_or_loopback = False

        try:
            # Check if hostname itself is directly an IP literal
            ip_obj = ipaddress.ip_address(hostname)
            resolved_ip = str(ip_obj)
            is_private_or_loopback = (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            )
        except ValueError:
            # Hostname is a domain name — check for localhost
            if hostname == "localhost" or hostname.endswith(".local") or hostname.endswith(".internal"):
                is_private_or_loopback = True
            else:
                try:
                    # DNS resolve check
                    addr_info = socket.getaddrinfo(hostname, None)
                    if addr_info:
                        resolved_ip = str(addr_info[0][4][0])
                        ip_obj = ipaddress.ip_address(resolved_ip)
                        is_private_or_loopback = (
                            ip_obj.is_private
                            or ip_obj.is_loopback
                            or ip_obj.is_link_local
                            or ip_obj.is_multicast
                            or ip_obj.is_reserved
                            or ip_obj.is_unspecified
                        )
                except Exception:
                    # If offline or cannot resolve, evaluate based on hostname
                    pass

        is_cloud_metadata = (
            resolved_ip == "169.254.169.254" or hostname in cls.CLOUD_METADATA_HOSTS
        )

        is_safe = not is_private_or_loopback and not is_cloud_metadata

        if is_safe:
            defense_action = DefenseAction.ALLOW
            rejection_reason = None
        else:
            defense_action = DefenseAction.BLOCK
            reason = (
                "Cloud metadata endpoint access denied"
                if is_cloud_metadata
                else f"Private or loopback address access denied ({resolved_ip or hostname})"
            )
            rejection_reason = f"SSRF Protection triggered: {reason}"

        return SSRFSafetyResult(
            url=url,
            is_safe=is_safe,
            scheme=scheme,
            hostname=hostname,
            resolved_ip=resolved_ip,
            is_private_or_loopback=is_private_or_loopback,
            is_cloud_metadata=is_cloud_metadata,
            defense_action=defense_action,
            rejection_reason=rejection_reason,
        )
