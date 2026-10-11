"""Phase 11: Agent Conversational Grounding & Natural Language Intent Routing Test Suite.

Verifies end-to-end conversational grounding from natural language chat queries
("play Bohemian Rhapsody on my living room desktop", "transfer this session to my laptop",
"what devices are online?") through DeviceIntentParser, DeviceConversationalGrounder,
AgentPlanner, and FastAPI /runtime/chat and /runtime/chat/stream endpoints under Zero Simulation.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx
import pytest

from app.agent_runtime.planner import AgentPlanner
from app.api.v1.runtime import classify_intent
from app.auth.dependencies import get_current_user, get_optional_current_user
from app.auth.models import User
from app.device.conversational_grounding import DeviceConversationalGrounder
from app.device.intent_parser import DeviceIntentParser, DeviceIntentType, ParsedDeviceIntent
from app.device.schemas import (
    AppControlExecutionResult,
    IntegrationResolutionResult,
)
from app.device.service import DeviceService
from app.main import app


# -----------------------------------------------------------------------------
# 1. Intent Parser: Media Playback with Target Device Extraction
# -----------------------------------------------------------------------------

def test_intent_parser_media_playback_with_target_device() -> None:
    """Verify 'play Bohemian Rhapsody on my living room desktop' extracts track, Spotify, and device hint."""
    query = "play Bohemian Rhapsody on my living room desktop"
    res = DeviceIntentParser.parse(query)

    assert res.intent_type == DeviceIntentType.APP_CONTROL
    assert res.application == "Spotify"
    assert res.capability == "play_media"
    assert "Bohemian Rhapsody" in res.parameters.get("track", "")
    assert res.target_device_hint == "living room desktop"
    assert res.confidence >= 0.85


def test_intent_parser_explicit_media_app() -> None:
    """Verify explicit media app specification like 'play Hotel California on YouTube on my laptop'."""
    query = "play Hotel California on YouTube on my laptop"
    res = DeviceIntentParser.parse(query)

    assert res.intent_type == DeviceIntentType.APP_CONTROL
    assert res.application == "YouTube"
    assert res.capability == "play_media"
    assert "Hotel California" in res.parameters.get("track", "")
    assert res.target_device_hint == "laptop"


# -----------------------------------------------------------------------------
# 2. Intent Parser: Cross-Device Handover Intents
# -----------------------------------------------------------------------------

def test_intent_parser_handover_intent() -> None:
    """Verify 'transfer this session to my laptop' and 'handover to my phone'."""
    q1 = "transfer this session to my laptop"
    r1 = DeviceIntentParser.parse(q1)
    assert r1.intent_type == DeviceIntentType.HANDOVER
    assert r1.target_device_hint == "laptop"
    assert r1.confidence >= 0.90

    q2 = "handover to my phone please"
    r2 = DeviceIntentParser.parse(q2)
    assert r2.intent_type == DeviceIntentType.HANDOVER
    assert r2.target_device_hint == "phone"

    q3 = "switch to my macbook"
    r3 = DeviceIntentParser.parse(q3)
    assert r3.intent_type == DeviceIntentType.HANDOVER
    assert r3.target_device_hint == "macbook"


# -----------------------------------------------------------------------------
# 3. Intent Parser: Fleet Summary & Status Queries
# -----------------------------------------------------------------------------

def test_intent_parser_fleet_summary() -> None:
    """Verify detection of fleet inventory queries."""
    queries = [
        "what devices are online?",
        "which devices are in my fleet?",
        "show my devices",
        "list my fleet",
        "status of my devices",
        "what hardware do i have",
    ]
    for q in queries:
        res = DeviceIntentParser.parse(q)
        assert res.intent_type == DeviceIntentType.FLEET_SUMMARY, f"Failed for: {q}"
        assert res.confidence >= 0.90


# -----------------------------------------------------------------------------
# 4. Intent Parser: Fleet Broadcast Queries
# -----------------------------------------------------------------------------

def test_intent_parser_fleet_broadcast() -> None:
    """Verify broadcast queries like 'where is Spotify running?' or 'check cpu across my devices'."""
    q1 = "where is Spotify running"
    r1 = DeviceIntentParser.parse(q1)
    assert r1.intent_type == DeviceIntentType.FLEET_BROADCAST
    assert r1.application == "Spotify"
    assert r1.parameters.get("query_type") == "find_app"

    q2 = "check cpu across all my devices"
    r2 = DeviceIntentParser.parse(q2)
    assert r2.intent_type == DeviceIntentType.FLEET_BROADCAST
    assert r2.parameters.get("query_type") == "system_stats"


# -----------------------------------------------------------------------------
# 5. Intent Parser: Process Lifecycle Control
# -----------------------------------------------------------------------------

def test_intent_parser_process_control() -> None:
    """Verify terminate and restart process detection."""
    q1 = "close Docker on my workstation"
    r1 = DeviceIntentParser.parse(q1)
    assert r1.intent_type == DeviceIntentType.APP_CONTROL
    assert r1.application == "Docker"
    assert r1.capability == "terminate_process"
    assert r1.target_device_hint == "workstation"

    q2 = "restart VS Code on desktop"
    r2 = DeviceIntentParser.parse(q2)
    assert r2.intent_type == DeviceIntentType.APP_CONTROL
    assert r2.application == "Visual Studio Code"
    assert r2.capability == "restart_process"
    assert r2.target_device_hint == "desktop"


# -----------------------------------------------------------------------------
# 6. Intent Parser: Script Execution
# -----------------------------------------------------------------------------

def test_intent_parser_script_execution() -> None:
    """Verify script execution intent."""
    q = "run python script: print(12 * 12) on server"
    r = DeviceIntentParser.parse(q)
    assert r.intent_type == DeviceIntentType.APP_CONTROL
    assert r.application == "python"
    assert r.capability == "execute_script"
    assert "print(12 * 12)" in r.parameters.get("script", "")
    assert r.target_device_hint == "server"


# -----------------------------------------------------------------------------
# 7. Coordinator Agent Intent Classification Routing
# -----------------------------------------------------------------------------

def test_runtime_classify_intent_routes_to_device_fleet() -> None:
    """Verify classify_intent assigns 'device_fleet' slug to conversational device prompts."""
    assert classify_intent("play Bohemian Rhapsody on my living room desktop") == "device_fleet"
    assert classify_intent("transfer this session to my laptop") == "device_fleet"
    assert classify_intent("what devices are online?") == "device_fleet"
    assert classify_intent("show my fleet") == "device_fleet"
    assert classify_intent("close Docker on workstation") == "device_fleet"
    assert classify_intent("run python script: print(1)") == "device_fleet"


# -----------------------------------------------------------------------------
# 8. DeviceConversationalGrounder: Fleet Summary Execution
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversational_grounder_fleet_summary_execution() -> None:
    """Verify Grounder returns markdown table with enrolled devices and app catalog."""
    service = DeviceService.get_instance()
    user_id = "user_grounder_summary"

    await service.register_device(user_id=user_id, data={
        "device_name": "Living Room Workstation",
        "os_platform": sys.platform,
        "is_current_host": True,
    })
    await service.register_device(user_id=user_id, data={
        "device_name": "MacBook Laptop",
        "os_platform": "darwin",
    })

    handled, reply, meta = await DeviceConversationalGrounder.handle_conversational_request(
        user_id=user_id,
        message="what devices are in my fleet?",
    )

    assert handled is True
    assert "Roxy Multi-Device Fleet Status" in reply
    assert "Living Room Workstation" in reply
    assert "MacBook Laptop" in reply
    assert meta is not None
    assert meta["total_devices"] >= 2


# -----------------------------------------------------------------------------
# 9. DeviceConversationalGrounder: Autonomous Handover Execution
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversational_grounder_handover_execution() -> None:
    """Verify Grounder matches target hint ('laptop') and completes handover."""
    service = DeviceService.get_instance()
    user_id = "user_grounder_handover"

    dev_host = await service.register_device(user_id=user_id, data={
        "device_name": "Main Desktop",
        "os_platform": sys.platform,
        "is_current_host": True,
    })
    service._mem_devices[dev_host["id"]]["is_current_host"] = True

    dev_laptop = await service.register_device(user_id=user_id, data={
        "device_name": "Office Laptop",
        "os_platform": sys.platform,
    })

    handled, reply, meta = await DeviceConversationalGrounder.handle_conversational_request(
        user_id=user_id,
        message="transfer this session to my laptop",
    )

    assert handled is True
    assert "Autonomous Device Handover Completed" in reply
    assert "Office Laptop" in reply
    assert meta is not None
    assert meta["target_device_id"] == dev_laptop["id"]


# -----------------------------------------------------------------------------
# 10. DeviceConversationalGrounder: App Control Real Execution (2-turn Flow)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversational_grounder_app_control_execution() -> None:
    """Verify Grounder gates script execution behind human confirmation and executes upon 'confirm'."""
    service = DeviceService.get_instance()
    user_id = "user_grounder_app_exec"
    session_id = "sess_grounder_app_exec"

    dev = await service.register_device(user_id=user_id, data={
        "device_name": "Local Test Machine",
        "os_platform": sys.platform,
        "is_current_host": True,
    })
    service._mem_devices[dev["id"]]["is_current_host"] = True

    # Turn 1: Initial request gates on confirmation
    handled1, reply1, meta1 = await DeviceConversationalGrounder.handle_conversational_request(
        user_id=user_id,
        message="run python script: print('phase11 conversational success')",
        session_id=session_id,
    )

    assert handled1 is True
    assert "Action Requires Confirmation" in reply1
    assert "python" in reply1

    # Turn 2: User approves via chat
    handled2, reply2, meta2 = await DeviceConversationalGrounder.handle_conversational_request(
        user_id=user_id,
        message="confirm",
        session_id=session_id,
    )

    assert handled2 is True
    assert "Action Confirmed & Executed Successfully" in reply2
    assert "phase11 conversational success" in reply2
    assert meta2 is not None
    assert meta2["success"] is True


# -----------------------------------------------------------------------------
# 11. DeviceConversationalGrounder: Human Confirmation In-Chat Approval Flow
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversational_grounder_confirmation_in_chat_flow() -> None:
    """Verify two-turn in-chat confirmation flow: warning -> reply 'confirm' -> execution."""
    session_id = "sess_confirm_test_123"
    token = "simulated_challenge_tok"

    # Pre-populate pending token
    DeviceConversationalGrounder._PENDING_CHAT_CONFIRMATIONS[session_id] = token

    # Mock service.confirm_app_control
    service = DeviceService.get_instance()
    orig_confirm = service.confirm_app_control

    async def _mock_confirm(confirmation_token: str, **kwargs: Any) -> AppControlExecutionResult:
        from app.device.schemas import AppControlExecutionResult, IntegrationResolutionResult
        return AppControlExecutionResult(
            execution_id="exec_confirmed",
            plan_id="plan_confirmed",
            application="Docker",
            capability="terminate_process",
            stage="executed",
            success=True,
            verified=True,
            duration_ms=45.0,
            resolution=IntegrationResolutionResult(
                success=True,
                application="Docker",
                requested_capability="terminate_process",
                chosen_integration="system_launcher",
                confidence=0.9,
                required_permission="app:docker:terminate",
                risk="high",
                requires_confirmation=True,
                execution_method="process_launch",
                verification_method="process_pid_and_window_presence",
            ),
            execution_output={"terminated_pids": [9999]},
        )

    service.confirm_app_control = _mock_confirm  # type: ignore[assignment]

    try:
        handled, reply, meta = await DeviceConversationalGrounder.handle_conversational_request(
            user_id="user_confirm_flow",
            message="confirm",
            session_id=session_id,
        )

        assert handled is True
        assert "Action Confirmed & Executed Successfully" in reply
        assert "Docker" in reply
        assert meta is not None
        assert meta["success"] is True
        assert session_id not in DeviceConversationalGrounder._PENDING_CHAT_CONFIRMATIONS
    finally:
        service.confirm_app_control = orig_confirm


# -----------------------------------------------------------------------------
# 12. FastAPI POST /api/v1/runtime/chat (Fleet Summary)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fastapi_runtime_chat_fleet_summary() -> None:
    """Verify POST /api/v1/runtime/chat routes fleet query to device_fleet agent."""
    user = User(id="user_chat_fleet", email="chat_fleet@example.com")
    app.dependency_overrides[get_optional_current_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user

    service = DeviceService.get_instance()
    await service.register_device(user_id=user.id, data={
        "device_name": "API Primary Workstation",
        "os_platform": sys.platform,
        "is_current_host": True,
    })

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/runtime/chat",
                json={"message": "what devices are in my fleet?"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["agent_slug"] == "device_fleet"
            assert "Roxy Multi-Device Fleet Status" in data["response"]
            assert "API Primary Workstation" in data["response"]
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)
        app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 13. FastAPI POST /api/v1/runtime/chat (Real App Control Execution - 2 Turn)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fastapi_runtime_chat_app_control() -> None:
    """Verify POST /api/v1/runtime/chat gates script and executes on confirm."""
    user = User(id="user_chat_exec", email="chat_exec@example.com")
    app.dependency_overrides[get_optional_current_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user

    service = DeviceService.get_instance()
    dev = await service.register_device(user_id=user.id, data={
        "device_name": "Exec Host",
        "os_platform": sys.platform,
        "is_current_host": True,
    })
    service._mem_devices[dev["id"]]["is_current_host"] = True

    session_id = "sess_api_turn_test"

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Turn 1: Initial prompt triggers confirmation prompt
            resp1 = await client.post(
                "/api/v1/runtime/chat",
                json={
                    "message": "run python script: print('chat api exec pass')",
                    "session_id": session_id,
                },
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["agent_slug"] == "device_fleet"
            assert "Action Requires Confirmation" in data1["response"]

            # Turn 2: Confirm prompt triggers execution and returns output
            resp2 = await client.post(
                "/api/v1/runtime/chat",
                json={
                    "message": "confirm",
                    "session_id": session_id,
                },
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["agent_slug"] == "device_fleet"
            assert "Action Confirmed & Executed Successfully" in data2["response"]
            assert "chat api exec pass" in data2["response"]
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)
        app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 14. FastAPI POST /api/v1/runtime/chat/stream (SSE Streaming)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fastapi_runtime_chat_stream_device_fleet() -> None:
    """Verify POST /api/v1/runtime/chat/stream streams SSE deltas and attribution."""
    user = User(id="user_stream_fleet", email="stream_fleet@example.com")
    app.dependency_overrides[get_optional_current_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user

    service = DeviceService.get_instance()
    await service.register_device(user_id=user.id, data={
        "device_name": "Stream Device",
        "os_platform": sys.platform,
        "is_current_host": True,
    })

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/runtime/chat/stream",
                json={"message": "show my fleet"},
            )
            assert resp.status_code == 200
            body = resp.text
            assert "data: " in body
            assert "device_fleet" in body
            assert "Stream Device" in body
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)
        app.dependency_overrides.pop(get_current_user, None)


# -----------------------------------------------------------------------------
# 15. AgentPlanner: Fleet Execution & Media Decompositions
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_planner_fleet_play_media_plan() -> None:
    """Verify AgentPlanner formulates device_fleet_execute step for media playback."""
    planner = AgentPlanner()
    objective = "play Bohemian Rhapsody on my living room desktop"

    plan = await planner.create_plan(objective)
    assert len(plan) >= 1
    step = plan[0]
    assert step["tool_id"] in ("device_fleet_execute", "device_orchestrate_app_control")
    assert step["tool_input"]["application"] == "Spotify"
    assert step["tool_input"]["capability"] == "play_media"
    assert "Bohemian Rhapsody" in step["tool_input"]["parameters"]["track"]


# -----------------------------------------------------------------------------
# 16. AgentPlanner: Fleet Handover & Summary Decompositions
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_planner_handover_and_summary_plans() -> None:
    """Verify AgentPlanner uses device_fleet_handover and device_fleet_summary tools."""
    planner = AgentPlanner()

    # 1. Handover
    p_handover = await planner.create_plan("transfer this session to my laptop")
    assert len(p_handover) >= 1
    s_h = p_handover[0]
    assert s_h["tool_id"] in ("device_fleet_handover", "device_handover_session")
    assert "laptop" in s_h["tool_input"]["target_device_id"].lower()

    # 2. Fleet Summary
    p_summary = await planner.create_plan("what devices are online?")
    assert len(p_summary) >= 1
    s_s = p_summary[0]
    assert s_s["tool_id"] == "device_fleet_summary"
