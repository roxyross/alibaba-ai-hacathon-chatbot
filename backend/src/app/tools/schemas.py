"""Tool Registry schemas and type definitions for ROXY-AI 2.0.

Fulfills Phase 2 and Section 14 (Central Tool Registry architecture).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolSource(StrEnum):
    SYSTEM = "system"
    SKILL = "skill"
    CONNECTOR = "connector"
    MCP = "mcp"
    PLUGIN = "plugin"
    DEVICE = "device"
    AGENT = "agent"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentTool(BaseModel):
    """Specification of an executable capability in the Tool Registry."""

    id: str = Field(..., description="Unique tool identifier, e.g. 'system_calculator'")
    name: str = Field(..., description="Human-readable tool title")
    description: str = Field(..., description="Detailed description of tool functionality")
    source: ToolSource = Field(..., description="Origin of tool: system, skill, connector, mcp, plugin, device, agent")
    capabilities: list[str] = Field(default_factory=list, description="Categorical tags, e.g. ['math', 'calculation']")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSONSchema defining accepted input arguments")
    permissions: list[str] = Field(default_factory=list, description="Required permission scopes")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Risk assessment: low, medium, high, critical")
    requires_confirmation: bool = Field(default=False, description="Whether execution triggers approval gate by default")
    enabled: bool = Field(default=True, description="Whether tool is active and discoverable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source": self.source.value,
            "capabilities": self.capabilities,
            "input_schema": self.input_schema,
            "permissions": self.permissions,
            "risk_level": self.risk_level.value,
            "requires_confirmation": self.requires_confirmation,
            "enabled": self.enabled,
        }


class ToolExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    REQUIRES_PERMISSION = "requires_permission"
    VERIFICATION_FAILED = "verification_failed"


class ToolExecutionError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ToolVerificationResult(BaseModel):
    attempted: bool = False
    passed: bool = False
    evidence: Any = None


class ToolExecutionRequest(BaseModel):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] | None = None
    user_id: str
    workspace_id: str | None = None
    task_id: str | None = None
    step_id: str | None = None
    target_app: str | None = None
    target_device: str | None = None
    bypass_confirmation: bool = False
    confirmation_token: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.arguments and self.input:
            self.arguments = dict(self.input)


class ToolExecutionResult(BaseModel):
    tool_id: str
    success: bool
    status: ToolExecutionStatus = ToolExecutionStatus.COMPLETED
    target_app: str | None = None
    target_device: str | None = None
    output: Any = None
    error: str | None = None
    error_details: ToolExecutionError | None = None
    verification: ToolVerificationResult | None = None
    duration_ms: int = 0

    def model_post_init(self, __context: Any) -> None:
        if not self.success and self.status == ToolExecutionStatus.COMPLETED:
            self.status = ToolExecutionStatus.FAILED
        if self.error and self.error_details is None:
            self.error_details = ToolExecutionError(
                code=self.status.value,
                message=self.error,
                retryable=self.status in (ToolExecutionStatus.TIMEOUT, ToolExecutionStatus.REQUIRES_CONFIRMATION),
            )
        elif self.error_details and not self.error:
            self.error = self.error_details.message
