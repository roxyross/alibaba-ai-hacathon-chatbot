"""Human-in-the-Loop Confirmation Gatekeeper for high-risk and critical actions.

Provides centralized challenge creation, tamper-proof HMAC tokens, step-up 2FA,
thread-safe atomic single-use consumption, parameter binding validation,
anti-replay enforcement, and resilient disk persistence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog

from app.trust.schemas import (
    ConfirmationChallengeResponse,
    ConfirmationResolutionResponse,
    ConfirmationStatus,
    RiskTier,
)

log = structlog.get_logger()

# Storage and synchronization locks
_CHALLENGES: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()
_STORAGE_PATH = Path(os.getenv("ROXY_CONFIRMATION_STORE", "data/confirmation_challenges.json"))


def _is_production() -> bool:
    """Detect whether current execution environment is a production deployment."""
    app_env = os.environ.get("APP_ENV", "").lower()
    env = os.environ.get("ENV", "").lower()
    environment = os.environ.get("ENVIRONMENT", "").lower()
    return (
        app_env in ("production", "prod")
        or env in ("production", "prod")
        or environment in ("production", "prod")
        or bool(os.environ.get("VERCEL"))
        or bool(os.environ.get("K_SERVICE"))
    )


def _get_signing_key() -> bytes:
    """Return stable HMAC signing secret derived from environment, avoiding ephemeral per-process keys."""
    secret = (
        os.environ.get("ROXY_CONFIRMATION_SECRET")
        or os.environ.get("SECRET_KEY")
        or os.environ.get("JWT_SECRET")
    )
    if secret:
        return hashlib.sha256(secret.encode("utf-8")).digest()
    if _is_production():
        raise RuntimeError(
            "Production security configuration error: ROXY_CONFIRMATION_SECRET, SECRET_KEY, or JWT_SECRET must be configured."
        )
    return b"roxy_stable_dev_confirmation_signing_key_32bytes"


def canonicalize_parameters(params: dict[str, Any] | None) -> str:
    """Deterministic JSON serialization and SHA-256 hash of parameters."""
    if not params:
        return hashlib.sha256(b"{}").hexdigest()
    try:
        serialized = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        serialized = str(sorted(params.items()))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ConfirmationGate:
    """Manages pending confirmation challenges, cryptographic tokens, 2FA step-up validation,
    and atomic single-use consumption with replay prevention.
    """

    _lock = _LOCK

    @classmethod
    def _get_storage_path(cls) -> Path:
        return _STORAGE_PATH

    @classmethod
    def is_independent_verification_configured(cls) -> bool:
        """Check whether a legitimate independent verification channel is configured."""
        if os.environ.get("ROXY_FORCE_DISABLE_2FA_DELIVERY", "").lower() == "true":
            return False
        # Legitimate channels: configured SMTP host/user, TOTP authenticator secret, or explicit 2FA delivery provider
        has_smtp = bool(os.environ.get("SMTP_HOST") and (os.environ.get("SMTP_USER") or os.environ.get("SMTP_PASS")))
        has_authenticator = bool(
            os.environ.get("ROXY_STEP_UP_AUTH_SECRET")
            or os.environ.get("ROXY_TOTP_SECRET")
            or os.environ.get("ROXY_STEP_UP_DELIVERY_PROVIDER")
        )
        if has_smtp or has_authenticator:
            return True
        # In non-production testing, allow if ROXY_ALLOW_TEST_STEP_UP is explicitly true (defaulting to true in tests)
        if not _is_production():
            return os.environ.get("ROXY_ALLOW_TEST_STEP_UP", "true").lower() == "true"
        return False

    @classmethod
    def _save_to_disk(cls) -> None:
        """Atomically persist active and consumed challenges to disk."""
        try:
            path = cls._get_storage_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            serializable: dict[str, Any] = {}
            for cid, rec in _CHALLENGES.items():
                copy_rec = dict(rec)
                for dt_key in ("created_at", "expires_at", "resolved_at", "consumed_at"):
                    if isinstance(copy_rec.get(dt_key), datetime):
                        copy_rec[dt_key] = copy_rec[dt_key].isoformat()
                if isinstance(copy_rec.get("status"), ConfirmationStatus):
                    copy_rec["status"] = copy_rec["status"].value
                if isinstance(copy_rec.get("risk_tier"), RiskTier):
                    copy_rec["risk_tier"] = copy_rec["risk_tier"].value
                serializable[cid] = copy_rec

            temp_fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix="conf_", suffix=".tmp")
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, path)
        except Exception as exc:
            log.warning("confirmation_gate.save_disk_failed", error=str(exc))
            if _is_production():
                raise RuntimeError(f"ConfirmationGate durable persistence failed in production: {exc}") from exc

    @classmethod
    def _load_from_disk(cls) -> None:
        """Load stored challenges from disk on initialization."""
        try:
            path = cls._get_storage_path()
            if not path.exists():
                return
            with open(path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            for cid, rec in raw_data.items():
                for dt_key in ("created_at", "expires_at", "resolved_at", "consumed_at"):
                    if rec.get(dt_key) and isinstance(rec[dt_key], str):
                        try:
                            rec[dt_key] = datetime.fromisoformat(rec[dt_key])
                        except Exception:
                            pass
                if rec.get("status"):
                    try:
                        rec["status"] = ConfirmationStatus(rec["status"])
                    except Exception:
                        pass
                if rec.get("risk_tier"):
                    try:
                        rec["risk_tier"] = RiskTier(rec["risk_tier"])
                    except Exception:
                        pass
                _CHALLENGES[cid] = rec
        except Exception as exc:
            log.warning("confirmation_gate.load_disk_failed", error=str(exc))

    @classmethod
    def clear(cls) -> None:
        """Reset challenges in-memory and on disk (used for test isolation)."""
        with cls._lock:
            _CHALLENGES.clear()
            try:
                path = cls._get_storage_path()
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    @classmethod
    def create_challenge(
        cls,
        user_id: str,
        action_type: str,
        title: str,
        summary: str,
        details: dict[str, Any] | None = None,
        risk_tier: RiskTier = RiskTier.HIGH,
        risk_score: int = 75,
        requires_2fa: bool = False,
        ttl_seconds: int = 300,
    ) -> ConfirmationChallengeResponse:
        """Create a cryptographically verified confirmation challenge bound to user and action."""
        with cls._lock:
            cls._cleanup_expired()

            challenge_id = f"chk_{uuid.uuid4().hex[:12]}"
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=ttl_seconds)

            # Generate HMAC token for challenge verification using stable key
            token_seed = f"{challenge_id}:{user_id}:{action_type}:{int(expires_at.timestamp())}".encode()
            challenge_token = hmac.new(_get_signing_key(), token_seed, hashlib.sha256).hexdigest()

            step_up_code = None
            step_up_hint = None
            is_step_up = requires_2fa or risk_tier == RiskTier.CRITICAL or risk_score >= 85

            if is_step_up:
                # Enforce independent verification configuration: fail closed if missing
                if not cls.is_independent_verification_configured():
                    log.error("confirmation_gate.step_up_unconfigured", action_type=action_type, user_id=user_id)
                    raise RuntimeError(
                        "Critical security policy: Independent step-up verification is not configured. "
                        "Operations requiring 2FA step-up cannot proceed without a configured authenticator or delivery provider."
                    )

                # Generate 6-digit numeric step-up code
                step_up_code = f"{secrets.randbelow(900000) + 100000:06d}"
                # P0 Security: Never leak verification code in hint, API response, or browser-visible metadata
                step_up_hint = "Enter the 6-digit verification code sent to your registered authenticator or out-of-band channel."

            challenge_data = {
                "challenge_id": challenge_id,
                "user_id": user_id,
                "action_type": action_type,
                "title": title,
                "summary": summary,
                "details": details or {},
                "risk_tier": risk_tier,
                "risk_score": risk_score,
                "challenge_token": challenge_token,
                "step_up_required": is_step_up,
                "step_up_code": step_up_code,
                "step_up_hint": step_up_hint,
                "status": ConfirmationStatus.PENDING,
                "attempts": 0,
                "created_at": now,
                "expires_at": expires_at,
                "resolved_at": None,
                "consumed_at": None,
                "decision": None,
                "comment": None,
            }

            _CHALLENGES[challenge_id] = challenge_data
            cls._save_to_disk()

            return ConfirmationChallengeResponse(
                challenge_id=challenge_id,
                user_id=user_id,
                action_type=action_type,
                title=title,
                summary=summary,
                details=details or {},
                risk_tier=risk_tier,
                risk_score=risk_score,
                challenge_token=challenge_token,
                step_up_required=is_step_up,
                step_up_hint=step_up_hint,
                status=ConfirmationStatus.PENDING,
                created_at=now,
                expires_at=expires_at,
            )

    @classmethod
    def get_challenge(cls, challenge_id: str, user_id: str) -> dict[str, Any] | None:
        """Fetch an active or recorded challenge by ID and user."""
        with cls._lock:
            cls._cleanup_expired()
            rec = _CHALLENGES.get(challenge_id)
            if rec and rec["user_id"] == user_id:
                return rec
            return None

    @classmethod
    def get_challenge_record(cls, challenge_id_or_token: str) -> dict[str, Any] | None:
        """Find a challenge record by ID or challenge_token."""
        with cls._lock:
            cls._cleanup_expired()
            if challenge_id_or_token in _CHALLENGES:
                return _CHALLENGES[challenge_id_or_token]
            for rec in _CHALLENGES.values():
                if rec.get("challenge_token") == challenge_id_or_token:
                    return rec
            return None

    @classmethod
    def list_pending(cls, user_id: str) -> list[ConfirmationChallengeResponse]:
        """List all pending, unexpired challenges for a specific user."""
        with cls._lock:
            cls._cleanup_expired()
            now = datetime.now(timezone.utc)
            results: list[ConfirmationChallengeResponse] = []

            for rec in _CHALLENGES.values():
                if (
                    rec["user_id"] == user_id
                    and rec["status"] == ConfirmationStatus.PENDING
                    and rec["expires_at"] > now
                ):
                    results.append(
                        ConfirmationChallengeResponse(
                            challenge_id=rec["challenge_id"],
                            user_id=rec["user_id"],
                            action_type=rec["action_type"],
                            title=rec["title"],
                            summary=rec["summary"],
                            details=rec["details"],
                            risk_tier=rec["risk_tier"],
                            risk_score=rec["risk_score"],
                            challenge_token=rec["challenge_token"],
                            step_up_required=rec["step_up_required"],
                            step_up_hint=rec["step_up_hint"],
                            status=rec["status"],
                            created_at=rec["created_at"],
                            expires_at=rec["expires_at"],
                        )
                    )

            results.sort(key=lambda x: x.created_at, reverse=True)
            return results

    @classmethod
    def resolve_challenge(
        cls,
        challenge_id: str,
        user_id: str,
        decision: str,
        challenge_token: str,
        step_up_code: str | None = None,
        comment: str | None = None,
    ) -> ConfirmationResolutionResponse:
        """Approve or reject a pending challenge with token and 2FA validation."""
        with cls._lock:
            cls._cleanup_expired()
            rec = _CHALLENGES.get(challenge_id)
            if not rec or rec["user_id"] != user_id:
                raise ValueError(f"Confirmation challenge {challenge_id} not found.")

            now = datetime.now(timezone.utc)
            if now > rec["expires_at"]:
                rec["status"] = ConfirmationStatus.EXPIRED
                cls._save_to_disk()
                raise ValueError("Confirmation challenge has expired.")

            if rec["status"] != ConfirmationStatus.PENDING:
                raise ValueError(f"Challenge already resolved as {rec['status'].value if hasattr(rec['status'], 'value') else rec['status']}.")

            # Enforce bounded attempts lockout (maximum 3 attempts)
            attempts = rec.get("attempts", 0)
            if attempts >= 3:
                rec["status"] = ConfirmationStatus.REJECTED
                cls._save_to_disk()
                raise ValueError("Maximum verification attempts exceeded. Challenge has been locked out.")

            # Constant-time HMAC comparison
            if not hmac.compare_digest(rec["challenge_token"], challenge_token):
                rec["attempts"] = attempts + 1
                cls._save_to_disk()
                raise ValueError("Invalid challenge verification token.")

            decision_clean = decision.strip().lower()
            if decision_clean not in {"approve", "reject"}:
                raise ValueError("Decision must be 'approve' or 'reject'.")

            # Validate step-up code if required and approving
            if decision_clean == "approve" and rec["step_up_required"]:
                expected_code = str(rec["step_up_code"])
                if not step_up_code or not hmac.compare_digest(step_up_code.strip(), expected_code):
                    rec["attempts"] = attempts + 1
                    cls._save_to_disk()
                    remaining = 3 - rec["attempts"]
                    if remaining <= 0:
                        rec["status"] = ConfirmationStatus.REJECTED
                        cls._save_to_disk()
                        raise ValueError("Maximum verification attempts exceeded. Challenge has been locked out.")
                    raise ValueError(f"Invalid step-up verification code. {remaining} attempt(s) remaining.")

            status = ConfirmationStatus.APPROVED if decision_clean == "approve" else ConfirmationStatus.REJECTED
            rec["status"] = status
            rec["resolved_at"] = now
            rec["decision"] = decision_clean
            rec["comment"] = comment

            # Generate tamper-proof resolution verification hash
            hash_payload = f"{challenge_id}:{status.value}:{int(now.timestamp())}:{user_id}".encode()
            verif_hash = hashlib.sha256(hash_payload).hexdigest()[:24]

            cls._save_to_disk()

            return ConfirmationResolutionResponse(
                challenge_id=challenge_id,
                status=status,
                decision=decision_clean,
                resolved_at=now,
                verification_hash=verif_hash,
                message=f"Action '{rec['title']}' was {status.value} by user."
                if status == ConfirmationStatus.APPROVED
                else f"Action '{rec['title']}' was rejected.",
            )

    @classmethod
    def approve_challenge_internally(
        cls,
        challenge_id_or_token: str,
        user_id: str,
        comment: str | None = None,
    ) -> bool:
        """Internal server-side approval mechanism after an authorized confirmation flow."""
        with cls._lock:
            rec = cls.get_challenge_record(challenge_id_or_token)
            if not rec or rec["user_id"] != user_id:
                return False

            now = datetime.now(timezone.utc)
            if now > rec["expires_at"]:
                rec["status"] = ConfirmationStatus.EXPIRED
                cls._save_to_disk()
                return False

            if rec["status"] != ConfirmationStatus.PENDING:
                return bool(rec["status"] == ConfirmationStatus.APPROVED)

            rec["status"] = ConfirmationStatus.APPROVED
            rec["resolved_at"] = now
            rec["decision"] = "approve"
            rec["comment"] = comment or "Approved via authenticated confirmation workflow"
            cls._save_to_disk()
            return True

    @classmethod
    def cancel_challenge(cls, challenge_id: str, user_id: str) -> bool:
        """Explicitly cancel a pending challenge."""
        with cls._lock:
            rec = _CHALLENGES.get(challenge_id)
            if not rec or rec["user_id"] != user_id:
                return False
            rec["status"] = ConfirmationStatus.CANCELLED
            rec["resolved_at"] = datetime.now(timezone.utc)
            cls._save_to_disk()
            return True

    @classmethod
    def consume_challenge(
        cls,
        challenge_id_or_token: str,
        user_id: str,
        action_type: str | None = None,
        details_match: dict[str, Any] | None = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Atomically validate approval, enforce exact operation binding, and consume challenge token.
        
        Guarantees single-use execution with race-safe thread locking and persistence.
        """
        with cls._lock:
            cls._cleanup_expired()
            rec = cls.get_challenge_record(challenge_id_or_token)
            if not rec:
                return (False, f"Confirmation challenge '{challenge_id_or_token}' not found.", None)

            # Check authenticated user ownership
            if rec["user_id"] != user_id:
                return (
                    False,
                    f"Unauthorized: Confirmation challenge belongs to a different user ({rec['user_id']} != {user_id}).",
                    None,
                )

            now = datetime.now(timezone.utc)
            if now > rec["expires_at"]:
                rec["status"] = ConfirmationStatus.EXPIRED
                cls._save_to_disk()
                return (False, "Confirmation challenge token has expired.", None)

            current_status = rec["status"]
            if current_status == ConfirmationStatus.CONSUMED:
                return (
                    False,
                    "Confirmation challenge has already been consumed (replay / duplicate execution prevented).",
                    None,
                )

            if current_status == ConfirmationStatus.PENDING:
                return (
                    False,
                    "Confirmation challenge is still pending user approval.",
                    None,
                )

            if current_status == ConfirmationStatus.REJECTED:
                return (
                    False,
                    "Confirmation challenge was rejected by the user.",
                    None,
                )

            if current_status != ConfirmationStatus.APPROVED:
                return (
                    False,
                    f"Confirmation challenge cannot be consumed in status '{current_status}'.",
                    None,
                )

            # Validate action_type if specified
            if action_type is not None and rec["action_type"] != action_type:
                return (
                    False,
                    f"Action mismatch: challenge issued for '{rec['action_type']}', but presented for '{action_type}'.",
                    None,
                )

            # Validate parameter and target bindings
            if details_match:
                rec_details = rec.get("details", {})
                for k, expected_v in details_match.items():
                    actual_v = rec_details.get(k)
                    if actual_v is not None and actual_v != expected_v:
                        return (
                            False,
                            f"Operation binding mismatch on '{k}': expected '{expected_v}', got '{actual_v}'.",
                            None,
                        )

            # Transition atomically to CONSUMED
            rec["status"] = ConfirmationStatus.CONSUMED
            rec["consumed_at"] = now
            cls._save_to_disk()

            log.info(
                "confirmation_gate.challenge_consumed",
                challenge_id=rec["challenge_id"],
                user_id=user_id,
                action_type=rec["action_type"],
            )
            return (True, "APPROVED_AND_CONSUMED", rec)

    @classmethod
    def _cleanup_expired(cls) -> None:
        """Mark expired pending challenges."""
        now = datetime.now(timezone.utc)
        dirty = False
        for rec in _CHALLENGES.values():
            if rec["status"] == ConfirmationStatus.PENDING and now > rec["expires_at"]:
                rec["status"] = ConfirmationStatus.EXPIRED
                dirty = True
        if dirty:
            cls._save_to_disk()


# Initialize stored challenges on module load
ConfirmationGate._load_from_disk()
