"""Phase 1 Security & Execution Hardening Verification Suite.

Tests:
1. MCP honest failure propagation (no simulated success, real stdio subprocess transport, timeouts).
2. Tool Registry execution-boundary permission enforcement (preventing direct bypass).
3. Safe application launch (preventing shell injection, directory traversal, shell=True removal).
4. Screenshot privacy (trusted local snapshots, zero external URL leakage).
5. Secret handling and sanitization (masking, encryption, recursive log scrubbing).
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import patch

import pytest

from app.actions.service import clear_in_memory_actions
from app.browser.service import BrowserService
from app.core.secrets import SecretStore, mask_secret, sanitize_data_for_logging
from app.device.service import DeviceService
from app.mcp.client import MCPClient
from app.mcp.schemas import MCPTransportType
from app.permissions.schemas import PermissionGrantCreate, PermissionPolicy
from app.permissions.service import PermissionService, clear_in_memory_grants
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    AgentTool,
    RiskLevel,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolSource,
)


@pytest.fixture(autouse=True)
def _reset_test_environment() -> None:
    clear_in_memory_grants()
    clear_in_memory_actions()


# =============================================================================
# 1. MCP Security & Honest Failure Tests
# =============================================================================


@pytest.mark.asyncio
async def test_mcp_client_unreachable_endpoint_propagates_honest_failure() -> None:
    """Verify that an unreachable MCP server returns an honest error and never 'Successfully executed...'."""
    client = MCPClient(
        name="Unreachable Server",
        transport=MCPTransportType.SSE,
        endpoint_url="http://127.0.0.1:59999/nonexistent-mcp",
    )

    # Handshake must fail honestly
    with pytest.raises(RuntimeError) as exc_info:
        await client.initialize()
    assert "Unreachable Server" in str(exc_info.value)
    assert "Successfully executed" not in str(exc_info.value)

    # Direct tool call must return honest isError=True
    call_res = await client.call_tool("read_data", {"query": "test"})
    assert call_res.get("isError") is True
    assert "Successfully executed" not in str(call_res.get("content", ""))
    assert str(call_res.get("error", {}).get("code")) in ("-32001", "-32002")


@pytest.mark.asyncio
async def test_mcp_client_timeout_handling() -> None:
    """Verify MCP timeout handling honestly marks retryable timeout error."""
    client = MCPClient(
        name="Timeout Server",
        transport=MCPTransportType.SSE,
        endpoint_url="http://localhost:8000/timeout",
    )

    async def mock_post(*args: Any, **kwargs: Any) -> Any:
        raise TimeoutError("Request timed out after deadline.")

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        res = await client._send_rpc("tools/call", {"name": "calc"})
        assert res.error is not None
        assert res.error.code == -32000
        assert "timed out" in res.error.message.lower()
        assert res.error.data.get("retryable") is True


@pytest.mark.asyncio
async def test_mcp_real_stdio_subprocess_transport() -> None:
    """Verify real stdio subprocess MCP transport with live child process speaking JSON-RPC."""
    # Run python script as stdio MCP server that speaks JSON-RPC 2.0
    python_script = """
import sys, json

for line in sys.stdin:
    if not line.strip():
        continue
    try:
        req = json.loads(line)
        method = req.get("method")
        msg_id = req.get("id")

        if method == "initialize":
            res = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": res}
        elif method == "tools/list":
            res = {"tools": [{"name": "echo", "description": "Echoes back input", "inputSchema": {"type": "object"}}]}
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": res}
        elif method == "tools/call":
            args = req.get("params", {}).get("arguments", {})
            res = {"content": [{"type": "text", "text": f"ECHO: {args.get('text', '')}"}], "isError": False}
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": res}
        else:
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}) + "\\n")
        sys.stdout.flush()
