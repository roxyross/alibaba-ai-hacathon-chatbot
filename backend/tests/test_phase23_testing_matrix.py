"""Comprehensive Automated Test Suite for Phase 23: Testing Matrix.

End-to-End Multi-Platform Integration Tests across:
1. Desktop (Windows, macOS, Linux UI & process automation)
2. Mobile (Android ADB & iOS automation)
3. Cloud (Remote workers, distributed telemetry, multi-tenant IDOR isolation)
4. MCP (Model Context Protocol connectors, tool discovery, dynamic execution)
Plus multi-hop cross-platform E2E workflows with cryptographic ledger verification.

Strictly adheres to the Zero Simulation Doctrine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.fleet_orchestrator import FleetOrchestrator
from app.device.service import DeviceService
from app.main import app
from app.observability.ledger import ImmutableLedger
from app.testing_matrix.engine import MultiPlatformTestingMatrixEngine
from app.testing_matrix.schemas import (
    MatrixRunRequest,
    MatrixTestStatus,
    PlatformPillar,
    TestingMatrixReport,
)
from app.tools.registry import ToolRegistry


# =============================================================================
# Fixtures & Teardown
# =============================================================================

@pytest.fixture(autouse=True)
def clean_matrix_and_device_state() -> None:
    """Reset device, fleet, matrix, and ledger states between test cases."""
    DeviceService.get_instance().clear_in_memory_state()
    FleetOrchestrator.clear_state()
    MultiPlatformTestingMatrixEngine.clear_state()
    ImmutableLedger.get_instance().clear()


@pytest.fixture
def mock_user() -> User:
    """Mock authenticated user with full access."""
    return User(
        id="11111111-2222-3333-4444-555555555555",
        email="matrix_tester@roxy.internal",
    )


@pytest.fixture
def test_client(mock_user: User) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden user authentication."""
    app.dependency_overrides[get_current_user] = lambda: mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# =============================================================================
# Pillar 1: Desktop Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_desktop_pillar_integration(mock_user: User) -> None:
    """Verify Desktop pillar: OS detection, process lifecycle, screen surface, and fallback drivers."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    summary = await engine.run_desktop_pillar(user_id=str(mock_user.id))

    assert summary.pillar == PlatformPillar.DESKTOP
    assert summary.total_tests == 4
    assert summary.passed == 4
    assert summary.failed == 0
    assert summary.health_score == 100.0

    test_names = [t.name for t in summary.tests]
    assert "desktop_os_architecture_and_capabilities" in test_names
    assert "desktop_process_lifecycle_and_catalog" in test_names
    assert "desktop_screen_surface_geometry" in test_names
    assert "desktop_automation_fallback_driver_hierarchy" in test_names


# =============================================================================
# Pillar 2: Mobile Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_mobile_pillar_integration(mock_user: User) -> None:
    """Verify Mobile pillar: Android ADB intents, UI hierarchy coordinates, iOS bundles, and deep links."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    summary = await engine.run_mobile_pillar(user_id=str(mock_user.id))

    assert summary.pillar == PlatformPillar.MOBILE
    assert summary.total_tests == 4
    assert summary.passed == 4
    assert summary.failed == 0
    assert summary.health_score == 100.0

    test_names = [t.name for t in summary.tests]
    assert "mobile_android_adb_and_intent_protocol" in test_names
    assert "mobile_android_ui_hierarchy_engine" in test_names
    assert "mobile_ios_bundle_and_app_intents" in test_names
    assert "mobile_deep_link_synthesizer" in test_names


# =============================================================================
# Pillar 3: Cloud Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_cloud_pillar_integration(mock_user: User) -> None:
    """Verify Cloud pillar: Remote device registration, IDOR isolation, fleet telemetry, command queue."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    summary = await engine.run_cloud_pillar(user_id=str(mock_user.id))

    assert summary.pillar == PlatformPillar.CLOUD
    assert summary.total_tests == 4
    assert summary.passed == 4
    assert summary.failed == 0
    assert summary.health_score == 100.0

    test_names = [t.name for t in summary.tests]
    assert "cloud_remote_device_registration_and_heartbeat" in test_names
    assert "cloud_multi_tenant_idor_isolation" in test_names
    assert "cloud_distributed_telemetry_aggregation" in test_names
    assert "cloud_remote_command_queue_dispatch" in test_names


# =============================================================================
# Pillar 4: MCP Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_mcp_pillar_integration(mock_user: User) -> None:
    """Verify MCP pillar: Server discovery handshake, JSON-RPC schema extraction, dynamic tool binding, error sandbox."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    summary = await engine.run_mcp_pillar(user_id=str(mock_user.id))

    assert summary.pillar == PlatformPillar.MCP
    assert summary.total_tests == 4
    assert summary.passed == 4
    assert summary.failed == 0
    assert summary.health_score == 100.0

    test_names = [t.name for t in summary.tests]
    assert "mcp_server_discovery_and_handshake" in test_names
    assert "mcp_json_rpc_schema_extraction" in test_names
    assert "mcp_dynamic_tool_registry_binding" in test_names
    assert "mcp_error_sandboxing_and_resilience" in test_names


# =============================================================================
# Cross-Platform Scenarios
# =============================================================================

