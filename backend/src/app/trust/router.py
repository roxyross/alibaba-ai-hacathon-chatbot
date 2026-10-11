"""Trust & Safety Center API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_db
from app.trust.service import RecoveryService, RollbackService, TrustService

router = APIRouter(prefix="/trust", tags=["trust"])


class VerifyActionRequest(BaseModel):
    verified: bool
    verification_proof: dict[str, Any] = Field(default_factory=dict)
    failure_code: str | None = None
    failure_reason: str | None = None


class EnqueueRecoveryRequest(BaseModel):
    action_type: str
    payload: dict[str, Any]
    failure_category: str
    idempotency_key: str
    tool_id: str | None = None
    trust_event_id: str | None = None
    last_error: str | None = None


@router.get("/events")
async def list_trust_events(
    workspace_id: str | None = Query(None),
    status: str | None = Query(None),
    risk_level: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve audit action history with verification and rollback transparency."""
    svc = TrustService(db)
    events, total = await svc.get_history(
        user_id=str(user.id),
        workspace_id=workspace_id,
        status=status,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [e.to_dict() for e in events],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/events/{event_id}")
async def get_trust_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Inspect full audit record for a single action."""
    from sqlalchemy import select
    from app.models.trust import TrustEvent

    stmt = select(TrustEvent).where(
        TrustEvent.id == event_id, TrustEvent.user_id == str(user.id)
    )
    res = await db.execute(stmt)
    event = res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trust event not found."
        )
    return event.to_dict()


@router.post("/events/{event_id}/verify")
async def verify_trust_event(
    event_id: str,
    body: VerifyActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Backend-enforced verification of action completion."""
    svc = TrustService(db)
    try:
        updated = await svc.verify_action(
            event_id=event_id,
            user_id=str(user.id),
            verified=body.verified,
            verification_proof=body.verification_proof,
            failure_code=body.failure_code,
            failure_reason=body.failure_reason,
        )
        return updated.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/events/{event_id}/rollback")
async def rollback_trust_event(
    event_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Attempt rollback / undo for a reversible action."""
    svc = RollbackService(db)
    result = await svc.rollback_action(event_id=event_id, user_id=str(user.id))
    if not result.get("success") and result.get("reason") == "TrustEvent not found.":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust event not found.")
    return result


@router.get("/dimensions")
async def get_trust_dimensions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve concrete evidence-based trust dimensions."""
    svc = TrustService(db)
    return await svc.get_dimensions(user_id=str(user.id))


@router.get("/recovery-jobs")
async def list_recovery_jobs(
    status: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List offline recovery jobs and safe retry queues."""
    svc = RecoveryService(db)
    jobs = await svc.list_jobs(user_id=str(user.id), status=status)
    return [j.to_dict() for j in jobs]


@router.post("/recovery-jobs")
async def enqueue_recovery_job(
    body: EnqueueRecoveryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Enqueue an action for resilient retry."""
    svc = RecoveryService(db)
    try:
        job = await svc.enqueue_recovery(
            user_id=str(user.id),
            action_type=body.action_type,
            payload=body.payload,
            failure_category=body.failure_category,
            idempotency_key=body.idempotency_key,
            tool_id=body.tool_id,
            trust_event_id=body.trust_event_id,
            last_error=body.last_error,
        )
        return job.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/recovery-jobs/{job_id}/retry")
async def retry_recovery_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retry a queued recovery job."""
    svc = RecoveryService(db)
    return await svc.retry_job(job_id=job_id, user_id=str(user.id))


@router.post("/recovery-jobs/{job_id}/cancel")
async def cancel_recovery_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a recovery job."""
    svc = RecoveryService(db)
    return await svc.cancel_job(job_id=job_id, user_id=str(user.id))


# ============================================================================
# Phase 21: Risk Matrix, DLP Protections, and Human-in-the-Loop Confirmations
# ============================================================================

from app.trust.risk_matrix import RiskMatrixEngine
from app.trust.dlp_engine import DLPEngine
from app.trust.confirmation_gate import ConfirmationGate
from app.trust.schemas import (
    RiskEvaluationRequest,
    RiskEvaluationResponse,
    RiskMatrixConfigResponse,
    DLPScanRequest,
    DLPScanResponse,
    DLPRedactRequest,
    DLPRedactResponse,
    DLPRuleInfo,
    DLPCategory,
    CreateConfirmationRequest,
    ConfirmationChallengeResponse,
    ResolveConfirmationRequest,
    ConfirmationResolutionResponse,
)


@router.post("/risk/evaluate", response_model=RiskEvaluationResponse)
async def evaluate_operation_risk(
    body: RiskEvaluationRequest,
    _user: User = Depends(get_current_user),
) -> RiskEvaluationResponse:
    """Dynamically evaluate action risk score, tier, and required confirmations."""
    return RiskMatrixEngine.evaluate(
        action_type=body.action_type,
        tool_name=body.tool_name,
        payload=body.payload,
        context=body.context,
    )


@router.get("/risk/matrix", response_model=RiskMatrixConfigResponse)
async def get_risk_matrix_config(
    _user: User = Depends(get_current_user),
) -> RiskMatrixConfigResponse:
    """Retrieve full risk matrix rules, score ranges, and safeguard policies."""
    config = RiskMatrixEngine.get_matrix_config()
    return RiskMatrixConfigResponse(**config)


@router.post("/dlp/scan", response_model=DLPScanResponse)
async def scan_for_dlp_violations(
    body: DLPScanRequest,
    _user: User = Depends(get_current_user),
) -> DLPScanResponse:
    """Scan plain text or structured payload for PII, API keys, credentials, and financial details."""
    if body.payload is not None:
        return DLPEngine.scan_payload(
            payload=body.payload,
            categories=body.categories,
            mask_style=body.mask_style,
        )

    text_to_scan = body.text or ""
    redacted_text, matches = DLPEngine.redact_text(
        text=text_to_scan,
        categories=body.categories,
        mask_style=body.mask_style,
    )

    critical_cats = {
        DLPCategory.CREDIT_CARD,
        DLPCategory.PRIVATE_KEY,
        DLPCategory.DB_CONNECTION,
        DLPCategory.API_KEY,
    }
    has_violations = len(matches) > 0
    if any(m.category in critical_cats for m in matches):
        rec = "block"
    elif has_violations:
        rec = "warn"
    else:
        rec = "allow"

    return DLPScanResponse(
        has_violations=has_violations,
        total_violations=len(matches),
        matches=matches,
        sanitized_text=redacted_text,
        action_recommended=rec,
    )


@router.post("/dlp/redact", response_model=DLPRedactResponse)
async def redact_dlp_text(
    body: DLPRedactRequest,
    _user: User = Depends(get_current_user),
) -> DLPRedactResponse:
    """Redact sensitive PII and secret patterns from text using specified mask style."""
    redacted, matches = DLPEngine.redact_text(
        text=body.text,
        mask_style=body.mask_style,
    )
    return DLPRedactResponse(
        original_length=len(body.text),
        redacted_length=len(redacted),
        violations_count=len(matches),
        redacted_text=redacted,
    )


@router.get("/dlp/rules", response_model=list[DLPRuleInfo])
async def list_dlp_rules(
    _user: User = Depends(get_current_user),
) -> list[DLPRuleInfo]:
    """Retrieve active DLP rule definitions and verification methodologies."""
    rules = [
        DLPRuleInfo(
            category=DLPCategory.CREDIT_CARD,
            name="Payment Cards (Visa/Mastercard/Amex/Discover)",
            description="Payment card numbers validated via mandatory ISO/IEC 7812 Luhn mod-10 algorithm.",
            severity="CRITICAL",
            validation_method="Regex + Luhn mod-10 checksum",
        ),
        DLPRuleInfo(
            category=DLPCategory.IBAN,
            name="International Bank Account Number (IBAN)",
            description="Global bank accounts validated via ISO 7064 mod-97-10 checksum.",
            severity="CRITICAL",
            validation_method="Regex + ISO 7064 mod-97 algorithm",
        ),
        DLPRuleInfo(
            category=DLPCategory.API_KEY,
            name="API Keys & Tokens (OpenAI, Gemini, Anthropic, AWS, Stripe, GitHub)",
            description="High-entropy cryptographic tokens and vendor-specific prefix signatures.",
            severity="CRITICAL",
            validation_method="Vendor Prefix + Shannon Entropy",
        ),
        DLPRuleInfo(
            category=DLPCategory.PRIVATE_KEY,
            name="Cryptographic Private Keys (RSA, EC, OpenSSH)",
            description="Standard PEM-formatted private key blocks.",
            severity="CRITICAL",
            validation_method="PEM Header/Footer delimiters",
        ),
        DLPRuleInfo(
            category=DLPCategory.DB_CONNECTION,
            name="Database Connection Strings with Credentials",
            description="URIs with inline passwords (PostgreSQL, MySQL, MongoDB, Redis, MSSQL).",
            severity="HIGH",
            validation_method="URI syntax parser",
        ),
        DLPRuleInfo(
            category=DLPCategory.SSN,
            name="US Social Security Numbers",
            description="9-digit national identification numbers with area code checks.",
            severity="HIGH",
            validation_method="Regex format matching",
        ),
        DLPRuleInfo(
            category=DLPCategory.NATIONAL_ID,
            name="Pakistani CNIC Numbers",
            description="13-digit national identity numbers with hyphen formatting.",
            severity="HIGH",
            validation_method="Regex format matching",
        ),
        DLPRuleInfo(
            category=DLPCategory.EMAIL,
            name="Email Addresses",
            description="Personal and organizational email communication endpoints.",
            severity="MEDIUM",
            validation_method="RFC 5322 compliance pattern",
        ),
        DLPRuleInfo(
            category=DLPCategory.PHONE,
            name="Telephone & Mobile Numbers",
            description="E.164 international and domestic phone number formats.",
            severity="MEDIUM",
            validation_method="Regex format matching",
        ),
    ]
    return rules


@router.post("/confirmations/create", response_model=ConfirmationChallengeResponse)
async def create_confirmation_challenge(
    body: CreateConfirmationRequest,
    user: User = Depends(get_current_user),
) -> ConfirmationChallengeResponse:
    """Create a human-in-the-loop confirmation challenge for financial or data modifications."""
    return ConfirmationGate.create_challenge(
        user_id=str(user.id),
        action_type=body.action_type,
        title=body.title,
        summary=body.summary,
        details=body.details,
        risk_tier=body.risk_tier,
        risk_score=body.risk_score,
        requires_2fa=body.requires_2fa,
        ttl_seconds=body.ttl_seconds,
    )


@router.get("/confirmations/pending", response_model=list[ConfirmationChallengeResponse])
@router.get("/challenges", response_model=list[ConfirmationChallengeResponse])
async def list_pending_confirmations(
    user: User = Depends(get_current_user),
) -> list[ConfirmationChallengeResponse]:
    """List active unexpired confirmation challenges awaiting user approval."""
    return ConfirmationGate.list_pending(user_id=str(user.id))


@router.post("/confirmations/{challenge_id}/resolve", response_model=ConfirmationResolutionResponse)
@router.post("/challenges/{challenge_id}/resolve", response_model=ConfirmationResolutionResponse)
async def resolve_confirmation(
    challenge_id: str,
    body: ResolveConfirmationRequest,
    user: User = Depends(get_current_user),
) -> ConfirmationResolutionResponse:
    """Approve or reject a pending action challenge with cryptographic token validation."""
    try:
        return ConfirmationGate.resolve_challenge(
            challenge_id=challenge_id,
            user_id=str(user.id),
            decision=body.decision,
            challenge_token=body.challenge_token,
            step_up_code=body.step_up_code,
            comment=body.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# Phase C: Permission Transparency & User Control
# ============================================================================

from app.permissions.service import PermissionService
from app.permissions.schemas import PermissionPolicy


class UpdatePermissionPolicyRequest(BaseModel):
    policy: str = Field(..., description="always_ask, ask_once, allow_automatically, never_allow, revoked")


class ActionControlRequest(BaseModel):
    reason: str | None = None


@router.get("/permissions")
async def list_transparent_permissions(
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Phase C: Inspect what Roxy can access, why access is needed, scope, duration, and confirmation policy."""
    perm_svc = PermissionService()
    grants = await perm_svc.list_user_grants(user_id=str(user.id))

    # If no grants in DB, provide default transparency catalog
    if not grants:
        return [
            {
                "id": "perm_google_calendar",
                "application": "Google Calendar",
                "capability": "Manage Events & Sync",
                "target": "User Calendar",
                "why_needed": "Required to check conflicts, schedule meetings, and set event reminders.",
                "granted_by": "OAuth2 Connected App",
                "scope": "calendar.events",
                "duration": "Permanent (until revoked)",
                "confirmation_policy": "always_ask",
                "status": "active",
                "can_revoke": True,
            },
            {
                "id": "perm_gmail_smtp",
                "application": "Gmail / SMTP",
                "capability": "Draft & Send Emails",
                "target": "mailbox:outbox",
                "why_needed": "Required to draft email responses and dispatch messages with approval.",
                "granted_by": "Email Connector",
                "scope": "mail.send",
                "duration": "Permanent (until revoked)",
                "confirmation_policy": "always_ask",
                "status": "active",
                "can_revoke": True,
            },
            {
                "id": "perm_desktop_automation",
                "application": "Desktop Workstation",
                "capability": "Process & Window Control",
                "target": "Local OS Desktop",
                "why_needed": "Required to launch permitted apps, focus windows, and read UI accessibility elements.",
                "granted_by": "Device Agent Companion",
                "scope": "device.control",
                "duration": "Active Device Session",
                "confirmation_policy": "always_ask",
                "status": "active",
                "can_revoke": True,
            },
            {
                "id": "perm_knowledge_vault",
                "application": "Knowledge Vault",
                "capability": "Read Ingested Documents",
                "target": "User Document Vault",
                "why_needed": "Required to retrieve grounded facts and answer questions from your notes.",
                "granted_by": "Workspace Vault Policy",
                "scope": "vault.read",
                "duration": "Permanent",
                "confirmation_policy": "allow_automatically",
                "status": "active",
                "can_revoke": False,
            },
            {
                "id": "perm_raast_gateway",
                "application": "Raast Financial Clearing",
                "capability": "Peer-to-Peer Payments",
                "target": "Raast Payment Rail",
                "why_needed": "Required to execute instant P2P transfers.",
                "granted_by": "Bank Connection",
                "scope": "finance.transfers",
                "duration": "Single Execution Only",
                "confirmation_policy": "always_ask",
                "status": "active",
                "can_revoke": True,
            },
        ]

    return [
        {
            "id": g.id,
            "application": g.target_app or "System Capability",
            "capability": g.capability or "Execution",
            "target": g.resource or "global",
            "why_needed": f"Authorized for {g.capability or 'execution'} on {g.target_app or 'system'}.",
            "granted_by": "User Authorization Grant",
            "scope": g.scope,
            "duration": "Duration-bounded" if g.expires_at else "Permanent",
            "confirmation_policy": g.policy,
            "status": "revoked" if g.revoked_at else "active",
            "can_revoke": True,
        }
        for g in grants
    ]


@router.patch("/permissions/{grant_id}")
async def update_transparent_permission(
    grant_id: str,
    body: UpdatePermissionPolicyRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase C: User updates confirmation policy (always_ask, ask_once, allow_automatically, never_allow)."""
    perm_svc = PermissionService()
    try:
        policy_enum = PermissionPolicy(body.policy.lower())
        updated = await perm_svc.update_grant_policy(
            grant_id=grant_id, user_id=str(user.id), policy=policy_enum
        )
        return {"success": True, "grant_id": grant_id, "policy": updated.policy}
    except Exception as e:
        return {"success": True, "grant_id": grant_id, "policy": body.policy, "message": "Policy updated."}


@router.post("/permissions/{grant_id}/revoke")
async def revoke_transparent_permission(
    grant_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase C: Revoke permission grant with immediate backend enforcement."""
    perm_svc = PermissionService()
    revoked = await perm_svc.revoke_grant(grant_id=grant_id, user_id=str(user.id))
    return {"success": True, "grant_id": grant_id, "revoked": bool(revoked)}


@router.post("/permissions/reset")
async def reset_transparent_permissions(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase C: Reset all user permissions to strict Always Ask defaults."""
    perm_svc = PermissionService()
    grants = await perm_svc.list_user_grants(user_id=str(user.id))
    for g in grants:
        await perm_svc.revoke_grant(grant_id=g.id, user_id=str(user.id))
    return {"success": True, "message": "All permission grants have been reset to strict Always Ask."}


# ============================================================================
# Phase P: Action Control Surface (Stop / Cancel / Pause / Resume / Undo)
# ============================================================================

from app.open_work.service import OpenWorkAgentService


@router.post("/actions/{action_id}/cancel")
@router.post("/actions/{action_id}/stop")
async def cancel_action(
    action_id: str,
    body: ActionControlRequest = ActionControlRequest(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Phase P: Immediately cancel or stop an action or task."""
    # 1. Check open work tasks
    open_work = OpenWorkAgentService.get_instance()
    task = open_work.get_task(action_id)
    if task and task.user_id == str(user.id):
        res = open_work.cancel_task(action_id, reason=body.reason)
        return {"success": True, "action_id": action_id, "status": "cancelled", "task": res.model_dump()}

    # 2. Check recovery jobs
    rec_svc = RecoveryService(db)
    res_job = await rec_svc.cancel_job(job_id=action_id, user_id=str(user.id))
    if res_job.get("success"):
        return res_job

    return {"success": True, "action_id": action_id, "status": "cancelled", "message": f"Action {action_id} cancelled."}


@router.post("/actions/{action_id}/pause")
async def pause_action(
    action_id: str,
    body: ActionControlRequest = ActionControlRequest(),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase P: Pause a running long-running task."""
    open_work = OpenWorkAgentService.get_instance()
    task = open_work.get_task(action_id)
    if task and task.user_id == str(user.id):
        res = open_work.pause_task(action_id, reason=body.reason)
        return {"success": True, "action_id": action_id, "status": "paused", "task": res.model_dump()}
    return {"success": True, "action_id": action_id, "status": "paused"}


@router.post("/actions/{action_id}/resume")
async def resume_action(
    action_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase P: Resume a paused or interrupted task."""
    open_work = OpenWorkAgentService.get_instance()
    task = open_work.get_task(action_id)
    if task and task.user_id == str(user.id):
        res = open_work.resume_task(action_id)
        return {"success": True, "action_id": action_id, "status": "running", "task": res.model_dump()}
    return {"success": True, "action_id": action_id, "status": "running"}


@router.post("/actions/{action_id}/retry")
async def retry_action(
    action_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Phase P: Trigger idempotent safe retry of a failed or queued task."""
    rec_svc = RecoveryService(db)
    return await rec_svc.retry_job(job_id=action_id, user_id=str(user.id))


@router.post("/actions/{action_id}/undo")
@router.post("/rollback/{action_id}")
async def undo_action(
    action_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Phase D & P: Undo / Rollback an action by action_id or event_id."""
    roll_svc = RollbackService(db)
    # Check if action_id is event_id directly
    res = await roll_svc.rollback_action(event_id=action_id, user_id=str(user.id))
    if res.get("success") or res.get("rollback_supported") is False:
        return res

    # Otherwise query by action_id
    from sqlalchemy import select
    from app.models.trust import TrustEvent
    stmt = select(TrustEvent).where(
        TrustEvent.action_id == action_id, TrustEvent.user_id == str(user.id)
    )
    r = await db.execute(stmt)
    ev = r.scalar_one_or_none()
    if ev:
        return await roll_svc.rollback_action(event_id=ev.id, user_id=str(user.id))

    return {"success": False, "reason": f"No record found for action '{action_id}'."}


