"""Comprehensive Automated Test Suite for Phase 7: Dynamic Capability Discovery Engine.

Validates:
1. Semantic Action Risk Categorization (LOW, MEDIUM, HIGH, CRITICAL).
2. Executable/CLI Introspection:
   - Binary resolution in PATH and filesystem.
   - Robust help/options/subcommands parsing.
   - Real OS binary interrogation (e.g. Python CLI).
3. Protocol Probing:
   - UI automation window presence.
   - MCP local configuration interrogation.
   - HTTP/REST local port and OpenAPI probing.
4. Dynamic Schema Generation:
   - Synthesis of compliant AgentTool definitions from parsed subcommands.
   - Correct JSONSchema generation for arguments.
   - Target-scoped permission and confirmation gate assignments.
5. Live Action Verification (Zero Simulation):
   - Non-destructive probe execution (--version / dry-run).
   - Execution latency metrics and evidence capture.
   - Honest failure propagation for broken binaries.
6. Central ToolRegistry Dynamic Registration & Safe Execution:
   - Dynamic registration of synthesized tools.
   - Safe subprocess execution with parameter binding and stdout/stderr capture.
7. DeviceService & FastAPI REST Router Integration:
   - Service discovery pipeline and DB catalog capability merging.
   - FastAPI endpoints for discovery, metadata lookup, and live action execution.
8. Standalone RoxyDeviceDaemon Dispatch:
   - app_discover_capabilities and app_execute_action command queue handling.
"""

from __future__ import annotations

import os
import shutil
import sys
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.capability_engine import (
    CLIIntrospector,
    DynamicCapabilityDiscoveryEngine,
    DynamicSchemaGenerator,
    LiveActionVerifier,
    ProtocolProber,
    assess_action_risk,
)
from app.device.daemon import RoxyDeviceDaemon
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    AgentTool,
    RiskLevel,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolSource,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_user() -> User:
    """Mock authenticated user."""
    return User(
        id="user_dynamic_caps_test",
        email="capabilities@roxy.internal",
    )


# -----------------------------------------------------------------------------
# 1. Semantic Action Risk Categorization
# -----------------------------------------------------------------------------

def test_assess_action_risk_heuristics() -> None:
    """Verify semantic verbs accurately determine risk level and confirmation requirements."""
    # Critical risk
    assert assess_action_risk("delete", "Delete repository") == RiskLevel.CRITICAL
    assert assess_action_risk("rm", "Remove files permanently") == RiskLevel.CRITICAL
    assert assess_action_risk("purge", "Purge all records") == RiskLevel.CRITICAL
    assert assess_action_risk("kill", "Kill active process") == RiskLevel.CRITICAL

    # High risk
    assert assess_action_risk("commit", "Commit changes to tree") == RiskLevel.HIGH
    assert assess_action_risk("push", "Push commits to remote") == RiskLevel.HIGH
    assert assess_action_risk("update", "Update server config") == RiskLevel.HIGH
    assert assess_action_risk("deploy", "Deploy application") == RiskLevel.HIGH

    # Medium risk
    assert assess_action_risk("install", "Install package") == RiskLevel.MEDIUM
    assert assess_action_risk("pull", "Pull latest changes") == RiskLevel.MEDIUM
    assert assess_action_risk("exec", "Run script") == RiskLevel.MEDIUM

    # Low risk
    assert assess_action_risk("status", "Show working tree status") == RiskLevel.LOW
    assert assess_action_risk("list", "List installed extensions") == RiskLevel.LOW
    assert assess_action_risk("version", "Print version info") == RiskLevel.LOW
    assert assess_action_risk("help", "Display help guide") == RiskLevel.LOW


# -----------------------------------------------------------------------------
# 2. Executable / CLI Introspection
# -----------------------------------------------------------------------------

def test_cli_introspector_resolve_binary() -> None:
    """Verify binary resolution finds real system binaries and rejects non-existent paths."""
    py_bin = CLIIntrospector.resolve_binary("python")
    assert py_bin is not None
    assert os.path.exists(py_bin)

    # Rejection of nonexistent
    assert CLIIntrospector.resolve_binary("NonExistent_Binary_XYZ_99999") is None


