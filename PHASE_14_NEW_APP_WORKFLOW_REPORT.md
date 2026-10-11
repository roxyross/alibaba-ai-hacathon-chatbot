# PHASE 14: AUTOMATIC NEW-APP WORKFLOW
### Dynamic Detection, Capability Discovery, Integration Ranking, and Registration

## Executive Summary

Phase 14 delivers the authoritative, autonomous **Automatic New-App Workflow Engine** for Roxy AI. This subsystem enables Roxy to dynamically discover unknown desktop and mobile applications, introspect their executable capability surfaces, rank candidate integration pathways according to the 11-Tier Universal Integration Priority hierarchy, synthesize typed runtime agent tools, register them dynamically into the `ToolRegistry`, and conduct real, non-destructive verification probes under the **Zero Simulation Doctrine**.

Operating strictly without mock data or simulated behaviors, the pipeline bridges system binaries, package managers, network protocols, native UI automation engines, mobile device bridges, and cloud connector ecosystems into a unified, zero-touch registration flow.

---

## 1. Architectural Components Delivered

```
                             ROXY AI ARCHITECTURE (PHASE 14)
  
   [ Trigger: User Prompt / Process Watcher / FS Event / Package Mgr ]
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                            NewAppDetector                              │
   │ - Novelty Verification (Checks against registered memory & app catalog)│
   │ - App Canonicalization & Identification                                │
   │ - Platform Identification (Windows, macOS, Linux, Android, iOS)        │
   │ - Real Binary Path Resolution (System PATH, App Paths)                 │
   └─────────────────────────────┬──────────────────────────────────────────┘
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          NewAppIntrospector                            │
   │ - Multi-modal Surface Probing:                                         │
   │   1. CLI Introspection (Dynamic CLI runner, subcommands, help probe)  │
   │   2. Protocol Port Probe (Real TCP socket connect & banners)           │
   │   3. Desktop UI Controls (DesktopAutomationEngine window inspection)   │
   │   4. Mobile Capabilities (MobileAppRegistry packages & intent lookup)  │
   │   5. Cloud Connectors (Authoritative catalog resolution)               │
   └─────────────────────────────┬──────────────────────────────────────────┘
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                       IntegrationRankingEngine                         │
   │ - 11-Tier Universal Integration Priority Hierarchy:                    │
   │     Tier 1: Cloud Connector / API        Tier 7: Share Sheet Target    │
   │     Tier 2: MCP Tool / Server            Tier 8: Local Protocol Port   │
   │     Tier 3: CLI Subcommand / Tool        Tier 9: Desktop UI Automation │
   │     Tier 4: App Intent / Shortcut        Tier 10: Mobile UI Automation │
   │     Tier 5: Deep Link / URL Scheme       Tier 11: Process Lifecycle    │
   │     Tier 6: Android System Intent                                      │
   │ - Confidence Scoring & Estimated Latency Analysis                      │
   │ - User / Caller Preference Overrides                                   │
   └─────────────────────────────┬──────────────────────────────────────────┘
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                            NewAppRegistrar                             │
   │ - Dynamic AgentTool Synthesis (Typed input schema & risk metadata)     │
   │ - Dynamic Tool Registration into active ToolRegistry                   │
   │ - Memory & State Persistence in DeviceService._mem_apps                │
   │ - Zero-Simulation Non-Destructive Verification Probe                   │
   └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Modules Implemented

### 2.1 Data Models ([`schemas.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/schemas.py))
- **`NewAppDetectionRequest` & `NewAppDetectionResult`**:
  Input triggers (`user_request`, `filesystem_watcher`, `package_manager`, `process_monitor`), canonical application naming, novelty flag, target platform, resolved binary path, and system metadata.
- **`DiscoveredIntegrationPathway`**:
  Structural representation of a discovered pathway, including integration type (Tier 1-11), pathway identifier, confidence score (`0.0 - 1.0`), estimated latency, semantic risk level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), input schema, execution adapter, and verification strategy.
- **`NewAppIntrospectionRequest` & `NewAppIntrospectionResult`**:
  Parameters for targeted or deep multi-modal introspection across CLI, TCP ports, desktop UI, mobile bundles, and cloud APIs.
- **`NewAppRankingRequest` & `NewAppRankingResult`**:
  Input discovered pathways, caller override preferences, ranked candidate pathways with primary and fallback classifications, and clear ranking rationales.
- **`NewAppRegistrationRequest` & `NewAppRegistrationResult`**:
  Configuration for synthesizing dynamic `AgentTool` instances, registration confirmation, synthesized tool definitions, and verification probe audit trails.
- **`NewAppWorkflowRequest` & `NewAppWorkflowResponse`**:
  Full-lifecycle workflow request and execution response encapsulating detection, introspection, ranking, registration, and probe verification.

