"""Comprehensive automated test suite for Phase 10: Multi-Device Fleet Orchestration & Autonomous Device Handover.

Tests:
1. Multi-factor candidate scoring weights (liveness, app catalog, capabilities, locality, platform, preference).
2. Routing to device with installed/running application.
3. Platform compatibility filtering (e.g. darwin vs windows vs linux).
4. Stale heartbeat detection (>120s) penalizing inactive devices.
5. Fallback chain generation in prioritized order.
6. Current local host locality bias.
7. Fleet execution on local device via UniversalAppController.
8. Graceful handling when no fleet device supports the request.
9. Autonomous failover: Primary device failure triggers handover to fallback device.
10. Explicit cross-device task handover lifecycle with state payload transfer.
11. Strict multi-tenant anti-IDOR isolation across fleet operations.
12. Fleet summary telemetry aggregation and app distribution.
13. Fleet broadcast query across active devices (find_app, system_stats).
14. Standalone daemon command dispatch for fleet_task_execute and fleet_handover_receive.
15. ToolRegistry tool integration (device_fleet_route, device_fleet_execute, device_fleet_handover, device_fleet_summary).
16. FastAPI REST API endpoints (/api/v1/devices/fleet/route, /execute, /handover, /summary, /broadcast).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import sys
from typing import Any
import uuid

import httpx
import pytest

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.daemon import RoxyDeviceAgent
from app.device.fleet_orchestrator import FleetOrchestrator
from app.device.schemas import (
    AppControlExecutionResult,
    FleetBroadcastQueryRequest,
    FleetExecutionRequest,
    FleetHandoverRequest,
    FleetRoutingRequest,
)
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest


@pytest.fixture(autouse=True)
def clean_fleet_and_device_state() -> None:
    """Reset all in-memory device, app, command, and fleet state between tests."""
    DeviceService.get_instance().clear_in_memory_state()
    FleetOrchestrator.clear_state()


# -----------------------------------------------------------------------------
# 1. Multi-Factor Candidate Scoring
# -----------------------------------------------------------------------------

def test_fleet_candidate_scoring_weights() -> None:
    """Verify multi-factor evaluation weights for online state, app presence, capabilities, and platform."""
    orchestrator = FleetOrchestrator.get_instance()
    now = datetime.now(UTC)

    device = {
        "id": "dev_win_1",
        "device_name": "Windows Workstation",
        "os_platform": "windows",
        "status": "online",
        "is_current_host": True,
        "capabilities": ["app_discovery", "process_control", "system_commands", "desktop_automation"],
        "last_heartbeat_at": now.isoformat(),
        "telemetry": {"active_window": "Spotify Free"},
    }

    apps = [
        {
            "id": "app_1",
            "app_name": "Spotify",
            "is_running": True,
            "category": "media",
        }
    ]

    req = FleetRoutingRequest(
        user_id="user_test_1",
        application="Spotify",
        capability="play_music",
    )

    score = orchestrator._evaluate_candidate(device, apps, req, now)

    assert score.score > 0.8
    assert score.is_online is True
    assert score.is_current_host is True
    assert score.app_available is True
    assert score.score_breakdown["app_availability"] == 0.35  # Running app bonus
    assert score.score_breakdown["liveness"] == 0.25
    assert score.score_breakdown["locality"] == 0.15


# -----------------------------------------------------------------------------
# 2. Routing to Device with Target Application
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_resolver_routes_to_device_with_installed_app() -> None:
    """Verify routing selects the device that actually has the target application installed."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_app_route"

    # Enroll Device A (Windows Desktop with Spotify)
    dev_a = await service.register_device(user_id=user_id, data={
        "device_name": "Desktop PC",
        "os_platform": "windows",
        "device_type": "desktop",
    })
    # Enroll Device B (MacBook Laptop with Slack)
    dev_b = await service.register_device(user_id=user_id, data={
        "device_name": "MacBook Pro",
        "os_platform": "darwin",
        "device_type": "laptop",
    })

    dev_a_id = dev_a["id"]
    dev_b_id = dev_b["id"]

    # Register apps in in-memory catalogs
    service._mem_apps[dev_a_id] = [
        {"app_name": "Spotify", "executable_path": "C:\\Spotify\\spotify.exe", "is_running": False}
    ]
    service._mem_apps[dev_b_id] = [
        {"app_name": "Slack", "executable_path": "/Applications/Slack.app", "is_running": True}
    ]

    # Query for Spotify -> Should pick Device A
    decision_spotify = await orchestrator.resolve_device(FleetRoutingRequest(
        user_id=user_id,
        application="Spotify",
        capability="play_music",
    ))
    assert decision_spotify.target_device_id == dev_a_id
    assert "Spotify" in decision_spotify.selection_reason

    # Query for Slack -> Should pick Device B
    decision_slack = await orchestrator.resolve_device(FleetRoutingRequest(
        user_id=user_id,
        application="Slack",
        capability="send_message",
    ))
    assert decision_slack.target_device_id == dev_b_id
    assert "Slack" in decision_slack.selection_reason


