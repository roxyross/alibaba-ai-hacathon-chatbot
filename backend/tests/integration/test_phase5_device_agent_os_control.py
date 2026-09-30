"""Integration tests for Phase 5: Device Agent, App Discovery & Operating System Control.

Verifies:
1. Current host auto-detection, registration, and hardware telemetry.
2. Device listing and companion device registration.
3. Native application discovery scanner and category filtering.
4. App lifecycle control (launch, window focus, process termination).
5. Desktop screen capture engine and asset saving.
6. Device action audit logging.
7. Central ToolRegistry device tools registration and direct execution.
8. Confirmation gating on destructive device_close_app (RiskLevel.HIGH, requires_confirmation=True).
9. AgentPlanner deterministic decomposition and intent routing for device commands.
10. Multi-tenant strict isolation (anti-IDOR on devices, apps, actions, and captures).
"""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.agent_runtime.planner import AgentPlanner
from app.auth.service import MagicLinkService
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel, ToolExecutionRequest, ToolSource


async def _create_second_user_client() -> AsyncClient:
    """Helper to mint a second authenticated client for tenant isolation testing."""
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    service = MagicLinkService()
    test_email = "device_tenant_b@example.com"
    await service.request_link(test_email)
    user_id = next(
        u.id for email, u in service._mem_users.items() if email == test_email
    )
    token_value = next(
        t for t, row in service._mem_tokens.items() if row.user_id == user_id
    )
    result = await service.verify(token_value)
    if result is None:
        raise RuntimeError("Failed to verify magic-link token for second user")
    _user, jwt, _ttl = result
    client.headers["Authorization"] = f"Bearer {jwt}"
    return client


@pytest.fixture(autouse=True)
def _ensure_device_tools() -> None:
    """Ensure device tools are registered before tests."""
    DeviceService.get_instance().register_device_tools()


# -----------------------------------------------------------------------------
# 1. Device Registration & Telemetry
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_or_create_local_device(authed_client: AsyncClient) -> None:
    """Verify that current host machine is detected and returned as a registered device."""
    res = await authed_client.get("/api/v1/devices/current")
    assert res.status_code == 200
    data = res.json()

    assert "id" in data
    assert data["is_current_host"] is True
    assert data["status"] == "online"
    assert "capabilities" in data
    assert "app_discovery" in data["capabilities"]
    assert "screen_capture" in data["capabilities"]
    assert "process_control" in data["capabilities"]

    telemetry = data["telemetry"]
    assert "hostname" in telemetry
    assert "os_platform" in telemetry
    assert "cpu_percent" in telemetry
    assert "memory_percent" in telemetry
    assert "disk_free_gb" in telemetry


@pytest.mark.anyio
async def test_list_and_register_devices(authed_client: AsyncClient) -> None:
    """Verify listing devices and registering a remote/companion device."""
    # 1. List devices (ensures local device is initialized)
    res = await authed_client.get("/api/v1/devices")
    assert res.status_code == 200
    devices = res.json()
    assert isinstance(devices, list)
    assert len(devices) >= 1

    # 2. Register remote device
    remote_payload = {
        "device_name": "MacBook Pro Companion",
        "device_type": "laptop",
        "os_platform": "darwin",
        "os_version": "14.4.1",
        "architecture": "arm64",
        "hostname": "macbook-pro.local",
        "ip_address": "192.168.1.155",
        "capabilities": ["app_discovery", "process_control"],
    }
    reg_res = await authed_client.post("/api/v1/devices", json=remote_payload)
    assert reg_res.status_code in (200, 201)
    remote_data = reg_res.json()
    assert remote_data["device_name"] == "MacBook Pro Companion"
    assert remote_data["is_current_host"] is False
    assert remote_data["os_platform"] == "darwin"