### 2.2 Core Workflow Engine ([`new_app_workflow.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/new_app_workflow.py))
- **`NewAppDetector`**:
  - Validates application novelty against live registered apps and existing catalog entries.
  - Normalizes canonical names (`"Spotify.exe"` -> `"spotify"`, `"code.cmd"` -> `"vscode"`).
  - Determines host or mobile platform (`windows`, `macos`, `linux`, `android`, `ios`, `desktop`).
  - Resolves actual binary paths using `shutil.which` and standard operating system search directories.
- **`NewAppIntrospector`**:
  - **CLI Surface**: Queries `CLIIntrospector` to inspect binary arguments, `--help` strings, version commands, and dynamic subcommands.
  - **Network Protocol Surface**: Probes localhost TCP ports using real non-destructive `socket.create_connection` attempts.
  - **Desktop UI Surface**: Queries `DesktopAutomationEngine` to inspect active window controls, buttons, and accessibility trees.
  - **Mobile Surface**: Queries `MobileAppRegistry` for Android package intents, iOS bundle deep links, and share targets.
  - **Cloud Connector Surface**: Matches against authoritative connector catalog entries (Spotify, Slack, GitHub, Notion, etc.).
- **`IntegrationRankingEngine`**:
  - Implements the strict 11-Tier Universal Integration Priority hierarchy.
  - Grants highest priority to deterministic, low-latency, and authenticated pathways (Cloud APIs & MCP), followed by structured CLI tools, native intents/deep links, local protocols, UI automation, and fallback process lifecycle controls.
  - Supports user preference overrides (`preferred_pathway`), promoting user-specified tiers to primary status when available.
  - Computes confidence scores and estimated latency bounds for each tier.
- **`NewAppRegistrar`**:
  - Dynamically synthesizes an `AgentTool` instance complete with parameters schema, handler function, risk level, and docstrings.
  - Safely registers the tool into Roxy's live `ToolRegistry`.
  - Records application metadata in `DeviceService._mem_apps`.
  - Executes a zero-simulation non-destructive verification probe (e.g., connector ping, CLI version/help check, UI inspection).
- **`NewAppWorkflowEngine`**:
  - Orchestrates the complete automated sequence: `Detect` -> `Introspect` -> `Rank` -> `Register` -> `Verify`.
  - Provides thread-safe in-memory caching and retrieval of registered apps.

### 2.3 Service Layer Integration ([`service.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/service.py))
- Registered **5 first-class Agent Tools** in `ToolRegistry`:
  1. `new_app_workflow`: End-to-end detection, capability discovery, ranking, and registration.
  2. `new_app_detect`: Detect novelty and resolve binary/platform metadata for an application.
  3. `new_app_introspect`: Introspect capability surfaces of an application.
  4. `new_app_rank_integrations`: Rank integration pathways according to Universal Integration Priority.
  5. `new_app_register`: Register an app, synthesize agent tools, and run verification probes.
- Added **7 asynchronous service methods** to `DeviceService`:
  - `detect_new_app(...)`
  - `introspect_new_app(...)`
  - `rank_app_integrations(...)`
  - `register_new_app(...)`
  - `execute_new_app_workflow(...)`
  - `list_registered_new_apps(...)`
  - `get_registered_new_app(...)`
- Added cache cleanup hook to `DeviceService.clear_in_memory_state()`.

### 2.4 REST API Endpoints ([`router.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/router.py))
- `POST /api/v1/devices/{device_id}/new-app/workflow`
- `POST /api/v1/devices/{device_id}/new-app/detect`
- `POST /api/v1/devices/{device_id}/new-app/introspect`
- `POST /api/v1/devices/{device_id}/new-app/rank`
- `POST /api/v1/devices/{device_id}/new-app/register`
- `GET  /api/v1/devices/{device_id}/new-app/registered`
- `GET  /api/v1/devices/{device_id}/new-app/registered/{app_name}`

---

## 3. Universal Integration Priority Hierarchy (Tiers 1-11)

The ranking engine classifies and sorts discovered pathways according to the strict priority table:

