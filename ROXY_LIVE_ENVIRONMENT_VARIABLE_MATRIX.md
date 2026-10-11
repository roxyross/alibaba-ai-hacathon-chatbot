# ROXY-AI — LIVE ENVIRONMENT VARIABLE MATRIX
**Scope:** Universal App Intelligence, WhatsApp Multi-Route Integration & Android/Mobile Automation  
**Platform:** Windows 11 (NT 10.0.26100 AMD64) | Python 3.14.0 | Node.js v20.18.0  
**Audit Policy:** Zero Simulation Doctrine — Source-Grounded, Non-Invasive, Secret-Free  
**Timestamp:** 2026-10-11T20:45:00+05:00

---

## 1. Executive Summary

This matrix audits all thirteen (13) environment variables governing WhatsApp Multi-Route Integration (Desktop UWP, Web Playwright, and Meta Cloud API) and Mobile Automation (Android ADB & Companion Bridge) in Roxy-AI. Every variable is traced to its exact source-code references, reading processes, default values, runtime effects, and restart policies.

No secret values (tokens, credentials, API keys) are exposed in this document; all values are represented by safe classifications (`CONFIGURED`, `EMPTY`, `PLACEHOLDER`, `SET_BOOLEAN`, or `NOT_SET`).

---

## 2. Master Environment Variable Matrix

