# ROXY-AI Universal WhatsApp Acceptance Test Plan
**Document ID:** `docs/testing/WHATSAPP_ACCEPTANCE_TEST_PLAN.md`  
**Execution Lead:** Principal QA Lead & Security Architect  
**Test Suite Target:** `backend/tests/test_whatsapp_universal_integration.py` & `backend/tests/test_whatsapp_personal_e2e.py`

---

## 1. Test Methodology & Boundaries

The WhatsApp integration test plan is partitioned into:
1. **Offline Unit & Security Tests (100% Mocked / Deterministic):**  
   Validates recipient normalization, allowlist enforcement, ConfirmationGate cryptographic binding, single-use anti-replay tokens, route negotiation, and Meta Cloud API request/response parsing.
2. **Offline Webhook & Protocol Tests:**  
   Validates HMAC-SHA256 signature verification and delivery status mapping for Meta Graph API v21.0.
3. **Environment & Discovery Probes:**  
   Inspects host OS (Windows 11 AppX packages, StartApps AppIDs, Playwright browser profile existence).
4. **Live Interactive Acceptance Tests (E0–E5 Truthful Boundary):**  
   Only executed when real external prerequisites (authenticated desktop session, scanned QR code, or live Meta WABA token) are present. Otherwise truthfully reported as `BLOCKED`.

---

## 2. Test Execution Matrix

| Test ID | Test Name | Target Layer | Expected Result | Verified Result |
| :--- | :--- | :--- | :--- | :--- |
| **TC-01** | `test_recipient_normalization_e164` | `WhatsAppBaseAdapter` | Formats dirty phone strings into valid E.164 (`+14155552671`) | **PASS** |
| **TC-02** | `test_recipient_redaction_pii_safety` | `WhatsAppBaseAdapter` | Masks phone digits (`+14*****671`) in logs & diagnostics | **PASS** |
| **TC-03** | `test_allowlist_enforcement` | `WhatsAppService` | Rejects numbers outside allowlist with sanitized error message | **PASS** |
| **TC-04** | `test_challenge_creation_and_approval_binding` | `ConfirmationGate` | Generates HMAC challenge; rejects unapproved sends | **PASS** |
| **TC-05** | `test_approval_tampering_message_changed` | Security Gate | Rejects send if message body is modified after user approval | **PASS** |
| **TC-06** | `test_approval_tampering_recipient_changed` | Security Gate | Rejects send if recipient number is modified after approval | **PASS** |
| **TC-07** | `test_approval_tampering_route_switched` | Security Gate | Rejects send if sending route is switched after approval | **PASS** |
| **TC-08** | `test_single_use_token_anti_replay` | Security Gate | Prevents duplicate sends by invalidating consumed challenge token | **PASS** |
| **TC-09** | `test_desktop_adapter_discovery_not_running` | Desktop Adapter | Detects `5319275A.WhatsAppDesktop` and reports `NOT_RUNNING` | **PASS** |
| **TC-10** | `test_desktop_adapter_unauthenticated_qr` | Desktop Adapter | Distinguishes QR/login screen from authenticated chat window | **PASS** |
| **TC-11** | `test_web_adapter_status_unauthenticated_profile` | Web Adapter | Detects empty Playwright profile and reports `UNAUTHENTICATED` | **PASS** |
| **TC-12** | `test_web_adapter_status_authenticated_profile` | Web Adapter | Detects persistent browser session without extracting secrets | **PASS** |
| **TC-13** | `test_cloud_api_connection_probe_success` | Cloud API Adapter | Probes Meta Graph API v21.0 `/phone_number_id` with Bearer auth | **PASS** |
| **TC-14** | `test_cloud_api_send_message_success` | Cloud API Adapter | Posts E.164 text message payload; extracts provider `wamid` | **PASS** |
| **TC-15** | `test_cloud_api_webhook_signature_verification` | Cloud API Adapter | Validates `X-Hub-Signature-256` HMAC-SHA256 signature | **PASS** |
| **TC-16** | `test_cloud_api_webhook_status_processing` | Cloud API Adapter | Maps `delivered` and `read` statuses to active operation record | **PASS** |
| **TC-17** | `test_service_route_negotiation` | `WhatsAppService` | Automatically negotiates route: Cloud API $\to$ Desktop $\to$ Web | **PASS** |
| **TC-18** | `test_tool_registry_registration` | `ToolRegistry` | Registers `whatsapp_send_message` with `RiskLevel.HIGH` | **PASS** |
| **TC-19** | `test_multilingual_whatsapp_intents` | Intent Normalizer | Parses English & Roman Urdu commands into WhatsApp actions | **PASS** |

---

## 3. Real Acceptance Live Test Runbook

When the user is ready to execute a live real-world physical transmission:

### Step 1: Pre-flight Verification
1. Ensure `ROXY_WHATSAPP_TEST_RECIPIENT` is configured in `.env` with the user's second device.
2. Ensure the chosen channel is signed in:
   - For Desktop: Open WhatsApp Desktop and confirm recent chats are visible.
   - For Web: Open dedicated profile and confirm chats are visible.
   - For Cloud API: Confirm `WHATSAPP_ACCESS_TOKEN` is active.

### Step 2: Command Invocation
Invoke through Roxy Chat or CLI:
```bash
python -c "import asyncio; from app.integrations.whatsapp.service import WhatsAppService; print(asyncio.run(WhatsAppService.get_instance().send_message('user_1', '+14155552671', 'Test message from Roxy', route=WhatsAppRoute.AUTO)))"
```

### Step 3: Confirmation Dialog
Roxy returns `status=WAITING_FOR_APPROVAL` with a unique `challenge_id` (`chk_...`).  
Review the recipient, content, and route. Resolve the challenge via ConfirmationGate.

### Step 4: Verification of Outgoing Evidence
Upon execution:
- Desktop: Outgoing message bubble is verified in the UI tree.
- Web: Outgoing bubble and checkmark (`single_check` / `double_check`) verified.
- Cloud API: Provider `wamid` returned by Meta Graph API.
- Receiving Device: Real human verifies delivery on the physical second phone.
