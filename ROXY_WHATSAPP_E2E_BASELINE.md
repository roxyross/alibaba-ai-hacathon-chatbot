# ROXY-AI — WhatsApp Personal Session E2E Baseline Audit

**Document Version:** 1.0.0-BASELINE  
**Audit Date:** October 10, 2026  
**Auditor:** Independent Senior Verification Engineer & Integration Architect  
**Governing Doctrine:** Non-Negotiable Zero-Simulation Doctrine (E0–E5 Hierarchy)  

---

## 1. Executive Summary

This baseline audit inspects the current repository state across backend tools, the Central Tool Registry, the confirmation gatekeeper (`ConfirmationGate`), browser and desktop automation subsystems, and acceptance test suites prior to implementing the controlled personal WhatsApp E2E test.

### Core Findings Matrix

| Capability Area | Existing Implementation Location | Current Status | Proposed Minimal Change |
| :--- | :--- | :--- | :--- |
| **WhatsApp Skill / Tool in Tool Registry** | Not registered in `ToolRegistry`. Intent normalization exists in `backend/src/app/multilingual/normalizer.py`. | **MISSING IN REGISTRY** | Implement dedicated `WhatsAppPersonalIntegrationEngine` and register `whatsapp_send_message` in `ToolRegistry` with `RiskLevel.HIGH` and `requires_confirmation=True`. |
| **`RiskTier.HIGH` & HMAC Approval Flow** | `backend/src/app/trust/confirmation_gate.py` (`ConfirmationGate`) | **PRODUCTION READY** | Bind outbound WhatsApp message actions to `ConfirmationGate` challenge with strict cryptographic HMAC tokens, action payload binding, single-use nonce, and 120s TTL. |
| **Approval UI & Backend Endpoints** | `backend/src/app/trust/router.py`, `frontend/src/components/TrustCenter/ConfirmationGatePanel.tsx` | **PRODUCTION READY** | Leverage existing `/api/v1/trust/confirmations/{id}/resolve` endpoint and Trust Center UI; ensure exact recipient, message text, and risk tier are displayed without truncation. |
| **Browser Automation Adapter** | `backend/src/app/browser/playwright_manager.py` (`PlaywrightBrowserManager`), Playwright `1.63.0` | **AVAILABLE & VERIFIED** | Use `PlaywrightBrowserManager` with visible browser context and isolated profile at `~/.roxy/browser_profiles/whatsapp_personal`. |
| **Windows Desktop UI Automation** | `backend/src/app/device/windows_automation.py` (`WindowsUIAutomationEngine`), `5319275A.WhatsAppDesktop` | **INSTALLED BUT CONFLICT-PRONE** | Select **Browser UI Automation (Playwright)** for official WhatsApp Web (`https://web.whatsapp.com`) to provide reliable DOM selector verification, visible user QR login, and strict recipient matching. |
| **Authenticated Session Handling** | Dedicated persistent profiles in `~/.roxy/browser_profiles` | **UNCONFIGURED FOR WHATSAPP** | Detect authentication state via DOM inspection (`[data-testid='chat-list']` vs `canvas[aria-label='Scan me!']`). Stop and prompt user for manual login if unauthenticated. Never automate QR scanning or steal sessions. |
| **Message Send & Delivery Verification** | None implemented; `test_real_acceptance_scenarios.py` skipped | **MISSING LIVE EXECUTION** | Implement 12-stage workflow: `PREFLIGHT` $\to$ `AUTH_CHECK` $\to$ `RECIPIENT_RESOLUTION` $\to$ `MESSAGE_PREVIEW` $\to$ `AWAITING_APPROVAL` $\to$ `APPROVAL_VALIDATION` $\to$ `SENDING` $\to$ `SEND_ACCEPTANCE_CHECK` $\to$ `DELIVERY_PENDING` $\to$ `AWAITING_RECIPIENT_VERIFICATION` $\to$ `DELIVERED_VERIFIED`. |
| **Section 45 Acceptance Tests** | `backend/tests/test_real_acceptance_scenarios.py` (Scenario 4) | **SKIPPED TRUTHFULLY** | Add comprehensive unit tests, mocked failure-path tests, and an opt-in live E2E test guarded by `ROXY_LIVE_WHATSAPP_E2E=1` and `ROXY_WHATSAPP_TEST_RECIPIENT`. |

