"""Human-in-the-Loop Confirmation Gatekeeper for high-risk and critical actions.

Provides centralized challenge creation, tamper-proof HMAC tokens, step-up 2FA,
independent delivery verification channels, durable cross-worker PostgreSQL atomicity,
strict fail-closed parameter binding validation, anti-replay enforcement,
and resilient disk persistence.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import tempfile
import threading
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from app.trust.schemas import (
    ConfirmationChallengeResponse,
    ConfirmationResolutionResponse,
    ConfirmationStatus,
    RiskTier,
)

_T = TypeVar("_T")

log = structlog.get_logger()

# Storage and synchronization locks for local isolated execution
_CHALLENGES: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()
_STORAGE_PATH = Path(os.getenv("ROXY_CONFIRMATION_STORE", "data/confirmation_challenges.json"))

# Finding C: Mandatory required parameters per action type
# Non-presence of any required field in saved or caller details immediately fails closed.
REQUIRED_ACTION_PARAMETERS: dict[str, set[str]] = {
    "financial_wire": {"amount", "destination"},
    "bank_transfer": {"amount", "destination"},
    "delete_database": {"target_resource"},
    "wipe_resource": {"target_resource"},
}

# Sensitive keys that must strictly match if present in saved challenge
SENSITIVE_BINDING_KEYS: set[str] = {
    "amount",
    "destination",
    "recipient",
    "target_resource",
    "target",
    "target_user_id",
    "to",
}


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


def _canonicalize_param_value(val: Any) -> Any:
    """Normalize parameter values for secure equivalence checks without weakening exact constraints."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        stripped = val.strip()
        # Canonicalize email addresses to lowercase
        if "@" in stripped and not stripped.startswith("{"):
            return stripped.lower()
        # Try numeric string normalization
        try:
            return float(stripped)
        except ValueError:
            return stripped
    if isinstance(val, dict):
        try:
            return json.dumps(val, sort_keys=True, default=str)
        except Exception:
            return str(sorted(val.items()))
    return val


def _are_parameters_equivalent(val1: Any, val2: Any) -> bool:
    """Compare two parameter values under canonicalization."""
    c1 = _canonicalize_param_value(val1)
    c2 = _canonicalize_param_value(val2)
    return bool(c1 == c2)


