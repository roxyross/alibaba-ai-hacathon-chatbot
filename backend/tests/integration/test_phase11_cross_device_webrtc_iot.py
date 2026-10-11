"""Phase 11 Master Integration Test Suite: Cross-Device Continuity, P2P WebRTC & Matter IoT Layer.

Verifies:
1. Tool Discovery and confirmation gates (6 Phase 11 tools, RiskLevel.HIGH on smart lock).
2. Cross-Device active session handover lifecycle (initiation, state transfer, accept).
3. P2P WebRTC signaling channel exchange (SDP offer/answer, ICE candidates, session state).
4. Matter & Zigbee IoT device discovery across protocols and device types.
5. Smart appliance control (lights, plugs, thermostats) and real-time state telemetry.
6. Smart door lock / perimeter control and mandatory confirmation gating.
7. REST API endpoints for Continuity, WebRTC, and Matter IoT.
8. AgentPlanner deterministic intent routing for handover, WebRTC, and IoT commands.
9. Strict multi-tenant anti-IDOR isolation across devices, handovers, WebRTC, and IoT nodes.
"""

from __future__ import annotations

from typing import Any
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
    test_email = "phase11_tenant_b@example.com"
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
def _ensure_phase11_tools() -> None:
    """Ensure device and Phase 11 tools are registered before tests."""
    DeviceService.get_instance().register_device_tools()


# -----------------------------------------------------------------------------
# 1. Tool Discovery and Confirmation Gates
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_phase11_tool_discovery_and_confirmation_gates() -> None:
    """Verify all 6 Phase 11 tools are registered with correct risk levels and confirmation gates."""
    registry = ToolRegistry.get_instance()

    expected_tools = {
        "device_handover_session": (RiskLevel.LOW, False),
        "webrtc_signal_exchange": (RiskLevel.LOW, False),
        "iot_discover_devices": (RiskLevel.LOW, False),
        "iot_control_device": (RiskLevel.MEDIUM, False),
        "iot_get_device_state": (RiskLevel.LOW, False),
        "iot_lock_control": (RiskLevel.HIGH, True),
    }

    for tool_id, (expected_risk, expected_confirmation) in expected_tools.items():
        tool = registry.get(tool_id)
        assert tool is not None, f"Tool '{tool_id}' must be registered in ToolRegistry"
        assert tool.risk_level == expected_risk, f"Tool '{tool_id}' risk level mismatch"
        assert tool.requires_confirmation == expected_confirmation, (
            f"Tool '{tool_id}' requires_confirmation mismatch"
        )
        assert tool.source == ToolSource.DEVICE


# -----------------------------------------------------------------------------
# 2. Cross-Device Active Session Handover Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cross_device_session_handover_lifecycle() -> None:
    """Verify seamless session transfer token creation, inspection, and acceptance."""
    service = DeviceService.get_instance()
    user_id = "test_user_p11_handover"

    # 1. Register companion device for this user
    target_dev = await service.register_device(
        user_id=user_id,
        data={
            "device_name": "MacBook Air Companion",
            "device_type": "laptop",
            "os_platform": "darwin",
        },
    )
    target_dev_id = target_dev["id"]

    # 2. Initiate session handover via Tool Execution
    registry = ToolRegistry.get_instance()
    state_payload = {
        "active_prompt": "Help me refactor the database layer",
        "chat_turn_count": 4,
        "selected_files": ["src/app/device/service.py"],
    }
    exec_req = ToolExecutionRequest(
        tool_id="device_handover_session",
        arguments={
            "target_device_id": target_dev_id,
            "session_id": "session_test_456",
            "state_payload": state_payload,
            "ttl_seconds": 300,
        },
        user_id=user_id,
    )
    exec_res = await registry.execute(exec_req)
    assert exec_res.success is True, f"Execution failed: {exec_res.error}"
    handover = exec_res.output
    assert handover["status"] == "pending"
    assert handover["session_id"] == "session_test_456"
    assert handover["target_device_id"] == target_dev_id
    assert handover["state_payload"]["active_prompt"] == "Help me refactor the database layer"

    handover_id = handover["id"]

    # 3. Retrieve handover
    fetched = await service.get_session_handover(user_id=user_id, handover_id=handover_id)
    assert fetched is not None
    assert fetched["id"] == handover_id
    assert fetched["status"] == "pending"

    # 4. Accept handover from companion device
    accepted = await service.accept_session_handover(
        user_id=user_id,
        handover_id=handover_id,
        target_device_id=target_dev_id,
    )
    assert accepted["status"] == "accepted"
    assert accepted["completed_at"] is not None
    assert accepted["state_payload"]["chat_turn_count"] == 4


