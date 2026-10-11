"""Comprehensive Automated Test Suite for Phase 8: Integration Resolution Engine.

Under the Zero Simulation doctrine:
Validates the 8-tier decision hierarchy:
1. Cloud / SaaS Connector & API (Highest reliability, structured, robust OAuth)
2. Model Context Protocol (MCP) Tool (Standardized tool protocol)
3. CLI Subprocess / Local REST (Native high-speed deterministic binary execution)
4. Desktop UI Automation (Accessible Windows UIA, macOS Accessibility, Linux AT-SPI)
5. Mobile Bridge (Android ADB / iOS Instruments UI automation)
6. System Process Launcher (Application lifecycle start, stop, restart, focus)
7. Browser Web Subsystem (Web applications and browser sessions)
8. Honest Unsupported (Zero hallucination fallback with remediation guidance)

Also tests:
- Caller preference / override
- Target-scoped permission formatting (Phase 2 compliance)
- Semantic risk and confirmation gates
- ToolRegistry dynamic tool registration and invocation
- DeviceService service layer orchestration
- RoxyDeviceDaemon command dispatch
- FastAPI REST endpoints (/devices/{device_id}/resolve-integration and /devices/resolve-integration)
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.models import User
from app.device.integration_resolver import (
    APP_SYNONYMS,
    KNOWN_CLI_TOOLS,
    KNOWN_CONNECTOR_CATALOG,
    IntegrationResolver,
)
from app.device.schemas import (
    IntegrationCandidateModel,
    IntegrationResolutionRequest,
    IntegrationResolutionResult,
)
from app.device.service import DeviceService
from app.tools.registry import ToolRegistry


# =============================================================================
# Unit Tests: Normalization & Basic Resolver Logic
# =============================================================================

def test_normalization_app_and_capabilities() -> None:
    """Verify application name canonicalization and capability verb-noun normalization."""
    assert IntegrationResolver.normalize_app_name("Spotify Music") == "spotify"
    assert IntegrationResolver.normalize_app_name("  Gmail  ") == "google"
    assert IntegrationResolver.normalize_app_name("gh") == "github"
    assert IntegrationResolver.normalize_app_name("Google-Drive") == "google"
    assert IntegrationResolver.normalize_app_name("Unknown App!") == "unknown_app"

    assert IntegrationResolver.normalize_capability("play-music") == "play_music"
    assert IntegrationResolver.normalize_capability("  Send  Email ") == "send_email"
    assert IntegrationResolver.normalize_capability("terminate_process!") == "terminate_process"


# =============================================================================
# Unit Tests: Tier 1 - Cloud / SaaS Connector & API
# =============================================================================

def test_resolve_cloud_connector_active_oauth() -> None:
    """Test Spotify with active OAuth token resolves to cloud_connector with >= 0.95 confidence."""
    req = IntegrationResolutionRequest(
        application="Spotify",
        requested_capability="play_music",
        device={"os_platform": "windows"},
        user_context={
            "active_connectors": ["spotify"],
            "oauth_tokens": {"spotify": {"access_token": "mock_token"}},
        },
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "cloud_connector"
    assert res.integration == "cloud_connector"
    assert res.confidence >= 0.95
    assert res.execution_method == "connector_api"
    assert res.verification_method == "api_status_check"
    assert res.handler_target == "spotify_play_track"
    assert "app:spotify:play_music" in res.required_permission
    assert res.risk in ("LOW", "MEDIUM")


def test_resolve_cloud_connector_catalog_without_active_oauth() -> None:
    """Test Spotify known in catalog without active credentials evaluates candidate with lower confidence."""
    req = IntegrationResolutionRequest(
        application="Spotify",
        requested_capability="play_music",
        device={"os_platform": "windows", "open_windows": []},
        user_context={},
    )
    res = IntegrationResolver.resolve(req)

    # Cloud connector is evaluated with confidence 0.55
    connector_cand = next((c for c in res.candidates if c.integration == "cloud_connector"), None)
    assert connector_cand is not None
    assert connector_cand.confidence == 0.55
    assert "requires authentication" in connector_cand.description


def test_resolve_slack_connector_with_token() -> None:
    """Test Slack with active connector credentials."""
    req = IntegrationResolutionRequest(
        application="Slack",
        requested_capability="send_message",
        device={"os_platform": "darwin"},
        user_context={"active_connectors": ["slack"]},
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "cloud_connector"
    assert res.execution_method == "connector_api"
    assert res.handler_target == "slack_post_message"
    assert res.confidence >= 0.95


# =============================================================================
# Unit Tests: Tier 2 - Model Context Protocol (MCP) Tool
# =============================================================================

def test_resolve_mcp_tool_direct_match() -> None:
    """Test resolution to registered MCP tool in user context."""
    req = IntegrationResolutionRequest(
        application="postgres",
        requested_capability="query_database",
        device={"os_platform": "linux"},
        user_context={
            "mcp_tools": [
                {"name": "postgres_query_database", "description": "Execute SQL queries"},
            ],
        },
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "mcp_tool"
    assert res.confidence >= 0.90
    assert res.execution_method == "mcp_call"
    assert res.verification_method == "mcp_result_schema_validation"
    assert res.handler_target == "postgres_query_database"


def test_resolve_mcp_server_domain_match() -> None:
    """Test resolution to active MCP server registered for application domain."""
    req = IntegrationResolutionRequest(
        application="sqlite",
        requested_capability="execute_query",
        device={"os_platform": "windows"},
        user_context={
            "mcp_servers": ["sqlite-db-server"],
        },
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "mcp_tool"
    assert res.confidence >= 0.85
    assert res.execution_method == "mcp_call"
    assert "sqlite-db-server" in (res.handler_target or "")


# =============================================================================
# Unit Tests: Tier 3 - CLI Subprocess / Local Binary
# =============================================================================

def test_resolve_cli_process_known_tool() -> None:
    """Test resolution of standard CLI tool (git status / git commit)."""
    with patch("shutil.which", return_value="C:\\Program Files\\Git\\cmd\\git.exe"):
        req = IntegrationResolutionRequest(
            application="git",
            requested_capability="commit",
            device={"os_platform": "windows"},
            user_context={},
        )
        res = IntegrationResolver.resolve(req)

        assert res.success is True
        assert res.chosen_integration == "cli_process"
        assert res.confidence >= 0.85
        assert res.execution_method == "cli_exec"
        assert res.verification_method == "process_exit_code_and_output"
        assert res.required_permission == "cli:git:commit"


def test_resolve_cli_process_docker() -> None:
    """Test resolution of Docker CLI tool."""
    with patch("shutil.which", return_value="/usr/bin/docker"):
        req = IntegrationResolutionRequest(
            application="docker",
            requested_capability="ps",
            device={"os_platform": "linux"},
            user_context={},
        )
        res = IntegrationResolver.resolve(req)

        assert res.success is True
        assert res.chosen_integration == "cli_process"
        assert res.execution_method == "cli_exec"


# =============================================================================
# Unit Tests: Tier 4 - Native Desktop UI Automation
# =============================================================================

def test_resolve_desktop_ui_when_window_open() -> None:
    """Test that open window presence routes UI action to desktop_ui_automation."""
    req = IntegrationResolutionRequest(
        application="Notepad",
        requested_capability="type_text",
        device={
            "os_platform": "windows",
            "open_windows": ["Untitled - Notepad", "Calculator"],
            "foreground_window": "Untitled - Notepad",
        },
        user_context={},
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "desktop_ui_automation"
    assert res.confidence >= 0.80
    assert res.execution_method == "desktop_ui"
    assert res.verification_method == "accessibility_tree_match"


def test_resolve_desktop_ui_not_on_mobile() -> None:
    """Verify desktop UI automation is never selected on mobile operating systems."""
    req = IntegrationResolutionRequest(
        application="Notes",
        requested_capability="click_button",
        device={"os_platform": "android"},
        user_context={},
    )
    res = IntegrationResolver.resolve(req)
    assert res.chosen_integration != "desktop_ui_automation"


# =============================================================================
# Unit Tests: Tier 5 - System Process Launcher
# =============================================================================

def test_resolve_system_launcher_lifecycle_actions() -> None:
    """Test launch and terminate actions resolve to system_launcher."""
    # Launch
    req_launch = IntegrationResolutionRequest(
        application="Calculator",
        requested_capability="launch",
        device={"os_platform": "windows", "installed_apps": ["Calculator"]},
        user_context={},
    )
    res_launch = IntegrationResolver.resolve(req_launch)
    assert res_launch.success is True
    assert res_launch.chosen_integration == "system_launcher"
    assert res_launch.execution_method == "process_launch"
    assert res_launch.verification_method == "process_pid_and_window_presence"
    assert res_launch.required_permission == "app:calculator:launch"

    # Terminate (High Risk)
    req_term = IntegrationResolutionRequest(
        application="Firefox",
        requested_capability="terminate",
        device={"os_platform": "windows", "installed_apps": ["Firefox"]},
        user_context={},
    )
    res_term = IntegrationResolver.resolve(req_term)
    assert res_term.success is True
    assert res_term.chosen_integration == "system_launcher"
    assert res_term.risk == "HIGH"
    assert res_term.requires_confirmation is True


# =============================================================================
# Unit Tests: Tier 6 - Mobile Bridge
# =============================================================================

def test_resolve_mobile_bridge_android() -> None:
    """Test Android target resolves to mobile_bridge."""
    req = IntegrationResolutionRequest(
        application="com.whatsapp",
        requested_capability="open_chat",
        device={"os_platform": "android", "device_id": "pixel_7_pro"},
        user_context={},
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "mobile_bridge"
    assert res.confidence >= 0.80
    assert res.execution_method == "mobile_ui"
    assert res.verification_method == "mobile_ui_dump_match"
    assert "mobile_automation" in res.required_permission


def test_resolve_mobile_bridge_ios() -> None:
    """Test iOS target resolves to mobile_bridge."""
    req = IntegrationResolutionRequest(
        application="com.apple.camera",
        requested_capability="capture_photo",
        device={"os_platform": "ios", "device_type": "mobile", "device_id": "iphone_15"},
        user_context={},
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "mobile_bridge"
    assert res.execution_method == "mobile_ui"


# =============================================================================
# Unit Tests: Tier 7 - Browser Web Subsystem
# =============================================================================

def test_resolve_browser_automation_url() -> None:
    """Test web URLs resolve to browser_automation."""
    req = IntegrationResolutionRequest(
        application="https://app.slack.com/client/T123/C456",
        requested_capability="read_feed",
        device={"os_platform": "windows"},
        user_context={},
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "browser_automation"
    assert res.execution_method == "browser_session"
    assert res.verification_method == "dom_element_state_probe"


# =============================================================================
# Unit Tests: Tier 8 - Unsupported Fallback & Overrides
# =============================================================================

def test_resolve_unsupported_fallback() -> None:
    """Test unknown application with no API, MCP, CLI, or UI routes produces honest fallback."""
    with patch("shutil.which", return_value=None):
        req = IntegrationResolutionRequest(
            application="com.fictional.proprietary.tool.xyz",
            requested_capability="teleport_data",
            device={"os_platform": "windows", "open_windows": [], "installed_apps": []},
            user_context={},
        )
        res = IntegrationResolver.resolve(req)

        assert res.success is False
        assert res.chosen_integration == "unsupported"
        assert res.confidence == 0.0
        assert res.execution_method == "none"
        assert res.verification_method == "none"
        assert "No integration route found" in (res.recommended_action or "")


def test_resolve_caller_preferred_override() -> None:
    """Test caller preference overrides default priority if candidate is valid."""
    # When both system launcher and desktop UI are candidates, prefer desktop UI
    req = IntegrationResolutionRequest(
        application="VLC",
        requested_capability="launch",
        preferred_integration="desktop_ui_automation",
        device={
            "os_platform": "windows",
            "installed_apps": ["VLC"],
            "open_windows": ["VLC media player"],
        },
        user_context={},
    )
    res = IntegrationResolver.resolve(req)

    assert res.success is True
    assert res.chosen_integration == "desktop_ui_automation"
    assert res.diagnostics.get("override_applied") == "desktop_ui_automation"


# =============================================================================
# Unit Tests: DeviceService & ToolRegistry Integration
# =============================================================================

@pytest.mark.asyncio
async def test_device_service_resolve_integration() -> None:
    """Test DeviceService.resolve_integration method."""
    svc = DeviceService.get_instance()
    res = await svc.resolve_integration(
        user_id="test_user_p8",
        device_id="local",
        application="Spotify",
        requested_capability="play_music",
        user_context={"active_connectors": ["spotify"]},
    )

    assert isinstance(res, IntegrationResolutionResult)
    assert res.success is True
    assert res.chosen_integration == "cloud_connector"
    assert res.confidence >= 0.95


@pytest.mark.asyncio
async def test_tool_registry_device_resolve_integration_tool() -> None:
    """Test that device_resolve_integration tool is registered and callable via ToolRegistry."""
    svc = DeviceService.get_instance()
    reg = ToolRegistry.get_instance()

    tool = reg.get("device_resolve_integration")
    assert tool is not None
    assert tool.source.value == "device"
    assert "integration" in tool.capabilities

    # Execute tool via registry
    handler = reg._handlers.get("device_resolve_integration")
    assert handler is not None

    tool_res = await handler(
        application="git",
        requested_capability="commit",
        user_id="test_user_p8",
    )

    assert isinstance(tool_res, dict)
    assert tool_res["success"] is True
    assert tool_res["chosen_integration"] in ("cli_process", "system_launcher")
    assert "execution_method" in tool_res


# =============================================================================
# Unit Tests: Standalone Daemon Command Handling
# =============================================================================

@pytest.mark.asyncio
async def test_daemon_execute_command_resolve_integration() -> None:
    """Test RoxyDeviceDaemon handles cmd_type='resolve_integration'."""
    from app.device.daemon import RoxyDeviceDaemon

    daemon = RoxyDeviceDaemon(
        backend_url="http://localhost:8000/api/v1",
        device_id="daemon_test_dev",
        device_token="mock_token",
    )

    cmd = {
        "id": "cmd_res_1",
        "command_type": "resolve_integration",
        "payload": {
            "application": "Slack",
            "requested_capability": "send_message",
            "user_context": {"active_connectors": ["slack"]},
        },
    }

    status, result, error = await daemon.execute_command(cmd)

    assert status == "completed"
    assert error is None
    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["chosen_integration"] == "cloud_connector"


# =============================================================================
# Integration Tests: FastAPI REST Endpoints
# =============================================================================

@pytest.mark.asyncio
async def test_fastapi_resolve_integration_device_endpoint() -> None:
    """Test POST /api/v1/devices/{device_id}/resolve-integration endpoint."""
    from app.auth.dependencies import get_current_user
    from app.main import app

    mock_user = User(
        id="usr_p8_test",
        email="p8@example.com",
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        payload = {
            "application": "Spotify",
            "requested_capability": "play_music",
            "user_context": {"active_connectors": ["spotify"]},
        }
        resp = await client.post("/api/v1/devices/local/resolve-integration", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["chosen_integration"] == "cloud_connector"
        assert data["confidence"] >= 0.95
        assert data["execution_method"] == "connector_api"
        assert "candidates" in data

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fastapi_resolve_integration_generic_endpoint() -> None:
    """Test POST /api/v1/devices/resolve-integration generic endpoint."""
    from app.auth.dependencies import get_current_user
    from app.main import app

    mock_user = User(
        id="usr_p8_test",
        email="p8@example.com",
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        payload = {
            "application": "Unknown Proprietary Enterprise Tool",
            "requested_capability": "magic_sync",
        }
        resp = await client.post("/api/v1/devices/resolve-integration", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["chosen_integration"] == "unsupported"
        assert data["confidence"] == 0.0

    app.dependency_overrides.clear()
