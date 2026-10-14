# ROXY-AI — Consolidated Production Blocker & Exit Gate Register

**Document ID:** `ROXY-CBC-02-REV2`  
**Date:** October 14, 2026  
**Target Release:** Consolidated Launch Candidate (LC-1)  
**Branch:** `release/audit-remediation`  

---

## 1. Blocker Inventory & Status Overview

| Blocker ID | Gate Reference | Title | Severity | Staging Status | Production Status | Owner / Prerequisite |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **BLK-01** | `GATE-01-PHYSICAL-MOBILE` | Physical iOS & Android Hardware Verification | Critical | **PASS (VIRTUAL)** | **BLOCKED** | Mobile QA / Physical Lab |
| **BLK-02** | `GATE-02-DOMAIN-OAUTH` | Production Domain DNS & Google OAuth Callback | High | **PASS (DEV TOKEN)** | **BLOCKED** | DevOps / Google Cloud Console |
| **BLK-03** | `GATE-03-PAYMENTS` | Live Commercial Payment Provider Credentials | Critical | **PASS (SANDBOX)** | **BLOCKED** | Finance / Stripe & Safepay KYC |
| **BLK-04** | `GATE-04-TRANSACTIONAL-EMAIL`| Dedicated Transactional Email Provider (SES/Resend)| High | **PASS (SMTP)** | **BLOCKED** | SRE / Domain DNS SPF & DKIM |
| **BLK-05** | `GATE-05-GEMINI-CAPACITY` | Google AI Studio Dedicated Paid-Tier API Key | High | **PASS (FAILOVER)**| **BLOCKED** | Operations / Google AI Studio |
| **BLK-06** | `INTERNAL-CODE-TYPING` | Alembic Inspector None Type Annotation Mismatch | High | **RESOLVED (PASS)**| **RESOLVED (PASS)**| Software Architect |
| **SEC-01** | `INTERNAL-SEC-JWT` | JWT Dev Secret Fallback & Permissive Claims | Critical | **RESOLVED (PASS)**| **RESOLVED (PASS)**| AppSec / Backend |
| **SEC-02** | `INTERNAL-SEC-DEMO` | Public Demo Login Endpoint Authentication Bypass | Critical | **RESOLVED (PASS)**| **RESOLVED (PASS)**| AppSec / Backend |
| **SEC-03** | `INTERNAL-SEC-OAUTH-STATE`| OAuth State Signature Fallback & Replay Attack | Critical | **RESOLVED (PASS)**| **RESOLVED (PASS)**| AppSec / OAuth Architect |
| **SEC-04** | `INTERNAL-SEC-REDIRECT` | OAuth Redirect Destination Open Redirection | High | **RESOLVED (PASS)**| **RESOLVED (PASS)**| AppSec / OAuth Architect |
| **SEC-05** | `INTERNAL-SEC-CONFIRM` | Sensitive-Action Confirmation Gate Bypass | High | **RESOLVED (PASS)**| **RESOLVED (PASS)**| AppSec / Backend |
| **SEC-06** | `INTERNAL-SEC-TOKEN-ENC`| Plaintext Gmail OAuth Token File Persistence | Medium | **RESOLVED (PASS)**| **RESOLVED (PASS)**| AppSec / Backend |
| **GW-01** | `INTERNAL-AI-ROUTING` | Groq vs Grok Provider Disambiguation & Adapter | Medium | **RESOLVED (PASS)**| **RESOLVED (PASS)**| AI Gateway Architect |

---

## 2. Exhaustive Blocker Dossiers (External Production Gates)

### BLK-01: Physical Mobile Hardware & Sensor Testing
- **Gate:** `GATE-01-PHYSICAL-MOBILE`
- **Severity:** Release-Critical for native mobile launch; Non-blocking for web staging.
- **Affected Subsystem:** Mobile PWA, Web Audio recording, responsive orientation, native biometrics.
- **Reproduction / Constraint:** Local test runner runs on Windows desktop (`win32`, Python 3.14). Desktop runners cannot physically execute touch pinch-to-zoom gestures, physical camera capture, or native biometric prompts (`BiometricPrompt` on Android, `LocalAuthentication` on iOS).
- **Evidence Gathered:**
  - Frontend Vitest suite executes `viewportMatrix.test.ts` (8 passing tests across mobile, tablet, and desktop viewports).
  - PWA manifest (`manifest.json`) and service worker offline caching verified.