| Variable Name | Exact Source Code Reference(s) | Status in Local Environment | Required / Optional | Reading Process | Default Value | Actual Effect on Live Execution | Restart Required? |
|---|---|---|---|---|---|---|---|
| `WHATSAPP_INTEGRATION_ENABLED` | `backend/.env.example:129`, `backend/.env` | `SET_BOOLEAN (true)` | Optional / Feature Toggle | Backend Server (`uvicorn app.main:app`) | `"true"` | Global feature flag documented for deployment orchestration. In the backend, `WhatsAppService` tools are registered dynamically via `builtin.py` and probed on demand by `IntegrationResolver`. | Yes |
| `ROXY_WHATSAPP_TEST_RECIPIENT` | `backend/src/app/integrations/whatsapp/service.py:67`, `backend/src/app/integrations/whatsapp_personal.py:115`, `backend/.env.example:131`, `backend/.env` | `CONFIGURED (+923****63)` | **Required for Live Sending** | Backend Server (`WhatsAppService`, `WhatsAppPersonalIntegrationEngine`) | `""` (Empty string) | **Strict Safety Guard:** Restricts outbound messaging exclusively to the authorized developer test recipient in E.164 format. If missing or recipient differs, immediately fails closed with `BLOCKED: No test recipient allowlist configured` or `REJECTED: Recipient not in approved allowlist`. | Yes (Loaded at startup; read per-call via `os.environ.get`) |
| `WHATSAPP_TEST_RECIPIENT_ALLOWLIST` | `backend/src/app/integrations/whatsapp/service.py:73`, `backend/.env.example:132`, `backend/.env` | `CONFIGURED (+141****71)` | Optional | Backend Server (`WhatsAppService.get_configured_test_recipients()`) | `""` (Empty string) | Supplements `ROXY_WHATSAPP_TEST_RECIPIENT` by accepting a comma-separated list of additional pre-authorized E.164 test recipients. Evaluated during recipient validation. | Yes |
| `ROXY_LIVE_WHATSAPP_GUI` | `backend/src/app/integrations/whatsapp/desktop_adapter.py:31, 242`, `backend/.env.example:135`, `backend/.env` | `SET_BOOLEAN (0)` | **Required Opt-In for Physical GUI** | Backend Server (`WhatsAppDesktopAdapter.send_message()`) | `"0"` (Disabled) | **Physical Desktop Guard:** If not explicitly set to `"1"`, `WhatsAppDesktopAdapter` blocks physical keystrokes/clicks to the Windows desktop, returning `BLOCKED` with code `LIVE_GUI_OPT_IN_REQUIRED`. Prevents accidental mouse/keyboard hijacking during automated testing. | Yes |
| `WHATSAPP_API_ENABLED` | `backend/src/app/integrations/whatsapp/cloud_api_adapter.py:61, 131`, `backend/.env.example:138`, `backend/.env` | `SET_BOOLEAN (false)` | Optional (Route Gate) | Backend Server (`WhatsAppCloudApiAdapter.get_config()`) | `"false"` | Controls whether Meta Business Cloud API route is active. When `false`, connection probe returns `is_ready=False`, details `WhatsApp Cloud API is disabled (set WHATSAPP_API_ENABLED=true)`, preventing HTTP calls to `graph.facebook.com`. | Yes |
| `WHATSAPP_PHONE_NUMBER_ID` | `backend/src/app/integrations/whatsapp/cloud_api_adapter.py:62, 83, 85, 113, 158, 257`, `backend/.env.example:139`, `backend/.env` | `EMPTY` | **Required if Cloud API Enabled** | Backend Server (`WhatsAppCloudApiAdapter`) | `""` (Empty string) | Meta Business Cloud API registered sender Phone Number ID (must be numeric). If empty or non-numeric, `validate_credentials()` records an error and marks connection `NOT_CONFIGURED`. | Yes |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | `backend/src/app/integrations/whatsapp/cloud_api_adapter.py:63, 95`, `backend/.env.example:140`, `backend/.env` | `EMPTY` | Optional | Backend Server (`WhatsAppCloudApiAdapter.get_config()`) | `""` (Empty string) | Meta Business Account ID for WhatsApp Business assets. Validated for numeric format; used in audit logging and multi-tenant telemetry. | Yes |
| `WHATSAPP_ACCESS_TOKEN` | `backend/src/app/integrations/whatsapp/cloud_api_adapter.py:64, 88, 90, 115, 158, 257`, `backend/.env.example:141`, `backend/.env` | `EMPTY` | **Required if Cloud API Enabled** | Backend Server (`WhatsAppCloudApiAdapter.send_message()`) | `""` (Empty string) | System User permanent bearer token passed in HTTP `Authorization: Bearer <TOKEN>` header to Meta Graph API (`v21.0`). Validated for length $\ge 20$ characters. If missing, outbound cloud messaging fails closed with `CONFIG_MISSING`. | Yes |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | `backend/src/app/integrations/whatsapp/cloud_api_adapter.py:65, 185`, `backend/.env.example:142`, `backend/.env` | `EMPTY` | Optional (Required for Webhook Verification) | Backend Server (`WhatsAppCloudApiAdapter.verify_webhook_challenge()`) | `""` (Empty string) | Secret token shared with Meta Developer Portal to verify incoming webhook subscription GET challenge (`hub.verify_token`). | Yes |
| `WHATSAPP_APP_SECRET` | `backend/src/app/integrations/whatsapp/cloud_api_adapter.py:66, 98, 176, 177`, `backend/.env.example:143`, `backend/.env` | `EMPTY` | Optional (Required for Webhook Ingress) | Backend Server (`WhatsAppCloudApiAdapter.verify_webhook_signature()`) | `""` (Empty string) | Meta Application Secret used for constant-time HMAC-SHA256 signature verification on incoming `X-Hub-Signature-256` webhook headers to protect against spoofing. | Yes |
| `WHATSAPP_TEST_MODE` | `backend/src/app/integrations/whatsapp/cloud_api_adapter.py:67`, `backend/.env.example:144`, `backend/.env` | `SET_BOOLEAN (true)` | Optional | Backend Server (`WhatsAppCloudApiAdapter.get_config()`) | `"true"` | When `true`, flags all Cloud API operations with test/sandbox metadata in structured audit trails and prevents charging production SMS/template rates. | Yes |
| `ANDROID_ADB_PATH` | `backend/src/app/device/android_automation.py:225, 233, 271`, `backend/.env.example:150`, `backend/.env` | `NOT_SET` | Optional | Backend Server (`AndroidAutomationEngine.get_adb_path()`) | `None` (Falls back to system `PATH` via `shutil.which("adb")`) | Explicit absolute path to local `adb.exe` executable (e.g. `C:\platform-tools\adb.exe`). Bypasses system `PATH` requirements when custom Android SDK installations are used. | Yes |
| `ANDROID_DEFAULT_DEVICE_ID` | `backend/src/app/device/android_automation.py:874`, `backend/.env.example:152`, `backend/.env` | `NOT_SET` | Optional | Backend Server (`AndroidAutomationEngine.build_adb_am_command()`) | `""` (Auto-selects first attached device) | Target Android device serial or `IP:port` (e.g. `emulator-5554` or `192.168.1.50:5555`). Appends `-s <device_id>` to all dispatched `adb shell am` commands. | Yes |

---

## 3. Detailed Per-Variable Architectural Impact

### 3.1 `WHATSAPP_INTEGRATION_ENABLED`
- **Location:** Defined in `backend/.env.example:129`, loaded via `dotenv` in `backend/src/app/main.py:16`.
- **Purpose:** Top-level deployment flag. Allows container orchestration and staging scripts to declare WhatsApp capability availability.
- **Behavior:** The backend registers `WhatsAppService` tools into `ToolRegistry` during startup (`backend/src/app/tools/builtin.py:609`). The tool registry tags these tools with `ToolSource.BUILTIN` and `RiskLevel.HIGH`.

