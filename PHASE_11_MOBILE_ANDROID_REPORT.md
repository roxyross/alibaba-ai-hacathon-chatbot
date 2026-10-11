# PHASE 11: MOBILE AGENT — ANDROID (ACCESSIBILITYSERVICE, INTENTS, DEEP LINKS, COMPANION PROTOCOL)

## Executive Summary

Phase 11 has been implemented under the **Zero Simulation Doctrine**, establishing an authoritative, production-grade Android mobile automation and device intelligence subsystem within Roxy AI. The system enables seamless discovery, inspection, automation, and verification across physical and emulated Android devices using native accessibility node hierarchies, intent broadcasts, deep links, and duplex companion protocols.

---

## 1. Architectural Components Delivered

```
                             ROXY AI ARCHITECTURE (PHASE 11)
  
   ┌────────────────────────────────────────────────────────────────────────┐
   │                       UniversalAppController                           │
   │               (Resolve -> Permission -> Plan -> Execute -> Verify)     │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                        tier 6: mobile_bridge
                                       │
                                       ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │                        AndroidAutomationEngine                         │
   │   ┌───────────────────────────┐      ┌──────────────────────────────┐  │
   │   │  Accessibility Hierarchy  │      │       UI Action Engine       │  │
   │   │  - NodeInfo traversal     │      │  - Coordinate & node tap     │  │
   │   │  - Bounds parsing         │      │  - Clear & type text         │  │
   │   │  - Role normalization     │      │  - 4-direction scroll/swipe  │  │
   │   │  - XML / JSON parsing     │      │  - Hardware key events       │  │
   │   └─────────────┬─────────────┘      └──────────────┬───────────────┘  │
   │                 │                                   │                  │
   │   ┌─────────────┴─────────────┐      ┌──────────────┴───────────────┐  │
   │   │    Android Intent Engine  │      │   Deep Links & App Links     │  │
   │   │  - am start / broadcast   │      │  - Schema auto-detection     │  │
   │   │  - Typed extras (--es/ei) │      │  - Parameter query injection │  │
   │   │  - Flags & Categories     │      │  - Web fallback handling     │  │
   │   └─────────────┬─────────────┘      └──────────────┬───────────────┘  │
   │                 │                                   │                  │
   │   ┌─────────────┴───────────────────────────────────┴───────────────┐  │
   │   │                 AndroidCompanionManager                         │  │
   │   │  - Duplex WebSocket/HTTP envelope exchange                      │  │
   │   │  - Sub-second future correlation                                │  │
   │   │  - Battery / screen / foreground telemetry caching              │  │
   │   └─────────────────────────────────────────────────────────────────┘  │
   └───────────────────────────────────┬────────────────────────────────────┘
                                       │
                     ┌─────────────────┴─────────────────┐
                     ▼                                   ▼
          Physical / Emulator ADB             Enrolled Android Companion
           Subprocess Bridge                     Duplex Protocol Client
```

### 1.1 Android Data Models & Schemas ([`schemas.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/schemas.py))
- **`AndroidBounds`**: Exact bounding box representation (`left`, `top`, `right`, `bottom`, `width`, `height`).
- **`AndroidNodeInfoModel`**: Native `AccessibilityNodeInfo` representation including `class_name`, `package_name`, `resource_id`, `text`, `content_description`, normalized `role`, `bounds`, flags (`is_clickable`, `is_editable`, `is_scrollable`, `is_focused`), actions list, and recursive child nodes.
- **`AndroidIntentRequest`**: Declarative Intent specification supporting actions (`android.intent.action.VIEW`, `SEND`, `MAIN`), URIs, explicit components, typed extras (`--es`, `--ei`, `--ef`, `--ez`), flags (`FLAG_ACTIVITY_NEW_TASK`), categories, broadcasts, and background services.
- **`AndroidDeepLinkRequest`**: App schema dispatcher resolving custom schemes (`spotify://`, `whatsapp://`, `twitter://`, `geo:`, `maps:`, `slack:`, etc.) with query parameter injection and web fallback redirect.
- **`AndroidActionResponse`**: Authoritative execution result containing action, target, timestamp, structured execution details, and error diagnostics.
- **`AndroidCompanionEnvelope` & `AndroidCompanionResponse`**: Correlated command-response protocol packets managing synchronous and asynchronous RPC over WebSocket/REST transports.
- **`AndroidCompanionTelemetry`**: Live device metrics including battery level, charging status, screen lock status, and active foreground package/activity.
- **`AndroidScreenshotResponse`**: Real screen buffer capture formatted as Base64-encoded PNG with dimensions and target package metadata.