# -----------------------------------------------------------------------------
# 3. Platform Compatibility Filtering
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_resolver_platform_compatibility_filter() -> None:
    """Verify platform constraints disqualify incompatible operating systems."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_platform_filter"

    # Register a Windows machine
    dev_win = await service.register_device(user_id=user_id, data={
        "device_name": "WinBox",
        "os_platform": "windows",
    })
    # Register a Mac machine
    dev_mac = await service.register_device(user_id=user_id, data={
        "device_name": "MacMini",
        "os_platform": "darwin",
    })

    # Require darwin platform
    decision = await orchestrator.resolve_device(FleetRoutingRequest(
        user_id=user_id,
        application="Xcode",
        capability="build_project",
        required_os_platform="darwin",
    ))

    assert decision.target_device_id == dev_mac["id"]
    # Check that windows machine was disqualified
    win_cand = next(c for c in decision.candidates if c.device_id == dev_win["id"])
    assert win_cand.score == 0.0
    assert any("Incompatible OS platform" in r for r in win_cand.reasons)


# -----------------------------------------------------------------------------
# 4. Stale Heartbeat Detection
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_resolver_stale_heartbeat_detection() -> None:
    """Verify devices with expired heartbeats (>120s) are marked offline and ranked below fresh devices."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_stale_hb"

    # Device 1: Stale heartbeat (200s old)
    dev_stale = await service.register_device(user_id=user_id, data={
        "device_name": "Stale Server",
        "os_platform": "linux",
    })
    stale_id = dev_stale["id"]
    past_time = (datetime.now(UTC) - timedelta(seconds=200)).isoformat()
    service._mem_devices[stale_id]["last_heartbeat_at"] = past_time

    # Device 2: Fresh heartbeat (5s old)
    dev_fresh = await service.register_device(user_id=user_id, data={
        "device_name": "Fresh Server",
        "os_platform": "linux",
    })
    fresh_id = dev_fresh["id"]
    fresh_time = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    service._mem_devices[fresh_id]["last_heartbeat_at"] = fresh_time

    decision = await orchestrator.resolve_device(FleetRoutingRequest(
        user_id=user_id,
        application="python",
        capability="execute_script",
    ))

    assert decision.target_device_id == fresh_id
    stale_cand = next(c for c in decision.candidates if c.device_id == stale_id)
    assert stale_cand.is_online is False
    assert any("Heartbeat expired" in r for r in stale_cand.reasons)


# -----------------------------------------------------------------------------
# 5. Fallback Chain Generation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_resolver_fallback_chain() -> None:
    """Verify fallback chain lists backup devices in prioritized order."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_fallback_chain"

    dev1 = await service.register_device(user_id=user_id, data={"device_name": "Primary Dev", "os_platform": "windows"})
    dev2 = await service.register_device(user_id=user_id, data={"device_name": "Secondary Dev", "os_platform": "linux"})
    dev3 = await service.register_device(user_id=user_id, data={"device_name": "Tertiary Dev", "os_platform": "darwin"})

    # Primary has app installed
    service._mem_apps[dev1["id"]] = [{"app_name": "Docker", "is_running": True}]
    service._mem_apps[dev2["id"]] = [{"app_name": "Docker", "is_running": False}]

    decision = await orchestrator.resolve_device(FleetRoutingRequest(
        user_id=user_id,
        application="Docker",
        capability="start_container",
    ))

    assert decision.target_device_id == dev1["id"]
    assert dev2["id"] in decision.fallback_device_ids


# -----------------------------------------------------------------------------
# 6. Current Host Locality Bias
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_resolver_current_host_bias() -> None:
    """Verify local workstation is prioritized when other factors are comparable."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_local_bias"

    local_dev = await service.register_device(user_id=user_id, data={
        "device_name": "Current Host Laptop",
        "os_platform": sys.platform,
        "is_current_host": True,
    })
    service._mem_devices[local_dev["id"]]["is_current_host"] = True

    remote_dev = await service.register_device(user_id=user_id, data={
        "device_name": "Remote Office Rig",
        "os_platform": sys.platform,
        "is_current_host": False,
    })

    decision = await orchestrator.resolve_device(FleetRoutingRequest(
        user_id=user_id,
        application="Calculator",
        capability="launch",
    ))

    assert decision.target_device_id == local_dev["id"]
    top_cand = decision.candidates[0]
    assert top_cand.is_current_host is True
    assert top_cand.score_breakdown["locality"] == 0.15