### 3.2 `ROXY_WHATSAPP_TEST_RECIPIENT`
- **Location:** Read in `service.py:67` and `whatsapp_personal.py:115`.
- **Purpose:** Single primary recipient sandbox constraint under the Zero Simulation Doctrine.
- **Behavior:**
  1. The target phone number is normalized via `WhatsAppBaseAdapter.normalize_phone_number()` (E.164: removes spaces, dashes, parentheses; ensures `+` prefix).
  2. If `ROXY_WHATSAPP_TEST_RECIPIENT` is unset, `validate_recipient_allowlist()` returns:
     `BLOCKED: No test recipient allowlist configured. Set ROXY_WHATSAPP_TEST_RECIPIENT or WHATSAPP_TEST_RECIPIENT_ALLOWLIST in environment.`
  3. If the recipient does not match, the send is rejected **before** generating a confirmation challenge or launching a browser/process.

### 3.3 `WHATSAPP_TEST_RECIPIENT_ALLOWLIST`
- **Location:** Read in `service.py:73`.
- **Purpose:** Extended multi-number allowlist for authorized staging QA teams.
- **Behavior:** Parses comma-separated E.164 strings, normalizes each entry, and merges them with `ROXY_WHATSAPP_TEST_RECIPIENT`. Both entries form the set of permissible targets.

### 3.4 `ROXY_LIVE_WHATSAPP_GUI`
- **Location:** Read in `desktop_adapter.py:31, 242`.
- **Purpose:** Physical GUI safety circuit-breaker on Windows 11.
- **Behavior:**
  - `0` (Default): `WhatsAppDesktopAdapter.send_message()` checks `os.environ.get("ROXY_LIVE_WHATSAPP_GUI") == "1"`. When false, it returns `status=BLOCKED`, `error_code="LIVE_GUI_OPT_IN_REQUIRED"`. No shell execution (`os.startfile`) or UI clicks occur.
  - `1`: Allows the adapter to issue `os.startfile("whatsapp://send?phone=...&text=...")` and dispatch UI Automation clicks/keystrokes to the active WhatsApp window.

### 3.5 `WHATSAPP_API_ENABLED`
- **Location:** Read in `cloud_api_adapter.py:61, 131`.
- **Purpose:** Meta Business Cloud API gateway switch.
- **Behavior:** If `false`, `probe_all_routes()` marks the Cloud API route disabled. Inbound/outbound HTTP operations are prevented.

### 3.6 `WHATSAPP_PHONE_NUMBER_ID` & `WHATSAPP_ACCESS_TOKEN`
- **Location:** Read in `cloud_api_adapter.py:62, 64`.
- **Purpose:** Meta Graph API authentication credentials.
- **Behavior:**
  - `WHATSAPP_PHONE_NUMBER_ID` must be numeric (e.g. `109876543210987`).
  - `WHATSAPP_ACCESS_TOKEN` must be $\ge 20$ chars, typically starting with `EA`.
  - If either is absent, `get_connection_status()` marks `state=NOT_CONFIGURED` with `missing_prerequisites=["WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN"]`.

### 3.7 `ANDROID_ADB_PATH` & `ANDROID_DEFAULT_DEVICE_ID`
- **Location:** Read in `android_automation.py:225, 874`.
- **Purpose:** Android Debug Bridge CLI resolution and device targeting.
- **Behavior:**
  - `ANDROID_ADB_PATH`: Checked first in `get_adb_path()`. If it points to an existing file, it is used for all subprocess calls (`devices`, `shell am`, `uiautomator dump`). Otherwise, `shutil.which("adb")` on system `PATH` is used.
  - `ANDROID_DEFAULT_DEVICE_ID`: If set, automatically appends `-s <id>` to all `adb` command executions when `device_id="default"` is requested.

---

## 4. Current Environment State Verification

A live non-invasive environment audit was executed against `backend/.env`:

```
WHATSAPP_INTEGRATION_ENABLED: SET_BOOLEAN (true)
ROXY_WHATSAPP_TEST_RECIPIENT: CONFIGURED (+923****63)
WHATSAPP_TEST_RECIPIENT_ALLOWLIST: CONFIGURED (+141****71)
ROXY_LIVE_WHATSAPP_GUI: SET_BOOLEAN (0)
WHATSAPP_API_ENABLED: SET_BOOLEAN (false)
WHATSAPP_PHONE_NUMBER_ID: EMPTY
WHATSAPP_BUSINESS_ACCOUNT_ID: EMPTY
WHATSAPP_ACCESS_TOKEN: EMPTY
WHATSAPP_WEBHOOK_VERIFY_TOKEN: EMPTY
WHATSAPP_APP_SECRET: EMPTY
WHATSAPP_TEST_MODE: SET_BOOLEAN (true)
ANDROID_ADB_PATH: NOT_SET (Using system PATH fallback)
ANDROID_DEFAULT_DEVICE_ID: NOT_SET (Auto-targeting first device)
```

**Security Observation:** All Cloud API credentials remain safely `EMPTY`. No secrets are exposed or committed to source control.
