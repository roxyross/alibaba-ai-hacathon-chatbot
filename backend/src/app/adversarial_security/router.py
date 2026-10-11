"""FastAPI REST Router for Phase 24: Adversarial Security Testing."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
import structlog

from app.adversarial_security.engine import AdversarialSecurityEngine
from app.adversarial_security.schemas import (
    AdversarialAuditReport,
    CommandSafetyRequest,
    CommandSafetyResult,
    FuzzReport,
    PathSafetyRequest,
    PathSafetyResult,
    PromptInjectionScanRequest,
    PromptInjectionScanResult,
    RBACEvaluationRequest,
    RBACEvaluationResult,
    SQLSafetyRequest,
    SQLSafetyResult,
    SSRFSafetyRequest,
    SSRFSafetyResult,
)
from app.auth.dependencies import get_current_user
from app.auth.models import User

log = structlog.get_logger()

router = APIRouter(prefix="/security", tags=["Adversarial Security"])


@router.post("/fuzz/test", response_model=FuzzReport)
async def run_fuzz_test(
    sample_input: str = "valid_payload",
    current_user: User = Depends(get_current_user),
) -> FuzzReport:
    """Run an automated fuzzing battery against payload validators."""
    engine = AdversarialSecurityEngine.get_instance()

    def default_validator(val: Any) -> bool:
        if isinstance(val, (int, float, str, dict, list)):
            return True
        raise ValueError(f"Invalid type: {type(val)}")

    return engine.fuzzer.fuzz_validator("api_payload_fuzzer", default_validator, base_value=sample_input)


@router.post("/injection/scan-prompt", response_model=PromptInjectionScanResult)
async def scan_prompt(
    request: PromptInjectionScanRequest,
    current_user: User = Depends(get_current_user),
) -> PromptInjectionScanResult:
    """Scan a prompt or document for adversarial injection and jailbreak vectors."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.scan_prompt(request.prompt)


@router.post("/injection/validate-command", response_model=CommandSafetyResult)
async def validate_command(
    request: CommandSafetyRequest,
    current_user: User = Depends(get_current_user),
) -> CommandSafetyResult:
    """Inspect shell command against metacharacter chaining and dangerous binaries."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.validate_command(request.command)


@router.post("/injection/validate-sql", response_model=SQLSafetyResult)
async def validate_sql(
    request: SQLSafetyRequest,
    current_user: User = Depends(get_current_user),
) -> SQLSafetyResult:
    """Inspect SQL query against tautologies, stacked statements, and union attacks."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.validate_sql(request.query, request.parameters)


@router.post("/injection/validate-path", response_model=PathSafetyResult)
async def validate_path(
    request: PathSafetyRequest,
    current_user: User = Depends(get_current_user),
) -> PathSafetyResult:
    """Validate that a target path does not escape its sandbox boundary."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.validate_path(request.path, request.base_directory)


@router.post("/injection/validate-url", response_model=SSRFSafetyResult)
async def validate_url_ssrf(
    request: SSRFSafetyRequest,
    current_user: User = Depends(get_current_user),
) -> SSRFSafetyResult:
    """Inspect outbound URL destination to prevent SSRF and cloud metadata access."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.validate_url_ssrf(request.url)


@router.post("/rbac/evaluate", response_model=RBACEvaluationResult)
async def evaluate_rbac_access(
    request: RBACEvaluationRequest,
    current_user: User = Depends(get_current_user),
) -> RBACEvaluationResult:
    """Evaluate an authorization request against vertical RBAC and horizontal IDOR boundaries."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.evaluate_access(
        user_id=request.user_id,
        user_role=request.user_role,
        resource_id=request.resource_id,
        resource_owner_id=request.resource_owner_id,
        required_role=request.required_role,
        action=request.action,
        is_public=request.is_public,
    )


@router.post("/audit/run", response_model=AdversarialAuditReport)
async def run_security_audit(
    current_user: User = Depends(get_current_user),
) -> AdversarialAuditReport:
    """Execute full automated adversarial security audit and commit cryptographic ledger block."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.run_comprehensive_audit()


@router.get("/audit/report", response_model=AdversarialAuditReport)
async def get_security_audit_report(
    current_user: User = Depends(get_current_user),
) -> AdversarialAuditReport:
    """Retrieve the latest adversarial security audit report with cryptographic proof."""
    engine = AdversarialSecurityEngine.get_instance()
    return engine.get_latest_report()
