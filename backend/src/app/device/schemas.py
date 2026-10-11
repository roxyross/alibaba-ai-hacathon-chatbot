"""Pydantic schemas for Device Agent, App Discovery, and App Control."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    """Request to register or send heartbeat for a local/remote device."""

    device_name: str = Field(..., description="Human-readable device name")
    device_type: str = Field(default="desktop", description="desktop, laptop, mobile, or server")
    os_platform: str = Field(default="windows", description="windows, darwin, linux, android, ios")
    os_version: str = Field(default="", description="Operating system version string")
    architecture: str = Field(default="x86_64", description="CPU architecture")
    hostname: str = Field(default="localhost", description="System hostname")
    ip_address: str = Field(default="127.0.0.1", description="Device IP address")
    capabilities: list[str] = Field(
        default_factory=lambda: ["app_discovery", "process_control", "screen_capture", "system_commands"]
    )
    telemetry: dict[str, Any] = Field(default_factory=dict)


class DeviceTelemetryResponse(BaseModel):
    """Real-time system telemetry and hardware metrics."""

    device_id: str
    hostname: str
    os_platform: str
    cpu_percent: float
    memory_percent: float
    disk_free_gb: float
    active_window: str | None = None
    battery_percent: float | None = None
    timestamp: str


class DiscoveredAppResponse(BaseModel):
    """Metadata for an installed or active desktop application."""

    id: str
    user_id: str
    device_id: str
    app_name: str
    executable_path: str
    bundle_id: str | None = None
    category: str
    version: str | None = None
    publisher: str | None = None
    description: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    supported_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    install_location: str | None = None
    is_system_app: bool = False
    icon_url: str | None = None
    is_running: bool
    process_id: int | None = None
    launch_count: int = 0
    last_launched_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DeviceResponse(BaseModel):
    """Registered device response representation."""

    id: str
    user_id: str
    workspace_id: str | None = None
    device_name: str
    device_type: str
    os_platform: str
    os_version: str
    architecture: str
    hostname: str
    ip_address: str
    status: str
    is_current_host: bool
    hardware_fingerprint: str | None = None
    daemon_version: str | None = None
    capabilities: list[str]
    telemetry: dict[str, Any]
    last_heartbeat_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AppLaunchRequest(BaseModel):
    """Request to launch a discovered application or executable."""

    target: str | None = Field(default=None, description="Universal app identifier, path, or URI scheme")
    app_id: str | None = Field(default=None, description="Discovered app ID if known")
    app_name: str | None = Field(default=None, description="App name or binary command")
    executable_path: str | None = Field(default=None, description="Explicit executable path")
    app_name_or_path: str | None = Field(default=None, description="Universal app identifier or path")
    arguments: list[str] = Field(default_factory=list, description="Command line arguments")
    working_directory: str | None = Field(default=None, description="Optional working directory")
    environment: dict[str, str] | None = Field(default=None, description="Optional extra environment variables")
    wait_for_window: bool = Field(default=False, description="Wait until the application window appears")
    window_timeout_sec: float = Field(default=5.0, description="Max seconds to wait for window appearance")


class AppCloseRequest(BaseModel):
    """Request to close or terminate an application."""

    app_id: str | None = Field(default=None)
    app_name: str | None = Field(default=None)
    app_name_or_pid: str | int | None = Field(default=None)
    process_id: int | None = Field(default=None)
    force: bool = Field(default=False, description="Whether to kill forcibly (SIGKILL / taskkill /f)")


class AppFocusRequest(BaseModel):
    """Request to focus an application window."""

    app_name: str = Field(..., description="App name or window title to focus")


class ScreenCaptureResponse(BaseModel):
    """Screen capture result with static image path and data URL."""

    device_id: str
    image_url: str
    image_base64: str | None = None
    width: int
    height: int
    captured_at: str


class AppScanRequest(BaseModel):
    """Parameters to control application discovery scan depth."""

    force_refresh: bool = Field(default=False, description="Bypass cache and force deep system re-scan")
    include_system_apps: bool = Field(default=False, description="Include low-level OS utilities and background services")


class AppScanResponse(BaseModel):
    """Result of app discovery scan."""

    device_id: str
    scanned_count: int
    discovered_apps: list[DiscoveredAppResponse]
    categories_summary: dict[str, int] = Field(default_factory=dict)
    running_count: int = 0
    scan_duration_ms: float


class DiscoveredAppBulkSyncRequest(BaseModel):
    """Payload submitted by device daemon to synchronize discovered applications catalog."""

    apps: list[dict[str, Any]] = Field(..., description="List of discovered application dictionaries")


class DiscoveredAppBulkSyncResponse(BaseModel):
    """Result of catalog sync."""

    synced_count: int
    device_id: str
    message: str = "Application catalog synchronized successfully."


class DeviceActionLogResponse(BaseModel):
    """Action log record."""

    id: str
    user_id: str
    device_id: str
    action_type: str
    target: str
    parameters: dict[str, Any]
    status: str
    result: dict[str, Any]
    error_message: str | None = None
    executed_at: str | None = None


# =============================================================================
# Phase 11: Cross-Device Continuity & Session Handover Schemas
# =============================================================================

class SessionHandoverCreateRequest(BaseModel):
    """Request to initiate a cross-device session handover."""

    target_device_id: str = Field(..., description="ID of destination device")
    session_id: str = Field(..., description="Active session ID being transferred")
    source_device_id: str | None = Field(default=None, description="Optional source device ID (defaults to current host)")
    state_payload: dict[str, Any] = Field(default_factory=dict, description="Active conversation, draft, or workspace context")
    ttl_seconds: int = Field(default=600, ge=60, le=86400, description="Handover token validity period")


class SessionHandoverResponse(BaseModel):
    """Response representing a cross-device session handover record."""

    id: str
    user_id: str
    session_id: str
    source_device_id: str
    target_device_id: str
    status: str  # pending, accepted, completed, expired, rejected
    state_payload: dict[str, Any]
    expires_at: str
    completed_at: str | None = None
    created_at: str


# =============================================================================
# Phase 11: P2P WebRTC Signaling Schemas
# =============================================================================

class WebRTCSessionCreateRequest(BaseModel):
    """Request to establish a WebRTC P2P signaling session between paired devices."""

    target_device_id: str = Field(..., description="Destination peer device ID")
    initiator_device_id: str | None = Field(default=None, description="Initiating peer device ID")
    session_type: str = Field(default="data_channel", description="data_channel, screen_stream, audio_call, file_sync")
    sdp_offer: str | None = Field(default=None, description="Initial SDP Offer description if ready")


class WebRTCSignalRequest(BaseModel):
    """Signal exchange packet (SDP offer/answer, ICE candidate, or status)."""

    sender_device_id: str = Field(..., description="Device sending this signal")
    signal_type: str = Field(..., description="offer, answer, candidate, or close")
    payload: Any = Field(..., description="SDP string or ICE candidate dictionary")


class WebRTCSessionResponse(BaseModel):
    """WebRTC peer session state."""

    id: str
    user_id: str
    initiator_device_id: str
    target_device_id: str
    session_type: str
    status: str  # negotiating, connected, closed, failed
    sdp_offer: str | None = None
    sdp_answer: str | None = None
    ice_candidates: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    updated_at: str


# =============================================================================
# Phase 11: Matter & Zigbee IoT Smart Home Schemas
# =============================================================================

class IoTDeviceResponse(BaseModel):
    """Representation of a Matter, Zigbee, or Thread smart home device."""

    id: str
    user_id: str
    device_name: str
    device_type: str  # light, plug, thermostat, lock, sensor
    protocol: str  # matter, zigbee, thread
    vendor: str
    model: str
    node_id: str
    endpoint: int
    is_online: bool
    state: dict[str, Any]
    created_at: str
    updated_at: str


class IoTDiscoverRequest(BaseModel):
    """Parameters for discovering local Matter/IoT devices."""

    protocol: str = Field(default="all", description="all, matter, zigbee, thread")
    device_type: str = Field(default="all", description="all, light, plug, thermostat, lock, sensor")


class IoTDiscoverResponse(BaseModel):
    """Discovered smart home devices scan result."""

    discovered_count: int
    devices: list[IoTDeviceResponse]
    scan_timestamp: str


class IoTControlRequest(BaseModel):
    """Control command for smart home devices."""

    command: str = Field(..., description="turn_on, turn_off, toggle, set_brightness, set_temperature, set_color")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Command parameters (e.g. brightness, temperature, color)")


class IoTLockRequest(BaseModel):
    """Action request for smart door locks / security gates."""

    action: str = Field(..., description="lock or unlock")
    reason: str | None = Field(default=None, description="Optional audit reason")


# =============================================================================
# Phase 3: Standalone Roxy Device Agent Enrollment & Command Queue Schemas
# =============================================================================

class EnrollmentTokenCreateRequest(BaseModel):
    """Request to generate a pairing token for enrolling a new standalone agent."""

    label: str = Field(default="Device Enrollment Token", description="Human-readable label for device or location")
    ttl_seconds: int = Field(default=900, description="Validity period in seconds (default 15 minutes)")


class EnrollmentTokenResponse(BaseModel):
    """Temporary enrollment token representation."""

    id: str
    token: str
    label: str
    expires_at: str
    is_claimed: bool
    created_at: str


class EnrollmentClaimRequest(BaseModel):
    """Payload submitted by a standalone daemon to claim an enrollment token and pair."""

    enrollment_token: str = Field(..., description="15-minute one-time pairing token")
    device_name: str = Field(..., description="Device hostname or friendly name")
    device_type: str = Field(default="desktop", description="desktop, laptop, mobile, or server")
    os_platform: str = Field(..., description="windows, darwin, linux, android, ios")
    os_version: str = Field(default="", description="Operating system release / version")
    architecture: str = Field(default="x86_64", description="CPU architecture")
    hostname: str = Field(default="localhost", description="System hostname")
    ip_address: str = Field(default="127.0.0.1", description="Reported network IP")
    hardware_fingerprint: str = Field(..., description="Deterministic hardware fingerprint string")
    daemon_version: str = Field(default="1.0.0", description="Installed daemon software version")
    capabilities: list[str] = Field(
        default_factory=lambda: ["app_discovery", "process_control", "screen_capture", "system_commands"]
    )
    telemetry: dict[str, Any] = Field(default_factory=dict)


class EnrollmentClaimResponse(BaseModel):
    """Credentials returned to the standalone daemon upon successful pairing."""

    device_id: str
    device_name: str
    device_token: str = Field(..., description="Permanent secret token for daemon authentication")
    status: str = "online"
    message: str = "Device successfully enrolled and paired."


class DeviceHeartbeatRequest(BaseModel):
    """Telemetry payload periodically sent by the running daemon."""

    telemetry: dict[str, Any] = Field(default_factory=dict)
    daemon_version: str | None = None


class DeviceHeartbeatResponse(BaseModel):
    """Acknowledgment of heartbeat with pending commands count."""

    device_id: str
    status: str
    acknowledged_at: str
    pending_commands_count: int = 0


class DeviceCommandQueueRequest(BaseModel):
    """Request to queue an action for remote execution on an enrolled device."""

    command_type: str = Field(..., description="launch_app, close_app, focus_app, screen_capture, app_scan, system_telemetry, ping")
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, description="Expiration TTL for pending command")


class DeviceCommandResponse(BaseModel):
    """Representation of an asynchronous command in the device queue."""

    id: str
    device_id: str
    user_id: str
    command_type: str
    payload: dict[str, Any]
    status: str
    result: Any = None
    error: str | None = None
    created_at: str
    dispatched_at: str | None = None
    completed_at: str | None = None
    expires_at: str


class DeviceCommandResultSubmission(BaseModel):
    """Result reported by a daemon after completing a command."""

    status: str = Field(..., description="completed or failed")
    result: Any = None
    error: str | None = None


# =============================================================================
# UI Automation Schemas (Phase 4: Windows UI Automation)
# =============================================================================

class UIBoundsSchema(BaseModel):
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    width: int = 0
    height: int = 0


class UIElementResponse(BaseModel):
    role: str = Field(..., description="Normalized UI role (window, button, edit, etc.)")
    name: str = ""
    automation_id: str = ""
    control_type: str = ""
    bounds: UIBoundsSchema = Field(default_factory=UIBoundsSchema)
    enabled: bool = True
    visible: bool = True
    value: str | None = None
    children: list[UIElementResponse] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class UIInspectRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="HWND, PID, title, or executable name")
    max_depth: int = Field(default=3, description="Depth of child tree to inspect")
    max_children: int = Field(default=50, description="Max children per node")


class UIFindElementRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window")
    name: str | None = None
    automation_id: str | None = None
    control_type: str | None = None
    role: str | None = None
    timeout_sec: float = Field(default=5.0, description="Maximum search duration in seconds")


class UIClickElementRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window")
    name: str | None = None
    automation_id: str | None = None
    control_type: str | None = None
    click_type: str = Field(default="click", description="click, right_click, or double_click")


class UITypeTextRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window")
    text: str = Field(..., description="Text content to type")
    name: str | None = None
    automation_id: str | None = None
    control_type: str | None = None
    clear_first: bool = False
    press_enter: bool = False


class UISendHotkeyRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window")
    hotkey: str = Field(..., description="Keystroke sequence, e.g. 'ctrl+s', 'alt+f4', 'enter'")


class UIScrollRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window")
    name: str | None = None
    automation_id: str | None = None
    direction: str = Field(default="down", description="up, down, left, right")
    amount: int = Field(default=1, description="Scroll step count")


class UIWindowStateRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window HWND, PID, or title")


class UIWindowStateResponse(BaseModel):
    exists: bool = False
    hwnd: int = 0
    title: str = ""
    pid: int = 0
    process_name: str = ""
    class_name: str = ""
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
    is_visible: bool = False
    bounds: UIBoundsSchema = Field(default_factory=UIBoundsSchema)


class UIScreenshotRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Optional window to isolate, or None for entire desktop")


class UIScreenshotResponse(BaseModel):
    success: bool = True
    target: str = "Desktop"
    width: int = 0
    height: int = 0
    format: str = "image/png"
    base64_data: str = ""
    size_bytes: int = 0
    timestamp: float = 0.0


class UISelectElementRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window")
    name: str | None = None
    automation_id: str | None = None
    item_name: str | None = None


class UIWaitForElementRequest(BaseModel):
    window_target: str | int | None = Field(default=None, description="Target window")
    name: str | None = None
    automation_id: str | None = None
    control_type: str | None = None
    timeout_sec: float = Field(default=10.0, description="Seconds to poll before timing out")


class UIActionResponse(BaseModel):
    success: bool = True
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class DiscoverCapabilitiesRequest(BaseModel):
    probe_live: bool = Field(default=True, description="Perform live verification probes")
    register_tools: bool = Field(default=True, description="Dynamically register generated tools into ToolRegistry")


class ExecuteAppActionRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action arguments, flags, and parameters")


# -----------------------------------------------------------------------------
# Phase 8: Process Lifecycle Controller Models
# -----------------------------------------------------------------------------

class ProcessInfoModel(BaseModel):
    """Telemetry and identity for a running OS process."""

    pid: int
    name: str
    exe: str | None = None
    cmdline: list[str] = Field(default_factory=list)
    cpu_percent: float = 0.0
    memory_rss_mb: float = 0.0
    memory_vms_mb: float = 0.0
    status: str = "running"
    create_time: float = 0.0
    username: str | None = None


class ProcessDetailsModel(BaseModel):
    """In-depth telemetry and relationships for an OS process."""

    pid: int
    ppid: int | None = None
    name: str
    exe: str | None = None
    cmdline: list[str] = Field(default_factory=list)
    cpu_percent: float = 0.0
    memory_rss_mb: float = 0.0
    memory_vms_mb: float = 0.0
    status: str = "running"
    create_time: float = 0.0
    username: str | None = None
    num_threads: int = 1
    open_files_count: int = 0
    children_pids: list[int] = Field(default_factory=list)
    cwd: str | None = None


class ProcessLaunchRequest(BaseModel):
    """Request to launch an application, binary, or URI scheme."""

    target: str = Field(..., description="App name, executable path, or URI scheme (e.g. 'notepad', 'code', 'slack://')")
    arguments: list[str] = Field(default_factory=list, description="Command-line arguments")
    working_directory: str | None = Field(default=None, description="Working directory")
    environment: dict[str, str] | None = Field(default=None, description="Optional extra environment variables")
    wait_for_window: bool = Field(default=False, description="Wait until the application window appears")
    window_timeout_sec: float = Field(default=5.0, description="Max seconds to wait for window appearance")


class ProcessLaunchResultModel(BaseModel):
    """Outcome of process launch."""

    success: bool
    pid: int | None = None
    target: str
    status: str = "completed"
    executable_path: str | None = None
    window_detected: bool = False
    window_title: str | None = None
    error: str | None = None
    duration_ms: float = 0.0


class ProcessTerminationRequest(BaseModel):
    """Request to gracefully close or forcibly terminate a process."""

    target: str | int = Field(..., description="Target process PID or application name")
    force: bool = Field(default=False, description="Force termination (SIGKILL / TerminateProcess)")
    timeout_sec: float = Field(default=5.0, description="Grace period before killing forcibly")
    terminate_children: bool = Field(default=True, description="Recursively terminate child process tree")


class ProcessTerminationResultModel(BaseModel):
    """Outcome of process termination."""

    success: bool
    target: str
    terminated_pids: list[int] = Field(default_factory=list)
    already_dead: bool = False
    error: str | None = None


class ProcessRestartRequest(BaseModel):
    """Request to restart an active application."""

    target: str | int = Field(..., description="Target process PID or application name")
    force: bool = Field(default=False, description="Force termination before relaunch")
    arguments: list[str] | None = Field(default=None, description="Optional new arguments; preserves previous if None")
    wait_timeout_sec: float = Field(default=5.0, description="Seconds to wait for process exit before relaunch")


class ProcessFocusRequest(BaseModel):
    """Request to activate and focus an application window."""

    target: str | int = Field(..., description="Process PID, application name, or window title")


# -----------------------------------------------------------------------------
# Phase 8: Integration Resolution Engine Models
# -----------------------------------------------------------------------------

IntegrationType = Literal[
    "cloud_connector",
    "mcp_tool",
    "cli_process",
    "desktop_ui_automation",
    "mobile_bridge",
    "system_launcher",
    "browser_automation",
    "unsupported",
]

ExecutionMethodType = Literal[
    "connector_api",
    "mcp_call",
    "cli_exec",
    "desktop_ui",
    "mobile_ui",
    "process_launch",
    "browser_session",
    "none",
]

VerificationMethodType = Literal[
    "api_status_check",
    "mcp_result_schema_validation",
    "process_exit_code_and_output",
    "window_state_probe",
    "accessibility_tree_match",
    "mobile_ui_dump_match",
    "mobile_intent_and_ui_hierarchy",
    "process_pid_and_window_presence",
    "dom_element_state_probe",
    "ios_link_or_scheme_probe",
    "ios_shortcut_probe",
    "ios_app_intent_probe",
    "ios_share_sheet_probe",
    "ios_companion_telemetry_probe",
    "whatsapp_status_check",
    "whatsapp_delivery_probe",
    "none",
]


class IntegrationCandidateModel(BaseModel):
    """Evaluated integration pathway candidate for an application capability."""

    integration: IntegrationType
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    execution_method: ExecutionMethodType
    verification_method: VerificationMethodType
    required_permission: str = Field(..., description="Target-scoped permission identifier (e.g. 'app:spotify:play')")
    risk: str = Field(default="LOW", description="Risk classification: LOW, MEDIUM, HIGH, CRITICAL")
    requires_confirmation: bool = Field(default=False, description="Whether explicit user confirmation is enforced")
    source: str = Field(..., description="Discovery source (e.g. active_connector, mcp_server, desktop_window)")
    description: str = Field(..., description="Human-readable explanation of why this path was evaluated")
    handler_target: str | None = Field(default=None, description="Concrete identifier of the executing handler or tool")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Pre-resolved or default parameter mappings")


class IntegrationResolutionRequest(BaseModel):
    """Input contract for the Integration Resolution Engine."""

    application: str = Field(..., description="Target application name, identifier, or URI (e.g. 'spotify', 'slack', 'notepad')")
    requested_capability: str = Field(..., description="Requested capability, action, or intent (e.g. 'play_music', 'send_message', 'launch')")
    device: dict[str, Any] | None = Field(default=None, description="Optional target device metadata and platform info")
    user_context: dict[str, Any] | None = Field(default=None, description="User credentials, active accounts, OAuth tokens, and preferences")
    preferred_integration: IntegrationType | None = Field(default=None, description="Optional caller preference or override")


class IntegrationResolutionResult(BaseModel):
    """Output contract produced by IntegrationResolver."""

    success: bool
    application: str
    requested_capability: str
    chosen_integration: IntegrationType
    confidence: float = Field(..., ge=0.0, le=1.0)
    required_permission: str
    risk: str
    requires_confirmation: bool
    execution_method: ExecutionMethodType
    verification_method: VerificationMethodType
    handler_target: str | None = None
    candidates: list[IntegrationCandidateModel] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str | None = None
    duration_ms: float = 0.0

    @property
    def integration(self) -> IntegrationType:
        """Alias for chosen_integration."""
        return self.chosen_integration


# =============================================================================
# Phase 9: Universal App Control Orchestrator Schemas
# =============================================================================

AppControlLifecycleStage = Literal[
    "resolved",
    "permission_checked",
    "planned",
    "executed",
    "verified",
    "failed",
    "pending_confirmation",
    "permission_denied",
    "unsupported",
    "blocked",
]


class AppControlPlanStep(BaseModel):
    """Discrete executable step within an AppControlExecutionPlan."""

    step_number: int
    name: str
    action: str
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    output: Any | None = None
    error: str | None = None
    duration_ms: float = 0.0


class AppControlExecutionPlan(BaseModel):
    """Complete, auditable execution plan synthesized before execution."""

    plan_id: str
    application: str
    capability: str
    chosen_integration: IntegrationType
    execution_method: ExecutionMethodType
    verification_method: VerificationMethodType
    required_permission: str
    risk: str
    requires_confirmation: bool
    confirmed: bool = False
    steps: list[AppControlPlanStep] = Field(default_factory=list)
    verification_criteria: dict[str, Any] = Field(default_factory=dict)
    estimated_duration_ms: float = 0.0


class AppControlExecutionRequest(BaseModel):
    """Input request contract for UniversalAppController."""

    application: str = Field(..., description="Target application name (e.g. 'Spotify', 'Slack', 'Calculator', 'git')")
    capability: str = Field(..., description="Target capability or action (e.g. 'play_music', 'send_message', 'launch', 'terminate')")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action arguments, inputs, or flags")
    preferred_integration: IntegrationType | None = Field(default=None, description="Optional override preference for integration surface")
    device_id: str | None = Field(default="local", description="Target device ID ('local' or specific UUID)")
    user_id: str | None = Field(default=None, description="User ID for authorization and context")
    device_context: dict[str, Any] | None = Field(default=None, description="Device metadata and telemetry context")
    user_context: dict[str, Any] | None = Field(default=None, description="OAuth credentials, tokens, active accounts")
    confirmed: bool = Field(default=False, description="Whether caller explicitly confirms execution of this action")
    confirmation_token: str | None = Field(default=None, description="Confirmation token for previously pending action")
    skip_verification: bool = Field(default=False, description="Whether to bypass post-condition state verification")
    timeout_sec: float = Field(default=30.0, ge=1.0, le=300.0, description="Execution timeout in seconds")


class AppControlExecutionResult(BaseModel):
    """Comprehensive result of end-to-end resolve-permission-plan-execute-verify lifecycle."""

    execution_id: str
    plan_id: str
    application: str
    capability: str
    stage: AppControlLifecycleStage
    success: bool
    verified: bool
    resolution: IntegrationResolutionResult
    permission_check: dict[str, Any] | None = None
    plan: AppControlExecutionPlan | None = None
    execution_output: dict[str, Any] = Field(default_factory=dict)
    verification_details: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)
    pending_confirmation_details: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0
    audit_proof_hash: str | None = None
    trace_id: str | None = None


class AppControlConfirmationRequest(BaseModel):
    """Request to confirm and proceed with a pending AppControl execution."""

    confirmation_token: str = Field(..., description="Unique confirmation challenge token received in pending state")
    user_id: str | None = Field(default=None, description="Authenticated user confirming the action")


# =============================================================================
# Phase 10: Multi-Device Fleet Orchestration & Autonomous Device Handover Schemas
# =============================================================================

class FleetCandidateScore(BaseModel):
    """Evaluation breakdown and scoring metrics for a candidate device in the user's fleet."""

    device_id: str
    device_name: str
    os_platform: str
    status: str
    is_online: bool
    is_current_host: bool
    app_available: bool
    capabilities_matched: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class FleetRoutingRequest(BaseModel):
    """Request to evaluate user fleet and determine the optimal device for an action."""

    user_id: str = Field(..., description="User ID owning the device fleet")
    application: str = Field(..., description="Target application name")
    capability: str = Field(..., description="Target capability or action")
    preferred_device_id: str | None = Field(default=None, description="Optional caller preferred device ID")
    required_capabilities: list[str] = Field(default_factory=list, description="Capabilities required on target device")
    required_os_platform: str | None = Field(default=None, description="Required OS platform if constrained")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action arguments or parameters")
    allow_offline: bool = Field(default=False, description="Whether to consider offline devices")


