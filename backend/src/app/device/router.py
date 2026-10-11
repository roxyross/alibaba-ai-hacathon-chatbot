"""FastAPI router for Device Agent, App Discovery, and OS App Control."""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.schemas import (
    AndroidActionResponse,
    AndroidCompanionEnvelope,
    AndroidCompanionResponse,
    AndroidCompanionTelemetry,
    AndroidDeepLinkRequest,
    AndroidIntentRequest,
    AndroidNodeInfoModel,
    AndroidScreenshotResponse,
    APIResponseVerificationCriteria,
    AppCloseRequest,
    AppControlConfirmationRequest,
    AppControlExecutionPlan,
    AppControlExecutionRequest,
    AppControlExecutionResult,
    AppFocusRequest,
    AppLaunchRequest,
    AppScanRequest,
    AppScanResponse,
    CompositeVerificationRequest,
    CompositeVerificationResult,
    ConnectorDiscoveryRequest,
    ConnectorDiscoveryResult,
    ConnectorToolBindingRequest,
    ConnectorToolBindingResult,
    CreateSurfaceSessionRequest,
    DeviceActionLogResponse,
    DeviceCommandQueueRequest,
    DeviceCommandResponse,
    DeviceCommandResultSubmission,
    DeviceHeartbeatRequest,
    DeviceHeartbeatResponse,
    DeviceRegisterRequest,
    DeviceResponse,
    DeviceTelemetryResponse,
    DiscoverCapabilitiesRequest,
    DiscoveredAppBulkSyncRequest,
    DiscoveredAppBulkSyncResponse,
    DiscoveredAppResponse,
    DiscoveryBoundToolsResponse,
    DOMStateVerificationCriteria,
    EmbedEvaluationRequest,
    EmbedEvaluationResult,
    EnrollmentClaimRequest,
    EnrollmentClaimResponse,
    EnrollmentTokenCreateRequest,
    EnrollmentTokenResponse,
    ErrorClassificationRequest,
    ErrorClassificationResponse,
    ExecuteAppActionRequest,
    ExecuteRecoveryRequest,
    ExecuteRecoveryResult,
    FleetBroadcastQueryRequest,
    FleetBroadcastQueryResponse,
    FleetExecutionRequest,
    FleetExecutionResult,
    FleetHandoverRequest,
    FleetHandoverResult,
    FleetRoutingDecision,
    FleetRoutingRequest,
    FleetSummaryResponse,
    IntegrationResolutionRequest,
    IntegrationResolutionResult,
    IOSActionResponse,
    IOSAppIntentRequest,
    IOSCompanionEnvelope,
    IOSCompanionResponse,
    IOSShareSheetRequest,
    IOSShortcutRequest,
    IOSTelemetry,
    IOSUniversalLinkRequest,
    IOSURLSchemeRequest,
    IoTControlRequest,
    IoTDeviceResponse,
    IoTDiscoverRequest,
    IoTDiscoverResponse,
    IoTLockRequest,
    MCPDiscoveryRequest,
    MCPDiscoveryResult,
    MCPToolBindingRequest,
    MCPToolBindingResult,
    MobileAppDiscoveryRequest,
    MobileAppDiscoveryResponse,
    MobileAppModel,
    MobileCapabilityResolutionRequest,
    MobileCapabilityResolutionResponse,
    NewAppDetectionRequest,
    NewAppDetectionResult,
    NewAppIntrospectionRequest,
    NewAppIntrospectionResult,
    NewAppRankingRequest,
    NewAppRankingResult,
    NewAppRegistrationRequest,
    NewAppRegistrationResult,
    NewAppWorkflowRequest,
    NewAppWorkflowResponse,
    OCRVisualVerificationCriteria,
    ProcessRestartRequest,
    ProcessStateVerificationCriteria,
    ProcessTerminationRequest,
    RecoveryHistoryResponse,
    RelayInputRequest,
    RelayInputResult,
    ScreenCaptureResponse,
    SelfCorrectionRequest,
    SelfCorrectionResponse,
    SessionHandoverCreateRequest,
    SessionHandoverResponse,
    SingleCheckResult,
    SurfaceFrameSnapshot,
    UIActionResponse,
    UIClickElementRequest,
    UIElementResponse,
    UIFindElementRequest,
    UIInspectRequest,
    UIScreenshotRequest,
    UIScreenshotResponse,
    UIScrollRequest,
    UISelectElementRequest,
    UISendHotkeyRequest,
    UITypeTextRequest,
    UIWaitForElementRequest,
    UIWindowStateRequest,
    UIWindowStateResponse,
    UnifiedDiscoveryRequest,
    UnifiedDiscoveryResult,
    VerificationHistoryResponse,
    WebRTCSessionCreateRequest,
    WebRTCSessionResponse,
    WebRTCSignalRequest,
    WindowStateVerificationCriteria,
    WorkspaceSessionListResponse,
    WorkspaceSessionStatus,
    WorkspaceSurfaceSession,
)
from app.device.service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])
_service = DeviceService.get_instance()


def get_device_service() -> DeviceService:
    return _service


async def get_authenticated_device(
    device_id: str,
    x_device_token: str | None = Header(None, alias="X-Device-Token"),
) -> dict[str, Any]:
    """Validate secret device token presented by daemon in request headers."""
    if not x_device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Token authentication header.",
        )
    dev = await _service.authenticate_device_token(device_id=device_id, device_token=x_device_token)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unrecognized device token.",
        )
    return dev


# =============================================================================
# Phase 3: Standalone Agent Enrollment & Authentication Endpoints
# =============================================================================

