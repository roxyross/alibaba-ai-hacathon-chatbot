"""Phase 24: Adversarial Security Testing & Hardening Module.

Provides comprehensive fuzzing, injection defense (Prompt, Command, SQL, Path, SSRF),
and privilege escalation / IDOR prevention under the Zero Simulation Doctrine.
"""

from __future__ import annotations

from app.adversarial_security.engine import AdversarialSecurityEngine
from app.adversarial_security.fuzzer import AdversarialFuzzer
from app.adversarial_security.injection_defense import InjectionDefenseEngine
from app.adversarial_security.privilege_escalation import PrivilegeEscalationGuard
from app.adversarial_security.schemas import (
    AdversarialAuditReport,
    DefenseAction,
    FuzzMutationType,
    FuzzReport,
    SecurityThreatType,
    UserRole,
)

__all__ = [
    "AdversarialSecurityEngine",
    "AdversarialFuzzer",
    "InjectionDefenseEngine",
    "PrivilegeEscalationGuard",
    "SecurityThreatType",
    "DefenseAction",
    "UserRole",
    "FuzzMutationType",
    "FuzzReport",
    "AdversarialAuditReport",
]