class FleetRoutingDecision(BaseModel):
    """Decision emitted by FleetOrchestrator selecting the optimal device."""

    routing_id: str
    user_id: str
    application: str
    capability: str
    target_device_id: str | None
    target_device_name: str | None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    selection_reason: str
    candidates: list[FleetCandidateScore] = Field(default_factory=list)
    fallback_device_ids: list[str] = Field(default_factory=list)
    requires_handover: bool = False
    duration_ms: float = 0.0


class FleetHandoverRequest(BaseModel):
    """Request to initiate task/session handover between devices."""

    user_id: str = Field(..., description="User ID owning the devices")
    source_device_id: str = Field(..., description="Device initiating or transferring the task")
    target_device_id: str = Field(..., description="Device receiving and resuming the task")
    application: str = Field(..., description="Application being controlled")
    capability: str = Field(..., description="Capability being executed")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    execution_id: str | None = Field(default=None, description="Source execution ID if migrating")
    plan_id: str | None = Field(default=None, description="Source execution plan ID if migrating")
    state_payload: dict[str, Any] = Field(default_factory=dict, description="Migrated task context and step state")
    reason: str = Field(default="user_requested", description="Reason for handover (e.g. 'failover', 'user_preference')")
    auto_resume: bool = Field(default=True, description="Whether target device should immediately resume execution")


