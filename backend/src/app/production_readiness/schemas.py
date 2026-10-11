"""Pydantic schemas and models for Phase 25: Production Readiness Audit."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class GateCheckStatus(str, Enum):
    """Evaluation status for production gate checklist criteria."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class ReadinessGateCheck(BaseModel):
    """An individual evaluation checkpoint within the 7-Point Exit Gate."""
    gate_id: str = Field(description="Unique identifier e.g. GATE_1_FOUNDATIONS")
    title: str
    category: str
    status: GateCheckStatus
    score: int = Field(ge=0, le=100, description="Readiness score out of 100")
    details: str
    verification_proof: str


class ZeroMockAuditResult(BaseModel):
    """Static AST and lexical scan results for Zero-Mock compliance."""
    files_scanned: int
    violations_found: int
    prohibited_patterns_checked: list[str] = Field(default_factory=list)
    mock_occurrences: list[dict[str, Any]] = Field(default_factory=list)
    is_zero_mock_compliant: bool
    summary: str


class DeadCodeAuditResult(BaseModel):
    """AST-level dead code, unreachable block, and syntax audit results."""
    modules_analyzed: int
    unreachable_blocks_found: int
    syntax_errors_found: int
    is_clean: bool
    summary: str


class PackagingAuditResult(BaseModel):
    """Verification of deployment artifacts, containers, and bundles."""
    dockerfile_backend: bool
    dockerfile_frontend: bool
    docker_compose: bool
    production_env_spec: bool
    frontend_bundle_built: bool
    is_packaged: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ProductionExitCertificate(BaseModel):
    """Cryptographically signed formal exit gate certificate."""
    certificate_id: str
    issued_at: str
    overall_verdict: str = Field(description="'PRODUCTION_CERTIFIED', 'PROVISIONAL', or 'REJECTED'")
    checklist_scores: dict[str, int] = Field(default_factory=dict)
    total_score: int = Field(description="Combined score out of 700")
    zero_mock_certified: bool
    cryptographic_seal_hash: str
    ledger_block_id: str
    issuer: str = "ROXY Master Security & Reliability Gatekeeper"
    platform_version: str = "2.0.0-prod"


class ProductionReadinessReport(BaseModel):
    """Aggregated production readiness audit report."""
    audit_id: str
    timestamp: str
    overall_verdict: str
    zero_mock_audit: ZeroMockAuditResult
    dead_code_audit: DeadCodeAuditResult
    packaging_audit: PackagingAuditResult
    gate_checks: list[ReadinessGateCheck] = Field(default_factory=list)
    certificate: ProductionExitCertificate
    cryptographic_seal_hash: str
    ledger_block_id: str