def test_cli_introspector_parse_help_text() -> None:
    """Verify regex-based parsing of standard CLI help text."""
    sample_help = """
Usage: mytool [options] <command> [<args>]

A sample automation CLI utility.

Options:
  -v, --version           Print version information
  -h, --help              Show help information
  -o, --output <file>     Write results to output file
  --timeout <sec>         Network timeout in seconds

Commands:
  status     Show the current system status
  build      Compile the project assets
  deploy     Deploy build to production
  delete     Remove resources permanently
"""
    parsed = CLIIntrospector.parse_help_text(sample_help)

    # Validate subcommands
    subcmds = {c["name"]: c["description"] for c in parsed["subcommands"]}
    assert "status" in subcmds
    assert "build" in subcmds
    assert "deploy" in subcmds
    assert "delete" in subcmds
    assert "current system status" in subcmds["status"]

    # Validate options
    opts = {o["flag"]: o for o in parsed["options"]}
    assert "--version" in opts
    assert "--output" in opts
    assert opts["--output"]["type"] == "string"
    assert opts["--version"]["type"] == "boolean"


def test_cli_introspector_real_python_interrogation() -> None:
    """Introspect real Python interpreter on host."""
    res = CLIIntrospector.introspect("python")
    assert res["available"] is True
    assert "binary_path" in res
    assert "Python 3." in res["version"]
    assert isinstance(res["options"], list)