class FleetHandoverResult(BaseModel):
    """Result of task/session handover between fleet devices."""

    handover_id: str
    user_id: str
    source_device_id: str
    target_device_id: str
    status: Literal["pending", "transferred", "resumed", "completed", "failed"]
    reason: str
    state_payload: dict[str, Any] = Field(default_factory=dict)
    execution_result: AppControlExecutionResult | None = None
    error: str | None = None
    duration_ms: float = 0.0


class FleetExecutionRequest(BaseModel):
    """Request to execute an application control action across the device fleet with auto-routing."""

    application: str = Field(..., description="Target application name")
    capability: str = Field(..., description="Target capability or action")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Action arguments or parameters")
    preferred_device_id: str | None = Field(default=None, description="Optional preferred device ID; None or 'auto' routes via fleet")
    user_id: str | None = Field(default=None, description="User ID for authorization and fleet lookup")
    preferred_integration: IntegrationType | None = Field(default=None, description="Optional override integration surface")
    allow_failover: bool = Field(default=True, description="Whether to automatically failover to fallback devices on error")
    max_failovers: int = Field(default=2, ge=0, le=5, description="Maximum number of failover attempts")
    confirmed: bool = Field(default=False, description="Whether caller confirms execution")
    confirmation_token: str | None = Field(default=None, description="Confirmation challenge token")
    skip_verification: bool = Field(default=False, description="Whether to bypass post-condition verification")
    timeout_sec: float = Field(default=30.0, ge=1.0, le=300.0, description="Execution timeout in seconds")