---

## 2. Detailed Findings by Audit Domain

### 2.1 WhatsApp Skill / Tool and Tool Registry Registration
- **File Path:** [`backend/src/app/tools/builtin.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/tools/builtin.py), [`backend/src/app/tools/registry.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/tools/registry.py)
- **Current Evidence:**
  Running `ToolRegistry.get_instance().list_tools()` yields 95 registered tools (including `system_email_send`, `browser_navigate`, `file_read`, etc.). No tool with ID `whatsapp_*` is registered.
- **Intent Parsing Status:**
  In [`backend/src/app/multilingual/normalizer.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/multilingual/normalizer.py) (lines 38–40, 290–294), "WhatsApp" / "واٹس ایپ" / "व्हाट्सएप" is normalized to `IntentCategory.APP_CONTROL` with action `"send_message"` and parameters `{"recipient": ..., "message": ..., "app": "WhatsApp"}`.
- **Proposed Minimal Change:**
  Create [`backend/src/app/integrations/whatsapp_personal.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/integrations/whatsapp_personal.py) providing `WhatsAppPersonalIntegrationEngine` and register `whatsapp_send_message` in `ToolRegistry` with:
  - `risk_level`: `RiskLevel.HIGH`
  - `requires_confirmation`: `True`
  - `permissions`: `["messaging:whatsapp:send"]`

---

### 2.2 `RiskTier.HIGH` and HMAC Approval Flow
- **File Path:** [`backend/src/app/trust/confirmation_gate.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/trust/confirmation_gate.py)
- **Relevant Functions:**
  - `ConfirmationGate.create_challenge(...)` (lines 32–102)
  - `ConfirmationGate.resolve_challenge(...)` (lines 149–205)
- **Current Evidence:**
  Generates HMAC-SHA256 challenge tokens using secret key:
  `token_seed = f"{challenge_id}:{user_id}:{action_type}:{int(expires_at.timestamp())}".encode()`.
  Verifies decisions with constant-time `hmac.compare_digest`. Validates 2FA step-up codes for `RiskTier.CRITICAL` or `risk_score >= 85`. Expired challenges are purged via `_cleanup_expired`.
- **Proposed Minimal Change:**
  Enforce that the challenge `details` payload contains:
  ```json
  {
    "app": "WhatsApp",
    "recipient_normalized": "+XXXXXXXXXXX",
    "message_hash": "<sha256_of_message>",
    "run_correlation_id": "<uuid>"
  }
  ```
  Immediately prior to the physical UI send action, re-verify server-side that the approval is in state `APPROVED`, unexpired, matching the exact message text and recipient, and has not been consumed previously (single-use enforcement).

---

### 2.3 Approval UI and Backend Confirmation Endpoint
- **Backend Endpoints:** [`backend/src/app/trust/router.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/trust/router.py)
  - `POST /api/v1/trust/confirmations/create`
  - `GET /api/v1/trust/confirmations/pending`
  - `POST /api/v1/trust/confirmations/{challenge_id}/resolve`
- **Frontend Panel:** [`frontend/src/components/TrustCenter/ConfirmationGatePanel.tsx`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/TrustCenter/ConfirmationGatePanel.tsx)
- **Current Evidence:**
  The frontend Trust Center polls `/api/v1/trust/confirmations/pending` and provides explicit user controls to approve or reject actions.
- **Proposed Minimal Change:**
  Ensure the WhatsApp send challenge format cleanly renders in `ConfirmationGatePanel` with exact recipient, message snippet, and clear warning that one message will be dispatched to the verified test number.

---