# -----------------------------------------------------------------------------
# 3. P2P WebRTC Signaling Channel Exchange
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_webrtc_p2p_signaling_exchange() -> None:
    """Verify WebRTC P2P signaling exchange: SDP offer, answer, and ICE candidates."""
    service = DeviceService.get_instance()
    user_id = "test_user_webrtc_p11"

    # Register peer device for this user
    peer_dev = await service.register_device(
        user_id=user_id,
        data={
            "device_name": "iPad Pro Companion",
            "device_type": "mobile",
            "os_platform": "ios",
        },
    )
    peer_id = peer_dev["id"]

    registry = ToolRegistry.get_instance()

    # 1. Initiate WebRTC signaling with SDP Offer
    offer_sdp = "v=0\r\no=- 461173 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=data 9 UDP/DTLS/SCTP webrtc-datachannel\r\n"
    init_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="webrtc_signal_exchange",
            arguments={
                "target_device_id": peer_id,
                "signal_type": "offer",
                "payload": offer_sdp,
            },
            user_id=user_id,
        )
    )
    assert init_res.success is True, f"WebRTC init failed: {init_res.error}"
    session_data = init_res.output
    session_id = session_data["id"]
    assert session_data["status"] == "negotiating"
    assert session_data["sdp_offer"] == offer_sdp

    # 2. Respond with SDP Answer
    answer_sdp = "v=0\r\no=- 461173 3 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=data 9 UDP/DTLS/SCTP webrtc-datachannel\r\n"
    ans_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="webrtc_signal_exchange",
            arguments={
                "session_id": session_id,
                "target_device_id": peer_id,
                "signal_type": "answer",
                "payload": answer_sdp,
            },
            user_id=user_id,
        )
    )
    assert ans_res.success is True
    updated = ans_res.output
    assert updated["status"] == "connected"
    assert updated["sdp_answer"] == answer_sdp

    # 3. Exchange ICE Candidate
    candidate = {"candidate": "candidate:1 1 UDP 2130706431 192.168.1.100 50000 typ host", "sdpMid": "0"}
    cand_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="webrtc_signal_exchange",
            arguments={
                "session_id": session_id,
                "target_device_id": peer_id,
                "signal_type": "candidate",
                "payload": candidate,
            },
            user_id=user_id,
        )
    )
    assert cand_res.success is True
    with_candidate = cand_res.output
    assert len(with_candidate["ice_candidates"]) >= 1


# -----------------------------------------------------------------------------
# 4. Matter & Zigbee IoT Device Discovery
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_matter_iot_device_discovery() -> None:
    """Verify discovery of Matter, Zigbee, and Thread smart home nodes."""
    registry = ToolRegistry.get_instance()
    user_id = "test_user_iot_discovery"

    # 1. Discover all devices
    res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_discover_devices",
            arguments={"protocol": "all", "device_type": "all"},
            user_id=user_id,
        )
    )
    assert res.success is True
    data = res.output
    assert data["discovered_count"] >= 4
    devices = data["devices"]

    device_types = {d["device_type"] for d in devices}
    protocols = {d["protocol"] for d in devices}

    assert "light" in device_types
    assert "plug" in device_types
    assert "thermostat" in device_types
    assert "lock" in device_types
    assert "matter" in protocols

    # 2. Filter by protocol
    zigbee_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_discover_devices",
            arguments={"protocol": "zigbee", "device_type": "all"},
            user_id=user_id,
        )
    )
    assert zigbee_res.success is True
    assert len(zigbee_res.output["devices"]) >= 1
    for d in zigbee_res.output["devices"]:
        assert d["protocol"] == "zigbee"