class FleetExecutionResult(BaseModel):
    """Comprehensive result of fleet-orchestrated application control execution."""

    fleet_execution_id: str
    user_id: str
    application: str
    capability: str
    routing_decision: FleetRoutingDecision
    executed_device_id: str
    executed_device_name: str
    handover_occurred: bool = False
    handover_details: list[dict[str, Any]] = Field(default_factory=list)
    app_control_result: AppControlExecutionResult
    success: bool
    duration_ms: float = 0.0


class FleetSummaryResponse(BaseModel):
    """Consolidated state and application catalog distribution across the device fleet."""

    user_id: str
    total_devices: int
    online_devices: int
    offline_devices: int
    devices: list[DeviceResponse] = Field(default_factory=list)
    discovered_apps_count: int
    app_distribution: dict[str, list[str]] = Field(default_factory=dict)
    timestamp: str


class FleetBroadcastQueryRequest(BaseModel):
    """Request to query state across all active devices in the user's fleet."""

    user_id: str = Field(..., description="User ID owning the fleet")
    query_type: Literal["find_app", "find_process", "system_stats"] = Field(..., description="Type of broadcast query")
    query_target: str = Field(default="", description="Target app name or process executable to locate")


class FleetBroadcastQueryResponse(BaseModel):
    """Aggregated responses from all online devices for a broadcast query."""

    query_type: str
    query_target: str
    results_by_device: dict[str, Any] = Field(default_factory=dict)
    total_responding_devices: int = 0


# =============================================================================
# Phase 11: Mobile Agent — Android Schemas
# =============================================================================


class AndroidBounds(BaseModel):
    """Screen bounding coordinates for an Android UI element."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    width: int = 0
    height: int = 0


class AndroidNodeInfoModel(BaseModel):
    """Authoritative Android AccessibilityNodeInfo representation."""

    class_name: str = Field(default="android.view.View", description="Native Android view class name")
    package_name: str = Field(default="", description="Package identifier owning the view")
    text: str | None = Field(default=None, description="User-visible text label or input value")
    content_description: str | None = Field(default=None, description="Accessibility content description")
    resource_id: str | None = Field(default=None, description="View resource identifier (e.g. com.app:id/button)")
    role: str = Field(default="control", description="Canonical Roxy normalized role")
    bounds: AndroidBounds = Field(default_factory=AndroidBounds, description="Screen coordinates")
    is_clickable: bool = Field(default=False, description="Whether node accepts click events")
    is_editable: bool = Field(default=False, description="Whether node accepts text input")
    is_enabled: bool = Field(default=True, description="Whether node is currently enabled")
    is_focused: bool = Field(default=False, description="Whether node has input focus")
    is_scrollable: bool = Field(default=False, description="Whether node supports scroll actions")
    is_visible: bool = Field(default=True, description="Whether node is currently visible on screen")
    children: list[AndroidNodeInfoModel] = Field(default_factory=list, description="Nested child accessibility nodes")
    actions: list[str] = Field(default_factory=list, description="Available actions (click, type, scroll, select)")


class AndroidIntentRequest(BaseModel):
    """Specification for an explicit or implicit Android Intent dispatch."""

    action: str = Field(default="android.intent.action.VIEW", description="Android Intent action")
    package_name: str | None = Field(default=None, description="Target package name (e.g. com.spotify.music)")
    component: str | None = Field(default=None, description="Explicit ComponentName (e.g. com.spotify.music/.MainActivity)")
    data_uri: str | None = Field(default=None, description="URI payload (e.g. tel:12345, geo:37,-122, spotify:track:...)")
    mime_type: str | None = Field(default=None, description="Explicit MIME type")
    categories: list[str] = Field(default_factory=list, description="Intent categories")
    extras: dict[str, Any] = Field(default_factory=dict, description="Key-value Intent extras")
    flags: list[str] = Field(default_factory=lambda: ["FLAG_ACTIVITY_NEW_TASK"], description="Launch flags")
    broadcast: bool = Field(default=False, description="Send as broadcast rather than activity launch")
    service: bool = Field(default=False, description="Start as background service rather than activity")


class AndroidDeepLinkRequest(BaseModel):
    """Specification to open an Android universal or custom scheme deep link."""

    url_or_uri: str = Field(..., description="Target deep link URL or URI scheme (e.g. spotify://track/..., whatsapp://send)")
    fallback_url: str | None = Field(default=None, description="Web URL fallback if native application is not installed")
    package_name: str | None = Field(default=None, description="Target application package if known")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Query parameters to inject or format")


class AndroidActionResponse(BaseModel):
    """Result of an Android mobile device action."""

    success: bool
    action: str
    target: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: "")


class AndroidCompanionEnvelope(BaseModel):
    """Duplex command envelope exchanged with the enrolled Android Companion app."""

    command_id: str = Field(..., description="Unique command identifier")
    action: str = Field(..., description="Action name (ui_inspect, ui_click, ui_type, ui_scroll, start_intent, open_deep_link, take_screenshot, ping)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    timeout_ms: int = Field(default=10000, description="Max execution timeout in milliseconds")


class AndroidCompanionResponse(BaseModel):
    """Execution response returned by the Android Companion app."""

    command_id: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


class AndroidCompanionTelemetry(BaseModel):
    """Heartbeat and operational telemetry reported by an Android device."""

    device_id: str
    battery_level: int = 100
    is_charging: bool = False
    screen_on: bool = True
    foreground_package: str = ""
    foreground_activity: str = ""
    screen_width: int = 1080
    screen_height: int = 2400
    orientation: str = "portrait"
    android_version: str = "14"
    sdk_int: int = 34
    timestamp: str = Field(default_factory=lambda: "")


class AndroidScreenshotResponse(BaseModel):
    """Screen capture result from an Android device."""

    device_id: str
    width: int
    height: int
    image_base64: str
    format: str = "png"
    target_package: str = ""
    timestamp: str


class AndroidPrerequisiteReport(BaseModel):
    """Prerequisite status report for Android Debug Bridge (ADB) and mobile runtime."""

    is_adb_installed: bool = Field(..., description="Whether adb CLI binary is located on system PATH")
    adb_path: str | None = Field(default=None, description="Absolute filesystem path to adb binary")
    attached_devices: list[str] = Field(default_factory=list, description="List of connected Android device identifiers")
    installation_command: str | None = Field(default=None, description="Platform-specific shell command to install adb")
    status: Literal["READY", "NO_DEVICES", "ADB_MISSING", "PLATFORM_UNSUPPORTED"] = Field(..., description="High-level readiness state")
    recommendations: list[str] = Field(default_factory=list, description="Actionable step-by-step guidance for the user")
    timestamp: str = Field(default_factory=lambda: "")


# -----------------------------------------------------------------------------
# Phase 12: Mobile Agent — iOS Models
# -----------------------------------------------------------------------------

class IOSUniversalLinkRequest(BaseModel):
    """Specification to open an iOS Universal Link (HTTP/HTTPS) with native app fallback."""

    url: str = Field(..., description="Target Universal Link URL (e.g. https://open.spotify.com/track/...)")
    fallback_url: str | None = Field(default=None, description="Web fallback URL if app is not installed")
    bundle_id: str | None = Field(default=None, description="Associated Apple App Bundle ID (e.g. com.spotify.client)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="URL query parameters to format or append")


class IOSURLSchemeRequest(BaseModel):
    """Specification to open a native iOS Custom URL Scheme (e.g. spotify://, maps://, shortcuts://)."""

    scheme: str = Field(..., description="Target custom URL scheme (e.g. spotify, maps, facetime, shortcuts)")
    host: str | None = Field(default=None, description="Target host or action (e.g. track, run-shortcut)")
    path: str | None = Field(default=None, description="Path component (e.g. /play, /compose)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Query parameters to inject")
    raw_uri: str | None = Field(default=None, description="Fully formatted URI if provided directly (e.g. tel:123456789)")


class IOSShortcutRequest(BaseModel):
    """Specification to run an Apple Shortcut via the shortcuts:// URL scheme or x-callback-url."""

    shortcut_name: str = Field(..., description="Exact name of the installed Apple Shortcut")
    input_type: Literal["text", "clipboard", "file", "json", "none"] = Field(
        default="text", description="Input data type passed to the shortcut"
    )
    input_value: str | None = Field(default=None, description="Value passed as input to the shortcut")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Custom parameters or dictionary payload")
    use_x_callback: bool = Field(default=False, description="Use x-callback-url for return receipt and output capture")
    x_success_url: str | None = Field(default=None, description="Callback URL on successful completion")
    x_error_url: str | None = Field(default=None, description="Callback URL on failure")


class IOSAppIntentRequest(BaseModel):
    """Specification for an iOS 16+ App Intent dispatch."""

    bundle_id: str = Field(..., description="Target iOS application bundle ID (e.g. com.apple.MobileAddressBook)")
    intent_name: str = Field(..., description="App Intent identifier or SiriKit Intent class (e.g. INSendMessageIntent)")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Typed parameters conforming to the intent schema")
    suggested_invocation_phrase: str | None = Field(
        default=None, description="Optional Siri invocation phrase associated with the intent"
    )


class IOSShareSheetRequest(BaseModel):
    """Specification for an iOS Share Sheet (UIActivityViewController) presentation payload."""

    text: str | None = Field(default=None, description="Plain text to share")
    url: str | None = Field(default=None, description="Web URL or deep link to share")
    image_base64: str | None = Field(default=None, description="Base64-encoded image data")
    file_path: str | None = Field(default=None, description="Local or sandbox file path to share")
    mime_type: str | None = Field(default=None, description="MIME type of the shared payload")
    target_activity: str | None = Field(
        default=None, description="Target activity identifier (e.g. com.apple.UIKit.activity.PostToTwitter, AirDrop)"
    )


class IOSActionResponse(BaseModel):
    """Result of an iOS mobile action or legitimate unsupported declaration under Zero Simulation."""

    success: bool
    action: str
    target: str | None = None
    status: Literal["completed", "pending", "failed", "unsupported_on_this_platform"] = "completed"
    details: dict[str, Any] = Field(default_factory=dict)
    supported_alternatives: list[str] = Field(default_factory=list)
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: "")


