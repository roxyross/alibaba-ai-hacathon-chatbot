# Phase 15: Connector + MCP Discovery Report
**Dynamic Runtime MCP/Connector Detection and Tool Binding**
**Execution Date:** October 4, 2026  
**Status:** Completed & Validated (100% Pass Rate, Zero Regressions)

---

## 1. Executive Summary

Phase 15 implements the **Dynamic Runtime Connector and MCP Discovery Engine**, completing the dynamic tool acquisition and runtime integration capabilities of the Roxy Personal AI system.

Operating strictly under the **Zero Simulation Doctrine**, the engine enables autonomous, multi-vector discovery of external Model Context Protocol (MCP) servers and Cloud/REST Connectors, dynamically binding their capabilities into the live `ToolRegistry` as typed `AgentTool` instances without requiring server restarts or static hardcoded wrappers.

All discovered pathways are strictly harmonized with the **Universal Integration Priority**:
- **Tier 1 (Cloud Connector / OpenAPI):** Preferred for structured authentication, direct REST contracts, low latency, and zero local daemon overhead.
- **Tier 2 (MCP Tool):** Preferred for standardized protocol interactions, declarative schema enforcement, and process-isolated capabilities.

---

## 2. Core Architecture & Components

```
+---------------------------------------------------------------------------------------------------+
|                                 Unified Discovery Engine                                          |
|                                                                                                   |
|  +---------------------------------------+     +-----------------------------------------------+  |
|  |         MCPDiscoveryEngine            |     |           ConnectorDiscoveryEngine            |  |
|  | - Config Files (Claude, .agents, etc) |     | - Environment Credentials (GITHUB_TOKEN, etc) |  |
|  | - Live TCP/HTTP SSE Socket Probes     |     | - Localhost OpenAPI/Swagger 3.0 Probes        |  |
|  | - Running Process Table Inspection    |     | - Authoritative Cloud Connector Catalog       |  |
|  | - Authoritative 10-Item Catalog       |     | - Active User Instances from DB               |  |
|  +-------------------+-------------------+     +-----------------------+-----------------------+  |
|                      |                                                 |                          |
|                      +-----------------------+-------------------------+                          |
|                                              |                                                    |
|                                              v                                                    |
|                         +----------------------------------------+                                |
|                         |    Universal Integration Priority      |                                |
|                         |  Ranking: Tier 1 (API) > Tier 2 (MCP)  |                                |
|                         +--------------------+-------------------+                                |
|                                              |                                                    |
|                                              v                                                    |
|                         +----------------------------------------+                                |
|                         |       Dynamic Tool Synthesizer         |                                |
|                         |  - Synthesizes live AgentTool          |                                |
|                         |  - Registers in ToolRegistry           |                                |
|                         |  - Tracks in DiscoveryBindingRegistry  |                                |
|                         +----------------------------------------+                                |
+---------------------------------------------------------------------------------------------------+
```

### 2.1 Authoritative Catalogs

1. **Authoritative MCP Catalog (`AUTHORITATIVE_MCP_CATALOG`)**:
   - `postgres`: PostgreSQL database querying and schema inspection.
   - `sqlite`: Local SQLite database operations.
   - `github`: GitHub repository, pull request, issue, and code search management.
   - `slack`: Slack messaging and channel administration.
   - `filesystem`: Local filesystem navigation and content manipulation.
   - `puppeteer`: Headless browser automation and web scraping.
   - `brave_search`: Live web and local privacy-preserving search.
   - `fetch`: Web content fetching and Markdown conversion.
   - `git`: Local Git repository management and commit history.
   - `memory`: Knowledge graph-based persistent memory and entity retrieval.

2. **Authoritative Cloud Connector Catalog (`AUTHORITATIVE_CONNECTOR_CATALOG`)**:
   - `github`: Code search, pull request creation, issue tracking.
   - `slack`: Channel messaging, direct messaging, message history.
   - `notion`: Page creation, database querying, block editing.
   - `google_drive`: File upload, download, sharing, and folder management.
   - `google_calendar`: Event scheduling, meeting lookups, calendar invites.
   - `linear`: Issue creation, sprint tracking, project roadmaps.
   - `jira`: Agile board management, issue tracking, ticket updates.
   - `discord`: Guild channel messaging and webhook execution.
   - `stripe`: Payment intent verification and invoice lookups.
   - `spotify`: Playback control, playlist management, track searching.

