"""Pydantic schemas for Cowork Workspace and Multi-Artifact Canvas."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ArtifactType(StrEnum):
    MARKDOWN = "markdown"
    CODE = "code"
    MERMAID = "mermaid"
    SVG = "svg"
    HTML = "html"
    DOCUMENT = "document"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    FINAL = "final"
    ARCHIVED = "archived"


class ArtifactVersion(BaseModel):
    id: str = Field(..., description="Unique version identifier")
    version_number: int = Field(..., description="Sequential version index starting at 1")
    content: str = Field(..., description="Snapshot content at this version")
    diff_from_previous: str | None = Field(default=None, description="Unified diff against the previous version")
    change_summary: str = Field(default="", description="Summary of changes in this revision")
    created_by: str = Field(default="user", description="'user' or 'agent'")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Artifact(BaseModel):
    id: str = Field(..., description="Unique artifact identifier")
    user_id: str = Field(..., description="Owner user ID")
    task_id: str | None = Field(default=None, description="Optional associated task ID")
    session_id: str | None = Field(default=None, description="Optional associated session ID")
    title: str = Field(..., description="Human-readable title of the artifact")
    artifact_type: ArtifactType = Field(default=ArtifactType.MARKDOWN)
    language: str = Field(default="markdown", description="Language tag, e.g. typescript, python, markdown, mermaid")
    content: str = Field(..., description="Latest artifact content")
    current_version: int = Field(default=1, description="Current active version number")
    versions: list[ArtifactVersion] = Field(default_factory=list, description="Historical version snapshots")
    status: ArtifactStatus = Field(default=ArtifactStatus.DRAFT)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata tags, links, or settings")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CreateArtifactRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    artifact_type: ArtifactType = Field(default=ArtifactType.MARKDOWN)
    content: str = Field(default="", description="Initial artifact content")
    language: str | None = Field(default=None, description="Language or syntax mode")
    task_id: str | None = Field(default=None)
    session_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateArtifactRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, description="Updated content")
    status: ArtifactStatus | None = Field(default=None)
    change_summary: str = Field(default="Updated artifact content")
    metadata: dict[str, Any] | None = Field(default=None)


class RefineArtifactRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=2000, description="Human instruction or critique to refine artifact")
    target_aspect: str = Field(default="general", description="Aspect to prioritize: general, styling, structure, performance, fix_errors")


class RenderDiagramRequest(BaseModel):
    diagram_type: str = Field(default="mermaid", description="'mermaid' or 'svg'")
    specification: str = Field(default="flowchart", description="flowchart, sequence, class, state, or architecture")
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    nodes: list[dict[str, str]] | None = Field(default=None)
    relationships: list[dict[str, str]] | None = Field(default=None)


class RevertVersionRequest(BaseModel):
    version_number: int = Field(..., ge=1, description="Version number to restore")


class DiffReviewResponse(BaseModel):
    artifact_id: str
    from_version: int
    to_version: int
    unified_diff: str
    additions: int
    deletions: int