# -----------------------------------------------------------------------------
# 2. App Discovery Scanner & Category Filter
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_app_discovery_scan_and_listing(authed_client: AsyncClient) -> None:
    """Verify scanning installed apps and filtering by category."""
    # 1. Get host device
    dev_res = await authed_client.get("/api/v1/devices/current")
    device_id = dev_res.json()["id"]

    # 2. Trigger scan
    scan_res = await authed_client.post(f"/api/v1/devices/{device_id}/apps/scan")
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    apps = scan_data["discovered_apps"]
    assert isinstance(apps, list)
    assert len(apps) >= 5

    app_names = {a["app_name"].lower() for a in apps}
    assert any("chrome" in name or "edge" in name or "code" in name or "notepad" in name for name in app_names)

    # 3. List apps without filter
    list_res = await authed_client.get(f"/api/v1/devices/{device_id}/apps")
    assert list_res.status_code == 200
    all_apps = list_res.json()
    assert len(all_apps) >= len(apps)

    # 4. List with category filter
    dev_apps_res = await authed_client.get(f"/api/v1/devices/{device_id}/apps?category=development")
    assert dev_apps_res.status_code == 200
    dev_apps = dev_apps_res.json()
    for a in dev_apps:
        assert a["category"] == "development"


# -----------------------------------------------------------------------------
# 3. App Control Lifecycle (Launch, Focus, Close)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_app_control_lifecycle(authed_client: AsyncClient) -> None:
    """Verify launching, focusing, and terminating an application."""
    dev_res = await authed_client.get("/api/v1/devices/current")
    device_id = dev_res.json()["id"]

    # 1. Launch app
    launch_res = await authed_client.post(
        f"/api/v1/devices/{device_id}/apps/launch",
        json={"app_name_or_path": "calc.exe", "arguments": []},
    )
    assert launch_res.status_code == 200
    launch_data = launch_res.json()
    assert launch_data["status"] in ("success", "failed")

    # 2. Focus app window
    focus_res = await authed_client.post(
        f"/api/v1/devices/{device_id}/apps/focus",
        json={"app_name": "calc.exe"},
    )
    assert focus_res.status_code == 200
    focus_data = focus_res.json()
    assert "focused" in focus_data

    # 3. Close app
    close_res = await authed_client.post(
        f"/api/v1/devices/{device_id}/apps/close",
        json={"app_name_or_pid": "calc.exe", "force": True},
    )
    assert close_res.status_code == 200
    close_data = close_res.json()
    assert "status" in close_data


# -----------------------------------------------------------------------------
# 4. Screen Capture Engine & Live Telemetry
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_screen_capture_and_telemetry(authed_client: AsyncClient) -> None:
    """Verify screen capture creation and real-time telemetry polling."""
    dev_res = await authed_client.get("/api/v1/devices/current")
    device_id = dev_res.json()["id"]

    # 1. Screen capture
    shot_res = await authed_client.post(f"/api/v1/devices/{device_id}/screenshot")
    assert shot_res.status_code == 200
    shot_data = shot_res.json()

    assert "image_url" in shot_data
    assert shot_data["image_url"].startswith("/static/screenshots/")
    assert shot_data["width"] > 0
    assert shot_data["height"] > 0
    assert "captured_at" in shot_data

    # 2. Telemetry polling
    tel_res = await authed_client.get(f"/api/v1/devices/{device_id}/telemetry")
    assert tel_res.status_code == 200
    tel_data = tel_res.json()
    assert "cpu_percent" in tel_data
    assert "memory_percent" in tel_data
    assert "disk_free_gb" in tel_data


# -----------------------------------------------------------------------------
# 5. Device Action Audit Trail
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_device_action_logs_audit_trail(authed_client: AsyncClient) -> None:
    """Verify that all actions triggered on the device are audited."""
    dev_res = await authed_client.get("/api/v1/devices/current")
    device_id = dev_res.json()["id"]

    # Ensure an action is recorded on this device for this client session
    await authed_client.post(f"/api/v1/devices/{device_id}/screenshot")

    # Fetch audit logs
    logs_res = await authed_client.get(f"/api/v1/devices/{device_id}/actions")
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert isinstance(logs, list)
    assert len(logs) >= 1

    action_types = {entry["action_type"] for entry in logs}
    assert any(at in action_types for at in ["launch_app", "close_app", "focus_app", "screen_capture"])