@router.post("/enrollment/token", response_model=EnrollmentTokenResponse, status_code=status.HTTP_201_CREATED)
async def create_enrollment_token(
    req: EnrollmentTokenCreateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate a time-bounded pairing token for enrolling a standalone agent."""
    return await _service.create_enrollment_token(
        user_id=user.id,
        label=req.label,
        ttl_seconds=req.ttl_seconds,
    )


@router.post("/enrollment/claim", response_model=EnrollmentClaimResponse, status_code=status.HTTP_201_CREATED)
async def claim_enrollment_token(
    req: EnrollmentClaimRequest,
) -> dict[str, Any]:
    """Daemon claims pairing token, submits hardware fingerprint, and receives device credentials."""
    try:
        return await _service.claim_enrollment(data=req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{device_id}/heartbeat", response_model=DeviceHeartbeatResponse)
async def device_heartbeat(
    device_id: str,
    req: DeviceHeartbeatRequest,
    _device: dict[str, Any] = Depends(get_authenticated_device),
) -> dict[str, Any]:
    """Daemon periodically reports online status and hardware telemetry."""
    return await _service.heartbeat(
        device_id=device_id,
        telemetry=req.telemetry,
        daemon_version=req.daemon_version,
    )


@router.get("/{device_id}/commands/poll", response_model=list[DeviceCommandResponse])
async def poll_device_commands(
    device_id: str,
    limit: int = Query(default=10, le=50),
    _device: dict[str, Any] = Depends(get_authenticated_device),
) -> list[dict[str, Any]]:
    """Daemon polls for queued commands awaiting execution."""
    return await _service.poll_pending_commands(device_id=device_id, max_count=limit)


@router.post("/{device_id}/commands/{command_id}/result", response_model=DeviceCommandResponse)
async def submit_command_result(
    device_id: str,
    command_id: str,
    req: DeviceCommandResultSubmission,
    _device: dict[str, Any] = Depends(get_authenticated_device),
) -> dict[str, Any]:
    """Daemon submits result of an executed command."""
    try:
        return await _service.submit_command_result(
            device_id=device_id,
            command_id=command_id,
            status=req.status,
            result=req.result,
            error=req.error,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{device_id}/commands", response_model=DeviceCommandResponse, status_code=status.HTTP_201_CREATED)
async def queue_device_command(
    device_id: str,
    req: DeviceCommandQueueRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Queue an asynchronous command for a device."""
    return await _service.queue_command(
        user_id=user.id,
        device_id=device_id,
        command_type=req.command_type,
        payload=req.payload,
        timeout_seconds=req.timeout_seconds,
    )


@router.get("/{device_id}/commands", response_model=list[DeviceCommandResponse])
async def list_device_commands(
    device_id: str,
    limit: int = Query(default=50, le=100),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List recent commands sent to this device."""
    return await _service.list_device_commands(
        user_id=user.id,
        device_id=device_id,
        limit=limit,
    )


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


@router.get("/state")
@router.get("/current/state")
async def get_device_state(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve comprehensive live device operational state, telemetry, ADB report, and browser profile statuses."""
    from datetime import UTC, datetime
    from app.device.android_automation import AndroidAutomationEngine

    telemetry = _service.get_system_telemetry()
    active_window = telemetry.get("active_window")

    adb_report = AndroidAutomationEngine.check_prerequisites()

    whatsapp_status: dict[str, Any] = {}
    try:
        from app.integrations.whatsapp.service import WhatsAppService
        whatsapp_svc = WhatsAppService.get_instance()
        reports = await whatsapp_svc.probe_all_routes()
        whatsapp_status = {
            r.value: {
                "state": rep.state.value,
                "is_ready": rep.is_ready,
                "details": rep.details,
            }
            for r, rep in reports.items()
        }
    except Exception as exc:
        whatsapp_status = {"error": str(exc)}

    return {
        "status": "online",
        "active_window": active_window,
        "telemetry": telemetry,
        "connected_mobile_devices": {
            "adb_installed": adb_report.is_adb_installed,
            "attached_devices": adb_report.attached_devices,
            "device_count": len(adb_report.attached_devices),
            "recommendations": adb_report.recommendations,
            "install_command": adb_report.installation_command,
        },
        "browser_profiles": {
            "whatsapp": whatsapp_status,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


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
    is_running: bool | None = Query(default=None, description="Filter by running status"),
    search: str | None = Query(default=None, description="Search by app name, publisher, or description"),
    limit: int = Query(default=100, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all discovered applications installed on the specified device with search and filtering."""
    return await _service.list_apps(
        user_id=user.id,
        device_id=device_id,
        category=category,
        is_running=is_running,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{device_id}/apps/{app_id}", response_model=DiscoveredAppResponse)
async def get_app_details(
    device_id: str,
    app_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve detailed metadata and inferred capabilities for a specific application."""
    app = await _service.get_app_details(user_id=user.id, device_id=device_id, app_id_or_name=app_id)
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Application '{app_id}' not found.")
    return app


@router.post("/{device_id}/apps/scan", response_model=AppScanResponse)
async def scan_apps(
    device_id: str,
    req: AppScanRequest | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger a deep discovery scan across the device filesystem, registry, and running processes."""
    t0 = time.time()
    force_refresh = req.force_refresh if req else False
    include_system_apps = req.include_system_apps if req else False

    apps = await _service.scan_installed_apps(
        user_id=user.id,
        device_id=device_id,
        force_refresh=force_refresh,
        include_system_apps=include_system_apps,
    )
    duration_ms = round((time.time() - t0) * 1000, 2)

    categories_summary: dict[str, int] = {}
    running_count = 0
    for a in apps:
        cat = a.get("category", "other")
        categories_summary[cat] = categories_summary.get(cat, 0) + 1
        if a.get("is_running"):
            running_count += 1

    return {
        "device_id": device_id,
        "scanned_count": len(apps),
        "discovered_apps": apps,
        "categories_summary": categories_summary,
        "running_count": running_count,
        "scan_duration_ms": duration_ms,
    }


@router.post("/{device_id}/apps/sync", response_model=DiscoveredAppBulkSyncResponse)
async def sync_device_apps(
    device_id: str,
    req: DiscoveredAppBulkSyncRequest,
    _device: dict[str, Any] = Depends(get_authenticated_device),
) -> dict[str, Any]:
    """Synchronize application catalog reported by a standalone device daemon."""
    count = await _service.sync_device_apps(
        user_id=_device["user_id"],
        device_id=device_id,
        apps=req.apps,
    )
    return {
        "synced_count": count,
        "device_id": device_id,
        "message": f"Successfully synchronized {count} applications.",
    }


@router.post("/{device_id}/apps/launch")
async def launch_app(
    device_id: str,
    req: AppLaunchRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Launch an application on the user's computer."""
    target = req.target or req.app_name_or_path or req.executable_path or req.app_name or req.app_id
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide target, app_name, executable_path, or app_id to launch.",
        )
    return await _service.launch_app(
        user_id=user.id,
        device_id=device_id,
        app_name_or_path=target,
        arguments=req.arguments,
        working_directory=req.working_directory,
        environment=req.environment,
        wait_for_window=req.wait_for_window,
        window_timeout_sec=req.window_timeout_sec,
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


@router.post("/{device_id}/apps/terminate")
async def terminate_app(
    device_id: str,
    req: ProcessTerminationRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Gracefully close or forcibly terminate an application or process tree."""
    return await _service.terminate_app(
        user_id=user.id,
        device_id=device_id,
        app_name_or_pid=req.target,
        force=req.force,
        timeout_sec=req.timeout_sec,
        terminate_children=req.terminate_children,
    )


@router.post("/{device_id}/apps/restart")
async def restart_app(
    device_id: str,
    req: ProcessRestartRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Restart an active application preserving original arguments and working directory."""
    return await _service.restart_app(
        user_id=user.id,
        device_id=device_id,
        app_name_or_pid=req.target,
        force=req.force,
        arguments=req.arguments,
        wait_timeout_sec=req.wait_timeout_sec,
    )


@router.get("/{device_id}/processes")
async def list_processes(
    device_id: str,
    filter_name: str | None = Query(None, description="Filter processes by name substring"),
    running_only: bool = Query(True, description="Exclude dead or zombie processes"),
    limit: int = Query(100, ge=1, le=500, description="Max processes to return"),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List active processes with memory and CPU telemetry."""
    return await _service.list_processes(
        user_id=user.id,
        device_id=device_id,
        filter_name=filter_name,
        running_only=running_only,
        limit=limit,
    )


@router.get("/{device_id}/processes/{pid}")
async def get_process_details(
    device_id: str,
    pid: int,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve detailed telemetry, child process tree, and resource usage for a PID."""
    details = await _service.get_process_details(
        user_id=user.id,
        device_id=device_id,
        pid=pid,
    )
    if not details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process with PID {pid} not found on device.",
        )
    return details


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


# =============================================================================
# Phase 4: Windows UI Automation Endpoints
# =============================================================================

@router.post("/{device_id}/ui/inspect", response_model=UIElementResponse)
async def inspect_device_ui(
    device_id: str,
    req: UIInspectRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Deeply inspect the UI element hierarchy of a target window (or active desktop)."""
    try:
        return await _service.inspect_ui(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
            max_depth=req.max_depth,
            max_children=req.max_children,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/find", response_model=UIElementResponse)
async def find_device_ui_element(
    device_id: str,
    req: UIFindElementRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Find a specific UI element inside a target desktop window."""
    try:
        return await _service.find_ui_element(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
            name=req.name,
            automation_id=req.automation_id,
            control_type=req.control_type,
            role=req.role,
            timeout_sec=req.timeout_sec,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/click", response_model=UIActionResponse)
async def click_device_ui_element(
    device_id: str,
    req: UIClickElementRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Click a native UI element or button inside a desktop application window."""
    try:
        res = await _service.click_ui_element(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
            name=req.name,
            automation_id=req.automation_id,
            control_type=req.control_type,
            click_type=req.click_type,
        )
        return {"success": True, "action": "click", "details": res}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/type", response_model=UIActionResponse)
async def type_device_ui_text(
    device_id: str,
    req: UITypeTextRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Type text into a target edit control or desktop application window."""
    try:
        res = await _service.type_ui_text(
            user_id=user.id,
            device_id=device_id,
            text=req.text,
            window_target=req.window_target,
            name=req.name,
            automation_id=req.automation_id,
            control_type=req.control_type,
            clear_first=req.clear_first,
            press_enter=req.press_enter,
        )
        return {"success": True, "action": "type", "details": res}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/hotkey", response_model=UIActionResponse)
async def send_device_ui_hotkey(
    device_id: str,
    req: UISendHotkeyRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Send a keyboard shortcut or hotkey combination to a window."""
    try:
        res = await _service.send_ui_hotkey(
            user_id=user.id,
            device_id=device_id,
            hotkey=req.hotkey,
            window_target=req.window_target,
        )
        return {"success": True, "action": "hotkey", "details": res}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/scroll", response_model=UIActionResponse)
async def scroll_device_ui(
    device_id: str,
    req: UIScrollRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Scroll an application window or scrollable control."""
    try:
        res = await _service.scroll_ui(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
            name=req.name,
            automation_id=req.automation_id,
            direction=req.direction,
            amount=req.amount,
        )
        return {"success": True, "action": "scroll", "details": res}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/window-state", response_model=UIWindowStateResponse)
async def get_device_ui_window_state(
    device_id: str,
    req: UIWindowStateRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Inspect and return real runtime state of the specified window."""
    try:
        return await _service.get_ui_window_state(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/screenshot", response_model=UIScreenshotResponse)
async def capture_device_ui_screenshot(
    device_id: str,
    req: UIScreenshotRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Capture a secure screenshot of a window or entire desktop."""
    try:
        return await _service.capture_ui_screenshot(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/select", response_model=UIActionResponse)
async def select_device_ui_element(
    device_id: str,
    req: UISelectElementRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Select an item in a list or tab container."""
    try:
        res = await _service.select_ui_element(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
            name=req.name,
            automation_id=req.automation_id,
            item_name=req.item_name,
        )
        return {"success": True, "action": "select", "details": res}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{device_id}/ui/wait", response_model=UIElementResponse)
async def wait_for_device_ui_element(
    device_id: str,
    req: UIWaitForElementRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Poll window until target element is found and ready."""
    try:
        return await _service.wait_for_ui_element(
            user_id=user.id,
            device_id=device_id,
            window_target=req.window_target,
            name=req.name,
            automation_id=req.automation_id,
            control_type=req.control_type,
            timeout_sec=req.timeout_sec,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# =============================================================================
# Phase 7: Dynamic Capability Discovery & Execution Endpoints
# =============================================================================

@router.post("/{device_id}/apps/{app_id_or_name}/capabilities/discover")
async def discover_device_app_capabilities(
    device_id: str,
    app_id_or_name: str,
    req: DiscoverCapabilitiesRequest = DiscoverCapabilitiesRequest(),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Dynamically introspect an application (CLI flags, subcommands, REST endpoints) and generate executable tools."""
    try:
        return await _service.discover_app_capabilities(
            user_id=user.id,
            device_id=device_id,
            app_id_or_name=app_id_or_name,
            probe_live=req.probe_live,
            register_tools=req.register_tools,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{device_id}/apps/{app_id_or_name}/capabilities")
async def get_device_app_capabilities(
    device_id: str,
    app_id_or_name: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve discovered capabilities and action metadata for an application."""
    app_meta = await _service.get_app_details(user_id=user.id, device_id=device_id, app_id_or_name=app_id_or_name)
    if not app_meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Application '{app_id_or_name}' not found.")
    return {
        "app_name": app_meta.get("app_name"),
        "capabilities": app_meta.get("capabilities", []),
        "supported_actions": app_meta.get("supported_actions", []),
        "metadata": app_meta.get("metadata", {}),
    }


@router.post("/{device_id}/apps/{app_id_or_name}/actions/{action_name}/execute")
async def execute_device_app_action(
    device_id: str,
    app_id_or_name: str,
    action_name: str,
    req: ExecuteAppActionRequest = ExecuteAppActionRequest(),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute a dynamic capability or action against the specified application."""
    try:
        return await _service.execute_app_action(
            user_id=user.id,
            device_id=device_id,
            app_id_or_name=app_id_or_name,
            action_name=action_name,
            parameters=req.parameters,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# =============================================================================
# Phase 8: Universal Integration Resolution Engine Endpoints
# =============================================================================

@router.post("/{device_id}/resolve-integration", response_model=IntegrationResolutionResult)
async def resolve_device_integration(
    device_id: str,
    req: IntegrationResolutionRequest,
    user: User = Depends(get_current_user),
) -> IntegrationResolutionResult:
    """Determine the optimal verified integration route for an application capability on a device."""
    try:
        return await _service.resolve_integration(
            user_id=user.id,
            device_id=device_id,
            application=req.application,
            requested_capability=req.requested_capability,
            preferred_integration=req.preferred_integration,
            device_context=req.device,
            user_context=req.user_context,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/resolve-integration", response_model=IntegrationResolutionResult)
async def resolve_generic_integration(
    req: IntegrationResolutionRequest,
    user: User = Depends(get_current_user),
) -> IntegrationResolutionResult:
    """Determine the optimal verified integration route across available surfaces."""
    try:
        return await _service.resolve_integration(
            user_id=user.id,
            device_id="local",
            application=req.application,
            requested_capability=req.requested_capability,
            preferred_integration=req.preferred_integration,
            device_context=req.device,
            user_context=req.user_context,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# =============================================================================
# Phase 9: Universal App Control Orchestrator Endpoints
# =============================================================================

@router.post("/{device_id}/app-control/orchestrate", response_model=AppControlExecutionResult)
async def orchestrate_device_app_control(
    device_id: str,
    req: AppControlExecutionRequest,
    user: User = Depends(get_current_user),
) -> AppControlExecutionResult:
    """Orchestrate end-to-end execution of an application capability on a specific device."""
    try:
        return await _service.orchestrate_app_control(
            user_id=user.id,
            device_id=device_id,
            application=req.application,
            capability=req.capability,
            parameters=req.parameters,
            preferred_integration=req.preferred_integration,
            confirmed=req.confirmed,
            confirmation_token=req.confirmation_token,
            skip_verification=req.skip_verification,
            device_context=req.device_context,
            user_context=req.user_context,
            timeout_sec=req.timeout_sec,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/app-control/orchestrate", response_model=AppControlExecutionResult)
async def orchestrate_generic_app_control(
    req: AppControlExecutionRequest,
    user: User = Depends(get_current_user),
) -> AppControlExecutionResult:
    """Orchestrate end-to-end execution of an application capability across available surfaces."""
    try:
        target_dev = req.device_id or "local"
        return await _service.orchestrate_app_control(
            user_id=user.id,
            device_id=target_dev,
            application=req.application,
            capability=req.capability,
            parameters=req.parameters,
            preferred_integration=req.preferred_integration,
            confirmed=req.confirmed,
            confirmation_token=req.confirmation_token,
            skip_verification=req.skip_verification,
            device_context=req.device_context,
            user_context=req.user_context,
            timeout_sec=req.timeout_sec,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/app-control/confirm", response_model=AppControlExecutionResult)
async def confirm_app_control(
    req: AppControlConfirmationRequest,
    user: User = Depends(get_current_user),
) -> AppControlExecutionResult:
    """Confirm and proceed with a pending high-risk or sensitive application control action."""
    try:
        return await _service.confirm_app_control(
            confirmation_token=req.confirmation_token,
            user_id=user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/app-control/executions/{execution_id}", response_model=AppControlExecutionResult)
async def get_app_control_execution(
    execution_id: str,
    user: User = Depends(get_current_user),
) -> AppControlExecutionResult:
    """Retrieve historical application control execution result by ID."""
    from app.device.orchestrator import UniversalAppController

    res = UniversalAppController.get_execution(execution_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution '{execution_id}' not found.")
    return res


@router.get("/app-control/plans/{plan_id}", response_model=AppControlExecutionPlan)
async def get_app_control_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
) -> AppControlExecutionPlan:
    """Retrieve synthesized application control execution plan by ID."""
    from app.device.orchestrator import UniversalAppController

    plan = UniversalAppController.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution plan '{plan_id}' not found.")
    return plan


# =============================================================================
# Phase 10: Multi-Device Fleet Orchestration Endpoints
# =============================================================================

@router.post("/fleet/route", response_model=FleetRoutingDecision)
async def route_fleet_device(
    req: FleetRoutingRequest,
    user: User = Depends(get_current_user),
) -> FleetRoutingDecision:
    """Evaluate user fleet and determine the optimal device for an application control task."""
    try:
        return await _service.route_fleet_task(
            user_id=user.id,
            application=req.application,
            capability=req.capability,
            preferred_device_id=req.preferred_device_id,
            required_capabilities=req.required_capabilities,
            required_os_platform=req.required_os_platform,
            parameters=req.parameters,
            allow_offline=req.allow_offline,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/fleet/execute", response_model=FleetExecutionResult)
async def execute_fleet_action(
    req: FleetExecutionRequest,
    user: User = Depends(get_current_user),
) -> FleetExecutionResult:
    """Execute an application capability across the fleet with automatic routing and failover."""
    try:
        return await _service.execute_fleet_app_control(
            user_id=user.id,
            application=req.application,
            capability=req.capability,
            parameters=req.parameters,
            preferred_device_id=req.preferred_device_id,
            preferred_integration=req.preferred_integration,
            allow_failover=req.allow_failover,
            max_failovers=req.max_failovers,
            confirmed=req.confirmed,
            confirmation_token=req.confirmation_token,
            skip_verification=req.skip_verification,
            timeout_sec=req.timeout_sec,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/fleet/handover", response_model=FleetHandoverResult)
async def initiate_fleet_handover(
    req: FleetHandoverRequest,
    user: User = Depends(get_current_user),
) -> FleetHandoverResult:
    """Seamlessly migrate an active task or session from one device to another."""
    try:
        return await _service.initiate_fleet_handover(
            user_id=user.id,
            source_device_id=req.source_device_id,
            target_device_id=req.target_device_id,
            application=req.application,
            capability=req.capability,
            parameters=req.parameters,
            state_payload=req.state_payload,
            reason=req.reason,
            auto_resume=req.auto_resume,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/fleet/summary", response_model=FleetSummaryResponse)
async def get_fleet_summary(
    user: User = Depends(get_current_user),
) -> FleetSummaryResponse:
    """Retrieve consolidated status, liveness, and app catalog distribution across the user's fleet."""
    try:
        return await _service.get_fleet_summary(user_id=user.id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/fleet/broadcast", response_model=FleetBroadcastQueryResponse)
async def broadcast_fleet_query(
    req: FleetBroadcastQueryRequest,
    user: User = Depends(get_current_user),
) -> FleetBroadcastQueryResponse:
    """Broadcast a query across all active devices in the user's fleet."""
    try:
        return await _service.broadcast_fleet_query(
            user_id=user.id,
            query_type=req.query_type,
            query_target=req.query_target,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# =============================================================================
# Phase 11: Mobile Agent — Android Endpoints
# =============================================================================

@router.get("/{device_id}/android/inspect", response_model=AndroidNodeInfoModel)
async def android_inspect_ui(
    device_id: str,
    max_depth: int = Query(default=5, ge=1, le=20),
    user: User = Depends(get_current_user),
) -> AndroidNodeInfoModel:
    """Inspect the live AccessibilityNodeInfo tree on the specified Android device."""
    try:
        return await _service.android_inspect_ui(device_id=device_id, max_depth=max_depth)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{device_id}/android/find", response_model=AndroidNodeInfoModel)
async def android_find_element(
    device_id: str,
    text: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    content_description: str | None = Query(default=None),
    role: str | None = Query(default=None),
    package_name: str | None = Query(default=None),
    timeout_sec: float = Query(default=5.0, ge=0.5, le=30.0),
    user: User = Depends(get_current_user),
) -> AndroidNodeInfoModel:
    """Find a UI element in the active Android accessibility hierarchy matching criteria."""
    try:
        return await _service.android_find_element(
            device_id=device_id,
            text=text,
            resource_id=resource_id,
            content_description=content_description,
            role=role,
            package_name=package_name,
            timeout_sec=timeout_sec,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{device_id}/android/click", response_model=AndroidActionResponse)
async def android_click_element(
    device_id: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
) -> AndroidActionResponse:
    """Tap or click a UI element or coordinate on the active Android screen."""
    try:
        return await _service.android_click_element(
            device_id=device_id,
            text=payload.get("text"),
            resource_id=payload.get("resource_id"),
            content_description=payload.get("content_description"),
            x=payload.get("x"),
            y=payload.get("y"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{device_id}/android/type", response_model=AndroidActionResponse)
async def android_type_text(
    device_id: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
) -> AndroidActionResponse:
    """Type text into an active or targeted EditText on the Android screen."""
    try:
        text = str(payload.get("text", ""))
        return await _service.android_type_text(
            text=text,
            device_id=device_id,
            resource_id=payload.get("resource_id"),
            clear_first=bool(payload.get("clear_first", False)),
            press_enter=bool(payload.get("press_enter", False)),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{device_id}/android/scroll", response_model=AndroidActionResponse)
async def android_scroll(
    device_id: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
) -> AndroidActionResponse:
    """Scroll or swipe the Android screen in the specified direction."""
    try:
        direction = str(payload.get("direction", "down"))
        distance_px = int(payload.get("distance_px", 800))
        return await _service.android_scroll(
            direction=direction,
            device_id=device_id,
            distance_px=distance_px,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{device_id}/android/key", response_model=AndroidActionResponse)
async def android_press_key(
    device_id: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
) -> AndroidActionResponse:
    """Send navigation or hardware keyevents (back, home, enter, etc.) to Android."""
    try:
        key = str(payload.get("key", payload.get("keycode", "back")))
        return await _service.android_press_key(key=key, device_id=device_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{device_id}/android/intent", response_model=AndroidActionResponse)
async def android_send_intent(
    device_id: str,
    req: AndroidIntentRequest,
    user: User = Depends(get_current_user),
) -> AndroidActionResponse:
    """Dispatch an explicit or implicit Android Intent with action, URI, and typed extras."""
    try:
        return await _service.android_send_intent(intent=req, device_id=device_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{device_id}/android/deep-link", response_model=AndroidActionResponse)
async def android_open_deep_link(
    device_id: str,
    req: AndroidDeepLinkRequest,
    user: User = Depends(get_current_user),
) -> AndroidActionResponse:
    """Open a custom URI deep link or web app URL with fallback handling."""
    try:
        return await _service.android_open_deep_link(req=req, device_id=device_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/{device_id}/android/screenshot", response_model=AndroidScreenshotResponse)
async def android_take_screenshot(
    device_id: str,
    user: User = Depends(get_current_user),
) -> AndroidScreenshotResponse:
    """Capture a Base64-encoded PNG screenshot of the Android screen buffer."""
    try:
        return await _service.android_take_screenshot(device_id=device_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/android/companion/heartbeat")
async def android_companion_heartbeat(
    telemetry: AndroidCompanionTelemetry,
) -> dict[str, Any]:
    """Record heartbeat telemetry from an enrolled Android Companion agent."""
    return _service.android_companion_heartbeat(telemetry)


@router.post("/android/companion/response")
async def android_companion_response(
    resp: AndroidCompanionResponse,
) -> dict[str, Any]:
    """Resolve a pending companion command future with client execution result."""
    return _service.android_companion_response(resp)


@router.post("/{device_id}/android/companion/command", response_model=AndroidCompanionResponse)
async def android_companion_send_command(
    device_id: str,
    envelope: AndroidCompanionEnvelope,
    user: User = Depends(get_current_user),
) -> AndroidCompanionResponse:
    """Dispatch a command envelope to an enrolled Android companion device and await response."""
    try:
        return await _service.android_companion_send_command(device_id=device_id, envelope=envelope)
    except ConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# =============================================================================
# Phase 12: Mobile Agent — iOS Endpoints
# =============================================================================

@router.post("/{device_id}/ios/universal-link", response_model=IOSActionResponse)
async def ios_open_universal_link(
    device_id: str,
    req: IOSUniversalLinkRequest,
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Open an iOS Universal Link (HTTP/HTTPS) with native application claim and web fallback."""
    return await _service.ios_open_universal_link(req=req, device_id=device_id)


@router.post("/{device_id}/ios/url-scheme", response_model=IOSActionResponse)
async def ios_open_url_scheme(
    device_id: str,
    req: IOSURLSchemeRequest,
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Open a native iOS custom URL scheme (e.g. spotify://, maps://, shortcuts://)."""
    return await _service.ios_open_url_scheme(req=req, device_id=device_id)


@router.post("/{device_id}/ios/shortcut", response_model=IOSActionResponse)
async def ios_run_shortcut(
    device_id: str,
    req: IOSShortcutRequest,
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Dispatch execution of an Apple Shortcut via shortcuts:// or x-callback-url protocol."""
    return await _service.ios_run_shortcut(req=req, device_id=device_id)


@router.post("/{device_id}/ios/app-intent", response_model=IOSActionResponse)
async def ios_dispatch_app_intent(
    device_id: str,
    req: IOSAppIntentRequest,
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Dispatch an iOS 16+ App Intent with structured parameters."""
    return await _service.ios_dispatch_app_intent(req=req, device_id=device_id)


@router.post("/{device_id}/ios/share-sheet", response_model=IOSActionResponse)
async def ios_share_sheet(
    device_id: str,
    req: IOSShareSheetRequest,
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Format and present an iOS UIActivityViewController Share Sheet payload."""
    return await _service.ios_share_sheet(req=req, device_id=device_id)


@router.get("/{device_id}/ios/telemetry", response_model=IOSTelemetry)
async def ios_get_telemetry(
    device_id: str,
    user: User = Depends(get_current_user),
) -> IOSTelemetry:
    """Retrieve operational telemetry from an enrolled iOS device."""
    return _service.ios_get_telemetry(device_id=device_id)


@router.post("/{device_id}/ios/telemetry")
async def ios_companion_heartbeat(
    device_id: str,
    telemetry: IOSTelemetry,
) -> dict[str, Any]:
    """Record heartbeat telemetry from an enrolled iOS companion agent."""
    return _service.ios_companion_heartbeat(telemetry)


@router.get("/{device_id}/ios/inspect", response_model=IOSActionResponse)
async def ios_inspect_ui(
    device_id: str,
    bundle_id: str | None = None,
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Inspect active iOS UI hierarchy. (Under Zero Simulation, reports honest sandbox limits)."""
    return _service.ios_inspect_ui(device_id=device_id, bundle_id=bundle_id)


@router.post("/{device_id}/ios/click", response_model=IOSActionResponse)
async def ios_click_element(
    device_id: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Tap or click a UI element on iOS. (Under Zero Simulation, reports honest sandbox limits)."""
    return _service.ios_click_element(
        device_id=device_id,
        x=payload.get("x"),
        y=payload.get("y"),
        name=payload.get("name"),
    )


@router.post("/{device_id}/ios/type", response_model=IOSActionResponse)
async def ios_type_text(
    device_id: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
) -> IOSActionResponse:
    """Type text on iOS. (Under Zero Simulation, reports honest sandbox limits)."""
    return _service.ios_type_text(
        text=str(payload.get("text", "")),
        device_id=device_id,
        name=payload.get("name"),
    )


@router.post("/ios/companion/response")
async def ios_companion_response(
    resp: IOSCompanionResponse,
) -> dict[str, Any]:
    """Resolve a pending companion command future with client execution result."""
    return _service.ios_companion_response(resp)


@router.post("/{device_id}/ios/companion/command", response_model=IOSCompanionResponse)
async def ios_companion_send_command(
    device_id: str,
    envelope: IOSCompanionEnvelope,
    user: User = Depends(get_current_user),
) -> IOSCompanionResponse:
    """Dispatch a command envelope to an enrolled iOS companion device and await response."""
    try:
        return await _service.ios_companion_send_command(device_id=device_id, envelope=envelope)
    except ConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# -----------------------------------------------------------------------------
# Phase 13: Mobile App Discovery + Capability Resolution Endpoints
# -----------------------------------------------------------------------------

@router.post("/{device_id}/mobile/discover", response_model=MobileAppDiscoveryResponse)
async def discover_mobile_apps(
    device_id: str,
    req: MobileAppDiscoveryRequest,
    user: User = Depends(get_current_user),
) -> MobileAppDiscoveryResponse:
    """Trigger comprehensive app discovery on an enrolled Android or iOS mobile device."""
    return _service.discover_mobile_apps(
        device_id=device_id,
        platform=req.platform,
        force_refresh=req.force_refresh,
        include_system_apps=req.include_system_apps,
        companion_catalog=req.companion_catalog,
    )


@router.get("/{device_id}/mobile/apps", response_model=list[MobileAppModel])
async def list_mobile_apps(
    device_id: str,
    platform: str | None = None,
    include_system: bool = True,
    user: User = Depends(get_current_user),
) -> list[MobileAppModel]:
    """List discovered and registered mobile applications for a device."""
    return _service.list_mobile_apps(
        device_id=device_id,
        platform=platform,
        include_system=include_system,
    )


@router.get("/{device_id}/mobile/apps/{package_or_bundle:path}/capabilities")
async def get_mobile_app_capabilities(
    device_id: str,
    package_or_bundle: str,
    platform: str | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve fine-grained automation capabilities for a specific mobile application."""
    app = _service.get_mobile_app(package_or_bundle=package_or_bundle, platform=platform, device_id=device_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mobile application '{package_or_bundle}' not found.",
        )
    return {
        "app_id": app.app_id,
        "package_or_bundle_id": app.package_or_bundle_id,
        "name": app.name,
        "platform": app.platform,
        "total_capabilities": len(app.automation_capabilities),
        "capabilities": [c.model_dump() for c in app.automation_capabilities],
    }


@router.get("/{device_id}/mobile/apps/{package_or_bundle:path}", response_model=MobileAppModel)
async def get_mobile_app(
    device_id: str,
    package_or_bundle: str,
    platform: str | None = None,
    user: User = Depends(get_current_user),
) -> MobileAppModel:
    """Retrieve complete metadata for a specific mobile application."""
    app = _service.get_mobile_app(package_or_bundle=package_or_bundle, platform=platform, device_id=device_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mobile application '{package_or_bundle}' not found.",
        )
    return app


@router.post("/{device_id}/mobile/resolve", response_model=MobileCapabilityResolutionResponse)
async def resolve_mobile_capability(
    device_id: str,
    req: MobileCapabilityResolutionRequest,
    user: User = Depends(get_current_user),
) -> MobileCapabilityResolutionResponse:
    """Resolve the optimal mobile integration pathway under the Universal Integration Priority."""
    if not req.device_id:
        req.device_id = device_id
    return _service.resolve_mobile_capability(req)


# =============================================================================
# Phase 14: Automatic New-App Workflow REST API Endpoints
# =============================================================================

@router.post("/{device_id}/new-app/workflow", response_model=NewAppWorkflowResponse)
async def execute_new_app_workflow(
    device_id: str,
    req: NewAppWorkflowRequest,
    user: User = Depends(get_current_user),
) -> NewAppWorkflowResponse:
    """Execute end-to-end automatic new-app workflow: detect, introspect, rank, register, and verify."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return _service.execute_new_app_workflow(req)


@router.post("/{device_id}/new-app/detect", response_model=NewAppDetectionResult)
async def detect_new_app(
    device_id: str,
    req: NewAppDetectionRequest,
    user: User = Depends(get_current_user),
) -> NewAppDetectionResult:
    """Detect whether an application, binary, or process is new or already known to ROXY-AI."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return _service.detect_new_app(req)


@router.post("/{device_id}/new-app/introspect", response_model=NewAppIntrospectionResult)
async def introspect_new_app(
    device_id: str,
    req: NewAppIntrospectionRequest,
    user: User = Depends(get_current_user),
) -> NewAppIntrospectionResult:
    """Deeply introspect multi-modal capabilities of an application."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return _service.introspect_new_app(req)


@router.post("/{device_id}/new-app/rank", response_model=NewAppRankingResult)
async def rank_app_integrations(
    device_id: str,
    req: NewAppRankingRequest,
    user: User = Depends(get_current_user),
) -> NewAppRankingResult:
    """Rank candidate integration pathways for an application under the Universal Integration Priority."""
    return _service.rank_app_integrations(req)


@router.post("/{device_id}/new-app/register", response_model=NewAppRegistrationResult)
async def register_new_app(
    device_id: str,
    req: NewAppRegistrationRequest,
    user: User = Depends(get_current_user),
) -> NewAppRegistrationResult:
    """Finalize dynamic registration of an application and synthesize live AgentTools."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return _service.register_new_app(req)


@router.get("/{device_id}/new-app/registered", response_model=list[NewAppWorkflowResponse])
async def list_registered_new_apps(
    device_id: str,
    user: User = Depends(get_current_user),
) -> list[NewAppWorkflowResponse]:
    """List all dynamically registered applications and workflow execution records."""
    return _service.list_registered_new_apps()


@router.get("/{device_id}/new-app/registered/{app_name:path}", response_model=NewAppWorkflowResponse)
async def get_registered_new_app(
    device_id: str,
    app_name: str,
    user: User = Depends(get_current_user),
) -> NewAppWorkflowResponse:
    """Retrieve dynamic registration details and synthesized tools for an application."""
    record = _service.get_registered_new_app(app_name)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dynamic new-app workflow record for '{app_name}' not found.",
        )
    return record


# =============================================================================
# Phase 15: Connector + MCP Discovery Endpoints
# =============================================================================


@router.post("/{device_id}/discovery/mcp/scan", response_model=MCPDiscoveryResult)
async def scan_mcp_servers(
    device_id: str,
    req: MCPDiscoveryRequest,
    user: User = Depends(get_current_user),
) -> MCPDiscoveryResult:
    """Scan system configs, ports, processes, and catalogs for active or discoverable MCP servers."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return await _service.discover_mcp_servers(req)


@router.post("/{device_id}/discovery/mcp/bind", response_model=MCPToolBindingResult)
async def bind_mcp_server(
    device_id: str,
    req: MCPToolBindingRequest,
    user: User = Depends(get_current_user),
) -> MCPToolBindingResult:
    """Connect to a discovered MCP server, discover its tools via JSON-RPC, and register into ToolRegistry."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return await _service.bind_mcp_server(req)


@router.post("/{device_id}/discovery/connectors/scan", response_model=ConnectorDiscoveryResult)
async def scan_connectors(
    device_id: str,
    req: ConnectorDiscoveryRequest,
    user: User = Depends(get_current_user),
) -> ConnectorDiscoveryResult:
    """Scan active cloud connector instances, OpenAPI endpoints, credentials, and catalog."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return await _service.discover_connectors(req, user_id=user.id)


@router.post("/{device_id}/discovery/connectors/bind", response_model=ConnectorToolBindingResult)
async def bind_connector(
    device_id: str,
    req: ConnectorToolBindingRequest,
    user: User = Depends(get_current_user),
) -> ConnectorToolBindingResult:
    """Instantiate a Cloud Connector or OpenAPI endpoint and dynamically bind its actions into ToolRegistry."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return await _service.bind_connector(req)


@router.post("/{device_id}/discovery/unified", response_model=UnifiedDiscoveryResult)
async def unified_discovery(
    device_id: str,
    req: UnifiedDiscoveryRequest,
    user: User = Depends(get_current_user),
) -> UnifiedDiscoveryResult:
    """Execute unified MCP + Connector discovery across all vectors, rank candidates, and auto-bind live tools."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return await _service.unified_discover_and_bind(req, user_id=user.id)


@router.get("/{device_id}/discovery/bound-tools", response_model=DiscoveryBoundToolsResponse)
async def list_bound_discovery_tools(
    device_id: str,
    user: User = Depends(get_current_user),
) -> DiscoveryBoundToolsResponse:
    """List all active dynamically bound discovery tools and their server/connector bindings."""
    return _service.list_bound_discovery_tools()


@router.delete("/{device_id}/discovery/bound-tools/{binding_id}")
async def unbind_discovery_tools(
    device_id: str,
    binding_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Unbind and unregister dynamically registered discovery tools by binding ID."""
    success = _service.unbind_discovery_tools(binding_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dynamic discovery binding '{binding_id}' not found.",
        )
    return {"status": "success", "unbound": True, "binding_id": binding_id}


# =============================================================================
# Phase 16: App Embedding & In-Roxy Workspace Endpoints
# =============================================================================


@router.post("/{device_id}/embedding/evaluate", response_model=EmbedEvaluationResult)
async def evaluate_embed_security(
    device_id: str,
    req: EmbedEvaluationRequest,
    user: User = Depends(get_current_user),
) -> EmbedEvaluationResult:
    """Evaluate whether a web application or URL can be safely embedded in In-Roxy Workspace."""
    return await _service.evaluate_embed_security(
        url=req.url,
        app_name=req.app_name,
        allow_proxy=req.allow_proxy,
    )


@router.post("/{device_id}/embedding/sessions", response_model=WorkspaceSurfaceSession)
async def create_workspace_session(
    device_id: str,
    req: CreateSurfaceSessionRequest,
    user: User = Depends(get_current_user),
) -> WorkspaceSurfaceSession:
    """Create an active in-workspace surface embedding or desktop projection session."""
    if not req.device_id or req.device_id == "default":
        req.device_id = device_id
    return await _service.create_workspace_surface_session(req)


@router.get("/{device_id}/embedding/sessions", response_model=WorkspaceSessionListResponse)
async def list_workspace_sessions(
    device_id: str,
    user: User = Depends(get_current_user),
) -> WorkspaceSessionListResponse:
    """List all active workspace surface embedding and projection sessions."""
    sessions = await _service.list_workspace_surface_sessions(device_id=device_id)
    return WorkspaceSessionListResponse(total_sessions=len(sessions), sessions=sessions)


@router.get("/{device_id}/embedding/sessions/{session_id}", response_model=WorkspaceSurfaceSession)
async def get_workspace_session(
    device_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
) -> WorkspaceSurfaceSession:
    """Retrieve details of an active workspace surface session."""
    session = await _service.get_workspace_surface_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace session '{session_id}' not found.",
        )
    return session


@router.delete("/{device_id}/embedding/sessions/{session_id}")
async def terminate_workspace_session(
    device_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Terminate and clean up an active workspace surface session."""
    success = await _service.terminate_workspace_surface_session(session_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace session '{session_id}' not found.",
        )
    return {"status": "success", "session_id": session_id, "terminated": True}


@router.post("/{device_id}/embedding/sessions/{session_id}/heartbeat", response_model=WorkspaceSurfaceSession)
async def heartbeat_workspace_session(
    device_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
) -> WorkspaceSurfaceSession:
    """Refresh heartbeat and extend TTL on an active workspace surface session."""
    try:
        return await _service.heartbeat_workspace_surface_session(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace session '{session_id}' not found.",
        ) from exc


@router.post("/{device_id}/embedding/sessions/{session_id}/resize", response_model=WorkspaceSurfaceSession)
async def resize_workspace_session(
    device_id: str,
    session_id: str,
    width: int = Query(default=1280, ge=320, le=7680),
    height: int = Query(default=800, ge=200, le=4320),
    user: User = Depends(get_current_user),
) -> WorkspaceSurfaceSession:
    """Resize viewport dimensions for responsive desktop projection or iframe rendering."""
    try:
        return await _service.resize_workspace_surface_session(session_id, width, height)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace session '{session_id}' not found.",
        ) from exc


@router.get("/{device_id}/embedding/sessions/{session_id}/frame", response_model=SurfaceFrameSnapshot)
async def capture_workspace_frame(
    device_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
) -> SurfaceFrameSnapshot:
    """Capture live frame snapshot from a desktop projection session."""
    try:
        return await _service.capture_workspace_surface_frame(session_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace session '{session_id}' not found.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/{device_id}/embedding/sessions/{session_id}/stream")
async def stream_workspace_frames(
    device_id: str,
    session_id: str,
    fps: int = Query(default=15, ge=1, le=60),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Live MJPEG video stream of the projected application window."""
    session = await _service.get_workspace_surface_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace session '{session_id}' not found.",
        )

    delay = 1.0 / max(fps, 1)

    async def _mjpeg_generator() -> AsyncIterator[bytes]:
        try:
            while True:
                sess = await _service.get_workspace_surface_session(session_id)
                if not sess or sess.status != WorkspaceSessionStatus.ACTIVE:
                    break
                frame = await _service.capture_workspace_surface_frame(session_id)
                data = base64.b64decode(frame.data_base64)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n"
                )
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/{device_id}/embedding/sessions/{session_id}/input", response_model=RelayInputResult)
async def relay_workspace_input(
    device_id: str,
    session_id: str,
    req: RelayInputRequest,
    user: User = Depends(get_current_user),
) -> RelayInputResult:
    """Relay user canvas interactions into the target projected application."""
    try:
        return await _service.relay_workspace_surface_input(session_id, req)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace session '{session_id}' not found.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/{device_id}/embedding/proxy")
async def proxy_workspace_web_app(
    device_id: str,
    url: str = Query(..., description="Target web application URL to proxy"),
    user: User = Depends(get_current_user),
) -> Response:
    """Safe sandboxed reverse proxy endpoint for framed web apps requiring header rewriting."""
    status_code, headers, body = await _service.proxy_workspace_web_app(url)
    return Response(content=body, status_code=status_code, headers=headers)


# =============================================================================
# Phase 17: Verification Engine 2.0 Endpoints
# =============================================================================


@router.post("/{device_id}/verification/window", response_model=SingleCheckResult)
async def verify_window_state(
    device_id: str,
    criterion: WindowStateVerificationCriteria,
    user: User = Depends(get_current_user),
) -> SingleCheckResult:
    """Verify native desktop window state postconditions."""
    return await _service.verify_window_state(criterion)


@router.post("/{device_id}/verification/ocr", response_model=SingleCheckResult)
async def verify_ocr_text(
    device_id: str,
    criterion: OCRVisualVerificationCriteria,
    user: User = Depends(get_current_user),
) -> SingleCheckResult:
    """Verify visible rendered text in application window or screen."""
    return await _service.verify_ocr_text(criterion)


@router.post("/{device_id}/verification/dom", response_model=SingleCheckResult)
async def verify_dom_state(
    device_id: str,
    criterion: DOMStateVerificationCriteria,
    user: User = Depends(get_current_user),
) -> SingleCheckResult:
    """Verify browser/web DOM state (selector, text, attribute, URL)."""
    return await _service.verify_dom_state(criterion)


@router.post("/{device_id}/verification/api", response_model=SingleCheckResult)
async def verify_api_response(
    device_id: str,
    criterion: APIResponseVerificationCriteria,
    user: User = Depends(get_current_user),
) -> SingleCheckResult:
    """Verify HTTP/REST API endpoint response, status code, and JSONPath."""
    return await _service.verify_api_response(criterion)


@router.post("/{device_id}/verification/process", response_model=SingleCheckResult)
async def verify_process_state(
    device_id: str,
    criterion: ProcessStateVerificationCriteria,
    user: User = Depends(get_current_user),
) -> SingleCheckResult:
    """Verify operating system process status and health."""
    return await _service.verify_process_state(criterion)


@router.post("/{device_id}/verification/composite", response_model=CompositeVerificationResult)
async def execute_composite_verification(
    device_id: str,
    request: CompositeVerificationRequest,
    user: User = Depends(get_current_user),
) -> CompositeVerificationResult:
    """Execute cross-system, multi-modal composite postcondition verification with polling."""
    request.device_id = device_id
    return await _service.execute_composite_verification(request)


@router.get("/{device_id}/verification/history", response_model=VerificationHistoryResponse)
async def get_verification_history(
    device_id: str,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
) -> VerificationHistoryResponse:
    """Retrieve recent verification history records for device."""
    records = await _service.get_verification_history(limit=limit)
    return VerificationHistoryResponse(total_verifications=len(records), verifications=records)


# =============================================================================
# Phase 18: Recovery & Self-Correction Endpoints
# =============================================================================


@router.post("/{device_id}/recovery/execute", response_model=ExecuteRecoveryResult)
async def execute_recovery(
    device_id: str,
    request: ExecuteRecoveryRequest,
    user: User = Depends(get_current_user),
) -> ExecuteRecoveryResult:
    """Execute action with multi-tier fallback (API -> Browser -> Desktop) and postcondition verification."""
    request.device_id = device_id
    return await _service.execute_recovery(request)


@router.post("/{device_id}/recovery/classify", response_model=ErrorClassificationResponse)
async def classify_recovery_error(
    device_id: str,
    request: ErrorClassificationRequest,
    user: User = Depends(get_current_user),
) -> ErrorClassificationResponse:
    """Classify operational error, detect root cause and transience, and recommend recovery route."""
    return await _service.classify_recovery_error(request)


@router.post("/{device_id}/recovery/self-correct", response_model=SelfCorrectionResponse)
async def suggest_self_correction(
    device_id: str,
    request: SelfCorrectionRequest,
    user: User = Depends(get_current_user),
) -> SelfCorrectionResponse:
    """Formulate concrete parameter and strategy adjustments given empirical check failure."""
    return await _service.suggest_self_correction(request)


@router.get("/{device_id}/recovery/history", response_model=RecoveryHistoryResponse)
async def get_recovery_history(
    device_id: str,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
) -> RecoveryHistoryResponse:
    """Retrieve recent multi-tier recovery execution history records and cryptographic proof hashes."""
    records = await _service.get_recovery_history(limit=limit)
    return RecoveryHistoryResponse(total_records=len(records), records=records)