# -----------------------------------------------------------------------------
# 3. Protocol Probing
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_protocol_prober_http_mock() -> None:
    """Verify HTTP protocol probing against mock OpenAPI service."""
    mock_openapi = {
        "info": {"title": "Local Mock Service", "version": "1.0.0"},
        "paths": {
            "/api/generate": {"post": {"summary": "Generate text"}},
            "/api/models": {"get": {"summary": "List available models"}},
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_openapi

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = await ProtocolProber.probe_http_service(port=11434, timeout_sec=0.5)
        assert res is not None
        assert res["protocol"] == "rest"
        assert res["has_openapi"] is True
        assert "/api/generate" in res["endpoints"]
        assert res["title"] == "Local Mock Service"


def test_protocol_prober_ui_window() -> None:
    """Verify UI automation probing checks native window state."""
    # Active screen or non-existent app
    res = ProtocolProber.probe_ui_automation("GhostAppNonExistent_XYZ")
    assert isinstance(res, dict)
    assert res["has_native_window"] is False


# -----------------------------------------------------------------------------
# 4. Dynamic Schema Generation
# -----------------------------------------------------------------------------

def test_dynamic_schema_generator() -> None:
    """Verify synthesis of AgentTool definitions from parsed subcommands."""
    subcmd = {
        "name": "commit",
        "description": "Record changes to the repository",
        "options": [
            {"name": "message", "flag": "--message", "type": "string", "description": "Commit message"},
            {"name": "all", "flag": "--all", "type": "boolean", "description": "Stage all modified files"},
        ],
    }

    tool = DynamicSchemaGenerator.build_cli_subcommand_tool(
        app_name="git",
        binary_path=r"C:\Program Files\Git\bin\git.exe",
        subcmd=subcmd,
    )

    assert isinstance(tool, AgentTool)
    assert tool.id == "app_git_commit"
    assert tool.name == "git_commit"
    assert tool.source == ToolSource.DEVICE
    assert tool.risk_level == RiskLevel.HIGH
    assert tool.requires_confirmation is True
    assert "app:git:commit" in tool.permissions

    # JSONSchema validation
    schema = tool.input_schema
    assert schema["type"] == "object"
    assert "args" in schema["properties"]
    assert "message" in schema["properties"]
    assert schema["properties"]["message"]["type"] == "string"
    assert "all" in schema["properties"]
    assert schema["properties"]["all"]["type"] == "boolean"


# -----------------------------------------------------------------------------
# 5. Live Action Verification (Zero Simulation)
# -----------------------------------------------------------------------------

def test_live_action_verifier_cli() -> None:
    """Verify live action verifier executes real non-destructive probes."""
    py_bin = shutil.which("python") or sys.executable

    # Real verification against Python interpreter
    res = LiveActionVerifier.verify_cli_capability(py_bin)
    assert res["verified"] is True
    assert res["latency_ms"] >= 0
    assert res["exit_code"] == 0
    assert "Python" in res["evidence"]["output_preview"]

    # Honest failure on non-existent binary
    bad_res = LiveActionVerifier.verify_cli_capability("nonexistent_binary_xyz_123")
    assert bad_res["verified"] is False
    assert bad_res["error"] is not None


# -----------------------------------------------------------------------------
# 6. Dynamic Capability Discovery Engine End-to-End
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dynamic_capability_engine_discovery_pipeline() -> None:
    """Execute end-to-end capability discovery pipeline against Python CLI."""
    res = await DynamicCapabilityDiscoveryEngine.discover_app_capabilities(
        app_name="python",
        probe_live=True,
    )

    assert res["app_name"] == "python"
    assert res["executable_path"] is not None
    assert "probes" in res
    assert "capabilities" in res
    assert res["total_discovered"] >= 0
    assert len(res["generated_tools"]) >= 0


# -----------------------------------------------------------------------------
# 7. Central ToolRegistry Dynamic Registration & Safe Execution
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_registry_dynamic_tool_execution(mock_user: User) -> None:
    """Verify dynamically registered tools execute safely via ToolRegistry."""
    registry = ToolRegistry.get_instance()
    py_bin = shutil.which("python") or sys.executable

    # Define tool for python version check
    tool = AgentTool(
        id="app_py_version_test",
        name="py_version_test",
        description="Check python version dynamically",
        source=ToolSource.DEVICE,
        capabilities=["app", "cli", "python"],
        permissions=["app:python:version", "app:execute"],
        risk_level=RiskLevel.LOW,
        requires_confirmation=False,
        input_schema={
            "type": "object",
            "properties": {"version": {"type": "boolean", "default": True}},
        },
    )

    count = DynamicCapabilityDiscoveryEngine.register_in_tool_registry(
        tools=[tool],
        binary_path=py_bin,
        registry=registry,
    )
    assert count == 1

    # Execute through ToolRegistry boundary
    req = ToolExecutionRequest(
        tool_id="app_py_version_test",
        arguments={"version": True},
        user_id=mock_user.id,
    )
    result = await registry.execute(req)

    assert result.status == ToolExecutionStatus.COMPLETED
    assert result.output["success"] is True
    assert result.output["exit_code"] == 0
    assert "Python" in (result.output.get("stdout") or result.output.get("stderr") or "")


# -----------------------------------------------------------------------------
# 8. Service Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_service_capability_discovery(mock_user: User) -> None:
    """Verify DeviceService.discover_app_capabilities and execute_app_action."""
    service = DeviceService.get_instance()
    dev = await service.get_or_create_local_device(mock_user.id)

    # 1. Discover capabilities
    discovery = await service.discover_app_capabilities(
        user_id=mock_user.id,
        device_id=dev["id"],
        app_id_or_name="python",
        probe_live=True,
        register_tools=True,
    )

    assert discovery["app_name"] == "python"
    assert "capabilities" in discovery
    assert "total_discovered" in discovery

    # 2. Execute app action
    exec_res = await service.execute_app_action(
        user_id=mock_user.id,
        device_id=dev["id"],
        app_id_or_name="python",
        action_name="version",
        parameters={"version": True},
    )

    assert isinstance(exec_res, dict)
    assert exec_res["success"] is True
    assert exec_res["exit_code"] == 0


# -----------------------------------------------------------------------------
# 9. FastAPI REST Router Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_capability_discovery_api_router() -> None:
    """Verify REST API routes for dynamic capability discovery and execution."""
    app.dependency_overrides[get_current_user] = lambda: User(
        id="user_api_caps_test",
        email="apicaps@roxy.internal",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Discover capabilities endpoint
        disc_resp = await client.post(
            "/api/v1/devices/local/apps/python/capabilities/discover",
            json={"probe_live": True, "register_tools": True},
        )
        assert disc_resp.status_code == 200
        disc_data = disc_resp.json()
        assert disc_data["app_name"] == "python"
        assert "capabilities" in disc_data

        # 2. Execute action endpoint
        exec_resp = await client.post(
            "/api/v1/devices/local/apps/python/actions/version/execute",
            json={"parameters": {"version": True}},
        )
        assert exec_resp.status_code == 200
        exec_data = exec_resp.json()
        assert exec_data["success"] is True
        assert exec_data["exit_code"] == 0

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 10. Standalone RoxyDeviceDaemon Capability Commands
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daemon_capability_commands_dispatch() -> None:
    """Verify daemon executes app_discover_capabilities and app_execute_action commands."""
    daemon = RoxyDeviceDaemon(
        backend_url="http://127.0.0.1:8000",
        device_id="test_daemon_phase7",
    )

    # Command 1: app_discover_capabilities
    status_disc, payload_disc, err_disc = await daemon.execute_command({
        "command_type": "app_discover_capabilities",
        "payload": {"app_name": "python", "probe_live": True},
    })
    assert status_disc == "completed"
    assert payload_disc is not None
    assert payload_disc["app_name"] == "python"
    assert err_disc is None

    # Command 2: app_execute_action
    status_exec, payload_exec, err_exec = await daemon.execute_command({
        "command_type": "app_execute_action",
        "payload": {
            "app_name": "python",
            "action_name": "version",
            "parameters": {"version": True},
        },
    })
    assert status_exec == "completed"
    assert payload_exec is not None
    assert payload_exec["success"] is True
    assert err_exec is None
