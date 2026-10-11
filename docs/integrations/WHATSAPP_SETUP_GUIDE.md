# ROXY-AI Universal WhatsApp Integration Setup Guide
**Document ID:** `docs/integrations/WHATSAPP_SETUP_GUIDE.md`  
**Target System:** ROXY-AI Universal App Control  
**Channels:** WhatsApp Desktop (Windows 11 UWP), WhatsApp Web (Playwright), Official Cloud API (Meta Graph API v21.0)

---

## 1. Architecture Overview

ROXY-AI provides a multi-route WhatsApp messaging engine orchestrated by `WhatsAppService`. Routes are selected via runtime negotiation based on user preference and authenticated availability:

| Route | Implementation Base | Best Suited For | Prerequisites |
| :--- | :--- | :--- | :--- |
| **Official Cloud API** | Meta Graph API v21.0 client | Production business messaging, templates, webhooks | Meta Developer App, Phone Number ID, Access Token |
| **WhatsApp Desktop** | Windows 11 UWP (`5319275A.WhatsAppDesktop`) + UI Automation | Personal desktop workflows, interactive local UI | Windows 11, installed UWP app, signed-in session |
| **WhatsApp Web** | Isolated Playwright Chromium profile (`~/.roxy/browser_profiles/whatsapp_personal`) | Personal browser workflows without desktop app | Playwright Chromium, human-scanned QR session |

---

## 2. Environment Variables & Configuration

Configure the following variables in `.env` (or pass via environment):

```bash
# -----------------------------------------------------------------------------
# 1. Universal WhatsApp Core & Safety Controls
# -----------------------------------------------------------------------------
WHATSAPP_INTEGRATION_ENABLED=true
# Test allowlist: exactly one or more approved test recipients in E.164 format (+country digits)
ROXY_WHATSAPP_TEST_RECIPIENT=+14155552671
WHATSAPP_TEST_RECIPIENT_ALLOWLIST=+14155552671,+447911123456

# Optional live desktop GUI automation opt-in (required for real physical UI clicking)
ROXY_LIVE_WHATSAPP_GUI=0

# -----------------------------------------------------------------------------
# 2. Official WhatsApp Business Platform Cloud API (Optional)
# -----------------------------------------------------------------------------
WHATSAPP_API_ENABLED=false
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_TEST_MODE=true
```

> [!IMPORTANT]
> **Zero Simulation Security Rule:**  
> If `ROXY_WHATSAPP_TEST_RECIPIENT` is unset, all outbound message attempts fail closed immediately with `BLOCKED: No test recipient allowlist configured`.

---

## 3. Route Setup Instructions

### 3.1 WhatsApp Desktop (Windows 11)
1. **Installation:**
   Install WhatsApp Desktop from the official Microsoft Store:
   - Package Identity: `5319275A.WhatsAppDesktop`
   - AppID: `5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App`
2. **Authentication:**
   - Launch WhatsApp Desktop manually from the Windows Start menu.
   - On your mobile device, open WhatsApp $\to$ **Settings** $\to$ **Linked Devices** $\to$ **Link a Device**.
   - Scan the on-screen QR code. Ensure your chats load and the interface is interactive.
3. **Verification:**
   Run the session check via Roxy:
   ```bash
   python -c "import asyncio; from app.integrations.whatsapp.service import WhatsAppService; print(asyncio.run(WhatsAppService.get_instance().desktop_adapter.get_connection_status()))"
   ```

### 3.2 WhatsApp Web (Dedicated Browser Profile)
1. **Dedicated Profile Directory:**
   ROXY stores WhatsApp Web credentials in an isolated local directory:
   `C:\Users\<USER>\.roxy\browser_profiles\whatsapp_personal`