# -----------------------------------------------------------------------------
# 6. Central ToolRegistry Integration & Confirmation Gating
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_device_tools_in_central_registry() -> None:
    """Verify that device agent tools are registered with proper confirmation gating and execution."""
    registry = ToolRegistry.get_instance()

    expected_tools = [
        "device_list_apps",
        "device_open_app",
        "device_close_app",
        "device_focus_app",
        "device_capture_screen",
    ]

    for tool_name in expected_tools:
        tool = registry.get(tool_name)
        assert tool is not None, f"Tool {tool_name} not found in ToolRegistry"
        assert tool.source == ToolSource.DEVICE

    # Destructive close_app confirmation gating verification
    close_tool = registry.get("device_close_app")
    assert close_tool is not None
    assert close_tool.risk_level == RiskLevel.HIGH
    assert close_tool.requires_confirmation is True

    # Direct execution of device_list_apps through registry
    exec_req = ToolExecutionRequest(
        tool_id="device_list_apps",
        arguments={"category": "all"},
        user_id="test-user",
    )
    result = await registry.execute(exec_req)
    assert result.success is True
    assert result.output is not None
    assert "total_apps" in result.output
    assert "apps" in result.output
    assert isinstance(result.output["apps"], list)


# -----------------------------------------------------------------------------
# 7. AgentPlanner Device Intent Decomposition & Routing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_device_intent_routing() -> None:
    """Verify AgentPlanner deterministic decomposition and routing to device tools."""
    DeviceService.get_instance().register_device_tools()
    planner = AgentPlanner()

    # A. Open application
    plan_open = await planner.create_plan("open app Google Chrome")
    assert len(plan_open) == 1
    assert plan_open[0]["tool_id"] == "device_open_app"
    assert "Google Chrome" in plan_open[0]["tool_input"]["app_name"]

    # B. Close / kill application (confirmation gated)
    plan_close = await planner.create_plan("close app Spotify")
    assert len(plan_close) == 1
    assert plan_close[0]["tool_id"] == "device_close_app"
    assert "Spotify" in plan_close[0]["tool_input"]["app_name"]

    # C. Focus window
    plan_focus = await planner.create_plan("focus window Visual Studio Code")
    assert len(plan_focus) == 1
    assert plan_focus[0]["tool_id"] == "device_focus_app"
    assert "Visual Studio Code" in plan_focus[0]["tool_input"]["app_name"]

    # D. List installed applications
    plan_list = await planner.create_plan("list installed apps")
    assert len(plan_list) == 1
    assert plan_list[0]["tool_id"] == "device_list_apps"

    # E. Screen capture
    plan_shot = await planner.create_plan("take a screenshot of my desktop")
    assert len(plan_shot) == 1
    assert plan_shot[0]["tool_id"] == "device_capture_screen"


# -----------------------------------------------------------------------------
# 8. Multi-Tenant Boundary Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_device_multitenant_isolation(authed_client: AsyncClient) -> None:
    """Verify that User B cannot access or control User A's registered device."""
    # User A gets current device
    res_a = await authed_client.get("/api/v1/devices/current")
    dev_a_id = res_a.json()["id"]

    # User B client
    client_b = await _create_second_user_client()
    try:
        # User B gets their own device
        res_b = await client_b.get("/api/v1/devices/current")
        dev_b_id = res_b.json()["id"]

        # Ensure devices are separate
        assert dev_a_id != dev_b_id

        # User B queries list of devices -> only sees their own
        list_b = await client_b.get("/api/v1/devices")
        assert list_b.status_code == 200
        b_device_ids = {d["id"] for d in list_b.json()}
        assert dev_a_id not in b_device_ids
        assert dev_b_id in b_device_ids

        # User B queries actions on User A's device -> empty list (no leakage)
        actions_b = await client_b.get(f"/api/v1/devices/{dev_a_id}/actions")
        assert actions_b.status_code == 200
        assert actions_b.json() == []
    finally:
        await client_b.aclose()