### 2.2 Discovery Vectors & Probe Mechanisms

1. **Configuration Scanning (`discover_config_servers`)**:
   - Scans platform-standard locations:
     - Windows `%APPDATA%\Claude\claude_desktop_config.json`
     - Linux/macOS `~/.config/Claude/claude_desktop_config.json` and `~/Library/Application Support/Claude/...`
     - Workspace configuration `.agents/mcp_config.json`
     - System-wide MCP configuration `~/.config/mcp/config.json`
   - Parses `mcpServers` stanzas, extracting commands, arguments, environment variables, or SSE URLs.

2. **TCP & HTTP Port Probing (`probe_tcp_port`, `discover_local_sse_servers`)**:
   - Performs authentic TCP socket connections (`socket.create_connection`) with configurable timeouts (default: 350ms).
   - Scans standard developer ports (`8000, 8080, 3000, 5000, 8001, 8081, 9000, 3001`).
   - If an open port is discovered, probes HTTP endpoints for Server-Sent Events (SSE) or MCP headers (`/sse`, `/events`, `/mcp`).

3. **Running Process Inspection (`discover_running_mcp_processes`)**:
   - Inspects host processes via `psutil.process_iter()`.
   - Detects commands matching known MCP patterns: `mcp-server-`, `@modelcontextprotocol/server-`, `npx -y @modelcontextprotocol`, etc.

4. **Environment Credential Detection (`discover_environment_credentials`)**:
   - Probes host environment variables for recognized API tokens (`GITHUB_TOKEN`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `SLACK_BOT_TOKEN`, `NOTION_API_KEY`).
   - Identifies immediately usable cloud connectors without requiring manual OAuth registration.

5. **OpenAPI / Swagger Spec Probing (`discover_openapi_endpoints`)**:
   - Probes live localhost ports for OpenAPI specifications (`/openapi.json`, `/swagger.json`, `/api-docs`).
   - Parses endpoints, HTTP methods, parameter schemas, and synthesizes dynamic REST `AgentTool` instances with automatic parameter mapping.

### 2.3 Dynamic Tool Binding & Lifecycle Management

- **`DiscoveryBindingRegistry`**:
  - Thread-safe registry tracking active dynamic bindings (`register_binding`, `get_binding`, `list_bindings`, `unbind`, `clear`).
  - Supports clean unbinding (`unbind()`), automatically removing synthesized tools from `ToolRegistry` and tearing down associated resources.
- **Dynamic Tool Synthesis**:
  - For MCP: Synthesizes `AgentTool` executing via `MCPClient` or JSON-RPC SSE bridge.
  - For OpenAPI: Synthesizes `AgentTool` executing HTTP requests via `httpx.AsyncClient` with schema-validated input dictionaries.

---

## 3. Integration with Existing Subsystems

### 3.1 DeviceService & Tool Registration
Added 5 first-class Agent Tools to `ToolRegistry`:
1. `mcp_discover_servers`: Discovers active MCP servers across configs, ports, processes, and catalogs.
2. `mcp_bind_server`: Dynamically binds an MCP server and registers its tools into the live tool registry.
3. `connector_discover`: Discovers cloud connectors from active instances, credentials, and OpenAPI specs.
4. `connector_bind`: Dynamically binds a connector or OpenAPI spec into live executable tools.
5. `unified_mcp_connector_discover_and_bind`: Unifies discovery, ranks options by priority, and auto-binds available tools.

Added lifecycle cleanup hooks to `DeviceService.clear_in_memory_state()` ensuring clean test isolation.

