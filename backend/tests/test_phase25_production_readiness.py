"""Comprehensive Automated Test Suite for Phase 25: Production Readiness Audit.

Validates:
1. Zero-Mock Doctrine compliance across production sources (ast inspection).
2. Detection of prohibited mock imports, symbols, and simulation flags.
3. Dead code and syntax hygiene across runtime modules.
4. Packaging validation (backend/frontend Dockerfiles, docker-compose, prod env, frontend bundle).
5. Final Exit Gate 7-Point checklist evaluation.
6. Cryptographic Production Exit Seal and ImmutableLedger block commitment.
7. REST API endpoints under `/api/v1/production-readiness`.

Strictly adheres to the Zero Simulation Doctrine.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.main import app
from app.observability.ledger import ImmutableLedger
from app.production_readiness.dead_code_auditor import DeadCodeAuditor
from app.production_readiness.exit_gate import FinalExitGate
from app.production_readiness.packaging_validator import PackagingValidator
from app.production_readiness.schemas import GateCheckStatus
from app.production_readiness.zero_mock_auditor import ZeroMockAuditor


# =============================================================================
# Fixtures & Teardown
# =============================================================================

@pytest.fixture(autouse=True)
def clean_production_readiness_state() -> None:
    """Reset FinalExitGate and ImmutableLedger states between tests."""
    FinalExitGate.clear_state()
    ImmutableLedger.get_instance().clear()


@pytest.fixture
def mock_user() -> User:
    """Mock security & release compliance officer."""
    return User(
        id="rel-officer-9999-8888-7777-666655554444",
        email="release_officer@roxy.internal",
    )


@pytest.fixture
def test_client(mock_user: User) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden user authentication."""
    app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# =============================================================================
# 1. Zero-Mock Doctrine Validation on Production Sources
# =============================================================================

def test_zero_mock_auditor_on_production_code() -> None:
    """Verify that all production runtime modules contain zero mock frameworks or simulations."""
    auditor = ZeroMockAuditor()
    # Target backend/src/app
    app_dir = Path(__file__).resolve().parent.parent / "src" / "app"
    result = auditor.scan_directory(app_dir)

    assert result.files_scanned >= 50
    assert result.violations_found == 0
    assert result.is_zero_mock_compliant is True
    assert result.mock_occurrences == []
    assert "0 violations found" in result.summary


def test_zero_mock_auditor_detects_prohibited_patterns(tmp_path: Path) -> None:
    """Verify that the auditor correctly detects mock imports, symbols, and simulation flags."""
    fake_code = """
import unittest.mock
from unittest.mock import MagicMock
from faker import Faker

SIMULATION_MODE = True

def run():
    mock = MagicMock()
    return mock
"""
    bad_file = tmp_path / "simulated_service.py"
    bad_file.write_text(fake_code, encoding="utf-8")

    auditor = ZeroMockAuditor()
    result = auditor.scan_directory(tmp_path)

    assert result.files_scanned == 1
    assert result.is_zero_mock_compliant is False
    assert result.violations_found >= 3

    types_found = {v["type"] for v in result.mock_occurrences}
    assert "prohibited_import" in types_found
    assert "prohibited_symbol" in types_found
    assert "prohibited_flag" in types_found


# =============================================================================
# 2. Dead Code & Syntax Hygiene
# =============================================================================

def test_dead_code_auditor_on_production_code() -> None:
    """Ensure all production runtime modules parse cleanly with zero syntax errors."""
    auditor = DeadCodeAuditor()
    app_dir = Path(__file__).resolve().parent.parent / "src" / "app"
    result = auditor.audit_directory(app_dir)

    assert result.modules_analyzed >= 50
    assert result.syntax_errors_found == 0
    assert result.is_clean is True


def test_dead_code_auditor_detects_unreachable_blocks(tmp_path: Path) -> None:
    """Verify dead code auditor detects if False: and statements after unconditional return."""
    dead_code = """
def sample_func():
    return 42
    print("unreachable 1")
    x = 100

def another():
    if False:
        do_something()
"""
    dead_file = tmp_path / "dead_module.py"
    dead_file.write_text(dead_code, encoding="utf-8")

    auditor = DeadCodeAuditor()
    result = auditor.audit_directory(tmp_path)

    assert result.modules_analyzed == 1
    assert result.unreachable_blocks_found >= 2
    assert result.is_clean is False


