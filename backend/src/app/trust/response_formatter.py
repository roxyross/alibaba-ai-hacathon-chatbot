"""Phase O: Trust-Aware Response State Formatter for Roxy AI.

Strict Rule: ROXY MUST NEVER CLAIM SUCCESS WITHOUT VERIFIED SUCCESS.
Equating 'requested' or 'executed' with 'successful' is strictly forbidden.
"""

from __future__ import annotations

from typing import Any


class TrustResponseState:
    VERIFIED = "verified"
    QUEUED = "queued"
    PERMISSION_REQUIRED = "permission_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    FAILED = "failed"
    PARTIAL = "partial"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


def format_trust_aware_response(
    action_name: str,
    state: str,
    target: str | None = None,
    service_name: str | None = None,
    failure_reason: str | None = None,
    partial_details: str | None = None,
    queue_reason: str | None = None,
    verification_proof: dict[str, Any] | None = None,
) -> str:
    """Generate state-truthful human-readable agent responses.
    
    Guarantees:
    - Never generates 'Done' or claims completion unless state == VERIFIED.
    - Transparently discloses queued, interrupted, permission-blocked, or partial states.
    """
    st = (state or "").lower().strip()
    target_str = f" for '{target}'" if target else ""

    if st in ("verified", "succeeded", "completed"):
        if verification_proof and verification_proof.get("proof_hash"):
            return f"Done — {action_name}{target_str} was completed and verified successfully [proof: {verification_proof['proof_hash'][:8]}]."
        return f"Done — {action_name}{target_str} was completed and verified successfully."

    elif st in ("queued", "offline_queued"):
        svc = service_name or "the remote service"
        reason = queue_reason or f"{svc} is temporarily unavailable"
        return f"I've queued {action_name}{target_str} because {reason}."

    elif st in ("permission_required", "permission_denied", "needs_permission"):
        tgt = target or service_name or "this capability"
        return f"I need your permission to access {tgt} before I can {action_name}."

    elif st in ("confirmation_required", "needs_confirmation"):
        return f"Please confirm {action_name}{target_str} before I proceed with execution."

    elif st in ("failed", "error"):
        reason = failure_reason or f"the request could not be fulfilled by {service_name or 'the provider'}"
        return f"I couldn't complete {action_name}{target_str} because {reason}."

    elif st in ("partial", "partially_completed"):
        summary = partial_details or "some steps succeeded while subsequent steps encountered an error"
        return f"The task was partially completed. {summary}."

    elif st in ("running", "executing"):
        return f"Currently executing {action_name}{target_str}..."

    elif st in ("interrupted", "paused"):
        return f"{action_name}{target_str} was interrupted. State checkpoint preserved for recovery."

    else:
        return f"I can't verify whether {action_name}{target_str} completed successfully."