# -----------------------------------------------------------------------------
# 7. Fleet Local Execution
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_execute_local_success() -> None:
    """Verify executing via fleet when local device is chosen invokes UniversalAppController."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_fleet_local_exec"

    local_dev = await service.get_or_create_local_device(user_id)

    res = await orchestrator.execute_fleet_app_control(FleetExecutionRequest(
        application="python",
        capability="execute_script",
        parameters={"script": "result = 12 * 12\nprint(result)"},
        user_id=user_id,
        confirmed=True,
    ))

    assert res.success is True
    assert res.executed_device_id in (local_dev["id"], "local")
    assert res.handover_occurred is False
    assert res.app_control_result.stage in ("executed", "verified")


# -----------------------------------------------------------------------------
# 8. Graceful Handling for Unsupported Request
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_execute_unsupported_app_fails_gracefully() -> None:
    """Verify fleet execution returns structured diagnostics when no device supports the app."""
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_unsupported"

    res = await orchestrator.execute_fleet_app_control(FleetExecutionRequest(
        application="totally_nonexistent_custom_quantum_cad_99",
        capability="simulate_fusion",
        user_id=user_id,
    ))

    assert res.success is False
    assert res.app_control_result.stage == "unsupported"
    err_str = res.app_control_result.error or ""
    assert "No integration route found" in err_str or "No compatible or online device" in err_str


# -----------------------------------------------------------------------------
# 9. Autonomous Failover & Cross-Device Handover
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_autonomous_failover() -> None:
    """Verify failure on primary device automatically triggers failover to fallback device."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_auto_failover"

    # Device 1: Remote device that will fail execution
    dev1 = await service.register_device(user_id=user_id, data={
        "device_name": "Unstable Remote Node",
        "os_platform": "linux",
        "status": "online",
        "is_current_host": False,
    })
    dev1_id = dev1["id"]

    # Device 2: Local host fallback device that will succeed
    dev2 = await service.register_device(user_id=user_id, data={
        "device_name": "Reliable Local Node",
        "os_platform": sys.platform,
        "status": "online",
        "is_current_host": True,
    })
    dev2_id = dev2["id"]
    service._mem_devices[dev2_id]["is_current_host"] = True

    # Artificially set remote dispatch to fail fast for dev1
    orig_dispatch = orchestrator._dispatch_to_device

    async def _failing_dispatch(device_id: str, u_id: str, req: FleetExecutionRequest) -> AppControlExecutionResult:
        if device_id == dev1_id:
            from app.device.schemas import IntegrationResolutionResult
            return AppControlExecutionResult(
                execution_id="exec_err",
                plan_id="plan_err",
                application=req.application,
                capability=req.capability,
                stage="failed",
                success=False,
                verified=False,
                resolution=IntegrationResolutionResult(
                    success=False,
                    application=req.application,
                    requested_capability=req.capability,
                    chosen_integration="cli_process",
                    confidence=0.8,
                    required_permission="app:python:execute",
                    risk="low",
                    requires_confirmation=False,
                    execution_method="cli_exec",
                    verification_method="process_exit_code_and_output",
                ),
                error="Node out of memory or connection dropped.",
            )
        # Fallback to normal local dispatch
        return await orig_dispatch(device_id, u_id, req)

    orchestrator._dispatch_to_device = _failing_dispatch  # type: ignore[assignment]

    try:
        req = FleetExecutionRequest(
            application="python",
            capability="execute_script",
            parameters={"script": "print('failover successful')"},
            preferred_device_id=dev1_id,
            user_id=user_id,
            allow_failover=True,
            confirmed=True,
        )

        result = await orchestrator.execute_fleet_app_control(req)

        assert result.success is True
        assert result.handover_occurred is True
        assert result.executed_device_id == dev2_id
        assert len(result.handover_details) == 1
        assert result.handover_details[0]["source_device_id"] == dev1_id
        assert result.handover_details[0]["target_device_id"] == dev2_id
    finally:
        orchestrator._dispatch_to_device = orig_dispatch