### 2.4 Browser Automation and Windows UI Automation Dependencies
- **Browser Automation:**
  - Library: Playwright `1.63.0` installed in `backend/.venv`.
  - Architecture: [`backend/src/app/browser/playwright_manager.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/browser/playwright_manager.py) manages persistent browser profiles in `~/.roxy/browser_profiles`. Tested and passed in `backend/tests/test_phase10_browser_automation.py`.
- **Windows Desktop Automation:**
  - Library: `pywinauto`, `UIAutomationCore.dll`, Win32 `user32.dll`.
  - Package: `5319275A.WhatsAppDesktop` (`Version 2.2639.100.0`) is present in `C:\Program Files\WindowsApps`.
- **Selected Integration Adapter:**
  **Browser UI Automation via Official WhatsApp Web (`https://web.whatsapp.com`)**.
  - **Rationale:** WhatsApp Web runs in a visible Playwright Chromium context with a dedicated profile (`~/.roxy/browser_profiles/whatsapp_personal`), keeping personal browser cookies 100% untouched. It supports deterministic DOM inspection for login status (`[data-testid='chat-list']`), direct conversation opening via `https://web.whatsapp.com/send?phone=<phone>&text=<encoded_text>`, message input box inspection, and outgoing message bubble validation.
  - WhatsApp Desktop UI changes frequently across Windows Store app updates and would require intrusive window-stealing Win32 operations. Browser automation in a visible dedicated context provides total transparency and safety.

---

### 2.5 Authenticated-Session Handling
- **Profile Location:** `Path.home() / ".roxy" / "browser_profiles" / "whatsapp_personal"`
- **Authentication Discovery:**
  - On navigation to `https://web.whatsapp.com`:
    1. Check for `[data-testid='chat-list']` or `#pane-side` $\to$ Authenticated.
    2. Check for `canvas[aria-label='Scan me!']` or `[data-testid='qrcode']` $\to$ Unauthenticated / Login required.
- **Security & Privacy Rules:**
  - **Zero automated QR code processing:** Never capture, decode, or export QR codes.
  - **Zero session file exfiltration:** Profile files stay strictly local in `~/.roxy/browser_profiles/whatsapp_personal`.
  - **Zero scraping of personal messages:** Do not read other chat threads, contacts, or message histories.
  - If unauthenticated, stop immediately and report: `BLOCKED — User manual authentication required on official WhatsApp Web.`

---

### 2.6 Strict Recipient Allowlist
- **Configuration:** Read from environment variable `ROXY_WHATSAPP_TEST_RECIPIENT` (e.g. `+1234567890`).
- **Normalization:** Strip spaces, hyphens, and parentheses; enforce standard E.164 international format (`+` followed by country code and digits).
- **Enforcement Rules:**
  - Exactly **one** recipient allowed.
  - If `ROXY_WHATSAPP_TEST_RECIPIENT` is empty or invalid, fail closed with `BLOCKED`.
  - Rejection of group chats, broadcast lists, unknown phone numbers, or any contact outside the single allowlisted number.
  - Zero hardcoding of real phone numbers in source code, tests, or committed documentation. All committed reports will redact the number (`+XXXXXXXXXXX`).

---

### 2.7 Existing Tests and Acceptance Suites
- **File Path:** [`backend/tests/test_real_acceptance_scenarios.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/tests/test_real_acceptance_scenarios.py)
  - `TestScenario4RealAppActionAndConfirmation` (lines 483–520):
    - `test_unit_intent_normalization`: PASSED
    - `test_integration_confirmation_gate_enforcement`: PASSED
    - `test_real_e2e_whatsapp_delivery_truthful_state`: Currently skips with:
      `Scenario 4 E2E: ENVIRONMENT UNAVAILABLE - No live WhatsApp Web or API credentials configured`
- **Proposed Minimal Change:**
  - Expand `TestScenario4RealAppActionAndConfirmation` with:
    1. Unit tests for recipient allowlist validation, phone normalization, tamper-resistant HMAC payload checks, expired approvals, and duplicate-send prevention.
    2. Dedicated live E2E test `test_real_e2e_whatsapp_controlled_delivery` guarded by `ROXY_LIVE_WHATSAPP_E2E=1` and `ROXY_WHATSAPP_TEST_RECIPIENT`.

---

## 3. Baseline Audit Conclusion

All core foundation primitives (Playwright persistent profile manager, ConfirmationGate with cryptographic HMAC, ToolRegistry, intent normalizer) exist and are verified. The missing element is the dedicated WhatsApp personal integration engine that binds these primitives into the 12-stage controlled workflow.
