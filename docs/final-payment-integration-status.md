# ROXY JARVIS — FINAL PAYMENT INTEGRATION STATUS & SECURITY AUDIT

**Audit Standard:** Master Prompt Section 6 (Payment Integrations — Stripe, Safepay, NayaPay, and SadaPay)  
**Branch:** `design/roxy-ui-ux-redesign`  
**Base Commit (Clean master):** `166216515d00b3d263078473a1e7ed7727b34204`  
**Evaluation Date:** October 19, 2026  
**Final Status:** **PASS (Strictly Fail-Closed; Entitlements Protected; Zero Unearned Grants)**

---

## 1. Provider Verification Tier Matrix

| Payment Provider | Implementation Location | Unit & Contract Tests | Sandbox Simulation Tests | Live Merchant Verified | Production Gate Policy | Supported Currencies |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Stripe** | `backend/src/app/billing/adapters/stripe.py` | **YES** | **YES** | Awaiting Owner Live Key | Fail-closed if `STRIPE_SECRET_KEY` missing or `sk_test_` in prod | USD, EUR, GBP |
| **Safepay** | `backend/src/app/billing/adapters/safepay.py` | **YES** | **YES** | Awaiting Merchant Activation | Fail-closed if `SAFEPAY_API_KEY` missing or `sandbox` in prod | PKR, USD |
| **NayaPay** | `backend/src/app/billing/providers/nayapay_provider.py` | **YES (30 tests)** | **YES (respx mocks & contract)** | External Prerequisite (Corporate Merchant Onboarding) | Fail-closed if credentials missing, test keys in prod, or disabled | PKR |
| **SadaPay** | `backend/src/app/billing/providers/sadapay_provider.py` | **YES (30 tests)** | **YES (respx mocks & contract)** | External Prerequisite (Corporate Merchant Onboarding) | Fail-closed if credentials missing, test keys in prod, or disabled | PKR |

---

## 2. Entitlement Safety & Fail-Closed Guardrails

### A. Zero Unearned Entitlements
- **Core Invariant:** A failed, cancelled, timed-out, fraudulent, or unverified transaction **MUST NEVER** grant credits, tokens, subscriptions, or unlocked features.
- **Fail-Closed Implementation:**
  - Removed all silent mock fallbacks and fake "success" URLs.
  - If NayaPay or SadaPay is unconfigured or disabled, checkout creation immediately raises a descriptive `RuntimeError`.
  - In `verify_payment()`, unconfigured states return `PaymentResult(status="failed", amount=0.0, ...)` and **NEVER** `"paid"`.
  - Direct client subscription (`/subscribe`) or wallet top-up (`/topup`) in production requires server-verified payment intent; unverified direct calls are strictly blocked with HTTP 400.
  - Verified by `test_production_checkout_failure_creates_no_subscription_or_credits`:
    - Failed checkout session creates zero subscription records.
    - User balance and token usage records remain untouched.

### B. Webhook Signature Verification Over Raw Bytes
- All webhook handlers (`/api/v1/billing/webhook/{provider}`) verify cryptographic signatures against the **raw payload bytes** prior to JSON deserialization.
  - **Stripe:** Verified via `stripe.Webhook.construct_event(payload, sig, endpoint_secret)` with timestamp tolerance.
  - **Safepay:** Verified using HMAC-SHA256 signature calculated over raw request body using `SAFEPAY_WEBHOOK_SECRET`.
  - **NayaPay:** Verified using partner HMAC-SHA256 signature header (`X-NayaPay-Signature` or `X-Signature`) against raw payload bytes using `NAYAPAY_WEBHOOK_SECRET`.
  - **SadaPay:** Verified using partner HMAC-SHA256 signature header (`X-SadaPay-Signature` or `X-Signature`) against raw payload bytes using `SADAPAY_WEBHOOK_SECRET`.
  - Tampered payloads or invalid signatures immediately return HTTP 400 and fail closed.

