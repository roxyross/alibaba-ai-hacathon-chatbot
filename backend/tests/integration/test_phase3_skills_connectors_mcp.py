"""Integration tests for Phase 3: Skills, Connectors & Model Context Protocol (MCP).

Verifies:
1. Supported connector catalog types.
2. Connector CRUD lifecycle, health testing, credential masking.
3. Dynamic OpenAPI/Swagger spec parsing and automatic AgentTool compilation.
4. MCP Server registration, 2024-11-05 protocol sync, and direct tool calling.
5. Custom Skills prompt templating, safe Python sandbox, and execution.
6. Central ToolRegistry dynamic bridging and availability for agents.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.connectors.schemas import ConnectorType
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolSource


@pytest.mark.asyncio
async def test_connector_types_catalog(authed_client: AsyncClient) -> None:
    """Verify that all supported connector types are cataloged with schemas."""
    res = await authed_client.get("/api/v1/connectors/types")
    assert res.status_code == 200
    types = res.json()
    assert isinstance(types, list)
    assert len(types) >= 6

    type_names = {t["type"] for t in types}
    assert ConnectorType.GOOGLE.value in type_names
    assert ConnectorType.GITHUB.value in type_names
    assert ConnectorType.SLACK.value in type_names
    assert ConnectorType.NOTION.value in type_names
    assert ConnectorType.OPENAPI.value in type_names
    assert ConnectorType.WEBHOOK.value in type_names


@pytest.mark.asyncio
async def test_connector_crud_and_health_check(authed_client: AsyncClient) -> None:
    """Verify creating, listing, health-checking, and deleting a connector."""
    registry = ToolRegistry.get_instance()

    # 1. Create GitHub connector
    payload = {
        "connector_type": "github",
        "name": "Team GitHub Repo",
        "description": "Integration with GitHub for issue tracking",
        "auth_type": "personal_access_token",
        "config": {"owner": "test-org", "repo": "roxy-core"},
        "credentials": {"personal_access_token": "ghp_secretToken12345"},
    }
    create_res = await authed_client.post("/api/v1/connectors", json=payload)
    assert create_res.status_code in (200, 201)
    data = create_res.json()
    cid = data["id"]
    assert data["name"] == "Team GitHub Repo"
    assert data["connector_type"] == "github"
    # Verify credential masking
    assert data["credentials"]["personal_access_token"] == "••••••••"
    assert data["action_count"] == 3

    # Verify tools registered in ToolRegistry
    tools = registry.list_tools()
    github_tools = [t for t in tools if f"github_{cid[:8]}" in t.id]
    assert len(github_tools) == 3
    tool_names = {t.id for t in github_tools}
    assert f"connector_github_{cid[:8]}_search_code" in tool_names
    assert f"connector_github_{cid[:8]}_list_issues" in tool_names
    assert f"connector_github_{cid[:8]}_create_issue" in tool_names

    # 2. Test Connection health check
    test_res = await authed_client.post(f"/api/v1/connectors/{cid}/test")
    assert test_res.status_code == 200
    test_data = test_res.json()
    assert test_data["success"] is True
    assert test_data["status"] == "active"
    assert "GitHub connection verified" in test_data["message"]

    # 3. List connectors
    list_res = await authed_client.get("/api/v1/connectors")
    assert list_res.status_code == 200
    conn_list = list_res.json()
    assert any(c["id"] == cid for c in conn_list)

    # 4. Delete connector
    del_res = await authed_client.delete(f"/api/v1/connectors/{cid}")
    assert del_res.status_code in (200, 204)

    # Verify tools unregistered
    tools_after = registry.list_tools()
    assert not any(f"github_{cid[:8]}" in t.id for t in tools_after)


@pytest.mark.asyncio
async def test_openapi_import_and_dynamic_tool_generation(authed_client: AsyncClient) -> None:
    """Verify that importing an OpenAPI 3.0 spec dynamically generates executable AgentTools."""
    sample_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Customer CRM API",
            "version": "1.0.0",
            "description": "Production CRM REST service for customer management.",
        },
        "servers": [{"url": "https://api.crm.example.com/v1"}],
        "paths": {
            "/customers": {
                "get": {
                    "operationId": "listCustomers",
                    "summary": "List all registered customers",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 20},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "createCustomer",
                    "summary": "Create a new customer profile",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["email", "name"],
                                    "properties": {
                                        "email": {"type": "string"},
                                        "name": {"type": "string"},
                                        "tier": {"type": "string", "enum": ["free", "pro"]},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/customers/{customerId}": {
                "get": {
                    "operationId": "getCustomerById",
                    "summary": "Fetch customer details by unique ID",
                    "parameters": [
                        {
                            "name": "customerId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }

    import_payload = {
        "name": "CRM Connector",
        "spec_json": json.dumps(sample_spec),
        "api_key": "crm_live_sec_key_xyz",
    }

    res = await authed_client.post("/api/v1/connectors/openapi/import", json=import_payload)
    assert res.status_code in (200, 201)
    import_data = res.json()
    assert import_data["name"] == "CRM Connector"
    assert import_data["tools_generated"] == 3
    assert set(import_data["operations"]) == {"listCustomers", "createCustomer", "getCustomerById"}

    cid = import_data["connector_id"]
    registry = ToolRegistry.get_instance()
    crm_tools = [t for t in registry.list_tools() if f"openapi_{cid[:8]}" in t.id]
    assert len(crm_tools) == 3

    # Check input_schema of createCustomer and getCustomerById
    create_tool = next(t for t in crm_tools if t.id == f"connector_openapi_{cid[:8]}_createCustomer")
    assert create_tool.source == ToolSource.CONNECTOR
    schema_props = create_tool.input_schema.get("properties", {})
    assert "body" in schema_props

    get_tool = next(t for t in crm_tools if t.id == f"connector_openapi_{cid[:8]}_getCustomerById")
    assert "customerId" in get_tool.input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_mcp_client_handshake_and_tool_discovery(authed_client: AsyncClient) -> None:
    """Verify MCP client initialization, tool discovery, and tool registration."""
    # 1. Register MCP server
    payload = {
        "name": "Local Filesystem MCP",
        "description": "Exposes secure read/write filesystem tools",
        "transport": "sse",
        "endpoint_url": "http://localhost:8000/mock-mcp-sse",
    }
    create_res = await authed_client.post("/api/v1/mcp/servers", json=payload)
    assert create_res.status_code in (200, 201)
    server_data = create_res.json()
    sid = server_data["id"]
    assert server_data["protocol_version"] == "2024-11-05"

    from unittest.mock import patch
    from app.mcp.client import MCPClient
    from app.mcp.schemas import JSONRPCResponse

    async def mock_send_rpc(self: Any, method: str, params: dict[str, Any] | None = None) -> JSONRPCResponse:
        if method == "initialize":
            return JSONRPCResponse(jsonrpc="2.0", id="1", result={"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}})
        elif method == "tools/list":
            return JSONRPCResponse(
                jsonrpc="2.0",
                id="2",
                result={"tools": [{"name": "read_file", "description": "Read file from disk", "inputSchema": {"type": "object", "properties": {"action": {"type": "string"}}}}]})
        elif method == "tools/call":
            return JSONRPCResponse(
                jsonrpc="2.0",
                id="3",
                result={"content": [{"type": "text", "text": "Filesystem tool executed successfully."}], "isError": False})
        return JSONRPCResponse(jsonrpc="2.0", id="0", result={})

    with patch.object(MCPClient, "_send_rpc", mock_send_rpc):
        # 2. Trigger sync
        sync_res = await authed_client.post(f"/api/v1/mcp/servers/{sid}/sync")
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["tools_count"] >= 1
        assert len(sync_data["tools"]) >= 1
        discovered_tool_name = sync_data["tools"][0]["name"]

        # 3. Direct MCP tool call
        call_res = await authed_client.post(
            f"/api/v1/mcp/servers/{sid}/call",
            json={"tool_name": discovered_tool_name, "arguments": {"action": "query", "payload": {}}},
        )
        assert call_res.status_code == 200
        call_data = call_res.json()
        assert call_data.get("isError") is False
        assert "Filesystem tool executed successfully." in str(call_data["content"])

    # 4. Cleanup
    del_res = await authed_client.delete(f"/api/v1/mcp/servers/{sid}")
    assert del_res.status_code in (200, 204)


@pytest.mark.asyncio
async def test_custom_skills_templating_and_sandbox(authed_client: AsyncClient) -> None:
    """Verify Custom Skills creation, prompt variable rendering, and python sandbox execution."""
    registry = ToolRegistry.get_instance()

    # 1. Create Prompt Template Skill
    prompt_skill = {
        "name": "Project Status Digest",
        "skill_key": "status_digest",
        "description": "Generates a clean markdown status digest for a given project and milestone.",
        "execution_type": "prompt",
        "code_or_prompt_template": "Weekly status for {project} (Milestone {milestone}): All tasks on track!",
        "risk_level": "low",
        "requires_confirmation": False,
    }
    res1 = await authed_client.post("/api/v1/skills/custom", json=prompt_skill)
    assert res1.status_code in (200, 201)
    data1 = res1.json()
    skill_id_1 = data1["id"]

    # Verify tool in ToolRegistry
    tool = registry.get("custom_skill_status_digest")
    assert tool is not None
    assert tool.source == ToolSource.SKILL

    # Execute prompt skill
    exec_res1 = await authed_client.post(
        f"/api/v1/skills/custom/{skill_id_1}/execute",
        json={"arguments": {"project": "ROXY-2.0", "milestone": "Phase 3"}},
    )
    assert exec_res1.status_code == 200
    result1 = exec_res1.json()
    assert result1["execution_type"] == "prompt"
    assert "Weekly status for ROXY-2.0 (Milestone Phase 3)" in result1["rendered_prompt"]

    # 2. Create Python Sandbox Skill
    calc_skill = {
        "name": "Safe Cost Forecaster",
        "skill_key": "cost_forecaster",
        "description": "Calculates projected operational token cost multiplier.",
        "execution_type": "python_sandbox",
        "code_or_prompt_template": "result = sum(args.get('tokens', [])) * 0.00002",
        "risk_level": "low",
        "requires_confirmation": False,
    }
    res2 = await authed_client.post("/api/v1/skills/custom", json=calc_skill)
    assert res2.status_code in (200, 201)
    data2 = res2.json()
    skill_id_2 = data2["id"]

    exec_res2 = await authed_client.post(
        f"/api/v1/skills/custom/{skill_id_2}/execute",
        json={"arguments": {"tokens": [1000, 2000, 3000]}},
    )
    assert exec_res2.status_code == 200
    result2 = exec_res2.json()
    assert result2["execution_type"] == "python_sandbox"
    assert result2["result"] == pytest.approx(0.12)

    # 3. Clean up skills
    del1 = await authed_client.delete(f"/api/v1/skills/custom/{skill_id_1}")
    assert del1.status_code in (200, 204)
    del2 = await authed_client.delete(f"/api/v1/skills/custom/{skill_id_2}")
    assert del2.status_code in (200, 204)
    assert registry.get("custom_skill_status_digest") is None
