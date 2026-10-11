"""FastAPI Router for Phase 23: Multi-Platform Testing Matrix.

Endpoints:
- POST /api/v1/testing-matrix/run
- GET /api/v1/testing-matrix/report
- GET /api/v1/testing-matrix/scenarios
- POST /api/v1/testing-matrix/scenarios/{scenario_id}/execute
- GET /api/v1/testing-matrix/pillars/{pillar}
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.testing_matrix.engine import MultiPlatformTestingMatrixEngine
from app.testing_matrix.schemas import (
    CrossPlatformScenario,
    MatrixRunRequest,
    PillarSummary,
    PlatformPillar,
    ScenarioExecutionResult,
    TestingMatrixReport,
)

testing_matrix_router = APIRouter(prefix="/testing-matrix", tags=["Testing Matrix"])


@testing_matrix_router.post(
    "/run",
    response_model=TestingMatrixReport,
    summary="Execute multi-platform integration testing matrix",
)
async def run_testing_matrix(
    request: MatrixRunRequest | None = None,
    current_user: User = Depends(get_current_user),
) -> TestingMatrixReport:
    """Run automated testing matrix across Desktop, Mobile, Cloud, and MCP."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    user_id = str(current_user.id)
    return await engine.execute_matrix(user_id=user_id, request=request)


@testing_matrix_router.get(
    "/report",
    response_model=TestingMatrixReport,
    summary="Get latest testing matrix report",
)
async def get_latest_matrix_report(
    current_user: User = Depends(get_current_user),
) -> TestingMatrixReport:
    """Retrieve the latest matrix run report or execute an initial evaluation."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    report = engine.get_latest_report()
    if report is None:
        user_id = str(current_user.id)
        report = await engine.execute_matrix(user_id=user_id)
    return report


@testing_matrix_router.get(
    "/scenarios",
    response_model=list[CrossPlatformScenario],
    summary="List registered multi-platform scenarios",
)
async def list_scenarios(
    current_user: User = Depends(get_current_user),
) -> list[CrossPlatformScenario]:
    """List available cross-platform multi-hop integration scenarios."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    return engine.list_available_scenarios()


@testing_matrix_router.post(
    "/scenarios/{scenario_id}/execute",
    response_model=ScenarioExecutionResult,
    summary="Execute a specific multi-platform scenario",
)
async def execute_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
) -> ScenarioExecutionResult:
    """Trigger step-by-step execution of a specific cross-platform scenario."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    user_id = str(current_user.id)

    if scenario_id == "desktop_to_mobile_handoff":
        return await engine.execute_scenario_desktop_to_mobile_handoff(user_id=user_id)
    elif scenario_id == "cloud_to_desktop_sync":
        return await engine.execute_scenario_cloud_to_desktop_sync(user_id=user_id)
    elif scenario_id == "mcp_to_desktop_orchestration":
        return await engine.execute_scenario_mcp_to_desktop_orchestration(user_id=user_id)
    elif scenario_id == "e2e_observability_audit_chain":
        return await engine.execute_scenario_e2e_observability_audit_chain(user_id=user_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown multi-platform scenario: '{scenario_id}'",
        )


@testing_matrix_router.get(
    "/pillars/{pillar}",
    response_model=PillarSummary,
    summary="Execute and inspect a single platform pillar",
)
async def get_pillar_summary(
    pillar: PlatformPillar,
    current_user: User = Depends(get_current_user),
) -> PillarSummary:
    """Execute tests for a specific platform pillar (desktop, mobile, cloud, or mcp)."""
    engine = MultiPlatformTestingMatrixEngine.get_instance()
    user_id = str(current_user.id)

    if pillar == PlatformPillar.DESKTOP:
        return await engine.run_desktop_pillar(user_id=user_id)
    elif pillar == PlatformPillar.MOBILE:
        return await engine.run_mobile_pillar(user_id=user_id)
    elif pillar == PlatformPillar.CLOUD:
        return await engine.run_cloud_pillar(user_id=user_id)
    elif pillar == PlatformPillar.MCP:
        return await engine.run_mcp_pillar(user_id=user_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform pillar: '{pillar}'",
        )