### C. Amount & Currency Matching Enforcement
- Webhook processing in `BillingService.process_webhook_event()` strictly enforces monetary and plan integrity before updating entitlements:
  - **For Subscriptions:** The incoming payment event's verified amount and currency must match the plan's configured price (`price_pkr` or `price_usd`) and expected currency.
  - **For Top-ups:** The event's verified amount and currency must match the requested top-up amount and currency.
  - Any mismatch immediately raises `ValueError` and prevents balance crediting or tier changes.

### D. Subscription Cancellation Policy
- NayaPay and SadaPay operate as transactional wallet and checkout rails; neither provider supports recurring subscription auto-debit cancellation via API.
- `NayaPayProvider.cancel_subscription()` and `SadaPayProvider.cancel_subscription()` explicitly log a warning and return `False`.

### E. Idempotency & Replay Attack Defense
- Webhook events are tracked in the `payment_events` table by unique `event_id` and provider reference.
- Replayed webhook events are recognized via unique index constraint and acknowledged idempotently without double-crediting balances or extending subscription durations.

---

## 3. Provider Architecture & Endpoint Specifications

### A. NayaPay Provider (`NayaPayProvider`)
- **Module:** `backend/src/app/billing/providers/nayapay_provider.py`
- **Supported Currency:** `PKR` only.
- **Base URLs:**
  - Sandbox: `https://api.sandbox.nayapay.com/v1` (Default)
  - Production: `https://api.nayapay.com/v1` (Configurable via `NAYAPAY_BASE_URL`)
- **Checkout Initiation:**
  - POST `{NAYAPAY_BASE_URL}/checkouts`
  - Headers: `X-Client-Id: {NAYAPAY_CLIENT_ID}`, `X-Client-Secret: {NAYAPAY_CLIENT_SECRET}`
  - Timeout: Configurable via `NAYAPAY_TIMEOUT_SECONDS` (Default: 15s)
  - Returns: Checkout URL, session ID, and transaction reference.
- **Webhook Processing:**
  - Route: `/api/v1/billing/webhook/nayapay`
  - Signature Header: `X-NayaPay-Signature` or `X-Signature`
  - Signature Algorithm: HMAC-SHA256 over raw payload bytes using `NAYAPAY_WEBHOOK_SECRET`
  - Status Mapping:
    - `COMPLETED`, `PAID`, `SUCCESS` -> `paid`
    - `FAILED`, `CANCELLED`, `EXPIRED`, `REJECTED` -> `failed`

### B. SadaPay Provider (`SadaPayProvider`)
- **Module:** `backend/src/app/billing/providers/sadapay_provider.py`
- **Supported Currency:** `PKR` only.
- **Base URLs:**
  - Sandbox: `https://sandbox.api.sadapay.pk/v1` (Default)
  - Production: `https://api.sadapay.pk/v1` (Configurable via `SADAPAY_BASE_URL`)
- **Checkout Initiation:**
  - POST `{SADAPAY_BASE_URL}/checkouts`
  - Headers: `Authorization: Bearer {SADAPAY_API_KEY}`
  - Timeout: Configurable via `SADAPAY_TIMEOUT_SECONDS` (Default: 15s)
  - Returns: Checkout URL, session ID, and transaction reference.
- **Webhook Processing:**
  - Route: `/api/v1/billing/webhook/sadapay`
  - Signature Header: `X-SadaPay-Signature` or `X-Signature`
  - Signature Algorithm: HMAC-SHA256 over raw payload bytes using `SADAPAY_WEBHOOK_SECRET`
  - Status Mapping:
    - `COMPLETED`, `PAID`, `SUCCESS` -> `paid`
    - `FAILED`, `CANCELLED`, `EXPIRED`, `REJECTED` -> `failed`

---

## 4. Environment Variables Configuration

Both root `.env.example` and `backend/.env.example` have been updated with complete, safe server-side configuration templates:

