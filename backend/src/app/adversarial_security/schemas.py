"""Pydantic schemas and enums for Phase 24: Adversarial Security Testing."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SecurityThreatType(str, Enum):
    """Classification of adversarial attack vectors."""
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    COMMAND_INJECTION = "command_injection"
    SQL_INJECTION = "sql_injection"
    PATH_TRAVERSAL = "path_traversal"
    SSRF = "ssrf"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    IDOR_VIOLATION = "idor_violation"
    TOKEN_FORGERY = "token_forgery"
    MALFORMED_INPUT = "malformed_input"


class DefenseAction(str, Enum):
    """Enforced action resulting from security evaluation."""
    ALLOW = "allow"
    SANITIZE = "sanitize"
    WARN = "warn"
    BLOCK = "block"


class UserRole(str, Enum):
    """Role-based access control tiers."""
    GUEST = "guest"
    VIEWER = "viewer"
    MEMBER = "member"
    OPERATOR = "operator"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class FuzzMutationType(str, Enum):
    """Systematic mutation strategies for robustness fuzzing."""
    BOUNDARY_INTEGER = "boundary_integer"
    DEEP_JSON_NESTING = "deep_json_nesting"
    OVERSIZED_STRING = "oversized_string"
    NULL_BYTE_INJECTION = "null_byte_injection"
    UNICODE_HOMOGLYPH = "unicode_homoglyph"
    FORMAT_STRING = "format_string"
    UNCLOSED_DELIMITERS = "unclosed_delimiters"
    RECURSIVE_PAYLOAD = "recursive_payload"


class FuzzCaseResult(BaseModel):
    """Result of a single fuzz test case."""
    mutation_type: str
    description: str
    status: str = Field(description="'passed', 'failed', or 'error'")
    gracefully_handled: bool
    status_code: int = 200
    error_detail: str | None = None
    duration_ms: float = 0.0


class FuzzReport(BaseModel):
    """Aggregated report of fuzz testing mutations against a target schema."""
    target_name: str
    total_mutations: int
    passed_mutations: int
    failed_mutations: int
    is_resilient: bool
    cases: list[FuzzCaseResult] = Field(default_factory=list)


class PromptInjectionScanRequest(BaseModel):
    """Request to scan a prompt or document for injection vectors."""
    prompt: str = Field(..., min_length=1)
    context_source: str = Field(default="user_input", description="user_input, document, email, or tool_output")


class PromptInjectionScanResult(BaseModel):
    """Result of prompt injection analysis and sanitization."""
    prompt: str
    is_injection: bool
    threat_type: SecurityThreatType | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    detected_patterns: list[str] = Field(default_factory=list)
    defense_action: DefenseAction
    sanitized_prompt: str
    reason: str


class CommandSafetyRequest(BaseModel):
    """Request to validate a shell command against command injection."""
    command: str = Field(..., min_length=1)


class CommandSafetyResult(BaseModel):
    """Result of shell command security validation."""
    command: str
    is_safe: bool
    risk_score: float = Field(ge=0.0, le=1.0)
    dangerous_metachars: list[str] = Field(default_factory=list)
    tokenized_args: list[str] = Field(default_factory=list)
    defense_action: DefenseAction
    rejection_reason: str | None = None


class SQLSafetyRequest(BaseModel):
    """Request to inspect SQL query against injection attacks."""
    query: str = Field(..., min_length=1)
    parameters: dict[str, Any] | None = None


class SQLSafetyResult(BaseModel):
    """Result of SQL injection vulnerability detection."""
    query: str
    is_safe: bool
    detected_threats: list[str] = Field(default_factory=list)
    is_parameterized: bool = True
    defense_action: DefenseAction
    rejection_reason: str | None = None


class PathSafetyRequest(BaseModel):
    """Request to validate a file path against directory traversal."""
    path: str = Field(..., min_length=1)
    base_directory: str = Field(default="/workspace/sandbox")


class PathSafetyResult(BaseModel):
    """Result of directory traversal verification."""
    original_path: str
    base_directory: str
    resolved_path: str | None = None
    is_safe: bool
    is_contained: bool
    defense_action: DefenseAction
    rejection_reason: str | None = None


class SSRFSafetyRequest(BaseModel):
    """Request to validate a destination URL against SSRF."""
    url: str = Field(..., min_length=1)


class SSRFSafetyResult(BaseModel):
    """Result of SSRF and cloud metadata access validation."""
    url: str
    is_safe: bool
    scheme: str
    hostname: str
    resolved_ip: str | None = None
    is_private_or_loopback: bool
    is_cloud_metadata: bool
    defense_action: DefenseAction
    rejection_reason: str | None = None


class RBACEvaluationRequest(BaseModel):
    """Request to evaluate RBAC and tenant IDOR boundary."""
    user_id: str
    user_role: str = "member"
    resource_id: str
    resource_owner_id: str
    required_role: str = "member"
    action: str = "read"
    is_public: bool = False


class RBACEvaluationResult(BaseModel):
    """Result of privilege and multi-tenant access evaluation."""
    user_id: str
    resource_id: str
    is_permitted: bool
    violation_type: str | None = None
    defense_action: DefenseAction
    reason: str


class AdversarialAuditReport(BaseModel):
    """Comprehensive adversarial testing audit report."""
    __test__ = False  # Prevent pytest collection warning

    run_id: str
    timestamp: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    overall_posture: str = Field(description="'hardened', 'degraded', or 'vulnerable'")
    fuzzing_summary: dict[str, Any]
    prompt_injection_summary: dict[str, Any]
    command_injection_summary: dict[str, Any]
    sql_injection_summary: dict[str, Any]
    path_traversal_summary: dict[str, Any]
    ssrf_summary: dict[str, Any]
    rbac_privilege_summary: dict[str, Any]
    audit_block_id: str
    cryptographic_audit_hash: str
