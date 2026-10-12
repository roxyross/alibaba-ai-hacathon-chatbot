"""Integration tests for Roxy-AI Client Distribution & Device Fleet API.

Verifies:
1. App update manifests for Windows, macOS, Linux, Android, and iOS.
2. Device registration with custom hardware device IDs and daemon versions.
3. Device metadata updates (rename, capabilities).
4. Push notification token registration (APNs / FCM).
5. Device revocation and fleet deregistration.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_app_update_manifests_all_platforms(authed_client: AsyncClient) -> None:
    """Verify that update manifests return valid production metadata across all target platforms."""
    platforms = ["windows", "macos", "linux", "android", "ios"]
    for plat in platforms:
        res = await authed_client.get(f"/api/v1/devices/updates?platform={plat}")
        assert res.status_code == 200
        data = res.json()
        assert data["platform"] == plat
        assert data["latest_version"] == "2.0.0"
        assert "download_url" in data
        assert "sha256" in data
        assert "release_notes" in data
        assert isinstance(data["mandatory"], bool)


@pytest.mark.anyio
async def test_register_and_manage_client_device(authed_client: AsyncClient) -> None:
    """Verify registering a production client device, updating metadata, and revoking it."""
    device_id = "test-desktop-win-001"
    register_payload = {
        "device_id": device_id,
        "device_name": "Windows Workstation Client",
        "device_type": "desktop",
        "os_platform": "windows",
        "os_version": "11 Pro 23H2",
        "architecture": "x86_64",
        "hostname": "WORKSTATION-01",
        "daemon_version": "2.0.0",
        "capabilities": ["app_discovery", "process_control", "screen_capture", "push_notifications"],
    }

    # 1. Register device
    reg_res = await authed_client.post("/api/v1/devices/register", json=register_payload)
    assert reg_res.status_code in (200, 201)
    reg_data = reg_res.json()
    assert reg_data["id"] == device_id
    assert reg_data["device_name"] == "Windows Workstation Client"
    assert reg_data["daemon_version"] == "2.0.0"

    # 2. Update device name
    update_res = await authed_client.patch(
        f"/api/v1/devices/{device_id}",
        json={"device_name": "Primary Development PC"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["device_name"] == "Primary Development PC"

    # 3. Register APNs/FCM push token
    token_res = await authed_client.post(
        f"/api/v1/devices/{device_id}/push-token",
        json={"push_token": "fcm_token_sample_12345", "platform": "windows"},
    )
    assert token_res.status_code == 200
    assert token_res.json()["push_registered"] is True

    # 4. Revoke / deregister device
    revoke_res = await authed_client.delete(f"/api/v1/devices/{device_id}")
    assert revoke_res.status_code == 200
    assert revoke_res.json()["revoked"] is True
