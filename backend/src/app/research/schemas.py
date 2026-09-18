"""Pydantic schemas for Autonomous Web Research & Information Retrieval (Phase 14)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchSource(BaseModel):
    """Normalized research web source reference."""

    title: str = Field(..., description="Title of the source webpage or article")
    url: str = Field(..., description="Canonical URL of the source")
    snippet: str = Field(default="", description="Relevant textual excerpt or snippet")
    domain: str = Field(default="", description="Hostname or publisher domain")
    published_date: str | None = Field(default=None, description="Publication timestamp or date")


class ResearchFinding(BaseModel):
    """Individual synthesized finding or claim with verified source attribution."""

    theme: str = Field(..., description="Key topical category or thematic group")
    claim: str = Field(..., description="Synthesized finding, fact, or comparison")
    source_indices: list[int] = Field(
        default_factory=list, description="1-based indices referencing verified sources list"
    )
    confidence: str = Field(
        default="medium", description="Confidence rating: high, medium, or low"
    )


class ResearchReportCreate(BaseModel):
    """Payload to create or persist a research report."""

    query: str = Field(..., min_length=2, description="Original research question or topic")
    title: str | None = Field(default=None, description="Optional custom title for the report")
    summary: str = Field(..., min_length=5, description="Executive summary synthesized from sources")
    findings: list[dict[str, Any]] = Field(
        default_factory=list, description="List of structured key findings"
    )
    sources: list[dict[str, Any]] = Field(
        default_factory=list, description="List of verified web sources with titles and URLs"
    )
    confidence: str = Field(default="medium", description="Overall confidence level")
    depth: str = Field(default="deep", description="Investigation depth: quick, deep, or academic")
    tags: list[str] = Field(default_factory=list, description="Categorization or project tags")


class ResearchReportUpdate(BaseModel):
    """Payload to update an existing research report."""

    title: str | None = None
    summary: str | None = None
    findings: list[dict[str, Any]] | None = None
    sources: list[dict[str, Any]] | None = None
    confidence: str | None = None
    depth: str | None = None
    tags: list[str] | None = None


class ResearchReportResponse(BaseModel):
    """Single research report response."""

    report: dict[str, Any]


class ResearchReportListResponse(BaseModel):
    """Collection of research reports response."""

    reports: list[dict[str, Any]]
    total: int


class LiveSearchRequest(BaseModel):
    """Direct live web search request."""

    query: str = Field(..., min_length=2, description="Search query string")
    num_results: int = Field(default=5, ge=1, le=20, description="Max results to retrieve")
    source: str | None = Field(default=None, description="Optional provider preference: tavily, duckduckgo, google, bing")


class LiveSearchResponse(BaseModel):
    """Live web search response."""

    query: str
    results: list[dict[str, Any]]
    total_results: int


class DeepResearchRequest(BaseModel):
    """Autonomous deep research workflow request."""

    query: str = Field(..., min_length=2, description="Research topic or question to investigate")
    depth: str = Field(default="deep", description="Investigation depth: quick, deep, or academic")
    save_report: bool = Field(default=True, description="Whether to persist the generated report")
    title: str | None = Field(default=None, description="Custom title override")
    tags: list[str] = Field(default_factory=list, description="Optional tags for the saved report")


class DeepResearchResponse(BaseModel):
    """Synthesized autonomous deep research response."""

    topic: str
    title: str
    summary: str
    findings: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    citations: list[str]
    confidence: str
    depth: str
    sub_queries: list[str]
    next_actions: list[str]
    report_id: str | None = None


class WebFetchRequest(BaseModel):
    """Request to fetch and extract content from a target URL."""

    url: str = Field(..., description="Target web page URL")
    max_chars: int = Field(default=4000, ge=100, le=20000, description="Max character length to extract")


class WebFetchResponse(BaseModel):
    """Response containing extracted web page text and metadata."""

    url: str
    title: str
    content: str
    domain: str
    status: str = "success"
