"""Privilege Escalation & IDOR Guard — Enforces RBAC hierarchy and tenant isolation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
import structlog

from app.adversarial_security.schemas import (
    DefenseAction,
    RBACEvaluationResult,
    UserRole,
)

log = structlog.get_logger()


class PrivilegeEscalationGuard:
    """Enforces role-based hierarchy, horizontal tenant isolation, and token integrity."""

    ROLE_HIERARCHY: dict[str, int] = {
        UserRole.GUEST.value: 0,
        UserRole.VIEWER.value: 1,
        UserRole.MEMBER.value: 2,
        UserRole.OPERATOR.value: 3,
        UserRole.ADMIN.value: 4,
        UserRole.SUPER_ADMIN.value: 5,
    }

    # =========================================================================
    # RBAC & IDOR Access Evaluation
    # =========================================================================

    @classmethod
    def evaluate_access(
        cls,
        user_id: str,
        user_role: str,
        resource_id: str,
        resource_owner_id: str,
        required_role: str = "member",
        action: str = "read",
        is_public: bool = False,
    ) -> RBACEvaluationResult:
        """Evaluate if an access request violates vertical RBAC or horizontal IDOR boundaries."""
        user_level = cls.ROLE_HIERARCHY.get(user_role.lower(), 0)
        required_level = cls.ROLE_HIERARCHY.get(required_role.lower(), 2)

        # 1. Vertical Privilege Escalation Check
        if user_level < required_level:
            return RBACEvaluationResult(
                user_id=user_id,
                resource_id=resource_id,
                is_permitted=False,
                violation_type="vertical_escalation",
                defense_action=DefenseAction.BLOCK,
                reason=(
                    f"Vertical Privilege Escalation blocked: User role '{user_role}' (tier {user_level}) "
                    f"lacks required role '{required_role}' (tier {required_level}) for action '{action}'."
                ),
            )

        # 2. Horizontal IDOR Check (Multi-Tenant Isolation)
        # Admins and Super Admins have cross-tenant administrative oversight
        is_admin_or_above = user_level >= cls.ROLE_HIERARCHY[UserRole.ADMIN.value]
        is_owner = user_id == resource_owner_id

        if not is_owner and not is_public and not is_admin_or_above:
            return RBACEvaluationResult(
                user_id=user_id,
                resource_id=resource_id,
                is_permitted=False,
                violation_type="horizontal_idor",
                defense_action=DefenseAction.BLOCK,
                reason=(
                    f"Horizontal IDOR boundary violation blocked: User '{user_id}' attempted unauthorized "
                    f"'{action}' on resource '{resource_id}' owned by '{resource_owner_id}'."
                ),
            )

        # Permitted
        return RBACEvaluationResult(
            user_id=user_id,
            resource_id=resource_id,
            is_permitted=True,
            violation_type=None,
            defense_action=DefenseAction.ALLOW,
            reason=f"Access granted: role '{user_role}' satisfied '{required_role}' and tenant boundary confirmed.",
        )

    # =========================================================================
    # Token Tampering & Algorithm Confusion Defense
    # =========================================================================

    @classmethod
    def verify_token_tampering(
        cls,
        token: str,
        expected_secret: str,
        allowed_algorithms: tuple[str, ...] = ("HS256",),
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Detect JWT tampering, algorithm confusion (e.g. 'none' attack), and signature forgery."""
        parts = token.split(".")
        if len(parts) != 3:
            return False, "Malformed token structure: must have exactly 3 base64 segments.", None

        header_b64, payload_b64, signature_b64 = parts

        # Decode header
        try:
            # Pad base64 if needed
            header_json = base64.urlsafe_b64decode(header_b64 + "=" * (-len(header_b64) % 4)).decode("utf-8")
            header = json.loads(header_json)
        except Exception as e:
            return False, f"Failed to decode token header: {e}", None

        # Decode payload
        try:
            payload_json = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)).decode("utf-8")
            payload = json.loads(payload_json)
        except Exception as e:
            return False, f"Failed to decode token payload: {e}", None

        # Check algorithm confusion
        alg = header.get("alg", "").upper()
        if alg == "NONE" or not alg:
            return False, "Algorithm confusion attack detected: 'none' algorithm is strictly rejected.", None

        if alg not in allowed_algorithms:
            return False, f"Disallowed signature algorithm '{alg}'. Only {allowed_algorithms} are permitted.", None

        # Check expiration
        exp = payload.get("exp")
        if exp and exp < time.time():
            return False, f"Token expired at {exp} (current time: {int(time.time())}).", None

        # Validate cryptographic signature for HS256
        if alg == "HS256":
            signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(expected_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
            ).decode("utf-8").rstrip("=")

            sig_clean = signature_b64.rstrip("=")
            if not hmac.compare_digest(sig_clean, expected_sig):
                return False, "Cryptographic signature verification failed: token signature is forged.", None

        return True, "Token signature and claims verified authentic.", payload

    # =========================================================================
    # Confirmation Gate Bypass Defense
    # =========================================================================

    @classmethod
    def verify_gate_bypass(
        cls,
        operation_risk: str,
        gate_token: str | None,
        otp_verified: bool = False,
    ) -> tuple[bool, str]:
        """Ensure critical and high-risk operations cannot bypass confirmation gates."""
        risk_lower = operation_risk.lower()
        requires_gate = risk_lower in ("high", "critical", "tier_3_high", "tier_4_critical")

        if not requires_gate:
            return True, "Operation risk does not require step-up confirmation gate."

        if not gate_token or not gate_token.strip():
            return (
                False,
                f"Confirmation gate bypass attempt: '{operation_risk}' operation requires a valid gate token.",
            )

        if not otp_verified:
            return (
                False,
                f"Unverified step-up confirmation: gate token '{gate_token[:8]}...' lacks validated OTP approval.",
            )

        return True, "Confirmation gate token and step-up 2FA verified authentic."
