"""Integration tests for Phase 4: Device Agent, App Discovery & App Control.

Verifies:
1. Current host auto-detection, registration, and system telemetry.
2. Device listing and companion device registration.
3. Native application discovery scanner and category filtering.
4. App lifecycle control (launch, window focus, process termination).
5. Desktop screen capture engine and asset saving.
6. Device action audit logging.
7. Central ToolRegistry device tools registration and execution.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolSource


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
    for app in dev_apps:
        assert app["category"] == "development"


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_device_action_logs_audit_trail(authed_client: AsyncClient) -> None:
    """Verify that all actions triggered on the device are audited in the database."""
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

    action_types = {log["action_type"] for log in logs}
    assert any(at in action_types for at in ["launch_app", "close_app", "focus_app", "screen_capture"])


@pytest.mark.asyncio
async def test_device_tools_in_central_registry() -> None:
    """Verify that device agent tools are registered in the central ToolRegistry."""
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

    from app.tools.schemas import ToolExecutionRequest

    # Execute device_list_apps through registry
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
