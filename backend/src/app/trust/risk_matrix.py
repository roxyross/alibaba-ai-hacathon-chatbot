"""Risk Matrix Engine — Categorization, dynamic scoring, and human-in-the-loop safeguards."""

from __future__ import annotations

import re
from typing import Any
from app.trust.schemas import (
    ConfirmationType,
    OperationCategory,
    RiskEvaluationResponse,
    RiskTier,
)


class RiskMatrixEngine:
    """Evaluates operations and tool invocations against multi-dimensional risk thresholds."""

    DESTRUCTIVE_SQL_PATTERN = re.compile(
        r"\b(DROP\s+(TABLE|DATABASE|SCHEMA|VIEW)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\w+\s*(?:;|$)|ALTER\s+TABLE\s+\w+\s+DROP)\b",
        re.IGNORECASE,
    )
    DESTRUCTIVE_SHELL_PATTERN = re.compile(
        r"(\brm\s+-[rRfF]+\b|\bdel\s+/[fFsSqQ]+\b|\bformat\s+[a-zA-Z]:|\bdd\s+if=|\bmkfs\b|\bchmod\s+777\b|\bsudo\s+rm\b|\bkill\s+-9\s+1\b)",
        re.IGNORECASE,
    )
    SENSITIVE_PATHS = [
        "/etc/",
        "c:\\windows\\system32",
        "~/.ssh",
        "~/.aws",
        ".env",
        "id_rsa",
        "service_account.json",
    ]

    @classmethod
    def evaluate(
        cls,
        action_type: str,
        tool_name: str | None = None,
        payload: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskEvaluationResponse:
        """Dynamically evaluate the risk tier, score, and required confirmations for an action."""
        payload = payload or {}
        context = context or {}
        risk_factors: list[str] = []
        safeguards: list[str] = []

        action_lower = action_type.lower()
        tool_lower = (tool_name or "").lower()

        # 1. Financial Operations
        if (
            "financial" in action_lower
            or "payment" in action_lower
            or "transfer" in action_lower
            or "charge" in action_lower
            or "checkout" in action_lower
            or "wire" in action_lower
            or "crypto" in action_lower
            or "stripe" in tool_lower
        ):
            category = OperationCategory.FINANCIAL_TRANSACTION
            amount = float(payload.get("amount", payload.get("value", 0.0)))
            currency = str(payload.get("currency", "USD")).upper()
            recipient = str(payload.get("recipient", payload.get("to", "unknown")))

            if amount >= 1000.0 or currency in {"BTC", "ETH", "USDT"}:
                score = 95
                tier = RiskTier.CRITICAL
                confirmation_type = ConfirmationType.STEP_UP_2FA
                risk_factors.append(f"High-value financial transaction: {amount:,.2f} {currency}")
                risk_factors.append(f"Target recipient: {recipient}")
                safeguards.append("Enforce multi-factor step-up verification code")
                safeguards.append("Display recipient verification and fraud risk metrics")
            elif amount >= 100.0:
                score = 85
                tier = RiskTier.CRITICAL
                confirmation_type = ConfirmationType.STANDARD
                risk_factors.append(f"Substantial financial transfer: {amount:,.2f} {currency}")
                safeguards.append("Require explicit user approval token")
            elif amount > 0.0:
                score = 65
                tier = RiskTier.HIGH
                confirmation_type = ConfirmationType.STANDARD
                risk_factors.append(f"Direct financial charge: {amount:,.2f} {currency}")
                safeguards.append("Review itemized checkout cart before dispatch")
            else:
                score = 50
                tier = RiskTier.MEDIUM
                confirmation_type = ConfirmationType.NONE
                risk_factors.append("Financial inquiry or zero-amount authorization")

            return RiskEvaluationResponse(
                tier=tier,
                score=score,
                category=category,
                requires_confirmation=tier in {RiskTier.HIGH, RiskTier.CRITICAL},
                confirmation_type=confirmation_type,
                risk_factors=risk_factors,
                safeguards=safeguards,
            )

        # 2. Database & SQL Operations
        if "sql" in action_lower or "db" in action_lower or "database" in action_lower or "query" in tool_lower:
            category = OperationCategory.DATA_MODIFICATION
            query_str = str(payload.get("query", payload.get("sql", "")))

            if cls.DESTRUCTIVE_SQL_PATTERN.search(query_str):
                score = 95
                tier = RiskTier.CRITICAL
                confirmation_type = ConfirmationType.STEP_UP_2FA
                risk_factors.append("Destructive DDL/DML detected: DROP / TRUNCATE / unconditional DELETE")
                risk_factors.append(f"Query excerpt: {query_str[:80]}...")
                safeguards.append("Require database administrator 2FA authorization")
                safeguards.append("Ensure point-in-time recovery backup exists before execution")
            elif re.search(r"\b(UPDATE|DELETE|INSERT|ALTER|CREATE)\b", query_str, re.IGNORECASE):
                score = 65
                tier = RiskTier.HIGH
                confirmation_type = ConfirmationType.STANDARD
                risk_factors.append("Data mutation query altering database state")
                safeguards.append("Execute within an isolated transaction with dry-run verification")
            else:
                score = 15
                tier = RiskTier.LOW
                confirmation_type = ConfirmationType.NONE
                risk_factors.append("Read-only SQL query (SELECT / EXPLAIN)")

            return RiskEvaluationResponse(
                tier=tier,
                score=score,
                category=category,
                requires_confirmation=tier in {RiskTier.HIGH, RiskTier.CRITICAL},
                confirmation_type=confirmation_type,
                risk_factors=risk_factors,
                safeguards=safeguards,
            )

        # 3. Shell & System Command Execution
        if "shell" in action_lower or "terminal" in action_lower or "command" in action_lower or "exec" in tool_lower:
            category = OperationCategory.SYSTEM_COMMAND
            cmd_str = str(payload.get("command", payload.get("command_line", payload.get("cmd", ""))))

            if cls.DESTRUCTIVE_SHELL_PATTERN.search(cmd_str):
                score = 92
                tier = RiskTier.CRITICAL
                confirmation_type = ConfirmationType.STEP_UP_2FA
                risk_factors.append("Irreversible system destruction command detected (rm -rf / format / dd)")
                risk_factors.append(f"Command: {cmd_str[:70]}")
                safeguards.append("Block automated execution; require manual terminal entry or 2FA override")
            elif any(token in cmd_str.lower() for token in ["install", "pip ", "npm ", "kill", "systemctl", "curl", "wget"]):
                score = 65
                tier = RiskTier.HIGH
                confirmation_type = ConfirmationType.STANDARD
                risk_factors.append("System environment alteration / process termination / external download")
                safeguards.append("Inspect binary hash and target domain")
            elif any(token in cmd_str.lower() for token in ["ls", "dir", "git status", "whoami", "echo", "pwd", "pytest"]):
                score = 10
                tier = RiskTier.LOW
                confirmation_type = ConfirmationType.NONE
                risk_factors.append("Informational / diagnostic shell command")
            else:
                score = 55
                tier = RiskTier.HIGH
                confirmation_type = ConfirmationType.STANDARD
                risk_factors.append(f"General host shell execution: {cmd_str[:60]}")
                safeguards.append("Present exact command line to user before launch")

            return RiskEvaluationResponse(
                tier=tier,
                score=score,
                category=category,
                requires_confirmation=tier in {RiskTier.HIGH, RiskTier.CRITICAL},
                confirmation_type=confirmation_type,
                risk_factors=risk_factors,
                safeguards=safeguards,
            )

        # 4. File System Modification
        if "file" in action_lower or "write" in action_lower or "delete" in action_lower or "filesystem" in action_lower:
            category = OperationCategory.DATA_MODIFICATION
            file_path = str(payload.get("target_file", payload.get("file_path", payload.get("path", "")))).lower()
            is_deletion = "delete" in action_lower or "unlink" in action_lower or "rm" in action_lower

            if any(sens in file_path for sens in cls.SENSITIVE_PATHS):
                score = 90
                tier = RiskTier.CRITICAL
                confirmation_type = ConfirmationType.STEP_UP_2FA
                risk_factors.append(f"Access/modification of protected system or credential path: {file_path}")
                safeguards.append("Require explicit step-up token and path whitelist check")
            elif is_deletion:
                score = 75
                tier = RiskTier.HIGH
                confirmation_type = ConfirmationType.STANDARD
                risk_factors.append(f"Permanent file deletion: {file_path}")
                safeguards.append("Move to recycle/quarantine folder instead of permanent unlinking")
            elif payload.get("overwrite", False):
                score = 60
                tier = RiskTier.HIGH
                confirmation_type = ConfirmationType.STANDARD
                risk_factors.append(f"Overwriting existing workspace file: {file_path}")
                safeguards.append("Generate visual code diff preview")
            else:
                score = 30
                tier = RiskTier.MEDIUM
                confirmation_type = ConfirmationType.NONE
                risk_factors.append(f"Non-destructive file creation/append: {file_path}")

            return RiskEvaluationResponse(
                tier=tier,
                score=score,
                category=category,
                requires_confirmation=tier in {RiskTier.HIGH, RiskTier.CRITICAL},
                confirmation_type=confirmation_type,
                risk_factors=risk_factors,
                safeguards=safeguards,
            )

        # 5. External Communication & Email
        if "email" in action_lower or "webhook" in action_lower or "sms" in action_lower:
            category = OperationCategory.NETWORK_COMMUNICATION
            recipient = str(payload.get("recipient", payload.get("to", "external recipient")))
            score = 65
            tier = RiskTier.HIGH
            confirmation_type = ConfirmationType.STANDARD
            risk_factors.append(f"Outbound dispatch to external party: {recipient}")
            safeguards.append("Confirm sender address, recipient list, and full message draft")

            return RiskEvaluationResponse(
                tier=tier,
                score=score,
                category=category,
                requires_confirmation=True,
                confirmation_type=confirmation_type,
                risk_factors=risk_factors,
                safeguards=safeguards,
            )

        # 6. Permission & Capability Grant
        if "permission" in action_lower or "grant" in action_lower or "device_auth" in action_lower:
            category = OperationCategory.PERMISSION_GRANT
            perm_scope = str(payload.get("scope", payload.get("permission", "system_scope")))
            score = 85
            tier = RiskTier.CRITICAL
            confirmation_type = ConfirmationType.STANDARD
            risk_factors.append(f"Granting elevated device privilege scope: {perm_scope}")
            safeguards.append("Prompt user with specific capability checklist and revocation instructions")

            return RiskEvaluationResponse(
                tier=tier,
                score=score,
                category=category,
                requires_confirmation=True,
                confirmation_type=confirmation_type,
                risk_factors=risk_factors,
                safeguards=safeguards,
            )

        # 7. Default Read-Only / Benign Actions
        category = OperationCategory.READ_ONLY
        score = 10
        tier = RiskTier.LOW
        confirmation_type = ConfirmationType.NONE
        risk_factors.append("Standard read-only query or safe UI interaction")

        return RiskEvaluationResponse(
            tier=tier,
            score=score,
            category=category,
            requires_confirmation=False,
            confirmation_type=confirmation_type,
            risk_factors=risk_factors,
            safeguards=safeguards,
        )

    @classmethod
    def get_matrix_config(cls) -> dict[str, Any]:
        """Return the structured risk matrix configuration, thresholds, and safeguards."""
        return {
            "tiers": {
                RiskTier.LOW.value: {
                    "score_range": "0 - 20",
                    "policy": "Auto-Execute without confirmation",
                    "examples": ["Read file", "Search web", "List devices", "Get metrics"],
                },
                RiskTier.MEDIUM.value: {
                    "score_range": "21 - 50",
                    "policy": "Audited execution with soft notification",
                    "examples": ["Create scratch file", "Draft email", "Fetch third-party API"],
                },
                RiskTier.HIGH.value: {
                    "score_range": "51 - 80",
                    "policy": "Mandatory Standard Confirmation required",
                    "examples": ["Overwrite code file", "Install package", "Send outbound email", "Financial charge <= $100"],
                },
                RiskTier.CRITICAL.value: {
                    "score_range": "81 - 100",
                    "policy": "Step-up 2FA / Biometric Confirmation required",
                    "examples": ["Financial transfer > $1000", "DROP DATABASE", "rm -rf", "Grant admin permission"],
                },
            },
            "categories": {cat.value: cat.name.replace("_", " ").title() for cat in OperationCategory},
            "thresholds": {
                "high_risk_score": 51,
                "critical_risk_score": 81,
            },
            "financial_thresholds": {
                "require_standard_confirmation_usd": 10.0,
                "require_step_up_2fa_usd": 1000.0,
            },
        }
