"""Pydantic v2 schemas for Code Snippets, Executions, and AI Assistants (Phase 17)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CodeSnippetCreate(BaseModel):
    """Schema for creating a user code snippet."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    language: str = Field(default="python", max_length=50)
    code: str = Field(min_length=1)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_favorite: bool = False


class CodeSnippetUpdate(BaseModel):
    """Schema for updating an existing code snippet."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, max_length=50)
    code: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_favorite: bool | None = None


class CodeSnippetResponse(BaseModel):
    """Schema for returning code snippet details."""

    id: str
    user_id: str
    title: str
    language: str
    code: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_favorite: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class CodeSnippetListResponse(BaseModel):
    """Schema for listing user code snippets."""

    snippets: list[CodeSnippetResponse]
    total: int


# ---------------------------------------------------------------------------
# AI Coding Assistant Schemas
# ---------------------------------------------------------------------------

class CodeGenerateRequest(BaseModel):
    """Schema for AI code generation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    task: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="python", max_length=50)
    context_files: list[str] | None = None
    constraints: list[str] | None = None
    save_as_snippet: bool = False
    snippet_title: str | None = None


class CodeGenerateResponse(BaseModel):
    """Schema for returning generated code."""

    code: str
    language: str
    explanation: str
    warnings: list[str] = Field(default_factory=list)
    saved_snippet_id: str | None = None


class CodeExplainRequest(BaseModel):
    """Schema for AI code explanation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1)
    language: str = Field(default="python", max_length=50)
    scope: str = Field(default="block")  # line, block, file, module
    level: str = Field(default="intermediate")  # eli5, beginner, intermediate, expert
    focus: str | None = None


class CodeExplainResponse(BaseModel):
    """Schema for returning code explanation."""

    explanation: str
    language: str
    key_lines: list[dict[str, Any]] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)


class CodeDebugRequest(BaseModel):
    """Schema for AI code debugging and fix proposal."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1)
    language: str = Field(default="python", max_length=50)
    error_message: str | None = None
    expected_behavior: str | None = None
    actual_behavior: str | None = None


class CodeDebugResponse(BaseModel):
    """Schema for returning diagnostic debug analysis."""

    hypothesis: str
    evidence: str
    fix: str
    fixed_code: str
    verification: str
    alternatives: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Code Execution Schemas
# ---------------------------------------------------------------------------

class CodeExecuteRequest(BaseModel):
    """Schema for running code in the sandboxed environment."""

    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1)
    language: str = Field(default="python", max_length=50)
    stdin: str | None = None
    snippet_id: str | None = None


class CodeExecuteResponse(BaseModel):
    """Schema for code execution results."""

    id: str
    language: str
    status: str  # success, error, timeout
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
    created_at: str | None = None


class CodeExecutionListResponse(BaseModel):
    """Schema for listing execution run logs."""

    executions: list[CodeExecuteResponse]
    total: int


# ---------------------------------------------------------------------------
# Stats Schema
# ---------------------------------------------------------------------------

class CodeStatsResponse(BaseModel):
    """Schema for developer studio usage statistics."""

    total_snippets: int
    favorite_snippets: int
    languages_count: dict[str, int]
    total_executions: int
    successful_executions: int
    success_rate_percentage: float
