"""Pydantic v2 models for AI Gateway request/response types.

Schema definitions mirror data-model.md — any changes must be reflected there.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class CircuitState(str, Enum):
    CLOSED = "closed"
    HALF_OPEN = "half_open"
    OPEN = "open"


class TaskType(str, Enum):
    GENERAL = "general"
    CODING = "coding"
    REASONING = "reasoning"


# -----------------------------------------------------------------------------
# Message
# -----------------------------------------------------------------------------

class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """A single chat message."""

    model_config = ConfigDict(str_strip_whitespace=True)

    role: MessageRole
    content: str


# -----------------------------------------------------------------------------
# AI Request / Response
# -----------------------------------------------------------------------------

class AIRequest(BaseModel):
    """Inbound chat request from an agent or tool."""

    model_config = ConfigDict(str_strip_whitespace=True)

    messages: list[Message]
    provider: str | None = None  # Request-level override
    model: str | None = None  # Request-level model override (e.g. "deepseek-chat-v3")
    task_type: TaskType = TaskType.GENERAL
    temperature: float = Field(ge=0, le=2, default=0.7)
    max_tokens: int | None = Field(gt=0, default=None)
    stream: bool = False
    timeout_seconds: float | None = Field(gt=0, le=60, default=None)
    user_id: str | None = None
    agent_id: str | None = None
    request_id: UUID | None = None  # Optional client-supplied trace ID
    session_id: str | None = None  # When set, both turns are persisted to chat_history.


class AIResponse(BaseModel):
    """Outbound chat response with attribution and telemetry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    content: str
    provider: str
    model: str
    agent_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    request_id: UUID


class StreamingChunk(BaseModel):
    """A single chunk in a streaming SSE response."""

    model_config = ConfigDict(str_strip_whitespace=True)

    delta: str
    provider: str
    model: str
    done: bool = False


# -----------------------------------------------------------------------------
# Provider Status
# -----------------------------------------------------------------------------

class ProviderStatus(BaseModel):
    """Health and circuit state for a single provider."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    status: HealthStatus
    circuit_state: CircuitState
    last_error: str | None = None
    last_success: datetime | None = None


class ProviderHealthResponse(BaseModel):
    """Response model for GET /providers/health."""

    model_config = ConfigDict(str_strip_whitespace=True)

    providers: list[ProviderStatus]


# -----------------------------------------------------------------------------
# Error Response
# -----------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Structured error returned by all gateway endpoints."""

    model_config = ConfigDict(str_strip_whitespace=True)

    error: str
    code: str
    detail: str | None = None
    provider_error: bool = False
    failed_provider: str | None = None


# -----------------------------------------------------------------------------
# Token Usage Log
# -----------------------------------------------------------------------------

class TokenUsageLog(BaseModel):
    """Immutable audit log entry for a single AI request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: UUID
    request_id: UUID
    provider_id: UUID
    model_id: UUID
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    provider_response_ms: int | None = None
    timestamp: datetime


class TokenUsageLogCreate(BaseModel):
    """Input model for creating a token usage log entry.

    provider_id and model_id are stored as String(36) in the SQLAlchemy
    TokenUsageLog table — stored as provider/model names for observability
    without requiring a DB join at log time.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    request_id: UUID
    provider_id: str  # provider name, e.g. "deepseek"
    model_id: str  # model name, e.g. "deepseek-chat-v3"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    provider_response_ms: int | None = None