# -----------------------------------------------------------------------------
# 10. Explicit Cross-Device Task Handover
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_explicit_handover_lifecycle() -> None:
    """Verify initiate_handover transfers state payload and resumes execution on target device."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_explicit_handover"

    dev_source = await service.register_device(user_id=user_id, data={
        "device_name": "Source Phone",
        "os_platform": "android",
    })
    dev_target = await service.register_device(user_id=user_id, data={
        "device_name": "Target Desktop",
        "os_platform": sys.platform,
        "is_current_host": True,
    })
    service._mem_devices[dev_target["id"]]["is_current_host"] = True

    handover_req = FleetHandoverRequest(
        user_id=user_id,
        source_device_id=dev_source["id"],
        target_device_id=dev_target["id"],
        application="python",
        capability="execute_script",
        parameters={"script": "value = 42\nprint(f'Handed over: {value}')"},
        state_payload={"resume_token": "tok_xyz", "turn_count": 3},
        reason="User switched from phone to workstation",
        auto_resume=True,
    )

    res = await orchestrator.initiate_handover(handover_req)

    assert res.status == "completed"
    assert res.target_device_id == dev_target["id"]
    assert res.source_device_id == dev_source["id"]
    assert res.state_payload["resume_token"] == "tok_xyz"
    assert res.execution_result is not None
    assert res.execution_result.success is True


# -----------------------------------------------------------------------------
# 11. Multi-Tenant IDOR Protection
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_handover_multi_tenant_idor_protection() -> None:
    """Verify attempting to handover between devices owned by different users raises PermissionError."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()

    user_a = "tenant_alice"
    user_b = "tenant_bob"

    dev_alice = await service.register_device(user_id=user_a, data={"device_name": "Alice Laptop"})
    dev_bob = await service.register_device(user_id=user_b, data={"device_name": "Bob Desktop"})

    # Alice tries to migrate task onto Bob's device
    with pytest.raises(PermissionError, match="does not own target device"):
        await orchestrator.initiate_handover(FleetHandoverRequest(
            user_id=user_a,
            source_device_id=dev_alice["id"],
            target_device_id=dev_bob["id"],
            application="python",
            capability="execute_script",
        ))