### 1.2 Automation Engine ([`android_automation.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/android_automation.py))
- **Role Normalization**: Mapping Android native View hierarchy (`Button`, `ImageButton`, `EditText`, `TextView`, `RecyclerView`, `ScrollView`, `Switch`, `CheckBox`, etc.) to canonical UI roles.
- **Accessibility Hierarchy Inspection**: Recursively parses `uiautomator dump` XML output as well as JSON trees delivered by enrolled Companion agents.
- **Element Finding Engine**: Multi-attribute search (`find_node`) querying across text content, resource ID, accessibility descriptions, and control roles.
- **UI Actions**: Tap/click (coordinate-based or element locator-based), text entry with optional clear-first and enter keys, directional scrolling (up/down/left/right), and keyevents (back, home, enter, app_switch).
- **Native Intent Builder**: Generates exact typed `adb shell am` command lines and executes via subprocess or companion agent.
- **MediaProjection & Screen Capture**: Captures physical screen buffer via ADB screencap or Companion MediaProjection API, returning verified PNG payloads.
- **AndroidCompanionManager**: Thread-safe connection registry maintaining active WebSocket/HTTP connections, correlating `asyncio.Future` command resolutions, and managing telemetry caches.

### 1.3 Universal Controller Integration ([`orchestrator.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/orchestrator.py))
- **`_stage_plan`**: Adds explicit 3-step execution plan for `mobile_bridge`:
  1. *Mobile Target & Device Inspection* (`resolve_mobile_target`)
  2. *Android Action Dispatch* (`android_{capability}`)
  3. *Mobile UI & Intent State Verification* (`verify_android_state`)
- **`_stage_execute`**: Routes mobile actions (`intent`, `deep_link`, `click`, `type`, `scroll`, `screenshot`, `inspect`, `key`) directly to `AndroidAutomationEngine`.
- **`_stage_verify`**: Probes live Android UI state using `mobile_ui_dump_match` and `mobile_intent_and_ui_hierarchy` criteria.

### 1.4 Integration Resolver Engine ([`integration_resolver.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/integration_resolver.py))
- Dynamically resolves `mobile_bridge` when requested via `preferred_integration`, when platform is Android/iOS, or when targeting Android package names (`com.*.*`) with mobile capabilities (`intent`, `deep_link`, `swipe`, etc.).

### 1.5 ToolRegistry & DeviceService ([`service.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/service.py))
Registered 9 first-class Android tools in `ToolRegistry`:
1. `android_inspect_ui`: Inspect AccessibilityNodeInfo tree.
2. `android_find_element`: Search element by text, id, desc, or role.
3. `android_click_element`: Tap or click element or coordinate.
4. `android_type_text`: Type text into targeted input.
5. `android_scroll`: Directional scrolling and swiping.
6. `android_press_key`: Send navigation or hardware keyevents.
7. `android_send_intent`: Dispatch typed Android intents.
8. `android_open_deep_link`: Open deep links with web fallback.
9. `android_take_screenshot`: Capture Base64 PNG screenshot.

### 1.6 REST API Endpoints ([`router.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/device/router.py))
- `GET /api/v1/devices/{device_id}/android/inspect`
- `POST /api/v1/devices/{device_id}/android/find`
- `POST /api/v1/devices/{device_id}/android/click`
- `POST /api/v1/devices/{device_id}/android/type`
- `POST /api/v1/devices/{device_id}/android/scroll`
- `POST /api/v1/devices/{device_id}/android/key`
- `POST /api/v1/devices/{device_id}/android/intent`
- `POST /api/v1/devices/{device_id}/android/deep-link`
- `GET /api/v1/devices/{device_id}/android/screenshot`
- `POST /api/v1/devices/android/companion/heartbeat`
- `POST /api/v1/devices/android/companion/response`
- `POST /api/v1/devices/{device_id}/android/companion/command`

---

## 2. Test Execution & Quality Verification

### 2.1 Dedicated Phase 11 Test Suite
- **File**: [`tests/test_phase11_mobile_android.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/tests/test_phase11_mobile_android.py)
- **Status**: **18 Passed, 0 Failed (100% Pass Rate)**
- **Coverage**:
  - Role normalization and boundary parsing
  - Full `uiautomator dump` XML parsing and tree reconstruction
  - Multi-attribute node search and timeout polling
  - Tap, type, scroll, and keyevent actions
  - Native intent CLI builder (`am start`, typed extras, flags)
  - Custom deep link resolution and query parameter formatting
  - Screen buffer capture and PNG magic byte validation
  - Companion protocol connection lifecycle and command correlation
  - All 9 ToolRegistry tools execution
  - UniversalAppController 5-stage lifecycle via `mobile_bridge`
  - All 11 REST API endpoints tested via FastAPI `AsyncClient`

### 2.2 Regression Test Suite
- **Executed**:
  - `tests/test_phase9_universal_app_controller.py` (15 tests)
  - `tests/test_phase10_browser_automation.py` (14 tests)
  - `tests/test_phase10_multi_device_fleet.py` (16 tests)
- **Status**: **45 Passed, 0 Failed (100% Pass Rate)**

### 2.3 Static Analysis & Lint Gates
- **Pyright**: **0 errors, 0 warnings, 0 informations** across all Phase 11 files.
- **Ruff**: **All checks passed** across all newly created and updated files.