class IOSCompanionEnvelope(BaseModel):
    """Duplex command envelope exchanged with the enrolled iOS Companion app."""

    command_id: str = Field(..., description="Unique command identifier")
    action: str = Field(
        ...,
        description="Action name (open_universal_link, open_url_scheme, run_shortcut, dispatch_app_intent, present_share_sheet, get_telemetry, ping)",
    )
    parameters: dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    timeout_ms: int = Field(default=10000, description="Max execution timeout in milliseconds")


class IOSCompanionResponse(BaseModel):
    """Execution response returned by the iOS Companion app."""

    command_id: str
    success: bool
    status: str = "completed"
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


class IOSTelemetry(BaseModel):
    """Heartbeat and device operational telemetry reported by an enrolled iOS device."""

    device_id: str
    device_name: str = "iPhone"
    model: str = "iPhone 15 Pro"
    system_name: str = "iOS"
    system_version: str = "17.5"
    battery_level: int = 100
    battery_state: Literal["unknown", "unplugged", "charging", "full"] = "unplugged"
    is_low_power_mode: bool = False
    screen_width: int = 1179
    screen_height: int = 2556
    screen_scale: float = 3.0
    orientation: str = "portrait"
    foreground_bundle_id: str = "ai.roxy.companion"
    shortcuts_installed: list[str] = Field(default_factory=list)
    supported_schemes: list[str] = Field(default_factory=list)

    timestamp: str = Field(default_factory=lambda: "")


# -----------------------------------------------------------------------------
# Phase 13: Mobile App Discovery + Capability Resolution Models
# -----------------------------------------------------------------------------

class MobileCapabilityModel(BaseModel):
    """Normalized capability model for mobile applications (Android & iOS)."""

    capability_id: str = Field(..., description="Unique capability identifier (e.g. spotify_play, slack_send_message)")
    name: str = Field(..., description="Human-readable capability name")
    description: str = Field(default="", description="Detailed capability description")
    capability_type: Literal[
        "intent",
        "deep_link",
        "universal_link",
        "url_scheme",
        "app_intent",
        "shortcut",
        "share_sheet",
        "ui_automation",
        "connector",
        "mcp_tool",
        "api",
    ] = Field(..., description="Type of mobile capability")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for input parameters")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for output results")
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(default="LOW")
    required_permission: str = Field(default="", description="Required permission scope")
    execution_adapter: str = Field(..., description="Target execution adapter (e.g. android_intent, ios_shortcut, etc.)")
    verification_strategy: str = Field(..., description="Verification method probe")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source: Literal["package_manifest", "companion_inspection", "known_catalog", "shortcut_registry", "os_query"] = (
        "known_catalog"
    )
    parameters: dict[str, Any] = Field(default_factory=dict, description="Default parameters and handler config")


class MobileAppModel(BaseModel):
    """Authoritative representation of an installed or discoverable mobile application."""

    app_id: str = Field(..., description="Canonical ID (e.g. mobile:android:com.spotify.music or mobile:ios:com.spotify.client)")
    package_or_bundle_id: str = Field(..., description="Android package name or iOS bundle ID")
    name: str = Field(..., description="Human-readable application display name")
    version: str = Field(default="1.0.0", description="Application version")
    platform: Literal["android", "ios"] = Field(..., description="Target mobile OS")
    device_id: str | None = Field(default=None, description="Bound device ID if discovered on specific device")
    installed: bool = Field(default=True, description="Whether currently verified installed on device")
    is_system_app: bool = Field(default=False, description="Whether application is an OS system application")
    category: str = Field(default="general", description="Application category (media, communication, productivity, etc.)")

    # Required Phase 13 fields:
    supported_intents: list[str] = Field(default_factory=list, description="Supported Android intent actions or iOS intents")
    deep_links: list[str] = Field(default_factory=list, description="Supported custom URL schemes and deep link prefixes")
    share_targets: list[str] = Field(default_factory=list, description="Accepted MIME types and sharing activity types")
    app_intents: list[str] = Field(default_factory=list, description="Declared iOS 16+ App Intents or Android App Actions")
    known_integrations: list[str] = Field(default_factory=list, description="Available integration types (connector, mcp, intent, etc.)")
    permissions: list[str] = Field(default_factory=list, description="Declared or required mobile permissions")
    automation_capabilities: list[MobileCapabilityModel] = Field(
        default_factory=list, description="Resolved automation capabilities"
    )

    metadata: dict[str, Any] = Field(default_factory=dict, description="Platform-specific metadata")
    discovered_at: str = Field(default_factory=lambda: "")
    last_verified_at: str | None = Field(default=None)


class MobileAppDiscoveryRequest(BaseModel):
    """Request to discover mobile applications on an enrolled device or simulator."""

    device_id: str = Field(..., description="Target device ID")
    platform: Literal["android", "ios"] = Field(..., description="Mobile platform")
    force_refresh: bool = Field(default=False, description="Bypass cache and force re-scan")
    include_system_apps: bool = Field(default=False, description="Include built-in system applications")
    companion_catalog: list[dict[str, Any]] | None = Field(
        default=None, description="Optional raw app catalog provided directly by companion agent"
    )


class MobileAppDiscoveryResponse(BaseModel):
    """Response containing discovered mobile applications."""

    device_id: str
    platform: str
    total_apps: int
    apps: list[MobileAppModel]
    scan_source: Literal["adb_subsystem", "companion_protocol", "known_catalog", "hybrid"] = "known_catalog"
    duration_ms: float = 0.0
    discovered_at: str


class MobileCapabilityResolutionRequest(BaseModel):
    """Request to resolve the optimal mobile capability and integration for an app."""

    package_or_bundle_id: str = Field(..., description="Android package name or iOS bundle ID, or application name")
    requested_capability: str = Field(..., description="Requested action or capability (e.g. play_music, send_message, open)")
    platform: Literal["android", "ios"] | None = Field(default=None, description="Target platform if known")
    device_id: str | None = Field(default=None, description="Target device ID")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Input parameters for the action")
    preferred_integration: str | None = Field(default=None, description="Optional caller preference")


class MobileCapabilityResolutionResponse(BaseModel):
    """Result of mobile capability resolution."""

    success: bool
    app: MobileAppModel | None = None
    capability: MobileCapabilityModel | None = None
    integration_type: str = "unsupported"
    confidence: float = 0.0
    execution_adapter: str = "unsupported"
    verification_strategy: str = "none"
    required_permission: str = ""
    risk_level: str = "LOW"
    requires_confirmation: bool = False
    resolved_parameters: dict[str, Any] = Field(default_factory=dict)
    remediation_guidance: str | None = None
    alternatives: list[str] = Field(default_factory=list)


# =============================================================================
# Phase 14: Automatic New-App Workflow Schemas
# =============================================================================

class NewAppDetectionRequest(BaseModel):
    """Request to detect if an application, executable, or process is new to the system."""

    device_id: str = Field(default="default", description="Device ID")
    app_name: str | None = Field(default=None, description="Application or command name")
    executable_path: str | None = Field(default=None, description="Path to binary or executable")
    process_id: int | None = Field(default=None, description="PID of active process")
    window_title: str | None = Field(default=None, description="Window title of active window")
    bundle_id: str | None = Field(default=None, description="Mobile bundle ID or macOS bundle ID")
    package_name: str | None = Field(default=None, description="Android package name")
    trigger_source: Literal[
        "process_spawn", "window_active", "filesystem_install", "companion_beacon", "user_request", "api_trigger"
    ] = Field(default="user_request", description="Detection trigger mechanism")


class NewAppDetectionResult(BaseModel):
    """Result of new application detection."""

    is_new_app: bool = Field(..., description="Whether application was previously unknown/unregistered")
    app_name: str = Field(..., description="Application name")
    canonical_name: str = Field(..., description="Normalized canonical application name")
    platform: str = Field(default="desktop", description="Detected or specified platform")
    detected_paths: list[str] = Field(default_factory=list, description="Resolved executable or package paths")
    existing_app_id: str | None = Field(default=None, description="ID if app was already registered")
    confidence: float = Field(default=1.0, description="Detection confidence score (0.0 - 1.0)")
    trigger_source: str = Field(default="user_request")
    detected_at: str = Field(default_factory=lambda: "")