# -----------------------------------------------------------------------------
# 5. Smart Appliance Control & Real-Time Telemetry
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_matter_iot_device_control_and_telemetry() -> None:
    """Verify smart home device control (lights, plugs, thermostats) and state querying."""
    registry = ToolRegistry.get_instance()
    user_id = "test_user_iot_control"

    # 1. Query initial light state
    state_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_get_device_state",
            arguments={"device_name": "Living Room Main Light"},
            user_id=user_id,
        )
    )
    assert state_res.success is True, f"Query light state failed: {state_res.error}"
    assert state_res.output["device_name"] == "Living Room Main Light"

    # 2. Turn on the light and adjust brightness
    ctrl_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_control_device",
            arguments={
                "device_name": "Living Room Main Light",
                "command": "set_brightness",
                "parameters": {"brightness": 90},
            },
            user_id=user_id,
        )
    )
    assert ctrl_res.success is True
    assert ctrl_res.output["state"]["power"] == "on"
    assert ctrl_res.output["state"]["brightness"] == 90

    # 3. Control thermostat
    therm_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_control_device",
            arguments={
                "device_name": "Office Thermostat",
                "command": "set_temperature",
                "parameters": {"temperature": 23.5},
            },
            user_id=user_id,
        )
    )
    assert therm_res.success is True
    assert therm_res.output["state"]["target_temperature"] == 23.5

    # 4. Toggle smart plug
    plug_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_control_device",
            arguments={
                "device_name": "Kitchen Smart Plug",
                "command": "toggle",
            },
            user_id=user_id,
        )
    )
    assert plug_res.success is True
    # Was originally on, so toggle turns it off
    assert plug_res.output["state"]["power"] == "off"


# -----------------------------------------------------------------------------
# 6. Smart Door Lock Control & Confirmation Gate
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_smart_lock_control_confirmation_gate() -> None:
    """Verify smart door lock control requires confirmation and functions securely."""
    registry = ToolRegistry.get_instance()
    user_id = "test_user_smart_lock"

    lock_tool = registry.get("iot_lock_control")
    assert lock_tool is not None
    assert lock_tool.risk_level == RiskLevel.HIGH
    assert lock_tool.requires_confirmation is True

    # 1. Unconfirmed attempt must trigger confirmation gate
    unconfirmed_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_lock_control",
            arguments={
                "device_name": "Front Door Smart Lock",
                "action": "unlock",
                "reason": "Family member arriving home",
            },
            user_id=user_id,
            bypass_confirmation=False,
        )
    )
    assert unconfirmed_res.success is False
    assert unconfirmed_res.status == "requires_confirmation"

    # 2. Confirmed unlock (e.g. approved via Action Center)
    unlock_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_lock_control",
            arguments={
                "device_name": "Front Door Smart Lock",
                "action": "unlock",
                "reason": "Family member arriving home",
            },
            user_id=user_id,
            bypass_confirmation=True,
        )
    )
    assert unlock_res.success is True, f"Unlock failed: {unlock_res.error}"
    assert unlock_res.output["locked"] is False

    # 3. Lock the door (with confirmation)
    lock_res = await registry.execute(
        ToolExecutionRequest(
            tool_id="iot_lock_control",
            arguments={
                "device_name": "Front Door Smart Lock",
                "action": "lock",
            },
            user_id=user_id,
            bypass_confirmation=True,
        )
    )
    assert lock_res.success is True
    assert lock_res.output["locked"] is True


# -----------------------------------------------------------------------------
# 7. Device Continuity, WebRTC & IoT REST Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_device_continuity_and_iot_rest_endpoints(authed_client: AsyncClient) -> None:
    """Verify REST API routes for continuity handovers, WebRTC, and smart home IoT."""
    # 1. Register companion device
    c_res = await authed_client.post(
        "/api/v1/devices/register",
        json={"device_name": "Desktop PC Rig", "device_type": "desktop"},
    )
    assert c_res.status_code == 201
    dev_id = c_res.json()["id"]

    # 2. REST Handover endpoint
    handover_res = await authed_client.post(
        "/api/v1/devices/continuity/handover",
        json={
            "target_device_id": dev_id,
            "session_id": "rest_session_123",
            "state_payload": {"url": "https://example.com/project"},
        },
    )
    assert handover_res.status_code == 201
    h_data = handover_res.json()
    assert h_data["status"] == "pending"

    # List handovers
    h_list = await authed_client.get("/api/v1/devices/continuity/handovers")
    assert h_list.status_code == 200
    assert len(h_list.json()) >= 1

    # 3. REST WebRTC sessions endpoint
    webrtc_res = await authed_client.post(
        "/api/v1/devices/webrtc/sessions",
        json={
            "target_device_id": dev_id,
            "session_type": "screen_stream",
            "sdp_offer": "dummy_offer_sdp",
        },
    )
    assert webrtc_res.status_code == 201
    w_data = webrtc_res.json()
    assert w_data["status"] == "negotiating"

    # 4. REST IoT endpoints
    iot_list = await authed_client.get("/api/v1/devices/iot")
    assert iot_list.status_code == 200
    devices = iot_list.json()
    assert len(devices) >= 1

    first_dev_id = devices[0]["id"]
    get_dev = await authed_client.get(f"/api/v1/devices/iot/{first_dev_id}")
    assert get_dev.status_code == 200
    assert get_dev.json()["id"] == first_dev_id


