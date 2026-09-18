"""Pydantic schemas for Browser Automation & Web Studio (Phase 15)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrowserTaskCreate(BaseModel):
    """Payload to create a new browser automation task."""

    url: str = Field(..., min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=255)
    action_type: str = Field(default="navigate", max_length=32)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    result_data: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="pending", max_length=32)
    requires_confirmation: bool = Field(default=False)
    is_sensitive: bool = Field(default=False)
    tags: list[str] | str | None = Field(default=None)


class BrowserTaskUpdate(BaseModel):
    """Payload to patch an existing browser automation task."""

    title: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=32)
    result_data: dict[str, Any] | None = None
    error_message: str | None = None
    tags: list[str] | str | None = None


class BrowserTaskResponse(BaseModel):
    """Response returning a single browser task."""

    model_config = ConfigDict(from_attributes=True)
    task: dict[str, Any]


class BrowserTaskListResponse(BaseModel):
    """Response returning a paginated list of browser tasks."""

    model_config = ConfigDict(from_attributes=True)
    tasks: list[dict[str, Any]]
    total: int


class BrowserNavigateRequest(BaseModel):
    """Request to navigate to a URL and inspect DOM elements."""

    url: str = Field(..., min_length=1, max_length=2048)
    wait_for: str | None = Field(default=None, max_length=255)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    js_enabled: bool = Field(default=False)


class BrowserNavigateResponse(BaseModel):
    """Response with inspected page details."""

    url: str
    title: str | None = None
    final_url: str | None = None
    status: str = "success"
    content_preview: str = ""
    headings: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    forms: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BrowserExtractRequest(BaseModel):
    """Request to extract structured content (tables, links, headings) from a page."""

    url: str = Field(..., min_length=1, max_length=2048)
    extract_type: str = Field(
        default="all",
        description="Target element type: all, tables, links, headings, text",
    )
    selectors: list[str] | None = Field(default=None)
    max_items: int = Field(default=50, ge=1, le=200)


class BrowserExtractResponse(BaseModel):
    """Structured extraction response."""

    url: str
    title: str | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    headings: list[dict[str, Any]] = Field(default_factory=list)
    text_excerpt: str = ""
    status: str = "success"
    error: str | None = None


class BrowserScreenshotRequest(BaseModel):
    """Request to capture a visual preview of a web page."""

    url: str = Field(..., min_length=1, max_length=2048)
    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=800, ge=240, le=2160)


class BrowserScreenshotResponse(BaseModel):
    """Response containing screenshot visual snapshot."""

    url: str
    title: str | None = None
    screenshot_url: str
    width: int = 1280
    height: int = 800
    status: str = "success"
    timestamp: str


class BrowserExecuteFlowRequest(BaseModel):
    """Request to execute a multi-step browser automation workflow."""

    url: str = Field(..., min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=255)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    save_task: bool = Field(default=True)
    tags: list[str] | None = Field(default=None)


class BrowserExecuteFlowResponse(BaseModel):
    """Response containing flow execution steps and final result data."""

    task_id: str | None = None
    url: str
    title: str
    status: str  # completed, failed, confirmation_required
    steps_executed: list[dict[str, Any]] = Field(default_factory=list)
    result_data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
