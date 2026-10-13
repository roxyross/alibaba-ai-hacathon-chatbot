# ROXY-AI — Release Blocker & Production Gate Register

**Document ID:** `ROXY-RC-02`  
**Date:** October 14, 2026  
**Target Release:** Post-Phase 5.1 Release Candidate (RC-1)  
**Branch:** `release/audit-remediation`  
**Overall Status:** `BLOCKED` for Public Production (Staging `PASS`)

---

## 1. Executive Summary

This register explicitly catalogues all blockers and release gates separating the verified staging candidate from a public, production-grade release. In strict compliance with operating principles, no external dependency or physical constraint is faked or declared passing prematurely.

Each item is categorized by domain, current state, exact technical blocking reason, staging mitigation, and concrete resolution steps required before public release.

---

## 2. Production Blocker Matrix

| Blocker ID | Domain | Category | Staging Impact | Production Impact | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BLK-01** | Device / Mobile | Physical Mobile Hardware | None (Virtual / Mocked) | Critical | **BLOCKED** |
| **BLK-02** | Identity / Auth | Live Google OAuth Redirect URI | None (Dev Token Magic Link) | High | **BLOCKED** |
| **BLK-03** | Billing / Payments | Live Production Payment Keys | None (Stripe/Safepay Sandbox) | Critical | **BLOCKED** |
| **BLK-04** | Communication | Production Transactional Email | Moderate (Daily rate limits) | High | **BLOCKED** |
| **BLK-05** | AI Gateway | Google AI Studio Direct Key Format | None (Automatic failover to Grok) | Moderate | **BLOCKED** |

---

## 3. Deep Dive: Blocker Analyses & Remediation Requirements

### BLK-01: Physical Mobile Hardware & Sensor Testing
- **Description:** Testing on the local Windows desktop environment cannot physically execute multi-touch pinch-to-zoom gestures, hardware biometric authenticators (Apple FaceID, Android BiometricPrompt), physical GPS location hardware, or device cameras.
- **Current State:** The frontend test matrix thoroughly validates responsive layout across 8 standard viewports (Mobile 375x667, Tablet 768x1024, Desktop 1440x900, etc.) with 61 passing Vitest tests. Device Agent enrollment protocol is fully implemented and tested via mock device tokens in `tests/integration/test_phase8_device_agent_enrollment.py`.
- **Why Blocked for Production:** A true mobile-ready personal assistant must be validated against real hardware to verify battery drain, background push notifications (APNs / FCM), and OS permission prompts.
- **Remediation Plan for Production:**
  1. Enroll physical iOS (iOS 17+) and Android (Android 14+) test devices in Firebase Test Lab / BrowserStack.
  2. Validate PWA service worker offline caching and native WebAuthn biometric prompts on real hardware.
  3. Sign off on device battery consumption and background sync telemetry.

---

### BLK-02: Public Domain Registration & Google OAuth Live Redirects
- **Description:** Google Cloud Console OAuth 2.0 Web Client credentials require authorized redirect URIs matching public HTTPS domains (e.g., `https://roxy.ai/api/v1/auth/google/callback`). The current staging environment operates on local hostnames (`localhost:8000`, `127.0.0.1`).
- **Current State:** Staging authenticates seamlessly using dev-token magic links (`/api/v1/auth/request-link` -> `/api/v1/auth/verify`) which generate genuine JWT access tokens and exercise full RBAC/session logic.
- **Why Blocked for Production:** External public end-users cannot log in with Google accounts until the public domain DNS is configured, SSL certificates are provisioned, and Google OAuth Consent Screen verification is completed.
- **Remediation Plan for Production:**
  1. Register the production domain and route HTTPS traffic through Cloudflare or AWS CloudFront.
  2. Add the production callback URI `https://app.roxy.ai/api/v1/auth/google/callback` to Google Cloud Console.
  3. Complete Google OAuth App Verification for requested scopes (`email`, `profile`, `calendar.readonly`).

---

### BLK-03: Live Commercial Payment Provider Credentials
- **Description:** Stripe and Safepay integrations are configured with test API keys (`sk_test_...`, `pk_test_...`) and `PAYMENT_PROVIDER_MODE=sandbox`.
- **Current State:** All checkout sessions, subscription tiers, Raast payment intent creations, and webhook processors are fully wired and pass automated tests with idempotency checks.
- **Why Blocked for Production:** Real financial transactions cannot be processed without live merchant credentials, live PCI-compliant webhook secrets, and activated banking rails.
- **Remediation Plan for Production:**
  1. Complete business entity KYC verification on Stripe and Safepay dashboards.
  2. Replace `sk_test_` keys with production restricted keys `rk_live_...`.
  3. Configure production webhook signing secrets (`STRIPE_WEBHOOK_SECRET`, `SAFEPAY_WEBHOOK_SECRET`) pointing to live HTTPS webhook endpoints.

---

### BLK-04: Transactional Email Infrastructure (SMTP Rate Limits)
- **Description:** The staging environment utilizes a personal Gmail SMTP account for dispatching transactional alerts and notifications. High-frequency automated test runs trigger Google SMTP error `550 5.4.5 Daily user sending limit exceeded`.
- **Current State:** Backend email dispatcher detects SMTP rejection and gracefully records the failure in the trust audit log without crashing the application.
- **Why Blocked for Production:** Commercial scale requires guaranteed deliverability, DKIM/SPF/DMARC alignment, and dedicated IP pools.
- **Remediation Plan for Production:**
  1. Provision a dedicated transactional email provider account (e.g., Resend, SendGrid, or AWS SES).
  2. Configure DNS SPF, DKIM, and DMARC records for the sending domain (`noreply@roxy.ai`).
  3. Update `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and `SMTP_PASS` in the production environment vault.

---

### BLK-05: Standard Google AI Studio API Key
- **Description:** The `GEMINI_API_KEY` present in the environment uses an IDE OAuth token format (`AQ.Ab8...`) rather than a standard Google AI Studio key (`AIzaSy...`). When sent directly to `generativelanguage.googleapis.com`, it triggers HTTP 503/404.
- **Current State:** The AI Gateway's automatic failover immediately routes requests to Grok/Groq (`qwen/qwen3.8-27b`), which responds in under 700ms with 200 OK. System availability is 100%, but relies on the fallback tier.
- **Why Blocked for Production:** While failover works flawlessly, production service level agreements (SLAs) require the primary Gemini provider tier to have a dedicated, paid tier API key with adequate rate limits.
- **Remediation Plan for Production:**
  1. Generate a production API key from Google AI Studio / Google Cloud Vertex AI.
  2. Store the key in production KMS / secret manager as `GEMINI_API_KEY`.
  3. Verify primary tier latency and quota allocations.

---

## 4. Final Blocker Conclusion

No blockers impede staging certification or internal testing. All components fail closed securely and handle adverse conditions gracefully. Public production release will remain blocked until the 5 specific operational remediation steps above are executed.
