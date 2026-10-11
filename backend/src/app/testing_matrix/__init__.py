"""Multi-Platform Testing Matrix Engine.

Orchestrates and validates integration across:
- Desktop (Windows, macOS, Linux UI & process automation)
- Mobile (Android ADB & iOS automation)
- Cloud (Remote device agent, distributed sync, multi-tenant IDOR isolation)
- MCP (Model Context Protocol connectors, tool discovery, dynamic execution)
"""

from __future__ import annotations

from app.testing_matrix.engine import MultiPlatformTestingMatrixEngine
from app.testing_matrix.schemas import (
    CrossPlatformScenario,
    MatrixTestResult,
    MatrixTestStatus,
    PillarSummary,
    PlatformPillar,
    ScenarioExecutionResult,
    TestingMatrixReport,
)

__all__ = [
    "MultiPlatformTestingMatrixEngine",
    "PlatformPillar",
    "MatrixTestStatus",
    "MatrixTestResult",
    "PillarSummary",
    "CrossPlatformScenario",
    "ScenarioExecutionResult",
    "TestingMatrixReport",
]