class DiscoveredIntegrationPathway(BaseModel):
    """A candidate integration pathway discovered for an application."""

    pathway_id: str = Field(..., description="Unique pathway identifier")
    integration_tier: str = Field(
        ...,
        description="Integration tier (connector, mcp_tool, cli_subcommand, local_rest, app_intent, deep_link, system_intent, share_sheet, ui_automation, process_lifecycle, browser, unsupported)",
    )
    priority_rank: int = Field(..., description="Priority rank (1 = highest)")
    name: str = Field(..., description="Human-readable pathway name")
    description: str = Field(default="", description="Detailed pathway description")
    confidence_score: float = Field(default=0.8, description="Pathway viability confidence (0.0 - 1.0)")
    estimated_latency_ms: float = Field(default=50.0, description="Estimated execution latency in ms")
    risk_level: str = Field(default="LOW", description="Risk classification (LOW, MEDIUM, HIGH, CRITICAL)")
    requires_confirmation: bool = Field(default=False, description="Whether confirmation is required before execution")
    execution_adapter: str = Field(default="cli", description="Internal adapter responsible for execution")
    verification_strategy: str = Field(default="dry_run", description="Verification strategy for this pathway")
    required_permission: str = Field(default="app:execute", description="Target-scoped permission required")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSONSchema parameter definition")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Pathway-specific metadata")


class NewAppIntrospectionRequest(BaseModel):
    """Request to deeply introspect capabilities of a detected application."""

    device_id: str = Field(default="default", description="Device ID")
    app_name: str = Field(..., description="Target application name or identifier")
    executable_path: str | None = Field(default=None, description="Optional path to executable")
    platform: str | None = Field(default=None, description="Target platform")
    deep_scan: bool = Field(default=True, description="Whether to probe CLI, ports, and UI trees")
    timeout_sec: float = Field(default=5.0, description="Introspection timeout in seconds")


class NewAppIntrospectionResult(BaseModel):
    """Multi-modal capability introspection result."""

    app_name: str
    canonical_name: str
    platform: str
    executable_path: str | None = None
    cli_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    rest_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    ui_controls: list[dict[str, Any]] = Field(default_factory=list)
    mobile_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    cloud_connectors: list[dict[str, Any]] = Field(default_factory=list)
    mcp_tools: list[dict[str, Any]] = Field(default_factory=list)
    total_capabilities_found: int = 0
    introspection_duration_ms: float = 0.0
    introspected_at: str = Field(default_factory=lambda: "")


class NewAppRankingRequest(BaseModel):
    """Request to rank candidate integration pathways for an application."""

    app_name: str
    capabilities: list[dict[str, Any]] = Field(default_factory=list)
    platform: str = "desktop"
    user_preference: str | None = None


class NewAppRankingResult(BaseModel):
    """Integration pathway ranking result."""

    app_name: str
    canonical_name: str
    primary_pathway: DiscoveredIntegrationPathway
    alternative_pathways: list[DiscoveredIntegrationPathway] = Field(default_factory=list)
    ranking_rationale: str
    ranked_at: str = Field(default_factory=lambda: "")


class NewAppRegistrationRequest(BaseModel):
    """Request to finalize dynamic registration of an application and synthesize tools."""

    device_id: str = Field(default="default", description="Device ID")
    app_name: str = Field(..., description="Application name")
    primary_pathway: DiscoveredIntegrationPathway | None = Field(default=None)
    all_pathways: list[DiscoveredIntegrationPathway] = Field(default_factory=list)
    synthesize_tools: bool = Field(
        default=True, description="Synthesize and register AgentTool instances in ToolRegistry"
    )
    auto_verify: bool = Field(
        default=True, description="Perform non-destructive verification probe under Zero Simulation"
    )


class NewAppRegistrationResult(BaseModel):
    """Result of application registration and tool synthesis."""

    success: bool
    app_id: str
    app_name: str
    canonical_name: str
    registered_tools: list[str] = Field(default_factory=list)
    verification_status: Literal["verified", "partial", "failed", "skipped"] = "skipped"
    verification_latency_ms: float = 0.0
    verification_details: dict[str, Any] = Field(default_factory=dict)
    permission_scopes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: "")


class NewAppWorkflowRequest(BaseModel):
    """Request to execute the automated End-to-End New-App Workflow."""

    device_id: str = Field(default="default", description="Target device ID")
    target: str = Field(..., description="Application name, command, binary path, URL, or package identifier")
    platform: str | None = Field(
        default=None, description="Optional platform override (windows, macos, linux, android, ios)"
    )
    executable_path: str | None = Field(default=None, description="Explicit executable path if known")
    trigger_source: str = Field(default="user_request", description="Origin of new app detection")
    auto_register: bool = Field(default=True, description="Automatically register into ToolRegistry and catalogs")
    auto_verify: bool = Field(default=True, description="Execute live non-destructive verification probe")
    synthesize_tools: bool = Field(default=True, description="Generate executable AgentTools")


class NewAppWorkflowResponse(BaseModel):
    """Comprehensive output of the End-to-End New-App Workflow."""

    success: bool
    app_name: str
    canonical_name: str
    detection: NewAppDetectionResult
    introspection: NewAppIntrospectionResult
    ranking: NewAppRankingResult
    registration: NewAppRegistrationResult | None = None
    workflow_duration_ms: float = 0.0
    audit_trail: list[str] = Field(default_factory=list)


# =============================================================================
# Phase 15: Connector + MCP Discovery Schemas
# =============================================================================


class MCPDiscoverySource(StrEnum):
    CONFIG_FILE = "config_file"
    LOCAL_SSE_PORT = "local_sse_port"
    RUNNING_PROCESS = "running_process"
    ENVIRONMENT = "environment"
    AUTHORITATIVE_CATALOG = "authoritative_catalog"


class MCPDiscoveredServer(BaseModel):
    """An external or local MCP server discovered at runtime."""

    server_id: str
    name: str
    transport: Literal["sse", "stdio"]
    source: MCPDiscoverySource
    endpoint_url: str | None = None
    command: str | None = None
    arguments: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    config_path: str | None = None
    pid: int | None = None
    is_active: bool = False
    tools_count: int = 0
    discovered_tools: list[dict[str, Any]] = Field(default_factory=list)
    discovered_resources: list[dict[str, Any]] = Field(default_factory=list)
    discovered_prompts: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    discovered_at: str = Field(default_factory=lambda: "")


class MCPDiscoveryRequest(BaseModel):
    """Request to discover MCP servers on the system and network."""

    device_id: str = Field(default="default", description="Device ID")
    scan_configs: bool = Field(default=True, description="Scan standard MCP configuration files on disk")
    scan_ports: bool = Field(default=True, description="Probe local network ports for active MCP SSE servers")
    scan_processes: bool = Field(default=True, description="Inspect running processes for MCP server binaries")
    include_catalog: bool = Field(default=True, description="Include known open-source MCP catalog matches")
    ports_to_scan: list[int] = Field(default_factory=lambda: [8000, 8080, 3000, 5000, 3001, 8001])
    target_app: str | None = Field(default=None, description="Optional application filter (e.g. 'postgres', 'github')")


class MCPDiscoveryResult(BaseModel):
    """Result of MCP server discovery scan."""

    total_found: int = 0
    active_servers: list[MCPDiscoveredServer] = Field(default_factory=list)
    catalog_suggestions: list[MCPDiscoveredServer] = Field(default_factory=list)
    configs_scanned: list[str] = Field(default_factory=list)
    ports_scanned: list[int] = Field(default_factory=list)
    scan_duration_ms: float = 0.0
    scanned_at: str = Field(default_factory=lambda: "")


class MCPToolBindingRequest(BaseModel):
    """Request to bind tools from a discovered MCP server into ToolRegistry."""

    device_id: str = Field(default="default")
    server: MCPDiscoveredServer
    tool_prefix: str | None = None
    auto_handshake: bool = Field(default=True, description="Execute JSON-RPC handshake to discover live tools")


class MCPToolBindingResult(BaseModel):
    """Result of binding an MCP server's tools into ToolRegistry."""

    success: bool
    server_id: str
    server_name: str
    bound_tools: list[str] = Field(default_factory=list)
    total_bound: int = 0
    binding_id: str
    verification_status: Literal["verified", "failed", "unverified"] = "unverified"
    error: str | None = None
    bound_at: str = Field(default_factory=lambda: "")


class ConnectorDiscoverySource(StrEnum):
    ACTIVE_INSTANCE = "active_instance"
    OPENAPI_ENDPOINT = "openapi_endpoint"
    ENVIRONMENT_CREDENTIALS = "environment_credentials"
    AUTHORITATIVE_CATALOG = "authoritative_catalog"


class ConnectorDiscoveredItem(BaseModel):
    """A discovered Cloud Connector or OpenAPI endpoint."""

    connector_id: str
    connector_type: str
    title: str
    description: str
    source: ConnectorDiscoverySource
    has_credentials: bool = False
    auth_methods: list[str] = Field(default_factory=list)
    base_url: str | None = None
    spec_url: str | None = None
    available_actions: list[str] = Field(default_factory=list)
    action_count: int = 0
    health_status: Literal["healthy", "untested", "error", "unauthenticated"] = "untested"
    health_latency_ms: float = 0.0
    error_message: str | None = None
    discovered_at: str = Field(default_factory=lambda: "")