### 3.2 Integration Resolver (`IntegrationResolver`)
Enhanced the 8-Tier Universal Integration Resolver:
- **Tier 1 (Cloud Connector):** Integrated `ConnectorDiscoveryEngine.discover_environment_credentials()` to dynamically recognize connector availability when tokens are present in the environment (e.g. `GITHUB_TOKEN`).
- **Tier 2 (MCP Tool):** Integrated `get_discovery_binding_registry().list_bindings()` to resolve dynamically bound MCP tools in real-time.
- **Catalog Alignment:** Added `"search_code": "github_search_code"` to GitHub capabilities to match `ConnectorService`.

### 3.3 FastAPI Endpoints
Exposed 7 REST endpoints in `src/app/device/router.py`:
- `POST /api/v1/devices/{device_id}/discovery/mcp/scan`
- `POST /api/v1/devices/{device_id}/discovery/mcp/bind`
- `POST /api/v1/devices/{device_id}/discovery/connectors/scan`
- `POST /api/v1/devices/{device_id}/discovery/connectors/bind`
- `POST /api/v1/devices/{device_id}/discovery/unified`
- `GET  /api/v1/devices/{device_id}/discovery/bound-tools`
- `DELETE /api/v1/devices/{device_id}/discovery/bound-tools/{binding_id}`

---

## 4. Verification & Test Results

### 4.1 Dedicated Phase 15 Tests (`test_phase15_mcp_connector_discovery.py`)
| Test Name | Focus | Result |
| :--- | :--- | :--- |
| `test_mcp_config_discovery` | Discovery from Claude Desktop & custom MCP configs | **PASSED** |
| `test_tcp_port_probe` | Authentic TCP socket open/closed port probing | **PASSED** |
| `test_mcp_process_and_catalog_discovery` | Process table matching & authoritative catalog scans | **PASSED** |
| `test_mcp_tool_binding_and_execution` | Dynamic `AgentTool` synthesis and execution | **PASSED** |
| `test_openapi_tool_binding_and_execution` | OpenAPI 3.0 spec parsing, binding, and HTTP invocation | **PASSED** |
| `test_environment_credentials_discovery` | Token inspection (`GITHUB_TOKEN`, `SLACK_BOT_TOKEN`) | **PASSED** |
| `test_catalog_connector_discovery` | Authoritative connector catalog matching | **PASSED** |
| `test_unified_discovery_engine` | Unified multi-vector scan and priority ranking | **PASSED** |
| `test_resolver_with_dynamic_credentials` | Integration resolver Tier 1 dynamic token detection | **PASSED** |
| `test_resolver_with_dynamic_mcp_binding` | Integration resolver Tier 2 dynamic MCP binding resolution | **PASSED** |
| `test_device_service_discovery_tools` | Service layer tools invocation and lifecycle unbinding | **PASSED** |
| `test_api_discovery_endpoints` | Full suite of FastAPI discovery and binding REST endpoints | **PASSED** |

**Summary: 12 passed in 25.49s (100% pass rate)**

### 4.2 Comprehensive Regression Test Suite
Executed the full regression test suite across Phases 15, 14, 13, 8, and 7:
- Phase 15 (Connector + MCP Discovery): 12 tests
- Phase 14 (Automatic New-App Workflow): 17 tests
- Phase 13 (Mobile App Discovery): 19 tests
- Phase 8 (Integration Resolution Engine): 21 tests
- Phase 7 (Dynamic Capability Discovery): 13 tests

**Result: 82 passed, 0 failures, 8 warnings in 133.89s (100% pass rate)**

### 4.3 Static Code Analysis
- **Mypy Type Checking:** `0 issues found`
- **Ruff Linter:** `All checks passed!`

---

## 5. Artifacts and Source Locations

- **Data Models:** [`src/app/device/schemas.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/schemas.py)
- **Core Engine:** [`src/app/device/mcp_connector_discovery.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/mcp_connector_discovery.py)
- **Service Integration:** [`src/app/device/service.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/service.py)
- **Integration Resolver:** [`src/app/device/integration_resolver.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/integration_resolver.py)
- **FastAPI Endpoints:** [`src/app/device/router.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/router.py)
- **Automated Tests:** [`tests/test_phase15_mcp_connector_discovery.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/tests/test_phase15_mcp_connector_discovery.py)
