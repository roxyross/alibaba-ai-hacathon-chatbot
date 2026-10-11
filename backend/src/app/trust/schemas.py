"""Pydantic schemas for Trust & Safety, Risk Matrix, DLP, and Confirmations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OperationCategory(str, Enum):
    READ_ONLY = "read_only"
    CONTENT_GENERATION = "content_generation"
    DATA_MODIFICATION = "data_modification"
    SYSTEM_COMMAND = "system_command"
    NETWORK_COMMUNICATION = "network_communication"
    FINANCIAL_TRANSACTION = "financial_transaction"
    PERMISSION_GRANT = "permission_grant"
    CREDENTIAL_ACCESS = "credential_access"


class ConfirmationType(str, Enum):
    NONE = "none"
    STANDARD = "standard"
    STEP_UP_2FA = "step_up_2fa"
    BIOMETRIC = "biometric"


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"


class DLPCategory(str, Enum):
    CREDIT_CARD = "credit_card"
    IBAN = "iban"
    API_KEY = "api_key"
    PRIVATE_KEY = "private_key"
    DB_CONNECTION = "db_connection"
    PASSWORD = "password"
    SSN = "ssn"
    NATIONAL_ID = "national_id"
    EMAIL = "email"
    PHONE = "phone"


# --- Risk Evaluation ---

class RiskEvaluationRequest(BaseModel):
    action_type: str = Field(..., description="Action identifier, e.g. financial_transfer, sql_update, shell_exec")
    tool_name: str | None = Field(None, description="Tool name if invoked by an agent")
    payload: dict[str, Any] = Field(default_factory=dict, description="Action arguments and parameters")
    context: dict[str, Any] | None = Field(default_factory=dict, description="Session and workspace context")


class RiskEvaluationResponse(BaseModel):
    tier: RiskTier
    score: int = Field(..., ge=0, le=100, description="Risk score from 0 (harmless) to 100 (extreme)")
    category: OperationCategory
    requires_confirmation: bool
    confirmation_type: ConfirmationType
    risk_factors: list[str]
    safeguards: list[str]
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RiskMatrixConfigResponse(BaseModel):
    tiers: dict[str, dict[str, Any]]
    categories: dict[str, str]
    thresholds: dict[str, int]
    financial_thresholds: dict[str, float]


# --- DLP Engine ---

class DLPMatch(BaseModel):
    category: DLPCategory
    matched_text: str
    masked_text: str
    start: int
    end: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    rule_name: str
    details: str | None = None


class DLPScanRequest(BaseModel):
    text: str | None = None
    payload: dict[str, Any] | None = None
    mask_style: str = Field(default="tag", description="'tag' for [REDACTED_TYPE] or 'mask' for ••••")
    categories: list[DLPCategory] | None = None


class DLPScanResponse(BaseModel):
    has_violations: bool
    total_violations: int
    matches: list[DLPMatch]
    sanitized_text: str | None = None
    sanitized_payload: dict[str, Any] | None = None
    action_recommended: str = Field(..., description="'allow', 'warn', or 'block'")


class DLPRedactRequest(BaseModel):
    text: str
    mask_style: str = Field(default="tag", description="'tag' or 'mask'")


class DLPRedactResponse(BaseModel):
    original_length: int
    redacted_length: int
    violations_count: int
    redacted_text: str


class DLPRuleInfo(BaseModel):
    category: DLPCategory
    name: str
    description: str
    severity: str
    validation_method: str


# --- Confirmations & Human In The Loop ---

class CreateConfirmationRequest(BaseModel):
    action_type: str
    title: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    risk_tier: RiskTier = RiskTier.HIGH
    risk_score: int = 75
    requires_2fa: bool = False
    ttl_seconds: int = Field(default=300, ge=30, le=3600)


class ConfirmationChallengeResponse(BaseModel):
    challenge_id: str
    user_id: str
    action_type: str
    title: str
    summary: str
    details: dict[str, Any]
    risk_tier: RiskTier
    risk_score: int
    challenge_token: str
    step_up_required: bool
    step_up_hint: str | None = None
    status: ConfirmationStatus
    created_at: datetime
    expires_at: datetime


class ResolveConfirmationRequest(BaseModel):
    decision: str = Field(..., description="'approve' or 'reject'")
    challenge_token: str = Field(..., description="Tamper-proof HMAC token issued with challenge")
    step_up_code: str | None = Field(None, description="6-digit verification code if 2FA required")
    comment: str | None = None


class ConfirmationResolutionResponse(BaseModel):
    challenge_id: str
    status: ConfirmationStatus
    decision: str
    resolved_at: datetime
    verification_hash: str
    message: str