# -----------------------------------------------------------------------------
# 12. Fleet Summary Aggregation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_summary_aggregation() -> None:
    """Verify get_fleet_summary tallies online/offline counts and app distribution."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_fleet_summary"

    dev1 = await service.register_device(user_id=user_id, data={
        "device_name": "Office Rig",
        "status": "online",
        "is_current_host": True,
    })
    dev2 = await service.register_device(user_id=user_id, data={
        "device_name": "Home Laptop",
        "status": "offline",
        "is_current_host": False,
    })

    service._mem_apps[dev1["id"]] = [
        {"app_name": "Notion", "is_running": False},
        {"app_name": "VS Code", "is_running": True},
    ]
    service._mem_apps[dev2["id"]] = [
        {"app_name": "VS Code", "is_running": False},
    ]

    summary = await orchestrator.get_fleet_summary(user_id)

    assert summary.total_devices == 2
    assert summary.online_devices >= 1
    assert summary.offline_devices >= 1
    assert summary.discovered_apps_count == 3
    assert "VS Code" in summary.app_distribution
    assert len(summary.app_distribution["VS Code"]) == 2  # on both devices


# -----------------------------------------------------------------------------
# 13. Fleet Broadcast Query
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_broadcast_query() -> None:
    """Verify broadcast_query inspects active devices for app discovery or system stats."""
    service = DeviceService.get_instance()
    orchestrator = FleetOrchestrator.get_instance()
    user_id = "user_broadcast"

    dev = await service.register_device(user_id=user_id, data={
        "device_name": "Broadcast Target",
        "status": "online",
        "is_current_host": True,
    })
    service._mem_apps[dev["id"]] = [
        {"app_name": "Google Chrome", "is_running": True},
    ]

    b_res = await orchestrator.broadcast_query(FleetBroadcastQueryRequest(
        user_id=user_id,
        query_type="find_app",
        query_target="Chrome",
    ))

    assert b_res.total_responding_devices >= 1
    assert "Broadcast Target" in b_res.results_by_device
    assert b_res.results_by_device["Broadcast Target"]["matched_count"] == 1


# -----------------------------------------------------------------------------
# 14. Daemon Fleet Command Dispatch
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daemon_fleet_command_dispatch() -> None:
    """Verify standalone RoxyDeviceAgent handles fleet_task_execute and fleet_handover_receive."""
    daemon = RoxyDeviceAgent(
        backend_url="http://127.0.0.1:8000",
        device_id="test_daemon_fleet_box",
        device_token="roxy_dev_secret",
    )

    # 1. fleet_task_execute
    status_exec, result_exec, err_exec = await daemon.execute_command({
        "command_type": "fleet_task_execute",
        "payload": {
            "application": "python",
            "capability": "execute_script",
            "parameters": {"script": "print('daemon fleet ok')"},
            "confirmed": True,
            "skip_verification": True,
        },
    })
    assert status_exec == "completed"
    assert err_exec is None
    assert result_exec is not None
    assert result_exec.get("success") is True

    # 2. fleet_handover_receive
    status_recv, result_recv, err_recv = await daemon.execute_command({
        "command_type": "fleet_handover_receive",
        "payload": {
            "application": "python",
            "capability": "execute_script",
            "state_payload": {"parameters": {"script": "print('handover received')"}},
        },
    })
    assert status_recv == "completed"
    assert err_recv is None
    assert result_recv is not None
    assert result_recv.get("success") is True


# -----------------------------------------------------------------------------
# 15. Tool Registry Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_registry_fleet_tools() -> None:
    """Verify device_fleet_route and device_fleet_summary tools in ToolRegistry."""
    registry = ToolRegistry.get_instance()
    user_id = "user_tool_fleet"

    # Verify registration
    assert registry.get("device_fleet_route") is not None
    assert registry.get("device_fleet_execute") is not None
    assert registry.get("device_fleet_handover") is not None
    assert registry.get("device_fleet_summary") is not None

    # Execute device_fleet_route
    route_res = await registry.execute(ToolExecutionRequest(
        tool_id="device_fleet_route",
        arguments={"application": "python", "capability": "execute_script"},
        user_id=user_id,
    ))
    assert route_res.success is True
    assert "routing_id" in route_res.output
    assert "target_device_id" in route_res.output

    # Execute device_fleet_summary
    sum_res = await registry.execute(ToolExecutionRequest(
        tool_id="device_fleet_summary",
        arguments={},
        user_id=user_id,
    ))
    assert sum_res.success is True
    assert "total_devices" in sum_res.output


# -----------------------------------------------------------------------------
# 16. FastAPI Fleet REST Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fastapi_fleet_endpoints() -> None:
    """Verify FastAPI REST API endpoints for fleet routing, execution, and summary."""
    user = User(id="user_api_fleet", email="fleet_api@example.com")
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. POST /fleet/route
            route_resp = await client.post(
                "/api/v1/devices/fleet/route",
                json={"user_id": user.id, "application": "python", "capability": "execute_script"},
            )
            assert route_resp.status_code == 200
            data_route = route_resp.json()
            assert "target_device_id" in data_route
            assert "confidence" in data_route

            # 2. POST /fleet/execute
            exec_resp = await client.post(
                "/api/v1/devices/fleet/execute",
                json={
                    "application": "python",
                    "capability": "execute_script",
                    "parameters": {"script": "print('api fleet exec')"},
                    "confirmed": True,
                    "skip_verification": True,
                },
            )
            assert exec_resp.status_code == 200
            data_exec = exec_resp.json()
            assert data_exec["success"] is True
            assert "routing_decision" in data_exec

            # 3. GET /fleet/summary
            sum_resp = await client.get("/api/v1/devices/fleet/summary")
            assert sum_resp.status_code == 200
            data_sum = sum_resp.json()
            assert "total_devices" in data_sum

            # 4. POST /fleet/broadcast
            bcast_resp = await client.post(
                "/api/v1/devices/fleet/broadcast",
                json={"user_id": user.id, "query_type": "system_stats", "query_target": ""},
            )
            assert bcast_resp.status_code == 200
            data_bcast = bcast_resp.json()
            assert "results_by_device" in data_bcast
    finally:
        app.dependency_overrides.pop(get_current_user, None)
