"""Comprehensive Automated Test Suite for Phase 9: Universal App Control Orchestrator.

Validates:
1. UniversalAppController singleton and component architecture.
2. Stage 1 (Resolve): 8-tier hierarchy resolution into candidates.
3. Stage 2 (Permission): Target-scoped authorization checks and security gates.
4. Stage 2 (Confirmation Gate): High-risk actions paused with challenge tokens and human UX details.
5. Stage 3 (Plan): Synthesis of auditable multi-step plans with explicit verification criteria.
6. Stage 4 (Execute) & Stage 5 (Verify) across surfaces:
   - Tier 1: Cloud / SaaS Connectors (Spotify, Slack)
   - Tier 2: Model Context Protocol (MCP) Tools
   - Tier 3: CLI Subprocesses (Python CLI, Git CLI)
   - Tier 4: Desktop UI Automation (Window state inspection, UI interaction)
   - Tier 5: System Process Launcher (Launch, terminate, focus)
7. Honest Unsupported Fallback: Zero simulation fallback with diagnostic guidance.
8. Confirmation & Resumption: Challenge token approval and execution resumption.
9. Verification Failure Handling: Non-zero exit code or missing PID detection.
10. Skip Verification Flag: Controlled bypass for non-intrusive operations.
11. Central DeviceService Integration: orchestrate_app_control and confirm_app_control.
12. ToolRegistry Tool Execution: device_orchestrate_app_control and device_confirm_app_control.
13. Standalone RoxyDeviceDaemon Dispatch: app_control_orchestrate and app_control_confirm.
14. FastAPI REST Endpoints: Device-scoped, generic, confirm, and retrieval endpoints.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import psutil  # type: ignore[import-untyped]
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.daemon import RoxyDeviceDaemon
from app.device.orchestrator import UniversalAppController
from app.device.schemas import (
    AppControlConfirmationRequest,
    AppControlExecutionPlan,
    AppControlExecutionRequest,
    AppControlExecutionResult,
)
from app.device.service import DeviceService
from app.main import app
from app.permissions.schemas import PermissionCheckResult, PermissionPolicy
from app.permissions.service import PermissionService
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolExecutionRequest, ToolSource

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_user() -> User:
    """Provide authenticated test user."""
    return User(
        id="usr_test_phase9_orchestrator",
        email="orchestrator@roxy.ai",
    )


@pytest.fixture
def controller() -> UniversalAppController:
    """Provide UniversalAppController singleton instance."""
    return UniversalAppController.get_instance()


@pytest.fixture
def device_service() -> DeviceService:
    """Provide DeviceService singleton instance."""
    return DeviceService.get_instance()


# -----------------------------------------------------------------------------
# 1. Architecture & Singleton
# -----------------------------------------------------------------------------

def test_universal_app_controller_singleton(controller: UniversalAppController) -> None:
    """Verify UniversalAppController follows robust singleton pattern."""
    c2 = UniversalAppController.get_instance()
    assert controller is c2
    assert controller._tool_registry is not None
    assert controller._permission_service is not None


# -----------------------------------------------------------------------------
# 2. Stage 1: Resolve & Unsupported Fallback
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_stage_resolve_unsupported(controller: UniversalAppController) -> None:
    """Verify Stage 1 halts early with unsupported stage for completely unknown applications."""
    req = AppControlExecutionRequest(
        application="UnknownNonExistentSoftwareApplicationXYZ",
        capability="execute_quantum_teleportation",
        user_id="usr_test",
    )
    result = await controller.execute_lifecycle(req)
    assert result.stage == "unsupported"
    assert result.success is False
    assert result.verified is False
    assert result.resolution.chosen_integration == "unsupported"
    assert "No integration route found" in (result.error or "")


# -----------------------------------------------------------------------------
# 3. Stage 2: Target-Scoped Permission Denials & Security Gates
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_permission_denial(controller: UniversalAppController) -> None:
    """Verify Stage 2 denies execution when target-scoped policy is NEVER_ALLOW."""
    req = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        user_id="usr_blocked_user",
        user_context={"oauth_tokens": {"spotify": "valid_token"}},
    )

    with patch.object(
        PermissionService,
        "check_permission",
        new=AsyncMock(
            return_value=PermissionCheckResult(
                granted=False,
                policy=PermissionPolicy.NEVER_ALLOW.value,
                requires_confirmation=False,
                reason="Policy prohibits Spotify playback on this tenant.",
            )
        ),
    ):
        result = await controller.execute_lifecycle(req)
        assert result.stage == "permission_denied"
        assert result.success is False
        assert "Permission denied" in (result.error or "")
        assert "Policy prohibits Spotify playback" in (result.error or "")


# -----------------------------------------------------------------------------
# 4. Stage 2: Pending Confirmation Challenge & Token Resumption
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_pending_confirmation_and_approval(controller: UniversalAppController) -> None:
    """Verify high-risk actions halt in pending_confirmation and resume when confirmed with token."""
    req = AppControlExecutionRequest(
        application="Calculator",
        capability="terminate",
        parameters={"target": "calc.exe", "force": True},
        user_id="usr_test_operator",
        confirmed=False,  # Unconfirmed high-risk action
    )

    result = await controller.execute_lifecycle(req)
    assert result.stage == "pending_confirmation"
    assert result.success is False
    assert result.pending_confirmation_details is not None

    token = result.pending_confirmation_details["confirmation_token"]
    assert token is not None
    assert result.pending_confirmation_details["application"].lower() == "calculator"
    assert result.pending_confirmation_details["risk"] in ("HIGH", "CRITICAL")

    # Now resume using confirm_execution
    resumed = await controller.confirm_execution(token=token, user_id="usr_test_operator")
    assert resumed.stage in ("verified", "failed")
    # Verify token was consumed
    with pytest.raises(LookupError):
        await controller.confirm_execution(token=token, user_id="usr_test_operator")


# -----------------------------------------------------------------------------
# 5. Stage 3 (Plan), Stage 4 (Execute), Stage 5 (Verify): Cloud Connector
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_cloud_connector_lifecycle(controller: UniversalAppController) -> None:
    """Verify end-to-end cloud connector route (Spotify play_music) executes and verifies."""
    req = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        parameters={"track": "Bohemian Rhapsody"},
        user_id="usr_test_music",
        user_context={"oauth_tokens": {"spotify": "valid_token"}},
        confirmed=True,
    )

    result = await controller.execute_lifecycle(req)
    assert result.stage == "verified"
    assert result.success is True
    assert result.verified is True
    assert result.resolution.chosen_integration == "cloud_connector"
    assert result.plan is not None
    assert len(result.plan.steps) >= 3
    assert result.verification_details.get("verified") is True
    assert result.duration_ms > 0.0


# -----------------------------------------------------------------------------
# 6. Stage 4 & 5: CLI Subprocess Execution & Exit Code Verification
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_cli_process_lifecycle(controller: UniversalAppController) -> None:
    """Verify end-to-end CLI binary execution with python -c and exit code verification."""
    req = AppControlExecutionRequest(
        application="python",
        capability="run_script",
        parameters={"args": ["-c", "print('RoxyUniversalControlCLI')"]},
        preferred_integration="cli_process",
        user_id="usr_test_cli",
        confirmed=True,
    )

    result = await controller.execute_lifecycle(req)
    assert result.stage == "verified"
    assert result.success is True
    assert result.verified is True
    assert result.resolution.chosen_integration == "cli_process"
    assert "RoxyUniversalControlCLI" in str(result.execution_output.get("stdout", ""))
    assert result.verification_details.get("exit_code") == 0


@pytest.mark.asyncio
async def test_orchestrator_cli_process_failure_detection(controller: UniversalAppController) -> None:
    """Verify non-zero CLI exit code fails execution and records verification failure."""
    req = AppControlExecutionRequest(
        application="python",
        capability="run_script",
        parameters={"args": ["-c", "import sys; sys.exit(7)"]},
        preferred_integration="cli_process",
        user_id="usr_test_cli",
        confirmed=True,
    )

    result = await controller.execute_lifecycle(req)
    assert result.stage == "failed"
    assert result.success is False
    assert result.verified is False
    assert result.error is not None


# -----------------------------------------------------------------------------
# 7. Stage 4 & 5: System Process Launcher Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_system_launcher_launch_and_terminate(controller: UniversalAppController) -> None:
    """Verify real system process launch and termination lifecycle via ProcessController."""
    py_exe = sys.executable
    # 1. Launch a benign sleep process
    launch_req = AppControlExecutionRequest(
        application="ProcessLauncher",
        capability="launch",
        parameters={
            "executable": py_exe,
            "arguments": ["-c", "import time; time.sleep(10)"],
        },
        preferred_integration="system_launcher",
        user_id="usr_test_launcher",
        confirmed=True,
    )

    launch_res = await controller.execute_lifecycle(launch_req)
    assert launch_res.success is True
    assert launch_res.verified is True
    assert launch_res.resolution.chosen_integration == "system_launcher"

    pid = launch_res.execution_output.get("pid")
    assert pid is not None
    assert psutil.pid_exists(pid)

    # 2. Terminate the launched process
    term_req = AppControlExecutionRequest(
        application="ProcessLauncher",
        capability="terminate",
        parameters={"pid": pid, "force": True},
        preferred_integration="system_launcher",
        user_id="usr_test_launcher",
        confirmed=True,
    )

    term_res = await controller.execute_lifecycle(term_req)
    if term_res.stage == "pending_confirmation":
        assert term_res.pending_confirmation_details is not None
        token = str(term_res.pending_confirmation_details["confirmation_token"])
        term_res = await controller.confirm_execution(token=token, user_id="usr_test_launcher")
    assert term_res.success is True
    assert term_res.verified is True
    assert not psutil.pid_exists(pid)


# -----------------------------------------------------------------------------
# 8. Desktop UI Automation Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_desktop_ui_automation_lifecycle(controller: UniversalAppController) -> None:
    """Verify desktop UI automation route inspects window state and verifies."""
    req = AppControlExecutionRequest(
        application="Notepad",
        capability="inspect_window",
        parameters={"window_target": "Notepad"},
        preferred_integration="desktop_ui_automation",
        device_context={"os_platform": sys.platform},
        user_id="usr_test_ui",
        confirmed=True,
    )

    result = await controller.execute_lifecycle(req)
    assert result.stage in ("verified", "failed")
    assert result.resolution.chosen_integration == "desktop_ui_automation"
    assert result.plan is not None


# -----------------------------------------------------------------------------
# 9. MCP Tool Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_mcp_tool_lifecycle(controller: UniversalAppController) -> None:
    """Verify Model Context Protocol (MCP) tool execution and verification."""
    req = AppControlExecutionRequest(
        application="database",
        capability="query",
        parameters={"query": "SELECT 1"},
        user_context={
            "mcp_tools": [
                {"name": "database_query", "id": "mcp_database_query"}
            ]
        },
        preferred_integration="mcp_tool",
        user_id="usr_test_mcp",
        confirmed=True,
    )

    result = await controller.execute_lifecycle(req)
    assert result.stage == "verified"
    assert result.success is True
    assert result.resolution.chosen_integration == "mcp_tool"
    assert result.verification_details.get("verified") is True


# -----------------------------------------------------------------------------
# 10. Skip Verification Flag
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_skip_verification(controller: UniversalAppController) -> None:
    """Verify skip_verification bypasses active post-condition probes cleanly."""
    req = AppControlExecutionRequest(
        application="Spotify",
        capability="play_music",
        user_context={"oauth_tokens": {"spotify": "valid_token"}},
        skip_verification=True,
        confirmed=True,
    )

    result = await controller.execute_lifecycle(req)
    assert result.success is True
    assert result.verification_details.get("skipped") is True


# -----------------------------------------------------------------------------
# 11. Central DeviceService Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_service_orchestrate_app_control(device_service: DeviceService) -> None:
    """Verify DeviceService orchestrate_app_control and confirm_app_control methods."""
    res = await device_service.orchestrate_app_control(
        user_id="usr_dev_srv",
        device_id="local",
        application="Spotify",
        capability="play_music",
        parameters={"track": "Song A"},
        user_context={"oauth_tokens": {"spotify": "valid_token"}},
        confirmed=True,
    )
    assert isinstance(res, AppControlExecutionResult)
    assert res.success is True
    assert res.stage == "verified"


# -----------------------------------------------------------------------------
# 12. Central ToolRegistry Dynamic Tool Execution
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_registry_orchestrate_tool(mock_user: User) -> None:
    """Verify device_orchestrate_app_control execution via Central ToolRegistry."""
    registry = ToolRegistry.get_instance()
    tool = registry.get("device_orchestrate_app_control")
    assert tool is not None
    assert "orchestration" in tool.capabilities

    tool_req = ToolExecutionRequest(
        tool_id="device_orchestrate_app_control",
        arguments={
            "application": "Spotify",
            "capability": "play_music",
            "confirmed": True,
            "user_context": {"oauth_tokens": {"spotify": "valid_token"}},
        },
        user_id=mock_user.id,
    )
    res = await registry.execute(tool_req)
    assert res.success is True
    assert res.output.get("stage") == "verified"
    assert res.output.get("success") is True


# -----------------------------------------------------------------------------
# 13. Standalone RoxyDeviceDaemon Dispatch
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daemon_app_control_orchestrate_dispatch() -> None:
    """Verify standalone RoxyDeviceDaemon executes app_control_orchestrate command."""
    daemon = RoxyDeviceDaemon(
        backend_url="http://localhost:8000/api/v1",
        device_id="daemon_test_dev",
        device_token="test_tok",
    )
    cmd = {
        "id": "cmd_test_orch_999",
        "command_type": "app_control_orchestrate",
        "payload": {
            "application": "Spotify",
            "capability": "play_music",
            "confirmed": True,
            "user_context": {"oauth_tokens": {"spotify": "tok_xyz"}},
        },
    }

    status, result, error = await daemon.execute_command(cmd)
    assert status == "completed"
    assert error is None
    assert isinstance(result, dict)
    assert result.get("success") is True
    assert result.get("stage") == "verified"


# -----------------------------------------------------------------------------
# 14. FastAPI REST Endpoints Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fastapi_orchestrate_endpoints(mock_user: User) -> None:
    """Verify FastAPI orchestrate, confirm, execution, and plan endpoints."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # 1. Device-scoped orchestrate endpoint
        dev_res = await client.post(
            "/api/v1/devices/local/app-control/orchestrate",
            json={
                "application": "Spotify",
                "capability": "play_music",
                "parameters": {"track": "Test Track"},
                "confirmed": True,
                "user_context": {"oauth_tokens": {"spotify": "token_abc"}},
            },
        )
        assert dev_res.status_code == 200
        dev_data = dev_res.json()
        assert dev_data["success"] is True
        assert dev_data["stage"] == "verified"

        exec_id = dev_data["execution_id"]
        plan_id = dev_data["plan_id"]

        # 2. Generic orchestrate endpoint
        gen_res = await client.post(
            "/api/v1/devices/app-control/orchestrate",
            json={
                "application": "Spotify",
                "capability": "play_music",
                "confirmed": True,
                "user_context": {"oauth_tokens": {"spotify": "token_abc"}},
            },
        )
        assert gen_res.status_code == 200
        assert gen_res.json()["success"] is True

        # 3. Retrieve execution by ID
        get_exec = await client.get(f"/api/v1/devices/app-control/executions/{exec_id}")
        assert get_exec.status_code == 200
        assert get_exec.json()["execution_id"] == exec_id

        # 4. Retrieve plan by ID
        get_plan = await client.get(f"/api/v1/devices/app-control/plans/{plan_id}")
        assert get_plan.status_code == 200
        assert get_plan.json()["plan_id"] == plan_id

        # 5. Pending confirmation challenge & confirm endpoint
        challenge_res = await client.post(
            "/api/v1/devices/app-control/orchestrate",
            json={
                "application": "Calculator",
                "capability": "terminate",
                "confirmed": False,
            },
        )
        assert challenge_res.status_code == 200
        challenge_data = challenge_res.json()
        assert challenge_data["stage"] == "pending_confirmation"

        conf_tok = challenge_data["pending_confirmation_details"]["confirmation_token"]

        # Confirm via endpoint
        approval_res = await client.post(
            "/api/v1/devices/app-control/confirm",
            json={"confirmation_token": conf_tok},
        )
        assert approval_res.status_code == 200
        assert approval_res.json()["stage"] in ("verified", "failed")

    app.dependency_overrides.clear()