# -----------------------------------------------------------------------------
# 8. AgentPlanner Deterministic Intent Routing for Phase 11
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_phase11_intent_routing() -> None:
    """Verify AgentPlanner deterministic fast-path decomposition for Phase 11 intents."""
    planner = AgentPlanner()

    test_cases: list[tuple[str, str]] = [
        ("Handover session to MacBook Pro", "device_handover_session"),
        ("Transfer chat to iPhone", "device_handover_session"),
        ("Continue this on my iPad", "device_handover_session"),
        ("Start P2P stream with tablet", "webrtc_signal_exchange"),
        ("Discover smart home devices", "iot_discover_devices"),
        ("Scan for IoT devices", "iot_discover_devices"),
        ("Turn on Living Room Light", "iot_control_device"),
        ("Set thermostat to 72", "iot_control_device"),
        ("Check living room temperature", "iot_get_device_state"),
        ("Unlock front door", "iot_lock_control"),
    ]

    for user_prompt, expected_tool_id in test_cases:
        plan = await planner.create_plan(user_prompt)
        assert len(plan) >= 1, f"Failed to plan for: '{user_prompt}'"
        if expected_tool_id == "device_handover_session":
            assert plan[0]["tool_id"] in ("device_handover_session", "device_fleet_handover"), (
                f"Expected 'device_handover_session' or 'device_fleet_handover' for prompt '{user_prompt}', got '{plan[0]['tool_id']}'"
            )
        else:
            assert plan[0]["tool_id"] == expected_tool_id, (
                f"Expected '{expected_tool_id}' for prompt '{user_prompt}', got '{plan[0]['tool_id']}'"
            )


# -----------------------------------------------------------------------------
# 9. Strict Multi-Tenant Anti-IDOR Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_phase11_multi_tenant_anti_idor_isolation(authed_client: AsyncClient) -> None:
    """Verify strict tenant isolation across handovers, WebRTC sessions, and smart home IoT."""
    client_b = await _create_second_user_client()

    # Tenant A creates companion device and handover
    c_res = await authed_client.post(
        "/api/v1/devices/register",
        json={"device_name": "Tenant A Laptop", "device_type": "laptop"},
    )
    assert c_res.status_code == 201
    dev_a_id = c_res.json()["id"]

    h_res = await authed_client.post(
        "/api/v1/devices/continuity/handover",
        json={
            "target_device_id": dev_a_id,
            "session_id": "tenant_a_secret_session",
            "state_payload": {"confidential_token": "secret_123"},
        },
    )
    assert h_res.status_code == 201
    h_a_id = h_res.json()["id"]

    # 1. Tenant B attempts to read Tenant A's handover -> 404
    idor_read = await client_b.get(f"/api/v1/devices/continuity/handover/{h_a_id}")
    assert idor_read.status_code == 404

    # 2. Tenant B attempts to accept Tenant A's handover -> 400 or 404
    idor_accept = await client_b.post(f"/api/v1/devices/continuity/handover/{h_a_id}/accept")
    assert idor_accept.status_code in (400, 404)

    # 3. Tenant B attempts to discover Tenant A's devices via list -> Tenant B gets own devices
    b_iot_list = await client_b.get("/api/v1/devices/iot")
    assert b_iot_list.status_code == 200
    b_devices = b_iot_list.json()

    a_iot_list = await authed_client.get("/api/v1/devices/iot")
    a_devices = a_iot_list.json()

    b_device_ids = {d["id"] for d in b_devices}
    a_device_ids = {d["id"] for d in a_devices}
    assert b_device_ids.isdisjoint(a_device_ids), "Cross-tenant IoT device leakage detected!"

    # 4. Tenant B attempts to control Tenant A's smart lock -> 400 or 404
    a_lock = next((d for d in a_devices if d["device_type"] == "lock"), None)
    if a_lock:
        idor_lock = await client_b.post(
            f"/api/v1/devices/iot/{a_lock['id']}/lock",
            json={"action": "unlock"},
        )
        assert idor_lock.status_code in (400, 404)