- **Code Remediation Performed:** Hardened responsive CSS safe-area padding and implemented graceful permission denial fallbacks in `src/platform/PlatformBridge.ts`.
- **Remaining External Prerequisite:** Access to physical test devices (iPhone 15 running iOS 17+, Samsung Galaxy S24 running Android 14+) or cloud lab sessions via BrowserStack / Firebase Test Lab.
- **Exact Closure Criteria:**
  1. Complete end-to-end interactive voice session on a physical iPhone and Android phone.
  2. Verify microphone permission prompt grant, denial, and re-request lifecycle.
  3. Validate push notification token delivery via APNs / FCM.
- **Status:** **BLOCKED — DEVICE ACCESS REQUIRED**

---

### BLK-02: Public Domain DNS & Live Google OAuth Redirect URI
- **Gate:** `GATE-02-DOMAIN-OAUTH`
- **Severity:** High (External User Onboarding).
- **Affected Subsystem:** Authentication service (`app.auth`), Google OAuth router.
- **Reproduction / Constraint:** Google OAuth 2.0 Web Client policies require callback URIs to match publicly reachable HTTPS origins or `localhost`. Interactive user logins on a public domain require registered DNS, TLS termination, and Google Cloud Console authorization.
- **Evidence Gathered:**
  - Automated suite `test_auth_redirect_security.py` and `test_auth_oauth_state_security.py` validate cryptographic state generation, CSRF protection, and token exchange.
  - Development token magic-link engine (`/api/v1/auth/request-link`) fully functional for staging testing.
- **Code Remediation Performed:** Hardened `app/auth/router.py` and `app/auth/oauth_state.py` to prevent open redirects, state replaying, and secret fallback.
- **Remaining External Prerequisite:**
  1. Domain registration and DNS record configuration (e.g., `app.roxy.ai`).
  2. Google Cloud Console update adding `https://<backend-domain>/api/v1/auth/oauth/google/callback` to Authorized Redirect URIs.
  3. Completion of OAuth Consent Screen verification for sensitive scopes.
- **Exact Closure Criteria:** Successful end-to-end interactive login by an unwhitelisted Google account on `https://app.roxy.ai`.
- **Status:** **BLOCKED**

---

### BLK-03: Live Commercial Payment Provider Credentials
- **Gate:** `GATE-03-PAYMENTS`
- **Severity:** Critical (Financial Transactions).
- **Affected Subsystem:** Stripe checkout, Safepay tracker creation, subscription billing.
- **Reproduction / Constraint:** Environment variables `STRIPE_SECRET_KEY` and `SAFEPAY_API_KEY` are currently configured with test sandbox tokens (`sk_test_...`). Real financial charges cannot be processed without live merchant credentials.
- **Evidence Gathered:**
  - Sandbox checkout session creation and webhook signature validations verified.
  - Non-reversible payments (`raast_payment`) are strictly blocked from the automatic retry queue.
- **Code Remediation Performed:** Hardened idempotency key checking in `app/trust/service.py` to prevent duplicate financial requests.
- **Remaining External Prerequisite:**
  1. Complete merchant entity verification on Stripe and Safepay dashboards.
  2. Replace test API keys with live restricted keys (`rk_live_...`).
  3. Set `PAYMENT_PROVIDER_MODE=live` and configure production webhook endpoints with live signing secrets.
- **Exact Closure Criteria:** A verified $1.00 / PKR 300 test transaction successfully processed, settled, and refunded through live banking rails.
- **Status:** **BLOCKED**

---

