"""Pydantic v2 schemas for Semantic Memory and Memory Curator (Phase 18)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ImportanceLevel = Literal["low", "normal", "high", "forever"]


class MemoryCreateRequest(BaseModel):
    """Payload to store a new long-term semantic memory."""

    content: str = Field(..., min_length=1, max_length=4000, description="The fact, preference, or context to remember")
    importance: ImportanceLevel = Field(default="normal", description="Importance rating (forever exempts from curator pruning)")
    source: str = Field(default="user:explicit", max_length=50, description="Originating agent or user action")
    tags: list[str] = Field(default_factory=list, description="Categorization tags for clustering and retrieval")


class MemoryUpdateRequest(BaseModel):
    """Payload to update an existing semantic memory."""

    content: str | None = Field(default=None, min_length=1, max_length=4000)
    importance: ImportanceLevel | None = None
    tags: list[str] | None = None
    is_soft_deleted: bool | None = None
    soft_delete_reason: str | None = None


class MemoryResponse(BaseModel):
    """Standard representation of a semantic memory entry."""

    id: str
    user_id: str
    content: str
    importance: str
    source: str
    tags: list[str]
    is_soft_deleted: bool
    soft_deleted_at: str | None = None
    soft_delete_reason: str | None = None
    cluster_id: str | None = None
    source_entry_ids: list[str] = Field(default_factory=list)
    retrieval_count: int
    last_retrieved_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class MemoryRetrieveRequest(BaseModel):
    """Request payload for semantic or keyword memory retrieval."""

    query: str | None = Field(default=None, description="Search terms or semantic query")
    tags: list[str] | None = Field(default=None, description="Filter memories by tag")
    importance: str | None = Field(default=None, description="Filter memories by importance level")
    top_k: int = Field(default=10, ge=1, le=50, description="Maximum entries to return")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum relevance score threshold")


class MemoryRetrieveItem(BaseModel):
    """Individual retrieved memory entry with computed score."""

    entry_id: str
    content: str
    importance: str
    source: str
    tags: list[str]
    score: float
    stored_at: str | None = None


class MemoryRetrieveResponse(BaseModel):
    """Result of memory retrieval."""

    entries: list[MemoryRetrieveItem]
    total_candidates: int


class CuratorPolicyConfig(BaseModel):
    """Configuration thresholds for the autonomous Memory Curator agent."""

    summarize_after_days: int = Field(default=30, ge=1, le=365)
    cluster_min_size: int = Field(default=3, ge=2, le=20)
    soft_delete_never_retrieved_days: int = Field(default=180, ge=7, le=730)
    hard_delete_after_days: int = Field(default=30, ge=1, le=365)
    notify_on_changes: bool = Field(default=True)


class CuratorRunResponse(BaseModel):
    """Report representation of a completed curator pass."""

    id: str
    user_id: str
    entries_scanned: int
    summarized_count: int
    clusters_formed: list[Any] = Field(default_factory=list)
    soft_deleted_count: int
    hard_deleted_count: int
    errors_count: int
    duration_ms: int
    status: str
    diff_summary: str
    created_at: str | None = None


class MemoryStatsResponse(BaseModel):
    """Developer and user telemetry for semantic memory."""

    total_memories: int
    active_memories: int
    forever_memories: int
    soft_deleted_memories: int
    curator_runs_count: int
    last_curated_at: str | None = None


class DataExportResponse(BaseModel):
    """Portable GDPR-compliant export bundle of user memory and preferences."""

    user_id: str
    exported_at: str
    total_memories: int
    memories: list[dict[str, Any]]
    note: str = "Portable personal AI memory vault archive."
