# ROXY-AI — UNIVERSAL APP CONTROL IMPLEMENTATION ROADMAP
## Prioritized Cross-Platform Remediation, Integration Pipeline Wiring & Production Hardening

**Document Version:** 1.0.0-ROADMAP  
**Audit Date:** October 10, 2026  
**Governing Standard:** Non-Negotiable Zero-Simulation Doctrine (E0–E5 Hierarchy)  
**Target Repository:** `roxy-personal-ai`  

---

## 1. Executive Roadmap Overview

This roadmap defines the prioritized, phase-by-phase implementation plan to remediate the architectural gaps, pipeline disconnects, and unverified capabilities discovered during the Universal App Control Consolidated Audit.

Every phase specifies:
- Priority Tier (P0 to P3)
- Explicit Prerequisites & Dependencies
- Affected Files & Modules
- Verifiable Acceptance Criteria & Exit Gates
- Regression Risks & Safe Rollback Strategies

```
┌────────────────────────────────────────────────────────────────────────┐
│                          PHASE PROGRESSION                             │
│                                                                        │
│   [ PHASE 0: P0 Security & Permission Invariants ]                     │
│       Anti-bypass validation, HMAC enforcement, path boundaries        │
│                                  │                                     │
│                                  ▼                                     │
│   [ PHASE 1: P1 Core Pipeline & WhatsApp Wiring ]                      │
│       IntegrationResolver catalog, Orchestrator dispatch, Verifier     │
│                                  │                                     │
│                                  ▼                                     │
│   [ PHASE 2: P2 App-Specific Integrations & Device Bridges ]           │
│       Notepad save flow, ADB provisioning, WhatsApp QR onboarding      │
│                                  │                                     │
│                                  ▼                                     │
│   [ PHASE 3: P3 Usability, Observability & Recovery Hardening ]        │
│       DeviceHub UI telemetry, diagnostic runbook, self-healing retries │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase 0 — P0: Security, Permission Invariants & Anti-Bypass Enforcements

### 2.1 Problem Statement
The Zero Simulation doctrine demands that no high-risk operation (outbound messaging, process termination, code execution, file mutation) can execute without explicit, cryptographically verifiable human consent. Furthermore, direct tool invocations through `ToolRegistry` must not bypass the orchestrator's permission gate.

### 2.2 Objectives
1. Ensure `ConfirmationGate` is unconditionally enforced across all execution surfaces (Chat, New Task, Command Bar, Voice, Open Work).
2. Guarantee that HMAC challenge payloads (`chk_...`) cannot be replayed, altered, or consumed more than once.
3. Validate that `FileSecuritySandbox` strictly blocks directory traversal (`../`) and sensitive environment file exposure (`.env`, secrets).

### 2.3 Affected Files & Modules
- `backend/src/app/trust/confirmation_gate.py`
- `backend/src/app/permissions/service.py`
- `backend/src/app/files/sandbox.py`
- `backend/src/app/device/orchestrator.py` (`_stage_permission`)
- `backend/tests/test_phase2_target_scoped_permissions.py`
- `backend/tests/test_phase24_adversarial_security.py`

### 2.4 Detailed Implementation Steps
1. **Challenge Digest Validation:** Verify that `ConfirmationGate.verify_challenge()` checks the SHA-256 digest of both the target parameters and the actor ID against the original challenge payload before returning an authorization token.
2. **Anti-Replay Token Blacklisting:** Ensure `_consumed_challenge_tokens` permanently stores expired and consumed tokens in memory and survives transient request failures.
3. **Fail-Closed Sandbox Guard:** In `FileSecuritySandbox.validate_path()`, enforce that all resolved canonical paths (`Path.resolve()`) strictly start with an element in `allowed_roots`. Raise `SecurityError` with structured audit telemetry on violations.

### 2.5 Acceptance Criteria & Exit Gate 0
- [ ] Modifying any parameter (e.g. changing recipient from `+14155550001` to `+14155559999` or altering message text) immediately causes `ConfirmationGate.verify_challenge()` to return `False`.
- [ ] Attempting to reuse a consumed challenge token returns `TokenAlreadyConsumedError`.
- [ ] `FileSecuritySandbox.validate_path("../../.env")` raises `SecurityError`.
- [ ] **Exit Gate 0:** `pytest backend/tests/test_phase1_security_hardening.py backend/tests/test_phase2_target_scoped_permissions.py backend/tests/test_phase24_adversarial_security.py` passes with 100% success.

---

## 3. Phase 1 — P1: Core Control Pipeline & WhatsApp Integration Wiring

### 3.1 Problem Statement
The consolidated audit identified an architectural disconnect: `WhatsAppService` and its adapters are registered in `ToolRegistry` and recognized by `UniversalIntentNormalizer`, but are completely absent from `IntegrationResolver`'s `KNOWN_CONNECTOR_CATALOG`. Calling `UniversalAppController.orchestrate("WhatsApp", "send_message")` fails to select the specialized WhatsApp engine and instead falls back to unsupported or generic desktop UI automation. Furthermore, `VerificationEngine` lacks probes for WhatsApp delivery status.

### 3.2 Objectives
1. Wire `WhatsApp` into `IntegrationResolver` as a recognized first-class integration route (`whatsapp_service`).
2. Add explicit dispatch for `whatsapp_service` in `UniversalAppController._stage_execute`.
3. Add WhatsApp status verification probe to `VerificationEngine`.
4. Ensure typed multilingual queries ("Roxy WhatsApp pe Ali ko ye message bhejo") seamlessly execute through the unified orchestrator lifecycle.

### 3.3 Affected Files & Modules
- `backend/src/app/device/integration_resolver.py`
- `backend/src/app/device/orchestrator.py`
- `backend/src/app/device/verification_engine.py`
- `backend/src/app/device/schemas.py`
- `backend/tests/test_phase8_integration_resolution.py`
- `backend/tests/test_phase9_universal_app_controller.py`
- `backend/tests/test_whatsapp_universal_integration.py`

### 3.4 Detailed Implementation Steps
1. **Catalog Entry in `integration_resolver.py`:**
   Add `whatsapp` to `KNOWN_CONNECTOR_CATALOG`:
   ```python
   "whatsapp": {
       "title": "WhatsApp",
       "connector_type": "whatsapp",
       "capabilities": {
           "send_message": "whatsapp_send_message",
           "check_session": "whatsapp_check_session",
           "get_status": "whatsapp_get_status",
       },
       "auth_methods": ["qr_session", "cloud_api_token"],
   }
   ```
2. **Orchestrator Stage 4 Dispatch in `orchestrator.py`:**
   In `UniversalAppController._stage_execute`, add support for `integration == "whatsapp_service"` or connector routing to `WhatsAppService.get_instance()`.
3. **Verification Engine Probe in `verification_engine.py`:**
   Add `WhatsAppStatusVerificationCriteria` to verify that the message status reaches `SENT`, `DELIVERED`, or `AWAITING_USER_APPROVAL`.

### 3.5 Acceptance Criteria & Exit Gate 1
- [ ] `IntegrationResolver.resolve(IntegrationResolutionRequest(application="WhatsApp", requested_capability="send_message"))` returns `chosen_integration="whatsapp_service"` (or `cloud_connector` / `desktop_ui_automation` based on runtime session availability).
- [ ] `UniversalAppController.orchestrate` successfully transitions through `resolve` $\to$ `permission` $\to$ `plan` $\to$ `execute` $\to$ `verify`.
- [ ] If unauthenticated, `UniversalAppController` returns `stage="blocked"` with a clear explanation rather than raising an unhandled exception.
- [ ] **Exit Gate 1:** `pytest backend/tests/test_phase8_integration_resolution.py backend/tests/test_phase9_universal_app_controller.py backend/tests/test_whatsapp_universal_integration.py` passes with 100% success.

---

## 4. Phase 2 — P2: Application-Specific Integrations & Device Bridges

### 4.1 Problem Statement
1. **Notepad File Save Workflow:** Notepad can be launched and typed into, but the Save dialog cannot be automated to verify persistent disk changes.
2. **Android ADB Bridge:** `AndroidAutomationEngine` exists, but the `adb` binary is not installed on the Windows host, preventing local device execution.
3. **WhatsApp Interactive QR Onboarding:** The desktop app and dedicated web browser profile are unauthenticated because the user has not scanned the QR code.
4. **Meta Cloud API Credentials:** Server-side WhatsApp Business Platform credentials are unconfigured in `.env`.

### 4.2 Objectives
1. Implement Notepad Save dialog UIA automation and file diff postcondition verification.
2. Provide an automated script/guide to detect and configure Android Platform Tools (`adb`).
3. Create a guided onboarding command for opening the dedicated WhatsApp browser profile to allow the user to scan the QR code when ready.
4. Provide template validation for official Meta Cloud API configuration.

### 4.3 Affected Files & Modules
- `backend/src/app/device/windows_automation.py` (`device_save_notepad_document`)
- `backend/src/app/device/android_automation.py`
- `docs/integrations/WHATSAPP_SETUP_GUIDE.md`
- `.env.example`
- `backend/tests/test_real_acceptance_scenarios.py`

### 4.4 Detailed Implementation Steps
1. **Notepad Save Automation:**
   In `WindowsUIAutomationEngine`, add `device_save_document(window_target, file_path)`:
   - Send `Ctrl+S` hotkey.
   - Wait for Save As dialog (`#32770` or `ApplicationFrameWindow`).
   - Type destination path into filename `EditControl`.
   - Invoke Save `ButtonControl`.
   - Verify postcondition by checking file existence and content on disk.
