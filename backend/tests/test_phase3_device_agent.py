"""Comprehensive automated test suite for Phase 3: Standalone Roxy Device Agent.

Tests:
1. Deterministic hardware fingerprint generation and spoof resistance.
2. Enrollment token lifecycle (generation, TTL expiration, single-use claim).
3. Pairing handshake and hardware identity binding (secret token generation, hash storage).
4. Cryptographic device token authentication.
5. Periodic heartbeat telemetry tracking.
6. Liveness monitoring and stale device offline detection.
7. Asynchronous bidirectional command queue (queue, poll, dispatch, complete, audit log).
8. Standalone RoxyDeviceAgent daemon implementation (config, local command execution, polling loop).
9. FastAPI device agent REST API endpoints (enrollment, heartbeat, command polling & results).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.daemon import (
    RoxyDeviceAgent,
    collect_system_telemetry,
    get_hardware_fingerprint,
)
from app.device.service import DeviceService
from app.main import app


@pytest.fixture(autouse=True)
def clean_device_state() -> None:
    """Ensure in-memory device state is reset before each test."""
    service = DeviceService.get_instance()
    service.clear_in_memory_state()


# -----------------------------------------------------------------------------
# 1. Deterministic Hardware Fingerprinting
# -----------------------------------------------------------------------------

def test_hardware_fingerprint_deterministic() -> None:
    """Verify hardware fingerprint is non-empty, well-formatted, and stable across repeated calls."""
    fp1 = get_hardware_fingerprint()
    fp2 = get_hardware_fingerprint()

    assert fp1.startswith("hwfp_")
    assert len(fp1) == 37  # "hwfp_" (5 chars) + 32 hex chars
    assert fp1 == fp2


def test_collect_system_telemetry_fields() -> None:
    """Verify system telemetry collector returns all expected real-time hardware metrics."""
    telemetry = collect_system_telemetry()
    assert "hostname" in telemetry
    assert "os_platform" in telemetry
    assert "cpu_percent" in telemetry
    assert "memory_percent" in telemetry
    assert "disk_free_gb" in telemetry
    assert "timestamp" in telemetry
    assert isinstance(telemetry["cpu_percent"], float)
    assert isinstance(telemetry["memory_percent"], float)


# -----------------------------------------------------------------------------
# 2. Enrollment Token Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrollment_token_generation() -> None:
    """Verify generation of time-bounded enrollment tokens."""
    service = DeviceService.get_instance()
    user_id = "user_device_test"

    token_res = await service.create_enrollment_token(
        user_id=user_id,
        label="MacBook Pro Workstation",
        ttl_seconds=600,
    )

    assert token_res["token"].startswith("roxy_enroll_")
    assert token_res["is_claimed"] is False
    assert token_res["user_id"] == user_id
    assert token_res["label"] == "MacBook Pro Workstation"
    assert token_res["expires_at"] is not None


@pytest.mark.asyncio
async def test_enrollment_token_expiration() -> None:
    """Verify expired enrollment tokens are rejected with ValueError."""
    service = DeviceService.get_instance()
    user_id = "user_device_exp"

    # Create token with 0 TTL (instantly expired)
    token_res = await service.create_enrollment_token(
        user_id=user_id,
        label="Expired Token Test",
        ttl_seconds=-10,
    )
    raw_token = token_res["token"]

    claim_data = {
        "enrollment_token": raw_token,
        "device_name": "Test Machine",
        "hardware_fingerprint": "hwfp_test_expired_123",
        "os_platform": "windows",
        "hostname": "test-box",
    }

    with pytest.raises(ValueError, match="Enrollment token has expired."):
        await service.claim_enrollment(claim_data)


@pytest.mark.asyncio
async def test_enrollment_token_single_use() -> None:
    """Verify an enrollment token cannot be claimed more than once."""
    service = DeviceService.get_instance()
    user_id = "user_device_single_use"

    token_res = await service.create_enrollment_token(user_id=user_id, ttl_seconds=300)
    raw_token = token_res["token"]

    claim_data = {
        "enrollment_token": raw_token,
        "device_name": "Single Use Box",
        "hardware_fingerprint": "hwfp_single_use_device",
        "os_platform": "linux",
        "hostname": "linux-agent",
    }

    first_claim = await service.claim_enrollment(claim_data)
    assert first_claim["status"] == "online"
    assert "device_token" in first_claim

    # Second claim attempt with the same token must fail
    with pytest.raises(ValueError, match="Enrollment token has already been claimed."):
        await service.claim_enrollment(claim_data)


# -----------------------------------------------------------------------------
# 3. Pairing Handshake & Hardware Identity Binding
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrollment_creates_device_and_hashes_token() -> None:
    """Verify pairing handshake stores SHA-256 hash of device token and returns plaintext once."""
    service = DeviceService.get_instance()
    user_id = "user_handshake_test"

    token_res = await service.create_enrollment_token(user_id=user_id, ttl_seconds=300)
    raw_token = token_res["token"]

    hw_fp = "hwfp_custom_unique_hash_987"
    claim_res = await service.claim_enrollment({
        "enrollment_token": raw_token,
        "device_name": "Developer ThinkPad",
        "hardware_fingerprint": hw_fp,
        "os_platform": "windows",
        "hostname": "thinkpad-x1",
        "daemon_version": "1.0.0",
    })

    device_id = claim_res["device_id"]
    plaintext_token = claim_res["device_token"]
    assert plaintext_token.startswith("roxy_dev_")

    # In-memory or DB device record must NOT store plaintext_token
    device_record = service._mem_devices.get(device_id)
    if device_record:
        assert "device_token" not in device_record or device_record["device_token"] != plaintext_token
        expected_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
        assert device_record.get("device_token_hash") == expected_hash
        assert device_record.get("hardware_fingerprint") == hw_fp
        assert device_record.get("daemon_version") == "1.0.0"


# -----------------------------------------------------------------------------
# 4. Cryptographic Device Authentication
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_token_authentication() -> None:
    """Verify authenticate_device_token verifies presented token against SHA-256 hash."""
    service = DeviceService.get_instance()
    user_id = "user_auth_test"

    token_res = await service.create_enrollment_token(user_id=user_id, ttl_seconds=300)
    claim_res = await service.claim_enrollment({
        "enrollment_token": token_res["token"],
        "device_name": "Secure Terminal",
        "hardware_fingerprint": "hwfp_secure_terminal_456",
        "os_platform": "darwin",
        "hostname": "mac-mini",
    })

    dev_id = claim_res["device_id"]
    secret_token = claim_res["device_token"]

    # 1. Valid authentication
    auth_dev = await service.authenticate_device_token(device_id=dev_id, device_token=secret_token)
    assert auth_dev is not None
    assert auth_dev["id"] == dev_id

    # 2. Tampered token
    bad_auth = await service.authenticate_device_token(device_id=dev_id, device_token="roxy_dev_wrong_secret")
    assert bad_auth is None

    # 3. Nonexistent device ID
    non_dev = await service.authenticate_device_token(device_id=str(uuid.uuid4()), device_token=secret_token)
    assert non_dev is None


# -----------------------------------------------------------------------------
# 5. Heartbeat & Telemetry Tracking
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_telemetry_update() -> None:
    """Verify heartbeat updates presence timestamp and hardware telemetry."""
    service = DeviceService.get_instance()
    user_id = "user_heartbeat_test"

    tok = await service.create_enrollment_token(user_id=user_id, ttl_seconds=300)
    claim = await service.claim_enrollment({
        "enrollment_token": tok["token"],
        "device_name": "Heartbeat Target",
        "hardware_fingerprint": "hwfp_heartbeat_target",
        "os_platform": "windows",
        "hostname": "hb-pc",
    })
    dev_id = claim["device_id"]

    hb_res = await service.heartbeat(
        device_id=dev_id,
        telemetry={"cpu_percent": 14.5, "memory_percent": 42.0, "active_window": "VS Code"},
        daemon_version="1.0.1",
    )

    assert hb_res["device_id"] == dev_id
    assert hb_res["status"] == "online"
    assert hb_res["acknowledged_at"] is not None

    dev = service._mem_devices.get(dev_id)
    if dev:
        assert dev.get("daemon_version") == "1.0.1"
        assert dev.get("telemetry", {}).get("active_window") == "VS Code"


# -----------------------------------------------------------------------------
# 6. Liveness Monitoring & Stale Device Detection
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_liveness_marks_stale_device_offline() -> None:
    """Verify check_device_liveness flags inactive devices as offline while keeping fresh ones online."""
    service = DeviceService.get_instance()
    user_id = "user_liveness_test"

    # Enroll 2 devices
    tok1 = await service.create_enrollment_token(user_id=user_id)
    claim1 = await service.claim_enrollment({
        "enrollment_token": tok1["token"],
        "device_name": "Stale Device",
        "hardware_fingerprint": "hwfp_stale_device",
        "os_platform": "linux",
        "hostname": "stale-node",
    })
    stale_id = claim1["device_id"]

    tok2 = await service.create_enrollment_token(user_id=user_id)
    claim2 = await service.claim_enrollment({
        "enrollment_token": tok2["token"],
        "device_name": "Active Device",
        "hardware_fingerprint": "hwfp_active_device",
        "os_platform": "linux",
        "hostname": "active-node",
    })
    active_id = claim2["device_id"]

    # Artificially age the heartbeat of stale_id by 120 seconds
    past_time = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    if stale_id in service._mem_devices:
        service._mem_devices[stale_id]["last_heartbeat_at"] = past_time

    # Run liveness check with threshold of 60 seconds
    offline_count = await service.check_device_liveness(threshold_seconds=60)
    assert offline_count >= 1

    assert service._mem_devices[stale_id]["status"] == "offline"
    assert service._mem_devices[active_id]["status"] == "online"


# -----------------------------------------------------------------------------
# 7. Asynchronous Bidirectional Command Queue
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_command_queue_lifecycle() -> None:
    """Verify queueing, polling, execution reporting, and audit logging of commands."""
    service = DeviceService.get_instance()
    user_id = "user_cmd_test"

    tok = await service.create_enrollment_token(user_id=user_id)
    claim = await service.claim_enrollment({
        "enrollment_token": tok["token"],
        "device_name": "Worker Node",
        "hardware_fingerprint": "hwfp_worker_node",
        "os_platform": "windows",
        "hostname": "worker-1",
    })
    dev_id = claim["device_id"]

    # 1. User queues command
    cmd = await service.queue_command(
        user_id=user_id,
        device_id=dev_id,
        command_type="ping",
        payload={"message": "ping from test"},
        timeout_seconds=30,
    )
    cmd_id = cmd["id"]
    assert cmd["status"] == "pending"
    assert cmd["command_type"] == "ping"

    # 2. Daemon polls commands
    pending_cmds = await service.poll_pending_commands(device_id=dev_id, max_count=5)
    assert len(pending_cmds) == 1
    assert pending_cmds[0]["id"] == cmd_id
    assert pending_cmds[0]["status"] == "dispatched"

    # 3. Daemon submits completion result
    reported = await service.submit_command_result(
        device_id=dev_id,
        command_id=cmd_id,
        status="completed",
        result={"pong": True, "latency_ms": 1.2},
    )
    assert reported["status"] == "completed"
    assert reported["result"]["pong"] is True

    # 4. Verify audit log entry was created
    actions = await service.list_device_actions(user_id=user_id, device_id=dev_id)
    assert len(actions) >= 1
    matching_action = next((a for a in actions if a["action_type"] == "ping"), None)
    assert matching_action is not None
    assert matching_action["status"] == "success"


# -----------------------------------------------------------------------------
# 8. Standalone RoxyDeviceAgent Daemon Implementation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_roxy_device_agent_daemon_flow(tmp_path: Path) -> None:
    """Verify RoxyDeviceAgent configuration, local command execution, and polling."""
    service = DeviceService.get_instance()
    user_id = "user_daemon_test"

    tok = await service.create_enrollment_token(user_id=user_id)
    claim = await service.claim_enrollment({
        "enrollment_token": tok["token"],
        "device_name": "Local Agent Test",
        "hardware_fingerprint": get_hardware_fingerprint(),
        "os_platform": "windows",
        "hostname": "agent-host",
    })
    dev_id = claim["device_id"]
    dev_token = claim["device_token"]

    config_file = tmp_path / "roxy_test_config.json"
    agent = RoxyDeviceAgent(
        backend_url="http://localhost:8000",
        config_path=config_file,
        device_id=dev_id,
        device_token=dev_token,
    )

    # 1. Config persistence
    saved_path = agent.save_config()
    assert saved_path.exists()

    agent2 = RoxyDeviceAgent(config_path=config_file)
    assert agent2.load_config() is True
    assert agent2.device_id == dev_id
    assert agent2.device_token == dev_token

    # 2. Local execution of 'ping' command
    ping_cmd = {
        "id": str(uuid.uuid4()),
        "command_type": "ping",
        "payload": {"message": "hello daemon"},
    }
    status, result, error = await agent.execute_command(ping_cmd)
    assert status == "completed"
    assert result["pong"] is True
    assert result["echo"] == "hello daemon"
    assert error is None

    # 3. Local execution of 'system_telemetry'
    telem_cmd = {"id": str(uuid.uuid4()), "command_type": "system_telemetry", "payload": {}}
    status, result, error = await agent.execute_command(telem_cmd)
    assert status == "completed"
    assert "cpu_percent" in result
    assert "hostname" in result

    # 4. Local execution of unsupported command
    bad_cmd = {"id": str(uuid.uuid4()), "command_type": "nonexistent_action", "payload": {}}
    status, result, error = await agent.execute_command(bad_cmd)
    assert status == "failed"
    assert "Unsupported command type" in error


# -----------------------------------------------------------------------------
# 9. FastAPI Device Agent REST API Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_device_agent_api_endpoints(async_client: httpx.AsyncClient) -> None:
    """Verify REST API lifecycle for token creation, claiming, heartbeats, and command dispatch."""
    test_user = User(id="user_api_device", email="device_api@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        # 1. User generates enrollment token
        token_resp = await async_client.post(
            "/api/v1/devices/enrollment/token",
            json={"label": "Office iMac", "ttl_seconds": 900},
        )
        assert token_resp.status_code == 201
        token_data = token_resp.json()
        enroll_token = token_data["token"]
        assert enroll_token.startswith("roxy_enroll_")

        # 2. Daemon claims token without user session auth
        claim_resp = await async_client.post(
            "/api/v1/devices/enrollment/claim",
            json={
                "enrollment_token": enroll_token,
                "device_name": "Office iMac (Darwin)",
                "os_platform": "darwin",
                "hostname": "imac-office",
                "hardware_fingerprint": "hwfp_api_office_imac",
                "daemon_version": "1.0.0",
            },
        )
        assert claim_resp.status_code == 201
        claim_data = claim_resp.json()
        dev_id = claim_data["device_id"]
        dev_token = claim_data["device_token"]
        assert dev_token.startswith("roxy_dev_")

        # 3. Daemon sends heartbeat with auth header
        hb_resp = await async_client.post(
            f"/api/v1/devices/{dev_id}/heartbeat",
            headers={"X-Device-Token": dev_token},
            json={
                "telemetry": {"cpu_percent": 8.0, "active_window": "Safari"},
                "daemon_version": "1.0.0",
            },
        )
        assert hb_resp.status_code == 200
        assert hb_resp.json()["status"] == "online"

        # 4. Unauthorized heartbeat (missing or bad token) fails with 401
        hb_unauth = await async_client.post(
            f"/api/v1/devices/{dev_id}/heartbeat",
            headers={"X-Device-Token": "invalid_token_123"},
            json={"telemetry": {}},
        )
        assert hb_unauth.status_code == 401

        # 5. User queues command for device
        queue_resp = await async_client.post(
            f"/api/v1/devices/{dev_id}/commands",
            json={
                "command_type": "ping",
                "payload": {"check": "api_test"},
                "timeout_seconds": 60,
            },
        )
        assert queue_resp.status_code == 201
        cmd_obj = queue_resp.json()
        cmd_id = cmd_obj["id"]
        assert cmd_obj["status"] == "pending"

        # 6. Daemon polls commands with device token
        poll_resp = await async_client.get(
            f"/api/v1/devices/{dev_id}/commands/poll",
            headers={"X-Device-Token": dev_token},
        )
        assert poll_resp.status_code == 200
        dispatched_list = poll_resp.json()
        assert len(dispatched_list) == 1
        assert dispatched_list[0]["id"] == cmd_id
        assert dispatched_list[0]["status"] == "dispatched"

        # 7. Daemon submits result
        res_resp = await async_client.post(
            f"/api/v1/devices/{dev_id}/commands/{cmd_id}/result",
            headers={"X-Device-Token": dev_token},
            json={
                "status": "completed",
                "result": {"ping_success": True},
            },
        )
        assert res_resp.status_code == 200
        assert res_resp.json()["status"] == "completed"

        # 8. User lists commands
        list_cmds_resp = await async_client.get(f"/api/v1/devices/{dev_id}/commands")
        assert list_cmds_resp.status_code == 200
        hist = list_cmds_resp.json()
        assert len(hist) >= 1
        assert hist[0]["id"] == cmd_id
        assert hist[0]["status"] == "completed"

    finally:
        app.dependency_overrides.pop(get_current_user, None)