def _validate_parameter_bindings(
    action_type: str,
    saved_details: dict[str, Any],
    caller_details: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Finding C: Strictly validate that caller-supplied parameters bind to saved values.

    Rules:
    1. If action_type has mandatory parameters in REQUIRED_ACTION_PARAMETERS:
       - Every mandatory parameter MUST be present in saved_details (not None).
       - Every mandatory parameter MUST be provided by caller in caller_details (not None).
    2. Any parameter present in caller_details MUST exist in saved_details (missing saved value is a mismatch).
    3. Parameter values must match under canonicalized comparison.
    4. If saved_details contains sensitive binding keys, caller MUST provide them and they must match.
    """
    # 1. Enforce mandatory parameters per action type
    if action_type in REQUIRED_ACTION_PARAMETERS:
        required_keys = REQUIRED_ACTION_PARAMETERS[action_type]
        for req_k in required_keys:
            if req_k not in saved_details or saved_details[req_k] is None:
                return (
                    False,
                    f"Security binding failure: Required parameter '{req_k}' is missing from saved challenge details for action '{action_type}'.",
                )
            if not caller_details or req_k not in caller_details or caller_details[req_k] is None:
                return (
                    False,
                    f"Security binding failure: Required parameter '{req_k}' was not provided by caller for action '{action_type}'.",
                )

    # 2. Check all caller-supplied parameter matches
    if caller_details:
        for k, caller_v in caller_details.items():
            if k not in saved_details:
                return (
                    False,
                    f"Operation binding mismatch on '{k}': parameter not present in saved challenge.",
                )
            saved_v = saved_details[k]
            if not _are_parameters_equivalent(saved_v, caller_v):
                return (
                    False,
                    f"Operation binding mismatch on '{k}': expected '{saved_v}', got '{caller_v}'.",
                )

    # 3. Check that security-sensitive saved keys are not omitted by caller
    if saved_details:
        saved_sensitive = {k for k in saved_details if k in SENSITIVE_BINDING_KEYS}
        if saved_sensitive:
            if not caller_details:
                return (
                    False,
                    "Security binding failure: Operation contains sensitive bindings but caller provided none.",
                )
            for sk in saved_sensitive:
                if sk not in caller_details or caller_details[sk] is None:
                    return (
                        False,
                        f"Security binding failure: Required sensitive parameter '{sk}' was omitted by caller.",
                    )

    return (True, "OK")


# ============================================================================
# Finding A: Real Step-Up Verification Delivery Channel Protocol & Providers
# ============================================================================

@dataclass
class StepUpDeliveryResult:
    """Outcome of attempting to deliver a verification code to an independent provider.

    CRITICAL ARCHITECTURAL DISTINCTION:
    - `provider_accepted`: The delivery gateway (e.g., SMTP MTA 250 OK or delivery gateway)
      has accepted the message into its transmission queue.
      This does NOT guarantee that the user has received or read the message (which depends
      on downstream network routing, spam filters, and device reception).
      However, verified provider acceptance is the mandatory cryptographic boundary required
      before ROXY treats the step-up challenge as active.
    - If provider acceptance is False, ROXY fails closed and halts execution.
    """
    success: bool
    provider_accepted: bool
    provider_name: str
    message_id: str | None = None
    error: str | None = None


@runtime_checkable
class StepUpDeliveryProvider(Protocol):
    """Protocol for independent step-up verification delivery channels."""

    name: str

    def send_step_up_code(
        self,
        user_id: str,
        code: str,
        action_type: str,
        title: str,
        recipient: str | None = None,
    ) -> StepUpDeliveryResult:
        """Dispatch a 6-digit verification code to the user via out-of-band channel."""
        ...


class SMTPStepUpDeliveryProvider:
    """Legitimate SMTP-based step-up delivery provider reusing standard email transport."""

    name: str = "smtp"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        sender: str | None = None,
        use_tls: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self.host = host or os.environ.get("SMTP_HOST", "")
        self.port = port or int(os.environ.get("SMTP_PORT", "587"))
        self.user = user or os.environ.get("SMTP_USER", "")
        self.password = password or os.environ.get("SMTP_PASS", "")
        self.sender = sender or os.environ.get("SMTP_FROM", "security@roxy.ai")
        self.use_tls = use_tls
        self.timeout = timeout

    def send_step_up_code(
        self,
        user_id: str,
        code: str,
        action_type: str,
        title: str,
        recipient: str | None = None,
    ) -> StepUpDeliveryResult:
        if not self.host:
            return StepUpDeliveryResult(
                success=False,
                provider_accepted=False,
                provider_name=self.name,
                error="SMTP host is not configured.",
            )
        target_email = recipient or os.environ.get("ROXY_STEP_UP_RECIPIENT_EMAIL") or f"{user_id}@users.roxy.ai"
        try:
            msg = EmailMessage()
            msg["Subject"] = f"Roxy AI Security Verification Code: [{title}]"
            msg["From"] = self.sender
            msg["To"] = target_email
            msg.set_content(
                f"A sensitive action requires your verification:\n\n"
                f"Action: {title} ({action_type})\n"
                f"Your 6-digit confirmation code is: {code}\n\n"
                f"This code expires in 5 minutes. If you did not request this, please report immediately."
            )
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                send_errs = server.send_message(msg)
                if send_errs:
                    return StepUpDeliveryResult(
                        success=False,
                        provider_accepted=False,
                        provider_name=self.name,
                        error=f"SMTP server rejected recipients: {send_errs}",
                    )
                return StepUpDeliveryResult(
                    success=True,
                    provider_accepted=True,
                    provider_name=self.name,
                    message_id=msg.get("Message-ID", f"smtp_{uuid.uuid4().hex[:12]}"),
                )
        except Exception as exc:
            return StepUpDeliveryResult(
                success=False,
                provider_accepted=False,
                provider_name=self.name,
                error=f"SMTP dispatch failure: {exc}",
            )


class MockStepUpDeliveryProvider:
    """Mock delivery provider for deterministic unit and acceptance testing."""

    name: str = "mock"

    def __init__(self, should_succeed: bool = True, provider_accepted: bool = True) -> None:
        self.should_succeed = should_succeed
        self.provider_accepted = provider_accepted
        self.dispatched_records: list[dict[str, Any]] = []

    def send_step_up_code(
        self,
        user_id: str,
        code: str,
        action_type: str,
        title: str,
        recipient: str | None = None,
    ) -> StepUpDeliveryResult:
        if not self.should_succeed:
            return StepUpDeliveryResult(
                success=False,
                provider_accepted=False,
                provider_name=self.name,
                error="Simulated delivery provider network outage / rejection.",
            )
        msg_id = f"mock_msg_{uuid.uuid4().hex[:12]}"
        self.dispatched_records.append(
            {
                "message_id": msg_id,
                "user_id": user_id,
                "code": code,
                "action_type": action_type,
                "title": title,
                "recipient": recipient,
                "timestamp": datetime.now(UTC),
            }
        )
        return StepUpDeliveryResult(
            success=True,
            provider_accepted=self.provider_accepted,
            provider_name=self.name,
            message_id=msg_id,
        )


# ============================================================================
# Central Confirmation Gate
# ============================================================================

class ConfirmationGate:
    """Manages pending confirmation challenges, cryptographic tokens, 2FA step-up validation,
    durable cross-worker single-use atomic consumption, and strict parameter binding.
    """

    _lock = _LOCK
    _delivery_provider: StepUpDeliveryProvider | None = None
    _db_engine: AsyncEngine | None = None

    @classmethod
    def register_delivery_provider(cls, provider: StepUpDeliveryProvider | None) -> None:
        """Register an active out-of-band delivery provider."""
        with cls._lock:
            cls._delivery_provider = provider

    @classmethod
    def get_delivery_provider(cls) -> StepUpDeliveryProvider | None:
        """Retrieve the configured delivery provider, auto-discovering SMTP if available."""
        with cls._lock:
            if cls._delivery_provider is not None:
                return cls._delivery_provider

            # Check if SMTP is configured
            smtp_host = os.environ.get("SMTP_HOST")
            if smtp_host:
                return SMTPStepUpDeliveryProvider()

            return None

    @classmethod
    def set_db_engine(cls, engine: AsyncEngine | None) -> None:
        """Explicitly set an AsyncEngine for PostgreSQL durable persistence."""
        with cls._lock:
            cls._db_engine = engine

    @classmethod
    def get_db_engine(cls) -> AsyncEngine | None:
        """Get currently configured or global database engine."""
        with cls._lock:
            if cls._db_engine is not None:
                return cls._db_engine
            # If in production or explicit DB url configured, attempt to use global engine
            if _is_production() or os.environ.get("ROXY_USE_DB_CONFIRMATION", "").lower() == "true":
                try:
                    from app.db import get_engine
                    return get_engine()
                except Exception as exc:
                    log.warning("confirmation_gate.get_db_engine_failed", error=str(exc))
                    if _is_production():
                        raise RuntimeError(
                            f"Production failure: database engine unavailable for durable confirmation storage: {exc}"
                        ) from exc
            return None

    @classmethod
    def is_independent_verification_configured(cls) -> bool:
        """Check whether a legitimate independent verification channel is actively configured and available.

        A configuration string or environment flag alone NEVER counts as proof of delivery configuration.
        """
        if os.environ.get("ROXY_FORCE_DISABLE_2FA_DELIVERY", "").lower() == "true":
            return False

        # Finding A Requirement 2: Configuration flag without a real delivery implementation fails closed!
        provider_flag = os.environ.get("ROXY_STEP_UP_DELIVERY_PROVIDER", "").strip().lower()
        if provider_flag and cls._delivery_provider is None and provider_flag not in ("smtp", "mock"):
            return False

        provider = cls.get_delivery_provider()
        return provider is not None

    @classmethod
    def _get_storage_path(cls) -> Path:
        return _STORAGE_PATH

    @classmethod
    def _save_to_disk(cls) -> None:
        """Atomically persist active and consumed challenges to disk (for local development)."""
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
            with open(path, encoding="utf-8") as f:
                raw_data = json.load(f)
            for cid, rec in raw_data.items():
                for dt_key in ("created_at", "expires_at", "resolved_at", "consumed_at"):
                    if rec.get(dt_key) and isinstance(rec[dt_key], str):
                        with contextlib.suppress(Exception):
                            rec[dt_key] = datetime.fromisoformat(rec[dt_key])
                if rec.get("status"):
                    with contextlib.suppress(Exception):
                        rec["status"] = ConfirmationStatus(rec["status"])
                if rec.get("risk_tier"):
                    with contextlib.suppress(Exception):
                        rec["risk_tier"] = RiskTier(rec["risk_tier"])
                _CHALLENGES[cid] = rec
        except Exception as exc:
            log.warning("confirmation_gate.load_disk_failed", error=str(exc))

    @classmethod
    def clear(cls) -> None:
        """Reset challenges in-memory and on disk (used for test isolation)."""
        with cls._lock:
            _CHALLENGES.clear()
            cls._delivery_provider = None
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
        """Create a cryptographically verified confirmation challenge bound to user and action.

        Enforces:
        - Finding A: Real step-up delivery provider dispatch and verification before challenge is created.
        - Finding B: Durable PostgreSQL persistence in production or when DB is configured.
        - Finding C: Preservation of exact action details for subsequent binding verification.
        """
        with cls._lock:
            cls._cleanup_expired()

            challenge_id = f"chk_{uuid.uuid4().hex[:12]}"
            now = datetime.now(UTC)
            expires_at = now + timedelta(seconds=ttl_seconds)

            # Generate HMAC token for challenge verification using stable signing secret
            token_seed = f"{challenge_id}:{user_id}:{action_type}:{int(expires_at.timestamp())}".encode()
            challenge_token = hmac.new(_get_signing_key(), token_seed, hashlib.sha256).hexdigest()

            step_up_code = None
            step_up_hint = None
            is_step_up = requires_2fa or risk_tier == RiskTier.CRITICAL or risk_score >= 85

            if is_step_up:
                # Finding A: Enforce independent verification configuration: fail closed if missing
                if not cls.is_independent_verification_configured():
                    log.error("confirmation_gate.step_up_unconfigured", action_type=action_type, user_id=user_id)
                    raise RuntimeError(
                        "Critical security policy: Independent step-up verification is not configured. "
                        "Operations requiring 2FA step-up cannot proceed without a configured delivery provider."
                    )

                provider = cls.get_delivery_provider()
                if provider is None:
                    raise RuntimeError(
                        "Critical security policy: Independent step-up verification delivery provider is missing."
                    )

                # Generate 6-digit numeric step-up code
                step_up_code = f"{secrets.randbelow(900000) + 100000:06d}"

                # Finding A: Real delivery provider invocation and acceptance verification
                recipient_addr = (details or {}).get("recipient_email") or (details or {}).get("to")
                delivery_res = provider.send_step_up_code(
                    user_id=user_id,
                    code=step_up_code,
                    action_type=action_type,
                    title=title,
                    recipient=recipient_addr,
                )

                if not delivery_res.success or not delivery_res.provider_accepted:
                    log.error(
                        "confirmation_gate.delivery_failed",
                        provider=provider.name,
                        error=delivery_res.error,
                        action_type=action_type,
                        user_id=user_id,
                    )
                    raise RuntimeError(
                        f"Step-up verification delivery failed closed: {delivery_res.error or 'Provider rejected dispatch'}"
                    )

                # Generic user-facing hint — NEVER leak code in response, hint, logs, or metadata
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

            # Finding B: Shared durable storage persistence if database engine configured
            engine = cls.get_db_engine()
            if engine is not None:
                cls._run_async(cls._save_challenge_to_db(challenge_data, engine))
            elif _is_production():
                raise RuntimeError("Shared durable database storage is required in production but unavailable.")

            _CHALLENGES[challenge_id] = challenge_data
            cls._save_to_disk()

            log.info(
                "confirmation_gate.challenge_created",
                challenge_id=challenge_id,
                action_type=action_type,
                user_id=user_id,
                is_step_up=is_step_up,
            )

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
            engine = cls.get_db_engine()
            if engine is not None:
                rec = cls._run_async(cls._get_challenge_from_db(challenge_id, user_id, engine))
                if rec:
                    return rec

            rec = _CHALLENGES.get(challenge_id)
            if rec and rec["user_id"] == user_id:
                return rec
            return None

    @classmethod
    def get_challenge_record(cls, challenge_id_or_token: str) -> dict[str, Any] | None:
        """Find a challenge record by ID or challenge_token."""
        with cls._lock:
            cls._cleanup_expired()
            engine = cls.get_db_engine()
            if engine is not None:
                rec = cls._run_async(cls._get_challenge_from_db(challenge_id_or_token, None, engine))
                if rec:
                    return rec

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
            engine = cls.get_db_engine()
            if engine is not None:
                return cls._run_async(cls._list_pending_from_db(user_id, engine))

            now = datetime.now(UTC)
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
            engine = cls.get_db_engine()

            rec = cls.get_challenge_record(challenge_id)
            if not rec or rec["user_id"] != user_id:
                raise ValueError(f"Confirmation challenge {challenge_id} not found.")

            now = datetime.now(UTC)
            if now > rec["expires_at"]:
                rec["status"] = ConfirmationStatus.EXPIRED
                cls._save_to_disk()
                if engine is not None:
                    cls._run_async(cls._update_challenge_in_db(challenge_id, {"status": "expired"}, engine))
                raise ValueError("Confirmation challenge has expired.")

            if rec["status"] != ConfirmationStatus.PENDING:
                raise ValueError(
                    f"Challenge already resolved as {rec['status'].value if hasattr(rec['status'], 'value') else rec['status']}."
                )

            attempts = rec.get("attempts", 0)
            if attempts >= 3:
                rec["status"] = ConfirmationStatus.REJECTED
                cls._save_to_disk()
                if engine is not None:
                    cls._run_async(cls._update_challenge_in_db(challenge_id, {"status": "rejected", "attempts": attempts}, engine))
                raise ValueError("Maximum verification attempts exceeded. Challenge has been locked out.")

            # Constant-time HMAC comparison
            if not hmac.compare_digest(rec["challenge_token"], challenge_token):
                rec["attempts"] = attempts + 1
                cls._save_to_disk()
                if engine is not None:
                    cls._run_async(cls._update_challenge_in_db(challenge_id, {"attempts": rec["attempts"]}, engine))
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
                        if engine is not None:
                            cls._run_async(cls._update_challenge_in_db(challenge_id, {"status": "rejected", "attempts": rec["attempts"]}, engine))
                        raise ValueError("Maximum verification attempts exceeded. Challenge has been locked out.")
                    if engine is not None:
                        cls._run_async(cls._update_challenge_in_db(challenge_id, {"attempts": rec["attempts"]}, engine))
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
            if engine is not None:
                cls._run_async(
                    cls._update_challenge_in_db(
                        challenge_id,
                        {
                            "status": status.value if hasattr(status, "value") else str(status),
                            "resolved_at": now,
                            "decision": decision_clean,
                            "comment": comment,
                        },
                        engine,
                    )
                )

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

            now = datetime.now(UTC)
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

            engine = cls.get_db_engine()
            if engine is not None:
                cls._run_async(
                    cls._update_challenge_in_db(
                        rec["challenge_id"],
                        {"status": "approved", "resolved_at": now, "decision": "approve", "comment": rec["comment"]},
                        engine,
                    )
                )
            return True

    @classmethod
    def cancel_challenge(cls, challenge_id: str, user_id: str) -> bool:
        """Explicitly cancel a pending challenge."""
        with cls._lock:
            rec = cls.get_challenge_record(challenge_id)
            if not rec or rec["user_id"] != user_id:
                return False
            rec["status"] = ConfirmationStatus.CANCELLED
            rec["resolved_at"] = datetime.now(UTC)
            cls._save_to_disk()
            engine = cls.get_db_engine()
            if engine is not None:
                cls._run_async(
                    cls._update_challenge_in_db(
                        challenge_id,
                        {"status": "cancelled", "resolved_at": rec["resolved_at"]},
                        engine,
                    )
                )
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

        Guarantees single-use execution with race-safe durable database locking or thread locking.
        """
        engine = cls.get_db_engine()
        if engine is not None:
            # Finding B: Cross-worker durable storage path via PostgreSQL
            return cls._run_async(
                cls.consume_challenge_db(
                    challenge_id_or_token=challenge_id_or_token,
                    user_id=user_id,
                    action_type=action_type,
                    details_match=details_match,
                    engine=engine,
                )
            )

        if _is_production():
            log.error("confirmation_gate.db_required_in_prod")
            return (
                False,
                "Durable shared database storage is required in production but unavailable. Fails closed.",
                None,
            )

        # Local in-memory store for unit test isolation
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

            now = datetime.now(UTC)
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

            # Finding C: Fail-Closed Parameter Binding
            saved_details = rec.get("details", {})
            valid_binding, binding_msg = _validate_parameter_bindings(
                action_type=rec["action_type"],
                saved_details=saved_details,
                caller_details=details_match,
            )
            if not valid_binding:
                return (False, binding_msg, None)

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
    async def consume_challenge_db(
        cls,
        challenge_id_or_token: str,
        user_id: str,
        action_type: str | None = None,
        details_match: dict[str, Any] | None = None,
        engine: AsyncEngine | None = None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Finding B: Cross-worker durable PostgreSQL single-use atomic consumption using row-level locking.

        Guarantees that across independent worker processes, containers, or nodes:
        - Exactly one worker can acquire row-level lock and transition from approved to consumed.
        - Concurrent consumption by a second worker is immediately blocked and rejected.
        - Fail-closed if database is unavailable.
        """
        target_engine = engine or cls.get_db_engine()
        if target_engine is None:
            if _is_production():
                return (
                    False,
                    "Durable shared database storage is required in production but unavailable. Fails closed.",
                    None,
                )
            return (False, "Database engine is not configured.", None)

        try:
            from sqlalchemy import or_, select
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

            from app.models.trust import ConfirmationChallengeModel

            session_maker = async_sessionmaker(target_engine, expire_on_commit=False, class_=AsyncSession)
            async with session_maker() as session, session.begin():
                # Acquire row-level exclusive lock (FOR UPDATE)
                stmt = (
                    select(ConfirmationChallengeModel)
                    .where(
                        or_(
                            ConfirmationChallengeModel.challenge_id == challenge_id_or_token,
                            ConfirmationChallengeModel.challenge_token == challenge_id_or_token,
                        )
                    )
                    .with_for_update()
                )
                res = await session.execute(stmt)
                rec = res.scalar_one_or_none()

                if not rec:
                    return (False, f"Confirmation challenge '{challenge_id_or_token}' not found.", None)

                # Check user ownership
                if rec.user_id != user_id:
                    return (
                        False,
                        f"Unauthorized: Confirmation challenge belongs to a different user ({rec.user_id} != {user_id}).",
                        None,
                    )

                now = datetime.now(UTC)
                if now > rec.expires_at:
                    rec.status = "expired"
                    await session.commit()
                    return (False, "Confirmation challenge token has expired.", None)

                if rec.status == "consumed":
                    return (
                        False,
                        "Confirmation challenge has already been consumed (replay / duplicate execution prevented).",
                        None,
                    )

                if rec.status == "pending":
                    return (False, "Confirmation challenge is still pending user approval.", None)

                if rec.status == "rejected":
                    return (False, "Confirmation challenge was rejected by the user.", None)

                if rec.status != "approved":
                    return (
                        False,
                        f"Confirmation challenge cannot be consumed in status '{rec.status}'.",
                        None,
                    )

                if action_type is not None and rec.action_type != action_type:
                    return (
                        False,
                        f"Action mismatch: challenge issued for '{rec.action_type}', but presented for '{action_type}'.",
                        None,
                    )

                # Finding C: Fail-Closed Parameter Binding
                saved_details = rec.get_details()
                valid_binding, binding_msg = _validate_parameter_bindings(
                    action_type=rec.action_type,
                    saved_details=saved_details,
                    caller_details=details_match,
                )
                if not valid_binding:
                    return (False, binding_msg, None)

                # Transition atomically to consumed
                rec.status = "consumed"
                rec.consumed_at = now
                await session.commit()

                log.info(
                    "confirmation_gate.db_challenge_consumed",
                    challenge_id=rec.challenge_id,
                    user_id=user_id,
                    action_type=rec.action_type,
                )
                return (True, "APPROVED_AND_CONSUMED", rec.to_dict())

        except Exception as exc:
            log.error("confirmation_gate.db_consumption_failed", error=str(exc))
            return (
                False,
                f"Durable storage error: action not authorized due to database failure: {exc}",
                None,
            )

    @classmethod
    async def _save_challenge_to_db(cls, rec_dict: dict[str, Any], engine: AsyncEngine) -> None:
        """Persist newly created challenge into PostgreSQL table."""
        try:
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

            from app.models.trust import ConfirmationChallengeModel

            session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with session_maker() as session, session.begin():
                m = ConfirmationChallengeModel(
                    challenge_id=rec_dict["challenge_id"],
                    user_id=rec_dict["user_id"],
                    action_type=rec_dict["action_type"],
                    title=rec_dict["title"],
                    summary=rec_dict["summary"],
                    risk_tier=rec_dict["risk_tier"].value
                    if hasattr(rec_dict["risk_tier"], "value")
                    else str(rec_dict["risk_tier"]),
                    risk_score=rec_dict["risk_score"],
                    challenge_token=rec_dict["challenge_token"],
                    step_up_required=rec_dict["step_up_required"],
                    step_up_code=rec_dict["step_up_code"],
                    step_up_hint=rec_dict["step_up_hint"],
                    status=rec_dict["status"].value
                    if hasattr(rec_dict["status"], "value")
                    else str(rec_dict["status"]),
                    attempts=rec_dict["attempts"],
                    created_at=rec_dict["created_at"],
                    expires_at=rec_dict["expires_at"],
                )
                m.set_details(rec_dict.get("details", {}))
                session.add(m)
        except Exception as exc:
            log.error("confirmation_gate.save_db_failed", error=str(exc))
            if _is_production():
                raise RuntimeError(f"ConfirmationGate durable persistence failed in production: {exc}") from exc

    @classmethod
    async def _update_challenge_in_db(
        cls, challenge_id: str, updates: dict[str, Any], engine: AsyncEngine
    ) -> None:
        """Update existing challenge record in PostgreSQL table."""
        try:
            from sqlalchemy import update
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

            from app.models.trust import ConfirmationChallengeModel

            session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with session_maker() as session, session.begin():
                stmt = (
                    update(ConfirmationChallengeModel)
                    .where(ConfirmationChallengeModel.challenge_id == challenge_id)
                    .values(**updates)
                )
                await session.execute(stmt)
        except Exception as exc:
            log.error("confirmation_gate.update_db_failed", error=str(exc))

    @classmethod
    async def _get_challenge_from_db(
        cls, challenge_id_or_token: str, user_id: str | None, engine: AsyncEngine
    ) -> dict[str, Any] | None:
        """Fetch challenge record from PostgreSQL table."""
        try:
            from sqlalchemy import or_, select
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

            from app.models.trust import ConfirmationChallengeModel

            session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with session_maker() as session:
                stmt = select(ConfirmationChallengeModel).where(
                    or_(
                        ConfirmationChallengeModel.challenge_id == challenge_id_or_token,
                        ConfirmationChallengeModel.challenge_token == challenge_id_or_token,
                    )
                )
                if user_id:
                    stmt = stmt.where(ConfirmationChallengeModel.user_id == user_id)
                res = await session.execute(stmt)
                m = res.scalar_one_or_none()
                return m.to_dict() if m else None
        except Exception as exc:
            log.error("confirmation_gate.get_db_failed", error=str(exc))
            return None

    @classmethod
    async def _list_pending_from_db(
        cls, user_id: str, engine: AsyncEngine
    ) -> list[ConfirmationChallengeResponse]:
        """Fetch pending challenges from PostgreSQL table."""
        try:
            from sqlalchemy import desc, select
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

            from app.models.trust import ConfirmationChallengeModel

            now = datetime.now(UTC)
            session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with session_maker() as session:
                stmt = (
                    select(ConfirmationChallengeModel)
                    .where(
                        ConfirmationChallengeModel.user_id == user_id,
                        ConfirmationChallengeModel.status == "pending",
                        ConfirmationChallengeModel.expires_at > now,
                    )
                    .order_by(desc(ConfirmationChallengeModel.created_at))
                )
                res = await session.execute(stmt)
                records = res.scalars().all()
                return [
                    ConfirmationChallengeResponse(
                        challenge_id=r.challenge_id,
                        user_id=r.user_id,
                        action_type=r.action_type,
                        title=r.title,
                        summary=r.summary,
                        details=r.get_details(),
                        risk_tier=RiskTier(r.risk_tier) if r.risk_tier in RiskTier.__members__ else RiskTier.HIGH,
                        risk_score=r.risk_score,
                        challenge_token=r.challenge_token,
                        step_up_required=r.step_up_required,
                        step_up_hint=r.step_up_hint,
                        status=ConfirmationStatus.PENDING,
                        created_at=r.created_at,
                        expires_at=r.expires_at,
                    )
                    for r in records
                ]
        except Exception as exc:
            log.error("confirmation_gate.list_pending_db_failed", error=str(exc))
            return []

    @classmethod
    def _cleanup_expired(cls) -> None:
        """Mark expired pending challenges."""
        now = datetime.now(UTC)
        dirty = False
        for rec in _CHALLENGES.values():
            if rec["status"] == ConfirmationStatus.PENDING and now > rec["expires_at"]:
                rec["status"] = ConfirmationStatus.EXPIRED
                dirty = True
        if dirty:
            cls._save_to_disk()

    @staticmethod
    def _run_async(coro: Coroutine[Any, Any, _T]) -> _T:
        """Execute an async coroutine synchronously, even when inside an active event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                res: _T = executor.submit(lambda: asyncio.run(coro)).result()
                return res
        return asyncio.run(coro)


# Initialize stored challenges on module load
ConfirmationGate._load_from_disk()