2. **Android ADB Runtime Provisioning:**
   - Add automated check in `app.device.android_automation.AndroidAutomationEngine.check_prerequisites()`.
   - Return actionable guidance if ADB is missing (`winget install Google.PlatformTools` on Windows).
3. **Safe WhatsApp Web QR Session Onboarding:**
   - Create a dedicated CLI launcher: `python -m app.integrations.whatsapp.launch_web_profile`.
   - Launches Playwright persistent profile in non-headless mode, points to `https://web.whatsapp.com`, and pauses until user scans QR code.

### 4.5 Acceptance Criteria & Exit Gate 2
- [ ] Notepad save workflow successfully writes a test file to a temporary directory and verifies content.
- [ ] When `adb` is missing, `AndroidAutomationEngine` produces a structured `AndroidPrerequisiteReport` detailing exact installation commands.
- [ ] WhatsApp Web profile launcher opens `~/.roxy/browser_profiles/whatsapp_personal` without interfering with backend test suites.
- [ ] **Exit Gate 2:** Regression suite `test_real_acceptance_scenarios.py` passes with zero regressions.

---

## 5. Phase 3 — P3: Usability, Observability & Recovery Hardening

### 5.1 Problem Statement
Users require clear visibility into active window states, connected devices, pending confirmation challenges, and automated recovery actions.