# =============================================================================
# 3. Packaging & Deployment Artifacts
# =============================================================================

def test_packaging_validator_artifacts() -> None:
    """Verify presence of Dockerfiles, docker-compose, prod env, and built frontend bundle."""
    validator = PackagingValidator()
    # Repo root is two levels up from backend/
    repo_root = Path(__file__).resolve().parent.parent.parent
    result = validator.validate_packaging(repo_root)

    assert result.dockerfile_backend is True
    assert result.dockerfile_frontend is True
    assert result.docker_compose is True
    assert result.production_env_spec is True
    assert result.frontend_bundle_built is True
    assert result.is_packaged is True
    assert result.details["frontend_bundle_files"] > 0
    assert result.details["frontend_bundle_size_kb"] > 100.0


# =============================================================================
# 4. Final Exit Gate Evaluation & Cryptographic Seal
# =============================================================================

def test_final_exit_gate_evaluation_and_seal() -> None:
    """Execute the full 7-Point Exit Gate and confirm cryptographic production certification."""
    gate = FinalExitGate.get_instance()
    report = gate.evaluate_gate()

    assert len(report.gate_checks) == 7
    assert report.overall_verdict in ("PRODUCTION_CERTIFIED", "PROVISIONAL")
    assert report.certificate.total_score >= 650
    assert report.certificate.zero_mock_certified is True

    # Check individual gate checkpoint presence
    gate_ids = {gc.gate_id for gc in report.gate_checks}
    assert "GATE_1_FOUNDATIONS" in gate_ids
    assert "GATE_2_PILLARS" in gate_ids
    assert "GATE_3_TRUST_SAFETY" in gate_ids
    assert "GATE_4_OBSERVABILITY" in gate_ids
    assert "GATE_5_ADVERSARIAL_SECURITY" in gate_ids
    assert "GATE_6_ZERO_MOCKS" in gate_ids
    assert "GATE_7_PACKAGING" in gate_ids

    # Cryptographic Seal Verification
    assert len(report.cryptographic_seal_hash) == 64  # SHA-256
    assert len(report.certificate.cryptographic_seal_hash) == 64
    assert report.ledger_block_id != ""

    # Ledger Verification
    ledger = gate.ledger
    verification = ledger.verify_integrity()
    assert verification.is_valid is True
    assert verification.total_records >= 1


# =============================================================================
# 5. REST API Endpoints
# =============================================================================

def test_production_readiness_rest_api_endpoints(test_client: TestClient) -> None:
    """Test all REST API endpoints under /api/v1/production-readiness."""
    # 1. Zero-Mock Scan endpoint
    zm_res = test_client.post("/api/v1/production-readiness/zero-mock-scan")
    assert zm_res.status_code == 200
    zm_data = zm_res.json()
    assert zm_data["is_zero_mock_compliant"] is True
    assert zm_data["violations_found"] == 0

    # 2. Evaluate Exit Gate endpoint
    eval_res = test_client.post("/api/v1/production-readiness/exit-gate/evaluate")
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["overall_verdict"] in ("PRODUCTION_CERTIFIED", "PROVISIONAL")
    assert len(eval_data["gate_checks"]) == 7
    assert len(eval_data["cryptographic_seal_hash"]) == 64

    # 3. Get latest audit report endpoint
    audit_res = test_client.get("/api/v1/production-readiness/audit")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["audit_id"] == eval_data["audit_id"]

    # 4. Get certificate endpoint
    cert_res = test_client.get("/api/v1/production-readiness/exit-gate/certificate")
    assert cert_res.status_code == 200
    cert_data = cert_res.json()
    assert cert_data["certificate_id"].startswith("CERT-")
    assert cert_data["zero_mock_certified"] is True
    assert cert_data["platform_version"] == "2.0.0-prod"
