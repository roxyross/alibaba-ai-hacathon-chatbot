"""Business service for Security, Privacy & Action Audit Studio (Phase 19).

Fulfills .claude/agents/security-privacy.md, .claude/agents/security-privacy-auditor.md,
specs/feature/audit-log.md, and Constitution §3.5 & §3.6.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import structlog

from app.audit.repository import AuditRepository
from app.audit.schemas import (
    ApprovalTier,
    AuditExportResponse,
    AuditLogCreate,
    AuditLogListResponse,
    AuditLogRead,
    AuditStatsResponse,
    RiskCheckRequest,
    RiskCheckResponse,
)

log = structlog.get_logger()

# Destructive action patterns that trigger a BLOCK verdict
_DESTRUCTIVE_COMMAND_PATTERNS = [
    r"\b(drop\s+(database|table|schema))\b",
    r"\b(truncate\s+table)\b",
    r"\b(rm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--recursive\s+--force))\b",
    r"\b(format\s+[c-z]:)\b",
    r"\b(mkfs(\.[a-z0-9]+)?)\b",
    r"\b(dd\s+if=.*of=)\b",
    r"\b(:(){ :\|:& };:)\b",  # fork bomb
]

# Sensitive credentials / exfiltration keywords
_CREDENTIAL_PATTERNS = [
    r"\b(id_rsa|id_ed25519|\.ssh/authorized_keys)\b",
    r"\b(api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*['\"][^'\"]+['\"]",
]

# Consequential external actions that trigger a CAUTION verdict (T2)
_CONSEQUENTIAL_ACTIONS = {
    "send_email",
    "email_send",
    "submit_form",
    "execute_terminal",
    "terminal_run",
    "delete_file",
    "write_file",
    "schedule_job",
    "make_payment",
    "post_publicly",
}


class AuditService:
    """Service providing append-only audit logging and pre-execution risk reviews."""

    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    async def log_action(
        self,
        user_id: str,
        data: AuditLogCreate,
        trace_id: str | None = None,
    ) -> AuditLogRead:
        """Record an immutable action entry in the audit log."""
        record = await self.repository.record_event(
            user_id=user_id, data=data, trace_id=trace_id
        )
        return AuditLogRead(**record)

    async def get_action(self, user_id: str, event_id: str) -> AuditLogRead | None:
        """Fetch a single audit log entry, returning None if not found or unowned."""
        record = await self.repository.get_event(user_id=user_id, event_id=event_id)
        if not record:
            return None
        return AuditLogRead(**record)

    async def list_actions(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 50,
        agent_slug: str | None = None,
        status_code: str | None = None,
        approval_tier: str | None = None,
        search: str | None = None,
    ) -> AuditLogListResponse:
        """List paginated audit events with filters."""
        skip = (page - 1) * limit
        items, total = await self.repository.list_events(
            user_id=user_id,
            skip=skip,
            limit=limit,
            agent_slug=agent_slug,
            status_code=status_code,
            approval_tier=approval_tier,
            search=search,
        )
        return AuditLogListResponse(
            items=[AuditLogRead(**item) for item in items],
            total=total,
            page=page,
            limit=limit,
        )

    async def get_today_actions(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[AuditLogRead]:
        """Fetch 'What did Jarvis do today' user-facing timeline feed."""
        records = await self.repository.list_today_events(user_id=user_id, limit=limit)
        return [AuditLogRead(**r) for r in records]

    async def get_stats(self, user_id: str) -> AuditStatsResponse:
        """Fetch aggregated security and execution metrics."""
        stats = await self.repository.get_stats(user_id=user_id)
        return AuditStatsResponse(**stats)

    async def export_audit_bundle(self, user_id: str) -> AuditExportResponse:
        """Produce portable GDPR Article 20 JSON bundle of all user audit records."""
        records = await self.repository.export_user_logs(user_id=user_id)
        events = [AuditLogRead(**r) for r in records]
        return AuditExportResponse(
            user_id=user_id,
            exported_at=datetime.now(UTC).isoformat(),
            total_records=len(events),
            retention_policy="1-Year Immutable Append-Only Log (§10.12)",
            events=events,
        )

    def assess_action_risk(self, request: RiskCheckRequest) -> RiskCheckResponse:
        """Perform pre-execution risk review per .claude/agents/security-privacy.md.

        Categorizes action against blast radius, irreversibility, and credentials.
        Returns:
            - 'block' (T3): high-stakes or irreversible destructive actions.
            - 'caution' (T2): side-effects requiring user confirmation prompt.
            - 'clear' (T1): read-only, non-destructive, safe actions.
        """
        action = request.action_type.strip().lower()
        combined_text = f"{action} {request.target or ''} {str(request.params)} {request.user_prompt or ''}".lower()

        # 1. Check for destructive commands or credentials exfiltration -> BLOCK
        for pattern in _DESTRUCTIVE_COMMAND_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return RiskCheckResponse(
                    action=request.action_type,
                    risk_verdict="block",
                    approval_tier="T3",
                    reason="Irreversible destructive operation detected that would compromise persistent state or infrastructure.",
                    warning_to_user="This action is classified as HIGH-RISK and BLOCKED. It would destroy critical persistent data.",
                    narrower_alternative="Consider taking a backup or executing a scoped dry-run inspection instead.",
                    blast_radius="critical_system",
                    is_reversible=False,
                    blocking=True,
                )

        for cred_pattern in _CREDENTIAL_PATTERNS:
            if re.search(cred_pattern, combined_text, re.IGNORECASE):
                return RiskCheckResponse(
                    action=request.action_type,
                    risk_verdict="block",
                    approval_tier="T3",
                    reason="Potential private key or sensitive credential exposure detected in action parameters.",
                    warning_to_user="This action is BLOCKED to prevent credential leakage or unauthorized secret exposure.",
                    narrower_alternative="Use environment variables or a secure key management vault.",
                    blast_radius="credentials_exposure",
                    is_reversible=False,
                    blocking=True,
                )

        # 2. Check for consequential actions requiring user confirmation -> CAUTION (T2)
        if any(c in action for c in ["email", "mail", "send", "submit", "delete", "write", "payment", "money"]):
            # Format custom warning
            target_str = f" to '{request.target}'" if request.target else ""
            warning = f"ROXY is preparing to {request.action_type}{target_str}. Please review before confirming."
            alternative = None

            if "payment" in action or "money" in action:
                tier: ApprovalTier = "T3"
                blast = "financial"
                warning = "High-stakes financial action: Requires verification before dispatch."
            elif "delete" in action:
                tier = "T2"
                blast = "local_storage"
                warning = "File or resource deletion: This will remove items from your storage."
                alternative = "Move item to soft-delete archive instead of permanent deletion."
            else:
                tier = "T2"
                blast = "external_network"

            return RiskCheckResponse(
                action=request.action_type,
                risk_verdict="caution",
                approval_tier=tier,
                reason="Action has side effects affecting external recipients, storage, or persistent resources.",
                warning_to_user=warning,
                narrower_alternative=alternative,
                blast_radius=blast,
                is_reversible=tier != "T3",
                blocking=False,
            )

        # 3. Safe read-only or internal actions -> CLEAR (T1)
        return RiskCheckResponse(
            action=request.action_type,
            risk_verdict="clear",
            approval_tier="T1",
            reason="Action is read-only, non-destructive, and within isolated user workspace boundaries.",
            warning_to_user="Safe to proceed automatically.",
            narrower_alternative=None,
            blast_radius="isolated",
            is_reversible=True,
            blocking=False,
        )
