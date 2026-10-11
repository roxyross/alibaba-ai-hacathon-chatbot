"""Pydantic schemas for Browser Automation & Web Studio (Phase 15)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrowserTaskCreate(BaseModel):
    """Payload to create a new browser automation task."""

    url: str = Field(..., min_length=1, max_length=65536)
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

    url: str = Field(..., min_length=1, max_length=65536)
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

    url: str = Field(..., min_length=1, max_length=65536)
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

    url: str = Field(..., min_length=1, max_length=65536)
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

    url: str = Field(..., min_length=1, max_length=65536)
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


# =============================================================================
# Phase 10: Browser Automation Hardening Models (Playwright Persistent Sessions)
# =============================================================================

class BrowserTabModel(BaseModel):
    """Model representing an open browser tab."""

    tab_id: str = Field(..., description="Unique identifier for the tab")
    url: str = Field(default="about:blank", description="Current URL of the tab")
    title: str = Field(default="", description="Current page title")
    is_active: bool = Field(default=False, description="Whether this tab is foreground active")


class BrowserSessionModel(BaseModel):
    """Model representing a persistent, managed browser session."""

    session_id: str = Field(..., description="Session identifier")
    device_id: str = Field(default="current_host", description="Host machine where browser runs")
    browser: str = Field(default="chromium", description="Browser engine: chromium, firefox, webkit")
    profile: str = Field(default="default", description="Persistent profile name or storage key")
    tabs: list[BrowserTabModel] = Field(default_factory=list, description="Open tabs in this session")
    active_tab_id: str | None = Field(default=None, description="Active tab ID")
    current_url: str = Field(default="about:blank", description="Current URL of active tab")
    authenticated_state: bool = Field(default=False, description="Whether cookies/auth tokens exist in session")
    created_at: str = Field(default="", description="ISO creation timestamp")
    last_active_at: str = Field(default="", description="ISO last activity timestamp")
    is_closed: bool = Field(default=False, description="Whether session is terminated")


class BrowserLaunchRequest(BaseModel):
    """Request to launch a persistent browser session."""

    profile_name: str = Field(default="default", description="User profile directory identifier")
    headless: bool = Field(default=True, description="Run headless or headed")
    browser_type: str = Field(default="chromium", description="chromium, firefox, or webkit")
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=800, ge=240, le=2160)
    user_agent: str | None = Field(default=None, description="Custom User-Agent override")


class BrowserLaunchResponse(BaseModel):
    """Response returned upon launching or attaching to a browser session."""

    session: BrowserSessionModel
    message: str = "Browser session active."


class BrowserNavigateHardenedRequest(BaseModel):
    """Request to navigate a browser session tab to a URL."""

    url: str = Field(..., min_length=1, max_length=65536)
    session_id: str | None = Field(default=None, description="Target session ID (auto-created if None)")
    tab_id: str | None = Field(default=None, description="Target tab ID (active tab if None)")
    wait_for: str | None = Field(default=None, description="Optional CSS/text selector to wait for")
    timeout_seconds: int = Field(default=30, ge=1, le=120)


class BrowserNavigateHardenedResponse(BaseModel):
    """Response with real inspected page details from Playwright."""

    session_id: str
    tab_id: str
    url: str
    title: str
    final_url: str
    status: str = "success"
    content_preview: str = ""
    headings: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    forms: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BrowserDOMInspectRequest(BaseModel):
    """Request to inspect DOM accessibility tree and interactive elements."""

    session_id: str
    tab_id: str | None = None
    selector: str | None = Field(default=None, description="Optional root CSS selector to inspect")
    max_depth: int = Field(default=4, ge=1, le=10)


class BrowserDOMInspectResponse(BaseModel):
    """Response containing inspected interactive elements."""

    session_id: str
    tab_id: str
    url: str
    title: str
    elements: list[dict[str, Any]] = Field(default_factory=list)
    html_snippet: str = ""
    total_elements_found: int = 0


class BrowserElementInteractRequest(BaseModel):
    """Request to click, type, select, upload, or hover on a DOM element."""

    session_id: str
    tab_id: str | None = None
    selector: str = Field(..., description="CSS, text, XPath, or ARIA selector (e.g. 'button:has-text(\"Submit\")')")
    action: str = Field(default="click", description="click, type, select, hover, clear, press_enter, upload")
    text: str | None = Field(default=None, description="Text to type if action is 'type'")
    value: str | None = Field(default=None, description="Value or label to select if action is 'select'")
    files: list[str] | str | None = Field(default=None, description="Local file paths to upload if action is 'upload'")
    clear_first: bool = Field(default=True, description="Clear existing input before typing")
    delay_ms: int = Field(default=0, ge=0, le=1000, description="Delay between keystrokes")
    timeout_ms: int = Field(default=5000, ge=500, le=60000)


class BrowserElementInteractResponse(BaseModel):
    """Response from DOM element interaction."""

    session_id: str
    tab_id: str
    selector: str
    action: str
    success: bool
    verified: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BrowserUploadRequest(BaseModel):
    """Request to upload one or more files to a file input element."""

    session_id: str
    selector: str = Field(..., description="CSS selector for file input element (e.g. 'input[type=file]')")
    file_paths: list[str] | str = Field(..., description="Local path(s) of files to upload")
    tab_id: str | None = None
    timeout_ms: int = Field(default=10000, ge=500, le=60000)


class BrowserUploadResponse(BaseModel):
    """Response from file upload interaction."""

    session_id: str
    tab_id: str
    selector: str
    files_uploaded: list[str]
    success: bool
    verified: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @property
    def uploaded_files_count(self) -> int:
        return len(self.files_uploaded)

    @property
    def file_names(self) -> list[str]:
        return self.files_uploaded


class BrowserDownloadRequest(BaseModel):
    """Request to trigger and capture a file download in the browser."""

    session_id: str
    selector: str | None = Field(default=None, description="Element to click to trigger download")
    trigger_action: str = Field(default="click", description="Action to trigger download: click or wait")
    tab_id: str | None = None
    timeout_ms: int = Field(default=30000, ge=1000, le=120000)


class BrowserDownloadResponse(BaseModel):
    """Response containing captured downloaded file details."""

    session_id: str
    tab_id: str
    downloaded_path: str
    filename: str
    file_size_bytes: int = 0
    success: bool
    error: str | None = None


class BrowserScrollRequest(BaseModel):
    """Request to scroll the page or an element."""

    session_id: str
    tab_id: str | None = None
    direction: str = Field(default="down", description="down, up, top, bottom")
    amount: int = Field(default=500, ge=10, le=10000)
    selector: str | None = Field(default=None, description="Optional element selector to scroll")


class BrowserScrollResponse(BaseModel):
    """Response containing post-scroll coordinates."""

    session_id: str
    tab_id: str
    direction: str
    amount: int
    scroll_x: int
    scroll_y: int
    success: bool


class BrowserScreenshotHardenedRequest(BaseModel):
    """Request to take a real pixel screenshot via Playwright."""

    session_id: str | None = None
    tab_id: str | None = None
    url: str | None = None
    full_page: bool = Field(default=False)
    selector: str | None = None
    width: int = 1280
    height: int = 800


class BrowserScreenshotHardenedResponse(BaseModel):
    """Response containing real screenshot metadata and local path."""

    session_id: str | None
    screenshot_path: str
    base64_data: str | None = None
    width: int
    height: int
    success: bool
    error: str | None = None


class BrowserTabManageRequest(BaseModel):
    """Request to create, switch, or close tabs in a session."""

    session_id: str
    action: str = Field(default="new_tab", description="new_tab, close_tab, switch_tab, list_tabs")
    tab_id: str | None = Field(default=None, description="Tab ID to switch to or close")
    url: str | None = Field(default="about:blank", description="Initial URL if action is 'new_tab'")


class BrowserTabManageResponse(BaseModel):
    """Response with updated tab list and active tab."""

    session_id: str
    action: str
    active_tab_id: str
    tabs: list[BrowserTabModel] = Field(default_factory=list)


class BrowserWaitRequest(BaseModel):
    """Request to wait for a selector, state, or timeout."""

    session_id: str
    tab_id: str | None = None
    state: str = Field(default="visible", description="visible, hidden, attached, detached, networkidle")
    selector: str | None = None
    timeout_ms: int = Field(default=5000, ge=100, le=60000)


class BrowserWaitResponse(BaseModel):
    """Response from wait operation."""

    session_id: str
    tab_id: str
    success: bool
    waited_ms: float
    error: str | None = None


class BrowserPageStateResponse(BaseModel):
    """Comprehensive page state and telemetry without leaking secrets."""

    session_id: str
    tab_id: str
    url: str
    title: str
    ready_state: str
    viewport: dict[str, int]
    tabs_count: int
    has_cookies: bool
    authenticated_state: bool
    storage_keys: list[str] = Field(default_factory=list)