@pytest.mark.asyncio
async def test_scenario_desktop_to_mobile_handoff(mock_user: User) -> None:
    """Scenario 1: Action context frozen on Desktop, transferred to Mobile, and verified."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    result = await engine.execute_scenario_desktop_to_mobile_handoff(user_id=str(mock_user.id))

    assert result.scenario_id == "desktop_to_mobile_handoff"
    assert result.success is True
    assert len(result.steps) == 4
    assert all(s.status == MatrixTestStatus.PASSED for s in result.steps)
    assert len(result.audit_block_hash) == 64


@pytest.mark.asyncio
async def test_scenario_cloud_to_desktop_sync(mock_user: User) -> None:
    """Scenario 2: Cloud worker computation, Zero Credential Leakage sanitization, local desktop write."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    result = await engine.execute_scenario_cloud_to_desktop_sync(user_id=str(mock_user.id))

    assert result.scenario_id == "cloud_to_desktop_sync"
    assert result.success is True
    assert len(result.steps) == 3
    assert all(s.status == MatrixTestStatus.PASSED for s in result.steps)
    # Check that Step 2 verified credential redaction
    assert result.steps[1].payload_summary.get("secrets_redacted") is True


@pytest.mark.asyncio
async def test_scenario_mcp_to_desktop_orchestration(mock_user: User) -> None:
    """Scenario 3: MCP connector tool queries data, Desktop UI controller fills application window, verified."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    result = await engine.execute_scenario_mcp_to_desktop_orchestration(user_id=str(mock_user.id))

    assert result.scenario_id == "mcp_to_desktop_orchestration"
    assert result.success is True
    assert len(result.steps) == 3
    assert all(s.status == MatrixTestStatus.PASSED for s in result.steps)
    assert result.steps[2].payload_summary.get("verified_match") is True


@pytest.mark.asyncio
async def test_scenario_e2e_observability_audit_chain(mock_user: User) -> None:
    """Scenario 4: Multi-hop transaction across Desktop, Cloud, MCP, and Mobile with SHA-256 ledger proof."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    result = await engine.execute_scenario_e2e_observability_audit_chain(user_id=str(mock_user.id))

    assert result.scenario_id == "e2e_observability_audit_chain"
    assert result.success is True
    assert len(result.steps) == 5
    assert all(s.status == MatrixTestStatus.PASSED for s in result.steps)

    # Verify ledger integrity was checked and passed
    verification = ImmutableLedger.get_instance().verify_integrity()
    assert verification.is_valid is True
    assert verification.total_records > 0


# =============================================================================
# Master Matrix Execution
# =============================================================================

@pytest.mark.asyncio
async def test_master_matrix_execution(mock_user: User) -> None:
    """Execute full master matrix across all 4 pillars and all cross-platform scenarios."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    report = await engine.execute_matrix(user_id=str(mock_user.id))

    assert report.overall_verdict == "healthy"
    assert report.total_tests == 16  # 4 tests * 4 pillars
    assert report.total_passed == 16
    assert report.total_failed == 0
    assert len(report.pillars) == 4
    assert len(report.scenarios) == 4
    assert all(s.success for s in report.scenarios)
    assert len(report.cryptographic_audit_hash) == 64

    # Cryptographic ledger verification
    verification = ImmutableLedger.get_instance().verify_integrity()
    assert verification.is_valid is True


# =============================================================================
# REST API Endpoints Integration Tests
# =============================================================================

def test_testing_matrix_rest_api_endpoints(test_client: TestClient) -> None:
    """Verify testing matrix REST API endpoints (/run, /report, /scenarios, /scenarios/{id}/execute, /pillars/{id})."""
    # 1. Trigger matrix run
    run_resp = test_client.post("/api/v1/testing-matrix/run", json={"include_scenarios": True})
    assert run_resp.status_code == 200
    report_data = run_resp.json()
    assert report_data["overall_verdict"] == "healthy"
    assert report_data["total_tests"] == 16
    assert len(report_data["cryptographic_audit_hash"]) == 64

    # 2. Get latest report
    get_resp = test_client.get("/api/v1/testing-matrix/report")
    assert get_resp.status_code == 200
    assert get_resp.json()["run_id"] == report_data["run_id"]

    # 3. List scenarios
    scenarios_resp = test_client.get("/api/v1/testing-matrix/scenarios")
    assert scenarios_resp.status_code == 200
    scenarios = scenarios_resp.json()
    assert len(scenarios) == 4
    scenario_ids = [s["scenario_id"] for s in scenarios]
    assert "desktop_to_mobile_handoff" in scenario_ids

    # 4. Execute individual scenario
    exec_resp = test_client.post("/api/v1/testing-matrix/scenarios/desktop_to_mobile_handoff/execute")
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["scenario_id"] == "desktop_to_mobile_handoff"
    assert exec_data["success"] is True
    assert len(exec_data["steps"]) == 4

    # 5. Inspect individual pillar
    pillar_resp = test_client.get("/api/v1/testing-matrix/pillars/desktop")
    assert pillar_resp.status_code == 200
    pillar_data = pillar_resp.json()
    assert pillar_data["pillar"] == "desktop"
    assert pillar_data["total_tests"] == 4
    assert pillar_data["health_score"] == 100.0
