"""Pydantic schemas for Phase 23: Multi-Platform Testing Matrix.

Defines schemas for:
- Desktop, Mobile, Cloud, and MCP test pillar results
- Multi-hop cross-platform scenario execution
- Cryptographic verification & audit ledger integration
- Fleet and platform health summaries
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field


class PlatformPillar(StrEnum):
    """Core platform pillars tested in the multi-platform matrix."""

    DESKTOP = "desktop"
    MOBILE = "mobile"
    CLOUD = "cloud"
    MCP = "mcp"


class MatrixTestStatus(StrEnum):
    """Execution status for matrix tests and scenario steps."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RUNNING = "running"


class MatrixTestResult(BaseModel):
    """Result of an individual platform pillar integration test."""

    test_id: str = Field(default_factory=lambda: f"test_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Descriptive name of test case")
    pillar: PlatformPillar
    target_platform: str = Field(..., description="Target runtime (e.g. windows, android, cloud_vm, mcp_server)")
    status: MatrixTestStatus
    duration_ms: float
    assertions_passed: int = 1
    assertions_failed: int = 0
    details: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    trace_id: str | None = None
    correlation_id: str | None = None


class PillarSummary(BaseModel):
    """Aggregated health summary for a platform pillar."""

    pillar: PlatformPillar
    total_tests: int
    passed: int
    failed: int
    skipped: int = 0
    health_score: float = Field(..., description="Percentage health score between 0.0 and 100.0")
    avg_latency_ms: float
    tests: list[MatrixTestResult] = Field(default_factory=list)


class ScenarioStep(BaseModel):
    """Individual hop in a multi-platform integration scenario."""

    step_index: int
    name: str
    platform: PlatformPillar
    target: str
    action: str
    status: MatrixTestStatus
    duration_ms: float
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    verification_hash: str | None = None
    error_message: str | None = None


class CrossPlatformScenario(BaseModel):
    """Metadata for an end-to-end multi-platform integration scenario."""

    scenario_id: str
    name: str
    description: str
    pillars_involved: list[PlatformPillar]
    step_count: int


class ScenarioExecutionResult(BaseModel):
    """Execution result for a multi-platform cross-cutting scenario."""

    scenario_id: str
    name: str
    success: bool
    total_duration_ms: float
    steps: list[ScenarioStep] = Field(default_factory=list)
    trace_id: str
    correlation_id: str
    audit_block_hash: str


class MatrixRunRequest(BaseModel):
    """Request payload to trigger testing matrix execution."""

    pillars: list[PlatformPillar] | None = Field(
        default=None,
        description="Optional subset of pillars to execute. If None, executes all 4 pillars.",
    )
    include_scenarios: bool = Field(
        default=True,
        description="Whether to run multi-hop cross-platform scenarios.",
    )
    fail_fast: bool = Field(
        default=False,
        description="Whether to abort scenario execution on the first step failure.",
    )


class TestingMatrixReport(BaseModel):
    """Comprehensive test matrix execution report with cryptographic audit link."""

    __test__ = False

    run_id: str = Field(default_factory=lambda: f"matrix_{uuid.uuid4().hex[:8]}")
    timestamp: str
    overall_verdict: Literal["healthy", "degraded", "failing"]
    total_tests: int
    total_passed: int
    total_failed: int
    pillars: dict[str, PillarSummary] = Field(default_factory=dict)
    scenarios: list[ScenarioExecutionResult] = Field(default_factory=list)
    audit_record_id: str
    cryptographic_audit_hash: str