### BLK-04: Dedicated Transactional Email Provider (AWS SES / Resend)
- **Gate:** `GATE-04-TRANSACTIONAL-EMAIL`
- **Severity:** High (Deliverability & Scalability).
- **Affected Subsystem:** Email notification service (`app.emails`), magic link delivery.
- **Reproduction / Constraint:** The staging environment connects to a personal Gmail SMTP account. High-frequency automated test execution triggers Google SMTP error `550 5.4.5 Daily user sending limit exceeded`.
- **Evidence Gathered:**
  - Staging dispatcher catches SMTP errors gracefully, records them in the audit log, and marks the task as temporary failure without crashing.
- **Code Remediation Performed:** Added structured logging and fail-closed handling in `app/emails/service.py`.
- **Remaining External Prerequisite:**
  1. Provision AWS SES or Resend transactional email account.
  2. Configure DNS SPF (`v=spf1 include:amazonses.com ~all`), DKIM, and DMARC records for the sending domain.
  3. Update `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and `SMTP_PASS` in production secrets.
- **Exact Closure Criteria:** Inbox delivery of 50 consecutive transactional emails without throttling or spam folder categorization.
- **Status:** **BLOCKED**

---

### BLK-05: Google AI Studio Dedicated Paid-Tier API Key
- **Gate:** `GATE-05-GEMINI-CAPACITY`
- **Severity:** Moderate / Operational.
- **Affected Subsystem:** Multi-provider AI Gateway (`app.ai_gateway`).
- **Reproduction / Constraint:** The current `GEMINI_API_KEY` uses an IDE token format (`AQ.Ab8...`), causing direct calls to `generativelanguage.googleapis.com` to return HTTP 503/404 during high-demand periods.
- **Evidence Gathered:**
  - AI Gateway's automatic failover immediately diverts traffic to Groq (`qwen/qwen3.8-27b`), which responds in 1568ms with HTTP 200 OK. System availability remains 100%.
- **Code Remediation Performed:** Multi-tier failover hierarchy verified in `app/ai_gateway/services/router.py`. Token accounting correctly attributes fallback providers.
- **Remaining External Prerequisite:** Provisioning of a paid Google AI Studio API key (`AIzaSy...`) with sustained production quotas for `gemini-3.8-flash`.
- **Exact Closure Criteria:** 10 consecutive direct generation requests to `gemini-3.8-flash` returning HTTP 200 OK with < 2000ms latency.
- **Status:** **BLOCKED**

---

## 3. Internal Code & Architecture Gates [ALL RESOLVED]

| Blocker ID | Title | File / Subsystem | Resolution Summary | Verification Test Proof |
| :--- | :--- | :--- | :--- | :--- |
| **BLK-06** | Alembic None Check | `alembic/versions/007,008,009,011` | Added `inspector is None` guard and narrowed block scoping | `mypy alembic/versions/` (0 errors) |
| **SEC-01** | JWT Dev Secret Fallback | `app/auth/jwt.py` | Fail closed in prod, pinned HS256, required claims | `test_auth_jwt_security.py` (8/8 pass) |
| **SEC-02** | Public Demo Login | `app/auth/router.py` | Disabled by default, HTTP 403 in prod | `test_auth_demo_security.py` (5/5 pass) |
| **SEC-03** | OAuth State Replay | `app/auth/oauth_state.py` | HMAC verification, thread-safe single-use nonce lock | `test_auth_oauth_state_security.py` (7/7 pass) |
| **SEC-04** | OAuth Open Redirect | `app/auth/router.py` | Strict allowlist origin validation for redirect targets | `test_auth_redirect_security.py` (8/8 pass) |
| **SEC-05** | Sensitive Action Bypass | `app/skills/router.py` | Client `confirm: true` ignored; HMAC token challenge | `test_skills_confirmation_security.py` (5/5 pass) |
| **SEC-06** | Gmail Token Plaintext | `app/skills/email_send.py` | Fernet symmetric authenticated encryption at rest | `test_gmail_token_storage_security.py` (3/3 pass) |
| **GW-01** | Groq vs Grok Routing | `app/ai_gateway/` | Dedicated GroqAdapter, GrokAdapter, priority order | `test_ai_routing_reconciliation.py` (7/7 pass) |