| Tier | Integration Type | Description | Default Confidence | Typical Latency | Risk Level |
|:---:|:---|:---|:---:|:---:|:---:|
| **1** | `connector` | Cloud Connector / Official REST API | 0.95 | ~150ms | LOW |
| **2** | `mcp` | MCP Tool / Server Endpoint | 0.92 | ~200ms | LOW |
| **3** | `cli` | CLI Binary Subcommand / Tool | 0.90 | ~100ms | LOW |
| **4** | `app_intent` / `shortcut` | Apple App Intent / Siri Shortcut | 0.88 | ~250ms | LOW |
| **5** | `deep_link` / `universal_link` | Custom URL Scheme / Universal Link | 0.82 | ~300ms | LOW |
| **6** | `intent` | Android Explicit / Implicit Intent | 0.80 | ~350ms | MEDIUM |
| **7** | `share_sheet` | System Share Sheet Target | 0.72 | ~400ms | MEDIUM |
| **8** | `protocol_rpc` | Local TCP/IPC Protocol Port | 0.70 | ~120ms | MEDIUM |
| **9** | `desktop_ui` | Desktop Accessibility / UI Automation | 0.65 | ~800ms | MEDIUM |
| **10** | `mobile_ui` | Mobile UI Automation (Zero Sim Guard) | 0.50 | ~1200ms | HIGH |
| **11** | `process_lifecycle` | OS Process Launch / Terminate Fallback | 0.40 | ~500ms | MEDIUM |

---

## 4. Verification and Test Results

### 4.1 Dedicated Phase 14 Test Suite ([`test_phase14_new_app_workflow.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/tests/test_phase14_new_app_workflow.py))
The dedicated suite tests all capabilities, surface inspections, live synthesized tool executions, service methods, and FastAPI endpoints:

| Test Name | Focus Area | Status |
|:---|:---|:---:|
| `test_detection_new_vs_existing_app` | Canonical name normalization & novelty check | **PASSED** |
| `test_detection_trigger_origins` | Verification across all 4 detection triggers | **PASSED** |
| `test_detection_real_binary_resolution` | Real executable path resolution via PATH | **PASSED** |
| `test_detection_mobile_package_identification` | Mobile package identifier resolution | **PASSED** |
| `test_introspection_real_cli_binary` | Dynamic CLI argument and subcommand probing | **PASSED** |
| `test_introspection_cloud_connector_catalog_match` | Cloud connector catalog capability discovery | **PASSED** |
| `test_introspection_mobile_catalog_match` | Mobile deep links, intents, and permissions discovery | **PASSED** |
| `test_introspection_desktop_ui_controls` | Desktop automation engine control introspection | **PASSED** |
| `test_ranking_priority_hierarchy_connector_first` | Verification of Tier 1 connector precedence | **PASSED** |
| `test_ranking_cli_preferred_over_ui` | Verification of Tier 3 CLI precedence over Tier 9 UI | **PASSED** |
| `test_ranking_user_preference_override` | Caller override elevating preferred pathway | **PASSED** |
| `test_registration_and_tool_synthesis` | Dynamic `AgentTool` synthesis and registry storage | **PASSED** |
| `test_live_execution_of_synthesized_tool` | Direct invocation of synthesized runtime tool | **PASSED** |
| `test_full_workflow_execution` | Complete pipeline (`Detect` -> `Rank` -> `Register` -> `Verify`) | **PASSED** |
| `test_device_service_workflow_tools` | DeviceService integration & tool execution | **PASSED** |
| `test_api_new_app_workflow_endpoint` | FastAPI endpoint `POST /new-app/workflow` | **PASSED** |
| `test_api_sub_endpoints` | FastAPI sub-endpoints (`detect`, `introspect`, `rank`, `register`, `registered`) | **PASSED** |

**Phase 14 Test Suite Results: 17 passed in 39.77s (100% pass rate).**

### 4.2 Regression Test Suite
A regression test run across Phase 14 (`test_phase14_new_app_workflow.py`), Phase 13 (`test_phase13_mobile_discovery.py`), Phase 8 (`test_phase8_integration_resolution.py`), and Phase 7 (`test_phase7_dynamic_capability_discovery.py`) completed successfully:
- **70 passed out of 70 tests in 105.41s (100% pass rate, 0 regressions).**

### 4.3 Static Type Checking and Linting
- **Mypy (`strict = true`)**: `Success: no issues found in 1 source file` (`new_app_workflow.py`).
- **Ruff Linter**: `All checks passed!` across all Phase 14 implementation and test files.

---

## 5. Architectural Compliance & Zero Simulation Doctrine

1. **Zero Simulation Doctrine**:
   - Every binary path check uses real filesystem lookup via `shutil.which`.
   - Protocol port checks execute authentic TCP connection attempts via `socket.create_connection`.
   - CLI introspection executes actual subprocess invocations with timeout guardrails.
   - Dynamic tools synthesized at runtime execute authentic handler functions with parameter validation.
   - Non-destructive verification probes produce authentic execution records and timing measurements.
2. **Dynamic Tool Synthesis**:
   - Unknown applications discoverable at runtime are seamlessly turned into callable `AgentTool` instances accessible by the LLM planner and execution engines.
3. **Multi-Platform Portability**:
   - Uniform API abstraction bridging Windows desktop processes, macOS/Linux binaries, Android packages, and iOS bundles.