"""

    client = MCPClient(
        name="Live Stdio Subprocess Server",
        transport=MCPTransportType.STDIO,
        command=sys.executable,
        args=["-c", python_script],
    )

    try:
        # 1. Initialize
        init_data = await client.initialize()
        assert init_data.get("protocolVersion") == "2024-11-05"

        # 2. List tools
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo"

        # 3. Call tool
        call_res = await client.call_tool("echo", {"text": "Production Hardening"})
        assert call_res.get("isError") is False
        assert "ECHO: Production Hardening" in str(call_res.get("content"))
    finally:
        await client.close()


# =============================================================================
# 2. Tool Registry Permission Gate & Unified Contract Tests
# =============================================================================


@pytest.mark.asyncio
async def test_tool_registry_permission_gate_blocks_direct_sensitive_execution() -> None:
    """Verify that ToolRegistry.execute() cannot be bypassed when called directly on high-risk tools."""
    registry = ToolRegistry.get_instance()

    # Register a high-risk system tool
    sensitive_tool = AgentTool(
        id="test_format_disk",
        name="Format Disk",
        description="Destructive system disk format utility",
        source=ToolSource.SYSTEM,
        capabilities=["system", "storage"],
        risk_level=RiskLevel.CRITICAL,
        requires_confirmation=True,
    )

    executed = False

    async def _handler(**kwargs: Any) -> dict[str, Any]:
        nonlocal executed
        executed = True
        return {"status": "formatted"}

    registry.register(sensitive_tool, _handler)

    try:
        # Direct call without prior confirmation
        req = ToolExecutionRequest(
            tool_id="test_format_disk",
            arguments={"drive": "D:"},
            user_id="user_security_audit",
            bypass_confirmation=False,
        )

        res = await registry.execute(req)

        # Must be blocked at the execution boundary
        assert res.success is False
        assert res.status == ToolExecutionStatus.REQUIRES_CONFIRMATION
        assert res.error_details is not None
        assert res.error_details.code == "requires_confirmation"
        assert executed is False  # Handler must NEVER have executed

        # Now approve through Action Center / bypass_confirmation
        req_approved = ToolExecutionRequest(
            tool_id="test_format_disk",
            arguments={"drive": "D:"},
            user_id="user_security_audit",
            bypass_confirmation=True,  # Approved via Action Center
        )
        res_approved = await registry.execute(req_approved)
        assert res_approved.success is True
        assert res_approved.status == ToolExecutionStatus.COMPLETED
        assert executed is True
    finally:
        registry.unregister("test_format_disk")


@pytest.mark.asyncio
async def test_tool_registry_denies_explicitly_forbidden_tools() -> None:
    """Verify that an explicitly blocked tool policy (never_allow) rejects execution."""
    registry = ToolRegistry.get_instance()
    perm_service = PermissionService()

    tool = AgentTool(
        id="test_read_secrets",
        name="Read Secrets",
        description="Reads confidential secrets",
        source=ToolSource.SYSTEM,
        risk_level=RiskLevel.HIGH,
    )

    async def _handler(**kwargs: Any) -> str:
        return "secret_leaked"

    registry.register(tool, _handler)

    try:
        # Set policy to never_allow
        await perm_service.grant_permission(
            user_id="user_blocked",
            grant_in=PermissionGrantCreate(
                tool_id="test_read_secrets",
                permission="execute",
                policy=PermissionPolicy.NEVER_ALLOW,
            ),
        )

        req = ToolExecutionRequest(
            tool_id="test_read_secrets",
            arguments={},
            user_id="user_blocked",
        )
        res = await registry.execute(req)
        assert res.success is False
        assert res.status == ToolExecutionStatus.DENIED
        assert "never_allow" in (res.error or "")
    finally:
        registry.unregister("test_read_secrets")


@pytest.mark.asyncio
async def test_tool_registry_unauthenticated_call_rejected() -> None:
    """Verify that ToolRegistry.execute rejects calls with missing user_id."""
    registry = ToolRegistry.get_instance()
    tool = AgentTool(
        id="test_public_utility",
        name="Utility",
        description="Utility tool",
        source=ToolSource.SYSTEM,
        risk_level=RiskLevel.LOW,
    )
    async def _dummy_handler(**kw: Any) -> str:
        return "ok"

    registry.register(tool, _dummy_handler)

    try:
        req = ToolExecutionRequest(
            tool_id="test_public_utility",
            arguments={},
            user_id="",  # Missing
        )
        res = await registry.execute(req)
        assert res.success is False
        assert res.status == ToolExecutionStatus.DENIED
        assert res.error_details is not None
        assert res.error_details.code == "unauthenticated"
    finally:
        registry.unregister("test_public_utility")


# =============================================================================
# 3. Secure Application Launch & Shell Injection Prevention
# =============================================================================


@pytest.mark.asyncio
async def test_launch_app_blocks_shell_injection() -> None:
    """Verify that device launch_app rejects shell metacharacters and directory traversal."""
    device_service = DeviceService.get_instance()

    malicious_inputs = [
        "calc.exe & echo pwned",
        "notepad.exe | dir",
        "app; rm -rf /",
        "`whoami`.exe",
        "calc.exe $(whoami)",
        "test > output.txt",
        "../../windows/system32/cmd.exe",
    ]

    for bad_path in malicious_inputs:
        res = await device_service.launch_app(
            user_id="test_user",
            device_id="local_host",
            app_name_or_path=bad_path,
        )
        assert res["status"] == "failed"
        assert "Security Violation" in res.get("error", "")
        assert res.get("pid") is None


@pytest.mark.asyncio
async def test_launch_app_nonexistent_binary_fails_gracefully_without_shell() -> None:
    """Verify non-existent binary returns honest failed status and does not spawn shell."""
    device_service = DeviceService.get_instance()

    res = await device_service.launch_app(
        user_id="test_user",
        device_id="local_host",
        app_name_or_path="completely_fake_nonexistent_binary_xyz_123.exe",
    )
    assert res["status"] == "failed"
    assert res.get("pid") is None


# =============================================================================
# 4. Screenshot Privacy Tests
# =============================================================================


@pytest.mark.asyncio
async def test_browser_screenshot_privacy_no_external_leakage() -> None:
    """Verify screenshot preview capture uses trusted local snapshot and does not contact thum.io."""
    browser_service = BrowserService.get_instance()

    private_internal_url = "https://internal-confidential.corp.local/secret-dashboard?token=xyz999"

    # Mock fetch_html to avoid real network call
    async def mock_fetch(*args: Any, **kwargs: Any) -> tuple[str, int, str]:
        return "<html><head><title>Confidential Vault</title></head><body>Vault</body></html>", 200, "text/html"

    with patch.object(browser_service, "fetch_html", mock_fetch):
        res = await browser_service.capture_screenshot(private_internal_url)

        assert res["status"] == "success"
        screenshot_url = res["screenshot_url"]

        # MUST NEVER contain third-party thumbnail service
        assert "image.thum.io" not in screenshot_url
        assert "thum.io" not in screenshot_url

        # Must be local static URL or data URI
        assert screenshot_url.startswith("/static/screenshots/") or screenshot_url.startswith("data:image/svg+xml")
        assert res["title"] == "Confidential Vault"


# =============================================================================
# 5. Secret Handling & Sanitization Tests
# =============================================================================


def test_mask_secret_utility() -> None:
    """Verify sensitive tokens and keys are properly masked."""
    assert mask_secret("sk-proj-1234567890abcdef") == "••••••••cdef"
    assert mask_secret("short") == "••••••••"
    assert mask_secret("") == ""
    assert mask_secret(None) == ""


def test_sanitize_data_for_logging() -> None:
    """Verify recursive sanitization of credentials in nested dictionaries and lists."""
    payload = {
        "user": "alice",
        "api_key": "secret-api-key-9999",
        "config": {
            "auth_token": "bearer-token-12345",
            "retries": 3,
            "nested_list": [
                {"password": "super-secret-password"},
                {"safe_field": "safe_value"},
            ],
        },
    }

    sanitized = sanitize_data_for_logging(payload)

    assert sanitized["user"] == "alice"
    assert sanitized["api_key"] == "••••••••9999"
    assert sanitized["config"]["auth_token"] == "••••••••2345"
    assert sanitized["config"]["retries"] == 3
    assert sanitized["config"]["nested_list"][0]["password"] == "••••••••word"
    assert sanitized["config"]["nested_list"][1]["safe_field"] == "safe_value"


def test_secret_store_encryption_and_decryption() -> None:
    """Verify SecretStore can encrypt and decrypt secrets without data corruption."""
    store = SecretStore.get_instance()
    raw_token = "ghp_PersonalAccessTokenForGitHub2026SecureXYZ"

    encrypted = store.encrypt(raw_token)
    assert encrypted != raw_token
    assert encrypted.startswith(("enc:", "obf:"))

    decrypted = store.decrypt(encrypted)
    assert decrypted == raw_token