2. **Initial One-Time QR Login via Dedicated Launcher:**
   - Launch the dedicated WhatsApp Web profile launcher in interactive mode:
     ```bash
     python -m app.integrations.whatsapp.launch_web_profile
     ```
   - Check current profile session status without opening a browser:
     ```bash
     python -m app.integrations.whatsapp.launch_web_profile --check-status
     ```
   - Perform a non-destructive dry-run validation:
     ```bash
     python -m app.integrations.whatsapp.launch_web_profile --dry-run
     ```
   - On the opened browser window (`https://web.whatsapp.com`), scan the QR code using your phone.
   - Once your chats appear, the session is securely saved in `~/.roxy/browser_profiles/whatsapp_personal`.
3. **Security Safeguards:**
   ROXY never extracts session tokens, injects scripts, or exports cookies. All interactions use native DOM selectors in the user's authorized browser context.

### 3.3 Official WhatsApp Business Platform Cloud API
1. **Meta Developer Portal Setup:**
   - Navigate to [developers.facebook.com](https://developers.facebook.com/) and register or log in.
   - Create a business app with the **WhatsApp** product added.
2. **Retrieve API Credentials:**
   - Navigate to **WhatsApp** $\to$ **API Setup**.
   - Copy the **Phone number ID** into `WHATSAPP_PHONE_NUMBER_ID`.
   - Copy the **WhatsApp Business Account ID** into `WHATSAPP_BUSINESS_ACCOUNT_ID`.
   - Generate a permanent System User Access Token with `whatsapp_business_messaging` permission and set `WHATSAPP_ACCESS_TOKEN`.
   - In **App settings** $\to$ **Basic**, copy the **App secret** into `WHATSAPP_APP_SECRET`.
3. **Configure Webhook:**
   - Under WhatsApp $\to$ Configuration, set the Callback URL:
     `https://your-roxy-domain/api/v1/integrations/whatsapp/webhook`
   - Set the Verify Token matching `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
   - Subscribe to the `messages` webhook field.

---

## 4. Usage Workflow Across Roxy Surfaces

### 4.1 Chat Window & Voice Commands
Users can interact naturally in English or Roman Urdu:
- *"Roxy, check whether WhatsApp is connected."*
- *"Roxy, WhatsApp kholo."*
- *"Draft a WhatsApp message to my test contact."*
- *"Message bhejne se pehle mujhe dikhao."*
- *"Send this approved message through WhatsApp Desktop."*
- *"Use WhatsApp Web for this action."*
- *"Abhi message send mat karna."*

### 4.2 Human-in-the-Loop Confirmation
Before any message is physically transmitted:
1. Roxy displays the `SensitiveActionConfirm` modal dialog.
2. The dialog lists:
   - Recipient (redacted, e.g. `+14*****267`)
   - Exact message text
   - Selected route (`desktop`, `web`, `cloud_api`)
   - Single-use challenge token (`chk_...`)
3. Clicking **⚡ Confirm & Execute** signs the request. Any alteration of recipient, text, or route immediately invalidates the HMAC signature.

---

## 5. Troubleshooting & Diagnostics

| Symptom | Root Cause | Remediation |
| :--- | :--- | :--- |
| `BLOCKED: No test recipient allowlist configured` | `ROXY_WHATSAPP_TEST_RECIPIENT` is empty in `.env` | Add your verified second phone number in international format (+E.164). |
| `REJECTED: Recipient not in approved allowlist` | Attempted to message an unverified number | Add number to `WHATSAPP_TEST_RECIPIENT_ALLOWLIST` or use configured test number. |
| `BLOCKED: WhatsApp Desktop is not running` | Desktop application process is closed | Start WhatsApp Desktop on Windows 11 and verify chats load. |
| `BLOCKED: WhatsApp Web profile is empty` | QR code has not been scanned in `whatsapp_personal` | Follow Section 3.2 to perform one-time QR login. |
| `REJECTED: Send challenge token already consumed` | Replay or duplicate send detected | Each send requires a fresh ConfirmationGate approval challenge. |
| `BLOCKED: Live desktop GUI automation requires opt-in` | `ROXY_LIVE_WHATSAPP_GUI=0` | Set `ROXY_LIVE_WHATSAPP_GUI=1` in environment to enable physical UI clicks. |
