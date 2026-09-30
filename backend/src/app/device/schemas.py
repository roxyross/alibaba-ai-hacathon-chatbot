"""Pydantic schemas for Device Agent, App Discovery, and App Control."""

from __future__ import annotations

from typing import Any

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
    icon_url: str | None = None
    is_running: bool
    process_id: int | None = None
    launch_count: int
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
    capabilities: list[str]
    telemetry: dict[str, Any]
    last_heartbeat_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AppLaunchRequest(BaseModel):
    """Request to launch a discovered application or executable."""

    app_id: str | None = Field(default=None, description="Discovered app ID if known")
    app_name: str | None = Field(default=None, description="App name or binary command")
    executable_path: str | None = Field(default=None, description="Explicit executable path")
    app_name_or_path: str | None = Field(default=None, description="Universal app identifier or path")
    arguments: list[str] = Field(default_factory=list, description="Command line arguments")
    working_directory: str | None = Field(default=None, description="Optional working directory")


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


class AppScanResponse(BaseModel):
    """Result of app discovery scan."""

    device_id: str
    scanned_count: int
    discovered_apps: list[DiscoveredAppResponse]
    scan_duration_ms: float


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