class ConnectorDiscoveryRequest(BaseModel):
    """Request to discover available cloud connectors and local OpenAPI endpoints."""

    device_id: str = Field(default="default")
    target_app: str | None = Field(default=None, description="Optional target app or service name (e.g. 'github', 'slack', 'weather')")
    scan_openapi_ports: bool = Field(default=True, description="Scan localhost ports for OpenAPI/Swagger endpoints")
    openapi_ports: list[int] = Field(default_factory=lambda: [8000, 8080, 5000, 3000, 8001])
    include_environment: bool = Field(default=True, description="Check environment for active API keys/tokens")
    include_catalog: bool = Field(default=True, description="Include supported connectors from Roxy's catalog")


class ConnectorDiscoveryResult(BaseModel):
    """Result of connector discovery scan."""

    total_found: int = 0
    active_connectors: list[ConnectorDiscoveredItem] = Field(default_factory=list)
    openapi_endpoints: list[ConnectorDiscoveredItem] = Field(default_factory=list)
    catalog_connectors: list[ConnectorDiscoveredItem] = Field(default_factory=list)
    scan_duration_ms: float = 0.0
    scanned_at: str = Field(default_factory=lambda: "")


class ConnectorToolBindingRequest(BaseModel):
    """Request to instantiate and bind connector actions into ToolRegistry."""

    device_id: str = Field(default="default")
    connector_type: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] = Field(default_factory=dict)
    openapi_spec: dict[str, Any] | None = None
    openapi_base_url: str | None = None


class ConnectorToolBindingResult(BaseModel):
    """Result of binding connector actions into ToolRegistry."""

    success: bool
    connector_id: str
    connector_name: str
    connector_type: str
    bound_tools: list[str] = Field(default_factory=list)
    total_bound: int = 0
    binding_id: str
    health_status: str = "healthy"
    error: str | None = None
    bound_at: str = Field(default_factory=lambda: "")


class UnifiedDiscoveryRequest(BaseModel):
    """Request for unified MCP + Connector discovery and optional auto-binding."""

    device_id: str = Field(default="default")
    target_app: str | None = Field(default=None, description="Optional target app or domain (e.g. 'github', 'postgres', 'fastapi')")
    auto_bind: bool = Field(default=True, description="Automatically bind discovered live tools into ToolRegistry")
    scan_mcp: bool = Field(default=True, description="Include MCP discovery")
    scan_connectors: bool = Field(default=True, description="Include Connector & OpenAPI discovery")


class UnifiedDiscoveryResult(BaseModel):
    """Comprehensive result of unified MCP + Connector discovery."""

    target_app: str | None = None
    mcp_discovery: MCPDiscoveryResult
    connector_discovery: ConnectorDiscoveryResult
    bound_tools: list[str] = Field(default_factory=list)
    total_tools_bound: int = 0
    ranked_pathways: list[DiscoveredIntegrationPathway] = Field(default_factory=list)
    duration_ms: float = 0.0
    discovered_at: str = Field(default_factory=lambda: "")


class DiscoveryBoundToolsResponse(BaseModel):
    """List of all dynamically bound discovery tools."""

    total_bindings: int = 0
    total_tools: int = 0
    bindings: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Phase 16: App Embedding & In-Roxy Workspace Schemas
# =============================================================================


class EmbeddingSurfaceType(StrEnum):
    """Surface rendering type for app embedding in In-Roxy Workspace."""

    DIRECT_IFRAME = "direct_iframe"
    SANDBOXED_PROXY = "sandboxed_proxy"
    DESKTOP_PROJECTION = "desktop_projection"
    REMOTE_SURFACE = "remote_surface"


class EmbedSecurityVerdict(StrEnum):
    """Security assessment verdict for web/app embedding."""

    ALLOWED_DIRECT = "allowed_direct"
    ALLOWED_SANDBOXED = "allowed_sandboxed"
    REQUIRES_PROXY = "requires_proxy"
    BLOCKED_UNSAFE = "blocked_unsafe"


class WorkspaceSessionStatus(StrEnum):
    """Status lifecycle of an active workspace surface session."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class IframeSandboxPolicy(BaseModel):
    """HTML5 iframe sandbox attributes and permissions policy for secure embedding."""

    allow_scripts: bool = True
    allow_same_origin: bool = False
    allow_forms: bool = True
    allow_popups: bool = False
    allow_downloads: bool = False
    allow_modals: bool = False
    permissions_policy: str = "camera 'none'; microphone 'none'; geolocation 'none'; display-capture 'none'; clipboard-read 'none'"
    csp_header: str = "frame-ancestors 'self' http://localhost:* http://127.0.0.1:*"


class EmbedEvaluationRequest(BaseModel):
    """Request to assess embedding security and headers for a target URL."""

    url: str
    app_name: str | None = None
    allow_proxy: bool = True


class EmbedEvaluationResult(BaseModel):
    """Result of assessing embedding security and headers."""

    url: str
    verdict: EmbedSecurityVerdict
    recommended_surface: EmbeddingSurfaceType
    is_embeddable: bool
    x_frame_options: str | None = None
    csp_frame_ancestors: str | None = None
    sandbox_attributes: list[str] = Field(default_factory=list)
    permissions_policy: str = ""
    proxy_url: str | None = None
    reason: str
    evaluated_at: str = Field(default_factory=lambda: "")


class WorkspaceSurfaceSession(BaseModel):
    """Active remote surface or in-workspace app embedding session."""

    session_id: str
    device_id: str = "default"
    app_name: str
    surface_type: EmbeddingSurfaceType
    status: WorkspaceSessionStatus = WorkspaceSessionStatus.ACTIVE
    target_url: str | None = None
    target_window_id: str | None = None
    target_pid: int | None = None
    viewport_width: int = 1280
    viewport_height: int = 800
    frame_rate: int = 30
    created_at: str
    last_heartbeat: str
    expires_at: str
    auth_token: str
    sandbox_policy: IframeSandboxPolicy | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSurfaceSessionRequest(BaseModel):
    """Request to create an in-workspace surface embedding or projection session."""

    app_name: str
    device_id: str = "default"
    surface_type: EmbeddingSurfaceType | None = None
    target_url: str | None = None
    target_window_id: str | None = None
    target_pid: int | None = None
    viewport_width: int = 1280
    viewport_height: int = 800
    preferred_fps: int = 30
    metadata: dict[str, Any] = Field(default_factory=dict)


class SurfaceFrameSnapshot(BaseModel):
    """Captured video/image frame snapshot from a desktop projection session."""

    session_id: str
    frame_number: int = 0
    timestamp: float
    width: int
    height: int
    format: str = "image/jpeg"
    data_base64: str
    window_state: dict[str, Any] | None = None


class RelayInputRequest(BaseModel):
    """Input event from workspace canvas to relay to the native desktop application."""

    session_id: str
    action: Literal["click", "double_click", "right_click", "mouse_move", "key_down", "type_text", "hotkey", "scroll"]
    x: int | None = None
    y: int | None = None
    text: str | None = None
    key: str | None = None
    hotkey: str | None = None
    delta_x: int = 0
    delta_y: int = 0
    button: Literal["left", "right", "middle"] = "left"


class RelayInputResult(BaseModel):
    """Outcome of relaying an input interaction into the desktop projection."""

    session_id: str
    action: str
    success: bool
    details: dict[str, Any] = Field(default_factory=dict)
    relayed_at: str = Field(default_factory=lambda: "")


class WorkspaceSessionListResponse(BaseModel):
    """List of active workspace surface sessions."""

    total_sessions: int = 0
    sessions: list[WorkspaceSurfaceSession] = Field(default_factory=list)


# =============================================================================
# Phase 17: Verification Engine 2.0 Schemas
# =============================================================================


class VerificationModality(StrEnum):
    """Evidence modality for postcondition verification."""

    WINDOW_STATE = "window_state"
    OCR_VISUAL = "ocr_visual"
    DOM_STATE = "dom_state"
    API_RESPONSE = "api_response"
    PROCESS_STATE = "process_state"
    WHATSAPP_STATUS = "whatsapp_status"


class VerificationOperator(StrEnum):
    """Comparison operator for postcondition assertions."""

    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    REGEX = "regex"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    JSON_PATH = "json_path"


class CompositeLogic(StrEnum):
    """Logical aggregation strategy for composite multi-criteria verification."""

    ALL_OF = "all_of"
    ANY_OF = "any_of"
    THRESHOLD = "threshold"


class WindowStateVerificationCriteria(BaseModel):
    """Criteria to verify native OS window postcondition."""

    target_window: str | int | None = Field(default=None, description="Window title, HWND, or pattern")
    expected_title: str | None = None
    title_operator: VerificationOperator = VerificationOperator.CONTAINS
    must_exist: bool = True
    must_be_visible: bool | None = None
    must_be_foreground: bool | None = None
    min_width: int | None = None
    min_height: int | None = None
    expected_process_name: str | None = None


class OCRVisualVerificationCriteria(BaseModel):
    """Criteria to verify visual text rendered on screen or in a window."""

    target_window: str | int | None = None
    expected_text: str
    text_operator: VerificationOperator = VerificationOperator.CONTAINS
    case_sensitive: bool = False
    region_box: list[int] | None = Field(default=None, description="Optional [left, top, right, bottom] bounding box")
    min_confidence: float = 0.5


class DOMStateVerificationCriteria(BaseModel):
    """Criteria to verify web DOM element, text, attribute, or URL in browser."""

    session_id: str | None = None
    page_url_pattern: str | None = None
    selector: str | None = Field(default=None, description="CSS selector or XPath to target element")
    expected_element_count: int | None = None
    expected_text: str | None = None
    text_operator: VerificationOperator = VerificationOperator.CONTAINS
    attribute_name: str | None = None
    expected_attribute_value: str | None = None
    js_expression: str | None = None
    expected_js_result: Any = None


class APIResponseVerificationCriteria(BaseModel):
    """Criteria to verify an HTTP/REST endpoint response."""

    endpoint_url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    expected_status_code: int = 200
    expected_body_contains: str | None = None
    json_path: str | None = Field(default=None, description="Dot-separated JSON path e.g. 'data.user.status'")
    expected_json_value: Any = None
    max_latency_ms: float | None = None


class ProcessStateVerificationCriteria(BaseModel):
    """Criteria to verify OS process status."""

    process_name: str
    must_be_running: bool = True
    min_instances: int = 1


class WhatsAppVerificationCriteria(BaseModel):
    """Criteria to verify WhatsApp message postconditions across route, session, and delivery."""

    action_name: str | None = None
    expected_status: str | None = None  # e.g. "SENT", "PENDING_APPROVAL", "DELIVERED", "BLOCKED"
    expected_recipient: str | None = None
    expected_message_contains: str | None = None
    require_authenticated_route: bool = True
    require_delivery_signal: bool = False
    task_id: str | None = None


class SingleCheckResult(BaseModel):
    """Outcome of an individual verification criterion."""

    modality: VerificationModality
    criterion_name: str
    passed: bool
    score: float = 1.0
    operator_used: VerificationOperator
    expected_value: Any = None
    actual_value: Any = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None


class CompositeVerificationRequest(BaseModel):
    """Request for cross-system, multi-modal postcondition verification."""

    verification_id: str | None = None
    action_name: str | None = None
    device_id: str = "default"
    logic: CompositeLogic = CompositeLogic.ALL_OF
    threshold: float = 1.0
    timeout_sec: float = 5.0
    poll_interval_sec: float = 0.25
    window_criteria: list[WindowStateVerificationCriteria] = Field(default_factory=list)
    ocr_criteria: list[OCRVisualVerificationCriteria] = Field(default_factory=list)
    dom_criteria: list[DOMStateVerificationCriteria] = Field(default_factory=list)
    api_criteria: list[APIResponseVerificationCriteria] = Field(default_factory=list)
    process_criteria: list[ProcessStateVerificationCriteria] = Field(default_factory=list)
    whatsapp_criteria: list[WhatsAppVerificationCriteria] = Field(default_factory=list)
    record_audit_event: bool = False
    audit_event_id: str | None = None


class CompositeVerificationResult(BaseModel):
    """Comprehensive result of executing Verification Engine 2.0."""

    verification_id: str
    action_name: str | None = None
    passed: bool
    overall_score: float
    logic: CompositeLogic
    total_criteria: int
    passed_criteria: int
    failed_criteria: int
    check_results: list[SingleCheckResult] = Field(default_factory=list)
    duration_ms: float
    verification_proof_hash: str
    verified_at: str
    audit_status: str | None = None


class VerificationHistoryResponse(BaseModel):
    """Recent verification history for a device or workspace."""

    total_verifications: int = 0
    verifications: list[CompositeVerificationResult] = Field(default_factory=list)


# =============================================================================
# Phase 18: Recovery & Self-Correction Schemas
# =============================================================================


class ExecutionTier(StrEnum):
    """Operational execution tier / interaction surface for action execution."""

    API = "api"
    BROWSER = "browser"
    DESKTOP = "desktop"


class ErrorCategory(StrEnum):
    """Taxonomy of operational execution and verification errors."""

    NETWORK_UNREACHABLE = "network_unreachable"
    AUTH_CREDENTIAL_ERROR = "auth_credential_error"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    RESOURCE_NOT_FOUND = "resource_not_found"
    SERVER_FAULT = "server_fault"
    DOM_ELEMENT_NOT_FOUND = "dom_element_not_found"
    CAPTCHA_CHALLENGE = "captcha_challenge"
    WINDOW_NOT_FOUND = "window_not_found"
    WINDOW_MINIMIZED = "window_minimized"
    PROCESS_UNRESPONSIVE = "process_unresponsive"
    POSTCONDITION_FAILED = "postcondition_failed"
    UNKNOWN_ERROR = "unknown_error"


class RecoveryStatus(StrEnum):
    """Lifecycle status of a multi-tier recovery execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED_PRIMARY = "succeeded_primary"
    RECOVERED_BROWSER = "recovered_browser"
    RECOVERED_DESKTOP = "recovered_desktop"
    FAILED_ALL_TIERS = "failed_all_tiers"