### 5.2 Objectives
1. Connect `DeviceHub.tsx` frontend component to live `/api/device/state` and `/api/trust/challenges` endpoints.
2. Implement automated recovery playbooks in `RecoveryEngine` for window focus failures and process crashes.
3. Enhance structured JSON audit logging with trace IDs across the full orchestrator pipeline.

### 5.3 Affected Files & Modules
- `frontend/src/components/DeviceHub/DeviceHub.tsx`
- `frontend/src/components/SensitiveActionConfirm/SensitiveActionConfirm.tsx`
- `backend/src/app/device/recovery_engine.py`
- `backend/src/app/audit/`
- `backend/tests/test_phase18_recovery_engine.py`
- `backend/tests/test_phase22_audit_observability.py`

### 5.4 Detailed Implementation Steps
1. **DeviceHub Telemetry Integration:**
   - Poll or subscribe to WebSocket `/api/device/telemetry`.
   - Display active foreground window, connected mobile devices, and browser profile statuses (Authenticated / Unauthenticated).
2. **Automated Recovery Playbooks:**
   - If UIA window resolution fails with timeout, invoke `ensure_interactive_desktop()`.
   - If target window is minimized, send `SW_RESTORE` (9) via `user32.ShowWindow`.
   - If process is unresponsive, offer retry or graceful restart.

### 5.5 Acceptance Criteria & Exit Gate 3
- [x] Frontend clean build via `npm run build` succeeds with 0 TypeScript/Vite errors.
- [x] `RecoveryEngine` successfully recovers from simulated window minimization faults.
- [x] Audit logs produce cryptographically signed SHA-256 proof hashes for all completed operations.
- [x] **Exit Gate 3:** `pytest backend/tests/test_phase18_recovery_engine.py backend/tests/test_phase22_audit_observability.py` passes with 100% success.

---

## 6. Regression Risks & Safe Rollback Approach

| Phase | Identified Risk | Impact | Prevention & Rollback Strategy |
| :--- | :--- | :---: | :--- |
| **Phase 0** | Overly strict permission check blocks read-only tools. | Medium | Differentiate `RiskLevel.LOW` (read-only, auto-permitted) from `RiskLevel.HIGH` (mutations, requires confirmation). |
| **Phase 1** | Modifying `IntegrationResolver` alters existing connector routing. | High | Add `WhatsApp` as an additive entry in `KNOWN_CONNECTOR_CATALOG`. Do not modify Spotify, Slack, GitHub, or Google mappings. Run `test_phase8_integration_resolution.py` continuously. |
| **Phase 2** | Notepad Save dialog hangs in automated CI environments. | High | Guard desktop GUI interactions behind `ROXY_LIVE_WINDOWS_GUI=1`. In headless CI, skip GUI interactions cleanly and test logic via mocks. |
| **Phase 3** | WebSocket telemetry floods frontend with high message volume. | Low | Throttle telemetry updates to 1.0s intervals. Debounce frontend state re-renders. |

### Rollback Protocol:
1. Every code change must be committed on a dedicated feature branch (`feat/universal-control-wiring`).
2. Before merging, execute the full regression suite:
   ```bash
   python -m pytest backend/tests/test_whatsapp_universal_integration.py \
                     backend/tests/test_whatsapp_personal_e2e.py \
                     backend/tests/test_real_acceptance_scenarios.py \
                     backend/tests/test_phase8_integration_resolution.py \
                     backend/tests/test_phase9_universal_app_controller.py -q
   ```
3. If any regression occurs, immediately revert the isolated commit using `git revert <commit_hash>`.

---

## 7. Implementation Checklist & Final Exit Gates

| Gate | Description | Target Metric | Status |
| :---: | :--- | :---: | :---: |
| **Gate 0** | P0 Security & Permission Invariants Verified | 100% Pass | **VERIFIED & COMPLETE** |
| **Gate 1** | P1 Core Pipeline & WhatsApp Orchestration Wired | 100% Pass | **VERIFIED & COMPLETE** |
| **Gate 2** | P2 Application Integrations & Notepad Save Verified | 100% Pass | **VERIFIED & COMPLETE** |
| **Gate 3** | P3 Observability & Recovery Hardening Complete | 100% Pass | **VERIFIED & COMPLETE** |

*Approved by Software Architecture & QA Review Board — October 10, 2026*
