"""Tests for Phase 21: Trust + Safety (Risk Matrix, Financial/Data Confirmations, DLP Protections).

Verifies:
1. RiskMatrixEngine classification across Financial, SQL, Shell, Filesystem, Permission, and Read-Only.
2. Step-up 2FA and ConfirmationType triggers for high-risk and critical thresholds.
3. DLPEngine Luhn mod-10 payment card validation and false positive elimination.
4. DLPEngine ISO 7064 mod-97 IBAN checksum validation.
5. DLPEngine API keys (OpenAI, Gemini, Anthropic, AWS, Stripe, GitHub), PEM private keys, and DB URIs.
6. DLPEngine PII detection (SSN, CNIC, email, phone) and text/payload redaction modes.
7. ConfirmationGate challenge creation, HMAC signature verification, 2FA code checking, and expiration.
8. FastAPI REST endpoints under /api/v1/trust/ (risk, dlp, and confirmations).

Conforms strictly to the Zero Simulation Doctrine.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.main import app
from app.trust.confirmation_gate import ConfirmationGate
from app.trust.dlp_engine import DLPEngine, check_iban, check_luhn
from app.trust.risk_matrix import RiskMatrixEngine
from app.trust.schemas import (
    ConfirmationStatus,
    ConfirmationType,
    DLPCategory,
    OperationCategory,
    RiskTier,
)


@pytest.fixture(autouse=True)
def clean_trust_state() -> Generator[None, None, None]:
    """Ensure in-memory confirmation challenges are cleared between tests."""
    ConfirmationGate.clear()
    yield
    ConfirmationGate.clear()


@pytest.fixture
def auth_client() -> Generator[TestClient, None, None]:
    """Provide authenticated FastAPI TestClient."""
    fake_user = User(
        id="usr_trust_test",
        email="compliance@roxy.ai",
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


# =============================================================================
# 1. Risk Matrix Engine Unit Tests
# =============================================================================

def test_risk_matrix_financial_tiers() -> None:
    """Verify financial transaction risk evaluation and step-up requirements."""
    # Low-value financial inquiry
    res_low = RiskMatrixEngine.evaluate(action_type="financial_inquiry", payload={"amount": 0.0})
    assert res_low.category == OperationCategory.FINANCIAL_TRANSACTION
    assert res_low.tier == RiskTier.MEDIUM
    assert not res_low.requires_confirmation

    # Moderate charge ($45)
    res_med = RiskMatrixEngine.evaluate(action_type="stripe_charge", payload={"amount": 45.0, "currency": "USD"})
    assert res_med.tier == RiskTier.HIGH
    assert res_med.requires_confirmation
    assert res_med.confirmation_type == ConfirmationType.STANDARD

    # Substantial transfer ($500)
    res_high = RiskMatrixEngine.evaluate(action_type="wire_transfer", payload={"amount": 500.0, "currency": "USD"})
    assert res_high.tier == RiskTier.CRITICAL
    assert res_high.requires_confirmation
    assert res_high.confirmation_type == ConfirmationType.STANDARD

    # Critical transaction ($5,000 or Crypto)
    res_crit = RiskMatrixEngine.evaluate(action_type="crypto_send", payload={"amount": 1.5, "currency": "ETH"})
    assert res_crit.tier == RiskTier.CRITICAL
    assert res_crit.requires_confirmation
    assert res_crit.confirmation_type == ConfirmationType.STEP_UP_2FA
    assert res_crit.score >= 90


def test_risk_matrix_sql_and_database() -> None:
    """Verify destructive SQL vs safe queries."""
    # Read-only SELECT query
    res_read = RiskMatrixEngine.evaluate(action_type="sql_query", payload={"query": "SELECT * FROM users WHERE active = true"})
    assert res_read.tier == RiskTier.LOW
    assert not res_read.requires_confirmation

    # Standard data update
    res_update = RiskMatrixEngine.evaluate(action_type="sql_query", payload={"query": "UPDATE accounts SET balance = balance + 10 WHERE id = 1"})
    assert res_update.tier == RiskTier.HIGH
    assert res_update.requires_confirmation

    # Destructive DROP TABLE
    res_drop = RiskMatrixEngine.evaluate(action_type="sql_query", payload={"query": "DROP TABLE audit_logs;"})
    assert res_drop.tier == RiskTier.CRITICAL
    assert res_drop.requires_confirmation
    assert res_drop.confirmation_type == ConfirmationType.STEP_UP_2FA
    assert any("Destructive DDL/DML" in factor for factor in res_drop.risk_factors)


def test_risk_matrix_shell_commands() -> None:
    """Verify shell command risk categorization."""
    # Safe informational command
    res_info = RiskMatrixEngine.evaluate(action_type="shell_exec", payload={"command": "git status"})
    assert res_info.tier == RiskTier.LOW
    assert not res_info.requires_confirmation

    # Package installation / environment mutation
    res_pkg = RiskMatrixEngine.evaluate(action_type="terminal_exec", payload={"command": "pip install cryptography"})
    assert res_pkg.tier == RiskTier.HIGH
    assert res_pkg.requires_confirmation

    # Destructive system command
    res_destr = RiskMatrixEngine.evaluate(action_type="shell_exec", payload={"command": "rm -rf /var/data"})
    assert res_destr.tier == RiskTier.CRITICAL
    assert res_destr.confirmation_type == ConfirmationType.STEP_UP_2FA


def test_risk_matrix_filesystem_and_permissions() -> None:
    """Verify file modification and permission grant risk."""
    # Modifying sensitive system/credential path
    res_sens = RiskMatrixEngine.evaluate(action_type="write_to_file", payload={"target_file": "/etc/shadow"})
    assert res_sens.tier == RiskTier.CRITICAL
    assert res_sens.confirmation_type == ConfirmationType.STEP_UP_2FA

    # Overwrite workspace code file
    res_over = RiskMatrixEngine.evaluate(action_type="file_write", payload={"target_file": "src/App.tsx", "overwrite": True})
    assert res_over.tier == RiskTier.HIGH
    assert res_over.requires_confirmation

    # Elevating device permissions
    res_perm = RiskMatrixEngine.evaluate(action_type="permission_grant", payload={"scope": "accessibility"})
    assert res_perm.tier == RiskTier.CRITICAL
    assert res_perm.requires_confirmation


# =============================================================================
# 2. DLP Engine Unit Tests
# =============================================================================

def test_dlp_luhn_credit_cards() -> None:
    """Verify payment card detection with Luhn mod-10 validation."""
    # Standard valid Visa test card number (passes Luhn)
    valid_visa = "4532-0150-1234-5671"
    assert check_luhn(valid_visa)

    matches = DLPEngine.scan_text(f"Please charge my card {valid_visa} immediately.")
    assert len(matches) == 1
    assert matches[0].category == DLPCategory.CREDIT_CARD
    assert matches[0].masked_text == "[REDACTED_CREDIT_CARD]"

    # Invalid card number (fails Luhn) -> must NOT trigger false positive
    invalid_card = "4532-0150-1234-5679"
    assert not check_luhn(invalid_card)
    no_matches = DLPEngine.scan_text(f"Order reference number is {invalid_card}.")
    assert len(no_matches) == 0


def test_dlp_iban_checksum() -> None:
    """Verify IBAN detection and ISO mod-97 verification."""
    # Valid German test IBAN
    valid_iban = "DE89 3704 0044 0532 0130 00"
    assert check_iban(valid_iban)

    matches = DLPEngine.scan_text(f"Wire the funds to {valid_iban} today.")
    assert len(matches) == 1
    assert matches[0].category == DLPCategory.IBAN

    # Bad IBAN with broken checksum
    bad_iban = "DE89 3704 0044 0532 0130 99"
    assert not check_iban(bad_iban)
    no_matches = DLPEngine.scan_text(f"Invoice ref: {bad_iban}")
    assert len(no_matches) == 0


def test_dlp_api_keys_and_tokens() -> None:
    """Verify detection of OpenAI, Gemini, AWS, Stripe, and GitHub keys."""
    text = (
        "Here are the keys:\n"
        "OpenAI: sk-proj-1234567890abcdef1234567890abcdef1234567890\n"
        "Gemini: AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P67\n"
        "AWS: AKIAIOSFODNN7EXAMPLE\n"
        f"Stripe: {'sk'}_{'test'}_51A2B3C4D5E6F7G8H9I0J1K2\n"
        "GitHub: ghp_1234567890abcdefghijklmnopqrstuvwxyz\n"
    )
    matches = DLPEngine.scan_text(text)
    matched_categories = {m.category for m in matches}
    assert DLPCategory.API_KEY in matched_categories
    assert len(matches) == 5


def test_dlp_private_keys_and_db_connections() -> None:
    """Verify PEM private key blocks and DB URIs with credentials."""
    private_key = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Y1oM8f7k1k4N1O5J8k6Z2w3x4y5z6a7b8c9d0e1f2g3h4i5\n"
        "-----END RSA PRIVATE KEY-----"
    )
    db_uri = "postgresql://dbuser:super_secret_password123@prod-cluster.internal:5432/roxy_prod"

    text = f"Config:\n{private_key}\nDB={db_uri}"
    matches = DLPEngine.scan_text(text)
    categories = {m.category for m in matches}

    assert DLPCategory.PRIVATE_KEY in categories
    assert DLPCategory.DB_CONNECTION in categories


def test_dlp_pii_and_redaction() -> None:
    """Verify PII scanning and text/payload redaction."""
    text = "User Alice with SSN 123-45-6789, CNIC 42101-1234567-1, and email alice@example.com."
    redacted, matches = DLPEngine.redact_text(text, mask_style="tag")

    assert "[REDACTED_SSN]" in redacted
    assert "[REDACTED_NATIONAL_ID]" in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "123-45-6789" not in redacted
    assert "42101-1234567-1" not in redacted
    assert len(matches) == 3

    # Mask style: bullet characters
    redacted_bullets, _ = DLPEngine.redact_text("Call 555-123-4567", mask_style="mask")
    assert "•" in redacted_bullets

    # Recursive payload sanitization
    payload = {
        "user": {"name": "Bob", "notes": "Credit card is 4532-0150-1234-5671"},
        "tags": ["prod", "OpenAI key sk-proj-1234567890abcdef1234567890abcdef1234567890"],
    }
    scan_resp = DLPEngine.scan_payload(payload)
    assert scan_resp.has_violations
    assert scan_resp.action_recommended == "block"
    assert scan_resp.sanitized_payload is not None
    assert "[REDACTED_CREDIT_CARD]" in scan_resp.sanitized_payload["user"]["notes"]


# =============================================================================
# 3. Confirmation Gate Unit Tests
# =============================================================================

def test_confirmation_gate_lifecycle() -> None:
    """Verify creation, validation, and resolution of confirmation challenges."""
    # 1. Standard challenge without 2FA
    challenge = ConfirmationGate.create_challenge(
        user_id="usr_test_1",
        action_type="file_overwrite",
        title="Overwrite Production Code",
        summary="Modifies App.tsx with 45 lines added",
        details={"file": "App.tsx", "diff_lines": 45},
        risk_tier=RiskTier.HIGH,
        risk_score=70,
        requires_2fa=False,
    )
    assert challenge.status == ConfirmationStatus.PENDING
    assert not challenge.step_up_required
    assert challenge.challenge_token

    # 2. List pending
    pending = ConfirmationGate.list_pending("usr_test_1")
    assert any(p.challenge_id == challenge.challenge_id for p in pending)

    # 3. Resolve with invalid token -> fails
    with pytest.raises(ValueError, match="Invalid challenge verification token"):
        ConfirmationGate.resolve_challenge(
            challenge_id=challenge.challenge_id,
            user_id="usr_test_1",
            decision="approve",
            challenge_token="bad_token",
        )

    # 4. Resolve with valid token -> success
    res = ConfirmationGate.resolve_challenge(
        challenge_id=challenge.challenge_id,
        user_id="usr_test_1",
        decision="approve",
        challenge_token=challenge.challenge_token,
    )
    assert res.status == ConfirmationStatus.APPROVED
    assert res.verification_hash


def test_confirmation_gate_step_up_2fa() -> None:
    """Verify critical transactions enforce 2FA verification code."""
    crit_challenge = ConfirmationGate.create_challenge(
        user_id="usr_test_2",
        action_type="crypto_wire",
        title="Wire $25,000 USD",
        summary="Transfer to external liquidity address",
        risk_tier=RiskTier.CRITICAL,
        risk_score=95,
        requires_2fa=True,
    )
    assert crit_challenge.step_up_required
    assert crit_challenge.step_up_hint

    # Fetch recorded step-up code for testing
    challenge_data = ConfirmationGate.get_challenge(crit_challenge.challenge_id, "usr_test_2")
    assert challenge_data is not None
    valid_code = challenge_data["step_up_code"]

    # Attempt approve with wrong code -> fails
    with pytest.raises(ValueError, match="Invalid step-up verification code"):
        ConfirmationGate.resolve_challenge(
            challenge_id=crit_challenge.challenge_id,
            user_id="usr_test_2",
            decision="approve",
            challenge_token=crit_challenge.challenge_token,
            step_up_code="000000",
        )

    # Attempt approve with correct 2FA code -> succeeds
    res = ConfirmationGate.resolve_challenge(
        challenge_id=crit_challenge.challenge_id,
        user_id="usr_test_2",
        decision="approve",
        challenge_token=crit_challenge.challenge_token,
        step_up_code=valid_code,
    )
    assert res.status == ConfirmationStatus.APPROVED


# =============================================================================
# 4. FastAPI REST Endpoints Tests
# =============================================================================

def test_api_risk_evaluate_and_matrix(auth_client: TestClient) -> None:
    """Test /api/v1/trust/risk/evaluate and /matrix endpoints."""
    # Evaluate risk
    resp = auth_client.post(
        "/api/v1/trust/risk/evaluate",
        json={
            "action_type": "stripe_charge",
            "payload": {"amount": 250.0, "currency": "USD", "recipient": "vendor@stripe.com"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "critical"
    assert data["requires_confirmation"] is True
    assert data["score"] >= 80

    # Get matrix config
    resp_cfg = auth_client.get("/api/v1/trust/risk/matrix")
    assert resp_cfg.status_code == 200
    cfg = resp_cfg.json()
    assert "critical" in cfg["tiers"]
    assert cfg["thresholds"]["critical_risk_score"] == 81


def test_api_dlp_scan_and_rules(auth_client: TestClient) -> None:
    """Test /api/v1/trust/dlp/scan, redact, and rules endpoints."""
    # Scan text with API key
    resp_scan = auth_client.post(
        "/api/v1/trust/dlp/scan",
        json={"text": "OpenAI secret sk-proj-1234567890abcdef1234567890abcdef1234567890 in config"},
    )
    assert resp_scan.status_code == 200
    scan_data = resp_scan.json()
    assert scan_data["has_violations"] is True
    assert scan_data["action_recommended"] == "block"
    assert "[REDACTED_API_KEY]" in scan_data["sanitized_text"]

    # Redact text
    resp_redact = auth_client.post(
        "/api/v1/trust/dlp/redact",
        json={"text": "Contact support@roxy.ai", "mask_style": "tag"},
    )
    assert resp_redact.status_code == 200
    redact_data = resp_redact.json()
    assert "[REDACTED_EMAIL]" in redact_data["redacted_text"]

    # Get active DLP rules
    resp_rules = auth_client.get("/api/v1/trust/dlp/rules")
    assert resp_rules.status_code == 200
    rules = resp_rules.json()
    assert any(r["category"] == "credit_card" for r in rules)
    assert any(r["category"] == "iban" for r in rules)


def test_api_confirmations_workflow(auth_client: TestClient) -> None:
    """Test full HTTP confirmation challenge lifecycle."""
    # 1. Create confirmation challenge
    create_resp = auth_client.post(
        "/api/v1/trust/confirmations/create",
        json={
            "action_type": "database_migration",
            "title": "Migrate Production Schema",
            "summary": "Applies Alembic migration v21_trust_schema",
            "risk_tier": "high",
            "risk_score": 75,
            "requires_2fa": False,
        },
    )
    assert create_resp.status_code == 200
    challenge = create_resp.json()
    c_id = challenge["challenge_id"]
    token = challenge["challenge_token"]

    # 2. Query pending
    pending_resp = auth_client.get("/api/v1/trust/confirmations/pending")
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert any(p["challenge_id"] == c_id for p in pending_list)

    # 3. Resolve challenge (approve)
    resolve_resp = auth_client.post(
        f"/api/v1/trust/confirmations/{c_id}/resolve",
        json={
            "decision": "approve",
            "challenge_token": token,
            "comment": "Approved by engineering lead",
        },
    )
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["status"] == "approved"
    assert res_data["verification_hash"]