class APIRouteConfig(BaseModel):
    """Direct API / HTTP route configuration for an action."""

    endpoint_url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    expected_status_code: int = 200
    timeout_sec: float = 10.0
    auth_token: str | None = None


class BrowserRouteConfig(BaseModel):
    """Web / Browser automation route configuration for an action."""

    target_url: str
    session_id: str | None = None
    form_selector: str | None = None
    input_actions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Sequential browser interactions, e.g. [{'action': 'type', 'selector': '#user', 'value': 'alice'}]",
    )
    expected_success_selector: str | None = None
    expected_success_text: str | None = None
    navigation_timeout_sec: float = 15.0


class DesktopRouteConfig(BaseModel):
    """Native OS desktop automation route configuration for an action."""

    app_name: str
    target_window: str | int | None = None
    launch_command: str | None = None
    focus_window: bool = True
    ui_actions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Sequential UI actions, e.g. [{'action': 'click', 'name': 'Submit'}, {'action': 'type', 'text': 'val'}]",
    )
    hotkeys: list[str] = Field(default_factory=list, description="Keyboard shortcuts to dispatch e.g. ['ctrl+enter']")
    settling_delay_sec: float = 0.5


class RecoveryPolicy(BaseModel):
    """Policy configuring tier escalation, retries, and backoff."""

    fallback_ladder: list[ExecutionTier] = Field(
        default_factory=lambda: [ExecutionTier.API, ExecutionTier.BROWSER, ExecutionTier.DESKTOP]
    )
    max_retries_per_tier: int = 1
    backoff_base_sec: float = 0.25
    fast_failover_on_auth_error: bool = True
    fast_failover_on_captcha: bool = True
    require_postcondition_verification: bool = True


class SelfCorrectionHint(BaseModel):
    """Targeted corrective guidance generated after an execution or verification failure."""

    target_tier: ExecutionTier
    suggested_action: str
    parameter_adjustments: dict[str, Any] = Field(default_factory=dict)
    reason: str


class RecoveryAttemptRecord(BaseModel):
    """Audit log of a single tier execution attempt."""

    attempt_number: int
    tier: ExecutionTier
    passed: bool
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    latency_ms: float = 0.0
    correction_applied: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class ExecuteRecoveryRequest(BaseModel):
    """Request to execute an action with multi-tier recovery and verification."""

    recovery_id: str | None = None
    action_name: str
    device_id: str = "default"
    api_route: APIRouteConfig | None = None
    browser_route: BrowserRouteConfig | None = None
    desktop_route: DesktopRouteConfig | None = None
    policy: RecoveryPolicy = Field(default_factory=RecoveryPolicy)
    verification_criteria: CompositeVerificationRequest | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecuteRecoveryResult(BaseModel):
    """Outcome of multi-tier recovery execution."""

    recovery_id: str
    action_name: str
    status: RecoveryStatus
    passed: bool
    resolved_tier: ExecutionTier | None = None
    total_attempts: int = 0
    tier_attempts: list[RecoveryAttemptRecord] = Field(default_factory=list)
    verification_result: CompositeVerificationResult | None = None
    recovery_proof_hash: str
    duration_ms: float = 0.0
    completed_at: str
    root_cause_analysis: str | None = None


class RecoveryHistoryResponse(BaseModel):
    """Recent recovery execution records for a device or workspace."""

    total_records: int = 0
    records: list[ExecuteRecoveryResult] = Field(default_factory=list)


class ErrorClassificationRequest(BaseModel):
    """Request to classify an operational error and recommend fallback actions."""

    error_message: str
    status_code: int | None = None
    current_tier: ExecutionTier = ExecutionTier.API
    page_content_snippet: str | None = None


class ErrorClassificationResponse(BaseModel):
    """Diagnostics and fallback recommendation from ErrorClassifier."""

    category: ErrorCategory
    is_transient: bool
    recommended_tier: ExecutionTier | None
    recommended_action: str
    rationale: str


class SelfCorrectionRequest(BaseModel):
    """Request to generate self-correction hints from a failed check."""

    failed_tier: ExecutionTier
    error_message: str
    verification_check: SingleCheckResult | None = None


class SelfCorrectionResponse(BaseModel):
    """Self-correction hints and adjustment recommendations."""

    hints: list[SelfCorrectionHint] = Field(default_factory=list)
    can_retry_current_tier: bool = False
    escalate_to_next_tier: bool = True




