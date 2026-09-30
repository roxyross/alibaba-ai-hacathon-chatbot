"""FastAPI router for Device Agent, App Discovery, and OS App Control."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.schemas import (
    AppCloseRequest,
    AppFocusRequest,
    AppLaunchRequest,
    AppScanResponse,
    DeviceActionLogResponse,
    DeviceRegisterRequest,
    DeviceResponse,
    DeviceTelemetryResponse,
    DiscoveredAppResponse,
    ScreenCaptureResponse,
)
from app.device.service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])
_service = DeviceService.get_instance()


def get_device_service() -> DeviceService:
    return _service


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all registered devices for the current user."""
    return await _service.list_devices(user_id=user.id)


@router.get("/current", response_model=DeviceResponse)
async def get_current_device(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve or automatically register the local host machine."""
    return await _service.get_or_create_local_device(user_id=user.id)


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
@router.post("/register", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    req: DeviceRegisterRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Register a remote or companion device."""
    return await _service.register_device(user_id=user.id, data=req.model_dump())


@router.get("/{device_id}/apps", response_model=list[DiscoveredAppResponse])
async def list_apps(
    device_id: str,
    category: str | None = Query(default=None, description="Filter by app category"),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all discovered applications installed on the specified device."""
    return await _service.list_apps(user_id=user.id, device_id=device_id, category=category)


@router.post("/{device_id}/apps/scan", response_model=AppScanResponse)
async def scan_apps(
    device_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger a fresh discovery scan across the device filesystem and running processes."""
    t0 = time.time()
    apps = await _service.scan_installed_apps(user_id=user.id, device_id=device_id)
    duration_ms = round((time.time() - t0) * 1000, 2)
    return {
        "device_id": device_id,
        "scanned_count": len(apps),
        "discovered_apps": apps,
        "scan_duration_ms": duration_ms,
    }


@router.post("/{device_id}/apps/launch")
async def launch_app(
    device_id: str,
    req: AppLaunchRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Launch an application on the user's computer."""
    target = req.app_name_or_path or req.executable_path or req.app_name or req.app_id
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide app_name, executable_path, or app_id to launch.",
        )
    return await _service.launch_app(
        user_id=user.id,
        device_id=device_id,
        app_name_or_path=target,
        arguments=req.arguments,
        working_directory=req.working_directory,
    )


@router.post("/{device_id}/apps/close")
async def close_app(
    device_id: str,
    req: AppCloseRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Terminate or close an active application on the user's computer."""
    target = (
        req.app_name_or_pid
        if req.app_name_or_pid is not None
        else (req.process_id if req.process_id is not None else (req.app_name or req.app_id))
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide app_name, process_id, or app_id to close.",
        )
    return await _service.close_app(
        user_id=user.id,
        device_id=device_id,
        app_name_or_pid=target,
        force=req.force,
    )


@router.post("/{device_id}/apps/focus")
async def focus_app(
    device_id: str,
    req: AppFocusRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Bring an application window to the foreground."""
    return await _service.focus_app(
        user_id=user.id,
        device_id=device_id,
        app_name=req.app_name,
    )


@router.post("/{device_id}/screenshot", response_model=ScreenCaptureResponse)
async def capture_screen(
    device_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Capture a live screenshot of the device's display."""
    return await _service.capture_screen(user_id=user.id, device_id=device_id)


@router.get("/{device_id}/telemetry", response_model=DeviceTelemetryResponse)
async def get_telemetry(
    device_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get real-time device hardware metrics and active window info."""
    data = _service.get_system_telemetry()
    return {
        "device_id": device_id,
        "hostname": str(data["hostname"]),
        "os_platform": str(data["os_platform"]),
        "cpu_percent": float(data["cpu_percent"]),
        "memory_percent": float(data["memory_percent"]),
        "disk_free_gb": float(data["disk_free_gb"]),
        "active_window": str(data.get("active_window")),
        "battery_percent": None,
        "timestamp": str(data["timestamp"]),
    }


@router.get("/{device_id}/actions", response_model=list[DeviceActionLogResponse])
async def list_device_actions(
    device_id: str,
    limit: int = Query(default=50, le=100),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retrieve audit history of actions and commands executed on this device."""
    return await _service.list_device_actions(user_id=user.id, device_id=device_id, limit=limit)

