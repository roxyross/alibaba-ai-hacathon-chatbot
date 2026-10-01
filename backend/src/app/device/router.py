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
    IoTControlRequest,
    IoTDeviceResponse,
    IoTDiscoverRequest,
    IoTDiscoverResponse,
    IoTLockRequest,
    ScreenCaptureResponse,
    SessionHandoverCreateRequest,
    SessionHandoverResponse,
    WebRTCSessionCreateRequest,
    WebRTCSessionResponse,
    WebRTCSignalRequest,
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


# =============================================================================
# Phase 11: Cross-Device Continuity & Session Handover Endpoints
# =============================================================================

@router.post("/continuity/handover", response_model=SessionHandoverResponse, status_code=status.HTTP_201_CREATED)
async def create_handover(
    req: SessionHandoverCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Initiate a seamless session transfer between user devices."""
    try:
        return await _service.create_session_handover(
            user_id=user.id,
            target_device_id=req.target_device_id,
            session_id=req.session_id,
            source_device_id=req.source_device_id,
            state_payload=req.state_payload,
            ttl_seconds=req.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/continuity/handover/{handover_id}", response_model=SessionHandoverResponse)
async def get_handover(
    handover_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve details for a specific session handover token."""
    res = await _service.get_session_handover(user_id=user.id, handover_id=handover_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handover not found or access denied.")
    return res


@router.post("/continuity/handover/{handover_id}/accept", response_model=SessionHandoverResponse)
async def accept_handover(
    handover_id: str,
    target_device_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Accept an active session handover and receive transferred context."""
    try:
        return await _service.accept_session_handover(
            user_id=user.id,
            handover_id=handover_id,
            target_device_id=target_device_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/continuity/handovers", response_model=list[SessionHandoverResponse])
async def list_handovers(
    device_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List session handovers for the current user."""
    return await _service.list_session_handovers(user_id=user.id, device_id=device_id, status=status_filter)


# =============================================================================
# Phase 11: P2P WebRTC Signaling Endpoints
# =============================================================================

@router.post("/webrtc/sessions", response_model=WebRTCSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_webrtc_session(
    req: WebRTCSessionCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Establish a WebRTC P2P signaling session between paired user devices."""
    try:
        return await _service.initiate_webrtc_session(
            user_id=user.id,
            target_device_id=req.target_device_id,
            initiator_device_id=req.initiator_device_id,
            session_type=req.session_type,
            sdp_offer=req.sdp_offer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/webrtc/sessions/{session_id}/signal", response_model=WebRTCSessionResponse)
async def exchange_signal(
    session_id: str,
    req: WebRTCSignalRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Exchange WebRTC signal (SDP offer/answer, ICE candidate, or close command)."""
    try:
        return await _service.exchange_webrtc_signal(
            user_id=user.id,
            session_id=session_id,
            sender_device_id=req.sender_device_id,
            signal_type=req.signal_type,
            payload=req.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/webrtc/sessions/{session_id}", response_model=WebRTCSessionResponse)
async def get_webrtc_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the current state of a WebRTC signaling session."""
    res = await _service.get_webrtc_session(user_id=user.id, session_id=session_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WebRTC session not found or access denied.")
    return res


# =============================================================================
# Phase 11: Matter & Zigbee IoT Smart Home Endpoints
# =============================================================================

@router.get("/iot/devices", response_model=list[IoTDeviceResponse])
@router.get("/iot", response_model=list[IoTDeviceResponse])
async def list_iot_devices(
    protocol: str = Query(default="all"),
    device_type: str = Query(default="all"),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List connected Matter, Zigbee, and Thread smart home devices."""
    return await _service.discover_iot_devices(user_id=user.id, protocol=protocol, device_type=device_type)


@router.post("/iot/discover", response_model=IoTDiscoverResponse)
async def discover_iot_devices(
    req: IoTDiscoverRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Scan local network and coordinators for new IoT devices."""
    devices = await _service.discover_iot_devices(user_id=user.id, protocol=req.protocol, device_type=req.device_type)
    return {
        "discovered_count": len(devices),
        "devices": devices,
        "scan_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@router.get("/iot/{device_id}", response_model=IoTDeviceResponse)
async def get_iot_device(
    device_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve operational state and telemetry for a specific smart home device."""
    dev = await _service.get_iot_device(user_id=user.id, device_id_or_name=device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found or access denied.")
    return dev


@router.post("/iot/{device_id}/control")
async def control_iot_device(
    device_id: str,
    req: IoTControlRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Send command to a Matter/Zigbee smart home appliance."""
    try:
        return await _service.control_iot_device(
            user_id=user.id,
            device_id_or_name=device_id,
            command=req.command,
            parameters=req.parameters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/iot/{device_id}/lock")
async def control_smart_lock(
    device_id: str,
    req: IoTLockRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Control smart door lock or perimeter security gate (destructive - requires confirmation)."""
    try:
        return await _service.control_smart_lock(
            user_id=user.id,
            device_id_or_name=device_id,
            action=req.action,
            reason=req.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


