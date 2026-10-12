# Privacy Policy for Roxy AI
**Effective Date:** October 13, 2026  
**Last Updated:** October 13, 2026  
**Entity:** Roxy-AI Inc. ("Roxy", "we", "our", or "us")  
**Contact:** privacy@roxy.ai | support@roxy.ai

---

### 1. Introduction
Roxy AI is an autonomous personal AI platform delivering intelligent task orchestration, Code Studio IDE workflows, multi-device automation, and conversational intelligence across Windows, macOS, Linux, Android, iOS, and Web. This Privacy Policy outlines our data handling practices, client-side cryptographic storage, telemetry boundaries, and user rights.

---

### 2. Data We Collect and Store

#### A. Account & Authentication Data
- **Email Address:** Used solely for magic-link passwordless authentication and account identity.
- **Session Tokens:** Cryptographically signed JWT tokens stored securely on your device using OS-native secure enclaves (Windows DPAPI, macOS Keychain, Android EncryptedSharedPreferences, iOS Keychain). Tokens are refreshed securely over TLS 1.3.

#### B. Device Identity & Telemetry
- **Hardware Device ID:** A unique cryptographic pseudonymous identifier generated on your device to associate connected clients (e.g. desktop host workstation, companion phone).
- **Device Metadata:** Device model, OS version, app version, and online/offline status to route agent actions and notifications accurately.
- **System Telemetry:** CPU utilization, memory percentage, and disk capacity are measured locally and transmitted only when authorized by you to facilitate device load balancing.

#### C. User Conversations, Agent Tasks & Code Studio Files
- **Prompts & Instructions:** Processed strictly to generate agent responses and fulfill user-requested automations.
- **Code & Workspace Files:** Processed in sandboxed local environments. We do not inspect private project files or use your proprietary code to train public foundational models without explicit consent.

#### D. Voice & Audio Dictation
- **Microphone Input:** Captured only during an active voice session initiated by you. Audio streams are encrypted in transit and processed for real-time natural speech conversation. Audio buffers are ephemeral and discarded after synthesis.

#### E. Push Notifications & Reminders
- **Push Device Tokens (APNs / FCM):** Collected solely to deliver scheduled reminders, agent completion alerts, and calendar notifications.

---

### 3. Permissions & Platform Restrictions
- **Microphone (`RECORD_AUDIO` / `NSMicrophoneUsageDescription`):** Required exclusively for voice commands and hands-free dictation.
- **Notifications (`POST_NOTIFICATIONS` / `UNUserNotificationCenter`):** Required to deliver scheduled alerts, task progress, and calendar events.
- **Local Device Automation (Desktop Only):** Operating system process management and screen capture are strictly restricted to your local host computer via user confirmation gating (RiskLevel HIGH requires explicit challenge consent).

---

### 4. Data Retention and Deletion
- You maintain complete control over your data.
- **Account Deletion:** You can delete your account, session records, Knowledge Vault documents, and registered devices anytime via the Settings modal or by sending a request to `privacy@roxy.ai`.
- Account deletion executes a hard cascade purge of your stored credentials, memories, tokens, and device bindings across our production clusters within 24 hours.

---

### 5. Third-Party Model Providers
Model inference requests (Google Gemini, Anthropic, DeepSeek, OpenAI) are proxied through secure API connections with zero-retention enterprise terms where supported.

---

### 6. Security Architecture
- End-to-end TLS 1.3 transport security.
- Hardware-backed token encryption at rest.
- Role-based access control and tenant-isolated database models.
- Audited confirmation gating on destructive commands.

---

### 7. Inquiries
If you have questions regarding this Privacy Policy, contact:
- **Email:** `privacy@roxy.ai`
- **Support Portal:** `https://app.roxy.ai/support`