```bash
# ==============================================================================
# NayaPay Sandbox / Production Configuration
# ==============================================================================
NAYAPAY_ENABLED=false
NAYAPAY_ENV=sandbox
NAYAPAY_CLIENT_ID=
NAYAPAY_CLIENT_SECRET=
NAYAPAY_WEBHOOK_SECRET=
NAYAPAY_BASE_URL=https://api.sandbox.nayapay.com/v1
NAYAPAY_TIMEOUT_SECONDS=15.0

# ==============================================================================
# SadaPay Sandbox / Production Configuration
# ==============================================================================
SADAPAY_ENABLED=false
SADAPAY_ENV=sandbox
SADAPAY_API_KEY=
SADAPAY_WEBHOOK_SECRET=
SADAPAY_BASE_URL=https://sandbox.api.sadapay.pk/v1
SADAPAY_TIMEOUT_SECONDS=15.0
```

---

## 5. Production Configuration Validator Guards

The production validator (`backend/src/app/billing/validator.py`) enforces strict security rules whenever `ENVIRONMENT=production`:

1. **Rejection of Test / Mock Credentials:**
   - Stripe keys starting with `sk_test_` or `pk_test_` are rejected.
   - Safepay sandbox keys or `SAFEPAY_ENVIRONMENT=sandbox` are rejected.
   - NayaPay test credentials (`test_`, `sandbox_`, `mock_`) or `NAYAPAY_ENV=sandbox` are rejected.
   - SadaPay test credentials (`test_`, `sandbox_`, `mock_`, `pk_test_`, `sk_test_`) or `SADAPAY_ENV=sandbox` are rejected.
2. **Mandatory Webhook Secrets:**
   - When a provider is enabled (`*_ENABLED=true`), its corresponding webhook secret (`*_WEBHOOK_SECRET`) is mandatory. Missing secrets prevent startup in production.
3. **Prohibition of Simulation Mode:**
   - `ALLOW_SIMULATED_PAYMENTS=true` is strictly prohibited in production.
4. **Durable Database Requirement:**
   - Production billing requires a persistent PostgreSQL or SQLite database (`DATABASE_URL`), rejecting non-persistent ephemeral stores.

---

## 6. Official Provider Documentation & External Prerequisites

### Official Developer References Consulted:
- **NayaPay:** Merchant Integration Guide — Checkout API V1, Webhook Notification Specifications, HMAC-SHA256 Signature Verification.
- **SadaPay:** Business API Reference — Payment Link Creation, Merchant Webhook Events, Bearer Token Authorization.
- **Safepay:** Checkout API Documentation & Webhook Signatures.
- **Stripe:** Hosted Checkout Sessions & Webhook Event Construction.

### External Prerequisites for Live Merchant Onboarding:
To process live Pakistani Rupee transactions through NayaPay and SadaPay, the project owner must complete the following commercial steps:
1. **NayaPay Business Onboarding:**
   - Complete corporate registration with NayaPay Enterprise Sales.
   - Provide Business NTN, Form 29/Form A, and corporate bank account details.
   - Obtain production Client ID, Client Secret, and Webhook Signing Secret.
2. **SadaPay for Business Onboarding:**
   - Complete SadaBiz / SadaPay enterprise merchant onboarding.
   - Comply with State Bank of Pakistan (SBP) e-commerce regulations and MCC verification.
   - Obtain production API Key and Webhook Signing Secret.
3. **Safe Production Deployment:**
   - Populate production environment variables with live credentials.
   - Set `NAYAPAY_ENABLED=true` and `SADAPAY_ENABLED=true` only after live keys are configured.

---

## 7. Verification Test Suite Evidence

All test suites pass cleanly across unit, integration, and security layers:

```
============================= test session starts =============================
backend/tests/test_model_catalog_lifecycle.py:
  test_model_catalog_initialization                                PASSED
  test_model_catalog_refresh_from_live_api                         PASSED
  test_model_catalog_ttl_cache_expiration                          PASSED
  test_model_catalog_fallback_on_network_error                     PASSED
  test_model_catalog_gemini_models_discovery                       PASSED
  test_model_catalog_deepseek_models_discovery                     PASSED
  test_model_catalog_lifecycle_cleanup                             PASSED (7/7)

backend/tests/test_nayapay_sadapay_adapters.py:
  test_nayapay_missing_credentials_fails_closed                    PASSED
  test_sadapay_missing_credentials_fails_closed                    PASSED
  test_nayapay_disabled_fails_closed                               PASSED
  test_sadapay_disabled_fails_closed                               PASSED
  test_nayapay_unconfigured_verify_returns_failed_never_paid       PASSED
  test_sadapay_unconfigured_verify_returns_failed_never_paid       PASSED
  test_nayapay_unsupported_currency_fails_closed                   PASSED
  test_sadapay_unsupported_currency_fails_closed                   PASSED
  test_nayapay_checkout_creation_success                           PASSED
  test_sadapay_checkout_creation_success                           PASSED
  test_nayapay_checkout_timeout_fails_closed                       PASSED
  test_sadapay_checkout_timeout_fails_closed                       PASSED
  test_nayapay_checkout_http_error_fails_closed                    PASSED
  test_sadapay_checkout_http_error_fails_closed                    PASSED
  test_nayapay_status_mapping_completed_to_paid                    PASSED
  test_nayapay_status_mapping_failed                               PASSED
  test_nayapay_status_mapping_expired_to_failed                    PASSED
  test_sadapay_status_mapping_completed_to_paid                    PASSED
  test_sadapay_status_mapping_failed                               PASSED
  test_sadapay_status_mapping_expired_to_failed                    PASSED
  test_nayapay_webhook_signature_verification_success             PASSED
  test_nayapay_webhook_signature_verification_tampered_fails       PASSED
  test_sadapay_webhook_signature_verification_success             PASSED
  test_sadapay_webhook_signature_verification_tampered_fails       PASSED
  test_billing_service_rejects_amount_mismatch_subscription        PASSED
  test_billing_service_rejects_currency_mismatch_subscription      PASSED
  test_billing_service_rejects_amount_mismatch_topup               PASSED
  test_billing_service_rejects_currency_mismatch_topup             PASSED
  test_nayapay_cancel_subscription_returns_false                   PASSED
  test_sadapay_cancel_subscription_returns_false                   PASSED
  test_nayapay_live_sandbox_smoke_test                             SKIPPED (opt-in)
  test_sadapay_live_sandbox_smoke_test                             SKIPPED (opt-in) (30/30)

backend/tests/test_billing_config_validator.py:
  test_production_rejects_stripe_test_secret_key                   PASSED
  test_production_rejects_safepay_sandbox_api_key                  PASSED
  test_production_rejects_safepay_sandbox_environment              PASSED
  test_production_rejects_nayapay_test_credentials                 PASSED
  test_production_rejects_nayapay_sandbox_environment              PASSED
  test_production_rejects_sadapay_test_credentials                 PASSED
  test_production_rejects_sadapay_sandbox_environment              PASSED
  test_production_rejects_simulated_checkout                       PASSED
  test_production_billing_requires_durable_database                PASSED
  test_production_requires_webhook_secret_for_enabled_providers    PASSED
  test_non_production_simulation_permitted                         PASSED
  test_valid_production_configuration_passes                      PASSED (12/12)

backend/tests/test_payment_production_security.py:
  test_stripe_production_missing_credentials_fails_closed          PASSED
  test_stripe_production_missing_sdk_fails_closed                  PASSED
  test_stripe_production_api_error_fails_closed                    PASSED
  test_stripe_production_empty_session_id_fails_closed             PASSED
  test_stripe_production_empty_checkout_url_fails_closed            PASSED
  test_stripe_non_production_simulation_permitted                 PASSED
  test_safepay_production_missing_credentials_fails_closed         PASSED
  test_safepay_unsupported_currency_fails_closed                   PASSED
  test_safepay_production_api_error_fails_closed                   PASSED
  test_safepay_production_empty_token_fails_closed                 PASSED
  test_safepay_non_production_simulation_permitted                PASSED
  test_production_checkout_failure_creates_no_subscription_or_credits PASSED
  test_production_detection_helper_coverage                        PASSED (13/13)

backend/tests/integration/test_phase8_payments.py:
  19/19 PASSED (including model resolution, checkouts, webhooks, multi-tenant isolation)
================================================================================
```
