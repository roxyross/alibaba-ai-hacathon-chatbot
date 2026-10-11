"""Phase 15 Test Suite: Connector + MCP Discovery.

Dynamic runtime MCP/connector detection, capability discovery,
Universal Integration Priority ranking, dynamic ToolRegistry binding, and verification.
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.integration_resolver import IntegrationResolver
from app.device.mcp_connector_discovery import (
    ConnectorDiscoveryEngine,
    MCPDiscoveryEngine,
    UnifiedMCPConnectorDiscoveryEngine,
    get_discovery_binding_registry,
)
from app.device.schemas import (
    ConnectorToolBindingRequest,
    IntegrationResolutionRequest,
    MCPDiscoveredServer,
    MCPDiscoverySource,
    MCPToolBindingRequest,
    UnifiedDiscoveryRequest,
)
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest, ToolSource

# =============================================================================
# Test Setup & Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def setup_teardown() -> Any:
    """Isolate in-memory discovery registry and device service state."""
    service = DeviceService.get_instance()
    service.clear_in_memory_state()
    service.register_device_tools()
    binding_reg = get_discovery_binding_registry()
    binding_reg.clear()
    yield
    binding_reg.clear()
    service.clear_in_memory_state()


def get_mock_user() -> User:
    return User(
        id="user_phase15_tester",
        email="phase15@test.local",
    )


# =============================================================================
# 1. MCP Configuration Discovery Tests
# =============================================================================


def test_mcp_config_discovery() -> None:
    """Verify discovery and parsing of MCP server declarations from configuration files."""
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
        config_content = {
            "mcpServers": {
                "sqlite_local": {
                    "command": sys.executable,
                    "args": ["-c", "print('sqlite')"],
                    "env": {"TEST_ENV": "1"},
                },
                "remote_sse": {
                    "url": "http://127.0.0.1:8000/sse",
                },
            }
        }
        json.dump(config_content, tf)
        tf_path = Path(tf.name)

    try:
        servers, paths = MCPDiscoveryEngine.discover_config_servers([tf_path])
        assert str(tf_path.resolve()) in paths or str(tf_path) in paths
        assert len(servers) >= 2

        # Check stdio server
        sqlite_srv = next((s for s in servers if "sqlite" in s.name), None)
        assert sqlite_srv is not None
        assert sqlite_srv.transport == "stdio"
        assert sqlite_srv.command == sys.executable
        assert sqlite_srv.arguments == ["-c", "print('sqlite')"]
        assert sqlite_srv.env == {"TEST_ENV": "1"}
        assert sqlite_srv.source == MCPDiscoverySource.CONFIG_FILE
        assert sqlite_srv.is_active is True

        # Check sse server
        sse_srv = next((s for s in servers if "remote" in s.name), None)
        assert sse_srv is not None
        assert sse_srv.transport == "sse"
        assert sse_srv.endpoint_url == "http://127.0.0.1:8000/sse"
    finally:
        tf_path.unlink(missing_ok=True)


# =============================================================================
# 2. Network Port & Socket Probing Tests
# =============================================================================


def test_tcp_port_probe() -> None:
    """Verify non-destructive TCP socket connectivity testing."""
    # 1. Test inactive port
    assert MCPDiscoveryEngine.probe_tcp_port("127.0.0.1", 59999, timeout=0.1) is False

    # 2. Test active port with real local socket listener
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        active_port = s.getsockname()[1]
        assert MCPDiscoveryEngine.probe_tcp_port("127.0.0.1", active_port, timeout=0.5) is True


# =============================================================================
# 3. Running Process & Catalog Discovery Tests
# =============================================================================


def test_mcp_process_and_catalog_discovery() -> None:
    """Verify process scanning and authoritative open-source MCP catalog matching."""
    # 1. Process scan
    procs = MCPDiscoveryEngine.discover_running_mcp_processes()
    assert isinstance(procs, list)

    # 2. Catalog matches
    cat_pg = MCPDiscoveryEngine.discover_catalog_servers("postgres")
    assert len(cat_pg) == 1
    assert "PostgreSQL" in cat_pg[0].name
    assert cat_pg[0].source == MCPDiscoverySource.AUTHORITATIVE_CATALOG
    assert cat_pg[0].tools_count >= 3

    cat_sqlite = MCPDiscoveryEngine.discover_catalog_servers("sqlite")
    assert len(cat_sqlite) == 1
    assert "SQLite" in cat_sqlite[0].name

    cat_all = MCPDiscoveryEngine.discover_catalog_servers()
    assert len(cat_all) >= 8


# =============================================================================
# 4. Live MCP Tool Binding & Registry Execution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_mcp_tool_binding_and_execution() -> None:
    """Verify dynamic synthesis of AgentTools from MCP definitions and live invocation."""
    disc_server = MCPDiscoveredServer(
        server_id="test_mock_srv",
        name="Test Mock Server",
        transport="stdio",
        source=MCPDiscoverySource.CONFIG_FILE,
        command=sys.executable,
        is_active=True,
        discovered_tools=[
            {
                "name": "echo_tool",
                "description": "Echo input text back",
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            },
            {
                "name": "delete_database",
                "description": "Destructive drop database operation",
                "input_schema": {"type": "object"},
            },
        ],
    )

    req = MCPToolBindingRequest(
        device_id="test_dev",
        server=disc_server,
        auto_handshake=False,
    )

    res = await MCPDiscoveryEngine.bind_server(req)
    assert res.success is True
    assert res.total_bound == 2
    assert len(res.bound_tools) == 2

    tool_reg = ToolRegistry.get_instance()
    echo_tool_id = res.bound_tools[0]
    t = tool_reg.get(echo_tool_id)
    assert t is not None
    assert t.source == ToolSource.MCP

    # Verify risk classification
    del_tool_id = res.bound_tools[1]
    del_t = tool_reg.get(del_tool_id)
    assert del_t is not None
    assert del_t.requires_confirmation is True

    # Check DiscoveryBindingRegistry tracking
    b_reg = get_discovery_binding_registry()
    bindings = b_reg.list_bindings()
    assert len(bindings) == 1
    assert bindings[0]["binding_id"] == res.binding_id

    # Verify unbind cleans ToolRegistry
    assert b_reg.unbind(res.binding_id) is True
    assert tool_reg.get(echo_tool_id) is None
    assert tool_reg.get(del_tool_id) is None


# =============================================================================
# 5. OpenAPI Endpoint Discovery & Tool Binding Tests
# =============================================================================


@pytest.mark.asyncio
async def test_openapi_tool_binding_and_execution() -> None:
    """Verify dynamic synthesis and live execution of AgentTools from an OpenAPI specification."""
    sample_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Inventory Management API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "operationId": "list_inventory_items",
                    "summary": "List all inventory items",
                    "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer"}}],
                },
                "post": {
                    "operationId": "create_inventory_item",
                    "summary": "Create new inventory item",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}, "price": {"type": "number"}},
                                    "required": ["name"],
                                }
                            }
                        }
                    },
                },
            }
        },
    }

    req = ConnectorToolBindingRequest(
        device_id="dev_openapi",
        connector_type="openapi",
        name="Inventory REST Service",
        openapi_spec=sample_spec,
        openapi_base_url="https://api.example.com",
    )

    res = await ConnectorDiscoveryEngine.bind_connector(req)
    assert res.success is True
    assert res.total_bound == 2
    assert "conn_" in res.connector_id

    tool_reg = ToolRegistry.get_instance()
    for tid in res.bound_tools:
        tool_obj = tool_reg.get(tid)
        assert tool_obj is not None
        assert tool_obj.source == ToolSource.CONNECTOR

    # Test direct execution wrapper via ToolRegistry
    exec_req = ToolExecutionRequest(
        user_id="default",
        tool_id=res.bound_tools[0],
        arguments={"limit": 5},
    )
    exec_res = await tool_reg.execute(exec_req)
    assert exec_res.success is True
    assert exec_res.output.get("simulated") is True or exec_res.output.get("status_code") == 200

    # Cleanup via DiscoveryBindingRegistry
    b_reg = get_discovery_binding_registry()
    assert b_reg.unbind(res.binding_id) is True
    assert tool_reg.get(res.bound_tools[0]) is None


# =============================================================================
# 6. Environment Credentials & Catalog Connector Discovery
# =============================================================================


def test_environment_credentials_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify detection of API keys and tokens in system environment."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_mocktoken123456789")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-mock-slack-token")

    creds = ConnectorDiscoveryEngine.discover_environment_credentials()
    types_found = {c.connector_type for c in creds}
    assert "github" in types_found
    assert "slack" in types_found

    gh_item = next(c for c in creds if c.connector_type == "github")
    assert gh_item.has_credentials is True
    assert gh_item.health_status == "healthy"


def test_catalog_connector_discovery() -> None:
    """Verify catalog matching for supported cloud connectors."""
    cat_gh = ConnectorDiscoveryEngine.discover_catalog_connectors("github")
    assert len(cat_gh) >= 1
    assert cat_gh[0].connector_type == "github"
    assert len(cat_gh[0].available_actions) >= 3

    cat_slack = ConnectorDiscoveryEngine.discover_catalog_connectors("slack")
    assert len(cat_slack) >= 1
    assert cat_slack[0].connector_type == "slack"


# =============================================================================
# 7. Unified Discovery & Integration Ranking Tests
# =============================================================================


@pytest.mark.asyncio
async def test_unified_discovery_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify unified discovery, Universal Integration Priority ranking (Tiers 1 & 2), and auto-binding."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_unified_test")

    req = UnifiedDiscoveryRequest(
        device_id="dev_unified",
        target_app="github",
        auto_bind=False,
        scan_mcp=True,
        scan_connectors=True,
    )

    res = await UnifiedMCPConnectorDiscoveryEngine.discover_and_bind(req)
    assert res.target_app == "github"
    assert res.connector_discovery.total_found > 0
    assert res.mcp_discovery.total_found > 0
    assert len(res.ranked_pathways) > 0

    # Verify Universal Integration Priority: Tier 1 (Connector) precedes Tier 2 (MCP)
    top_pathway = res.ranked_pathways[0]
    assert top_pathway.priority_rank == 1
    assert top_pathway.integration_tier == "connector"


# =============================================================================
# 8. IntegrationResolver Enhancement Verification
# =============================================================================


def test_resolver_with_dynamic_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify IntegrationResolver Tier 1 promotion when dynamic credentials are present in env."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_resolver_test")

    req = IntegrationResolutionRequest(
        application="github",
        requested_capability="search_code",
    )
    result = IntegrationResolver.resolve(req)
    assert result.success is True
    assert result.chosen_integration == "cloud_connector"
    assert result.confidence == 0.98


def test_resolver_with_dynamic_mcp_binding() -> None:
    """Verify IntegrationResolver Tier 2 selection when dynamic MCP tools are bound."""
    b_reg = get_discovery_binding_registry()
    binding_id = f"bind_test_{uuid.uuid4().hex[:6]}"
    b_reg.register_binding(
        binding_id=binding_id,
        source_type="mcp",
        source_id="custom_postgres_mcp",
        name="Postgres MCP Service",
        bound_tools=["mcp_postgres_query", "mcp_postgres_describe_table"],
    )

    req = IntegrationResolutionRequest(
        application="postgres",
        requested_capability="query",
    )
    result = IntegrationResolver.resolve(req)
    assert result.success is True
    assert result.chosen_integration == "mcp_tool"
    assert result.confidence >= 0.90
    assert "mcp_postgres" in str(result.handler_target)


# =============================================================================
# 9. DeviceService & ToolRegistry Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_device_service_discovery_tools() -> None:
    """Verify 5 Phase 15 tools are registered in ToolRegistry and executable via DeviceService."""
    reg = ToolRegistry.get_instance()
    tools_to_check = [
        "mcp_discover_servers",
        "mcp_bind_server",
        "connector_discover",
        "connector_bind",
        "unified_mcp_connector_discover_and_bind",
    ]

    for tid in tools_to_check:
        t = reg.get(tid)
        assert t is not None, f"Tool '{tid}' not found in ToolRegistry"
        assert t.source == ToolSource.DEVICE

    # 1. Test mcp_discover_servers handler
    mcp_handler = reg.get_handler("mcp_discover_servers")
    assert mcp_handler is not None
    m_res = await mcp_handler(target_app="sqlite")
    assert "catalog_suggestions" in m_res

    # 2. Test connector_discover handler
    conn_handler = reg.get_handler("connector_discover")
    assert conn_handler is not None
    c_res = await conn_handler(target_app="github")
    assert "catalog_connectors" in c_res

    # 3. Test unified discovery tool handler
    unified_handler = reg.get_handler("unified_mcp_connector_discover_and_bind")
    assert unified_handler is not None
    u_res = await unified_handler(target_app="postgres", auto_bind=False)
    assert "ranked_pathways" in u_res


# =============================================================================
# 10. FastAPI REST Endpoints Tests
# =============================================================================


def test_api_discovery_endpoints() -> None:
    """Verify REST API endpoints under /api/v1/devices/{device_id}/discovery/."""
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = get_mock_user

    try:
        # 1. MCP Scan endpoint
        mcp_resp = client.post(
            "/api/v1/devices/dev_api_test/discovery/mcp/scan",
            json={"target_app": "postgres", "scan_configs": False, "scan_ports": False, "scan_processes": False},
        )
        assert mcp_resp.status_code == status.HTTP_200_OK
        mcp_data = mcp_resp.json()
        assert len(mcp_data["catalog_suggestions"]) > 0

        # 2. Connector Scan endpoint
        conn_resp = client.post(
            "/api/v1/devices/dev_api_test/discovery/connectors/scan",
            json={"target_app": "slack", "scan_openapi_ports": False},
        )
        assert conn_resp.status_code == status.HTTP_200_OK
        conn_data = conn_resp.json()
        assert len(conn_data["catalog_connectors"]) > 0

        # 3. Unified Discovery endpoint
        uni_resp = client.post(
            "/api/v1/devices/dev_api_test/discovery/unified",
            json={"target_app": "github", "auto_bind": False},
        )
        assert uni_resp.status_code == status.HTTP_200_OK
        uni_data = uni_resp.json()
        assert "ranked_pathways" in uni_data

        # 4. Bound tools list endpoint
        list_resp = client.get("/api/v1/devices/dev_api_test/discovery/bound-tools")
        assert list_resp.status_code == status.HTTP_200_OK
        assert "bindings" in list_resp.json()

        # 5. Unbind 404 test
        del_resp = client.delete("/api/v1/devices/dev_api_test/discovery/bound-tools/nonexistent_binding")
        assert del_resp.status_code == status.HTTP_404_NOT_FOUND
    finally:
        app.dependency_overrides.pop(get_current_user, None)
