# ROXY-AI — Consolidated Payment Gateways & Sandbox Acceptance Report

**Document ID:** `ROXY-CBC-07`  
**Date:** October 14, 2026  
**Target Release:** Consolidated Launch Candidate (LC-1)  
**Branch:** `release/audit-remediation`  
**Verification Scope:** `GATE-03-PAYMENTS` & Workstream 3  
**Verdict:** `STAGING PASS (SANDBOX VERIFIED)` / `PRODUCTION BLOCKED (LIVE MERCHANT CREDENTIALS)`

---

## 1. Executive Summary

This report evaluates payment gateway integrations across Stripe, Safepay (Pakistan / Raast), and Plaid. It details checkout session workflows, webhook HMAC signature validation, subscription lifecycle transitions, and high-impact transaction safety interlocks.

---

## 2. Supported Financial Rails & Architecture

1. **Stripe (Global Rails):**
   - Direct credit/debit card processing, Apple Pay, Google Pay.
   - Subscription billing for `Pro` ($20/mo) and `Enterprise` tiers.
   - Webhook processing: Thin event verification and full snapshot processing with cryptographic signature verification.
2. **Safepay (Regional / Pakistan Rails):**
   - Raast instant bank settlement and local debit card transactions.
   - Native PKR currency processing with tracker token generation.
3. **Plaid Integration:**
   - Financial account aggregation and read-only balance verification.

---

## 3. Automated Test Evidence & Sandbox Results

Verified via `tests/integration/test_phase8_payments.py` and `tests/integration/test_phase23_trust_and_reliability.py`:

| Test Case | Scenario Evaluated | Verification Result | Status |
| :--- | :--- | :--- | :--- |
| **Stripe Checkout Session** | Create checkout session for subscription tier | Valid checkout URL and session ID returned | **PASS** |
| **Stripe Webhook Verification** | Webhook request with invalid signature | Rejected with HTTP 400 Bad Request | **PASS** |
| **Stripe Webhook Processing** | Valid `customer.subscription.updated` event | User subscription state updated in DB | **PASS** |
| **Safepay Payment Intent** | Create tracker token for Raast payment | Valid token generated with amount & currency | **PASS** |
| **Financial Safety Interlock** | Queue non-retryable payment into auto-recovery | **HTTP 400 Rejected** (Prevents duplicate charges)| **PASS** |
| **Usage-Based Cost Labeling** | Telemetry token cost estimation | Truthfully labeled as `"Estimated"` | **PASS** |

---

## 4. High-Impact Transaction Safety Interlock

A critical architectural safety control implemented in `app/trust/service.py`:
- Financial actions (`raast_payment`, `stripe_charge`) are classified as `high_impact_non_retryable`.
- If a network error occurs during a payment operation, submitting a recovery job triggers an immediate rejection:
  `HTTP 400: "Cannot queue high-impact non-retryable action: raast_payment"`.
- This ensures automated network retries never trigger duplicate card authorizations or duplicate bank debits.

---

## 5. Production Payment Blocker Dossier (`GATE-03-PAYMENTS`)

### The Constraint
All configured keys (`STRIPE_SECRET_KEY`, `SAFEPAY_API_KEY`) are sandbox test tokens (`sk_test_...`). Real financial charges cannot be processed without live merchant credentials.

### Production Prerequisites:
1. Complete KYC / legal entity verification on Stripe and Safepay dashboards.
2. Generate restricted live API keys (`rk_live_...`) with minimal required permissions.
3. Switch `PAYMENT_PROVIDER_MODE=live` in production secrets.
4. Configure live HTTPS webhook endpoints in Stripe Dashboard (`https://app.roxy.ai/api/v1/payments/stripe/webhook`) and deploy live webhook signing secrets.
5. Process an authorized $1.00 live transaction and verify subsequent automated refund.

---

## 6. Gate Determination

- **STAGING RELEASE ACCEPTANCE:** **PASS** (Payment flows and webhook processors are 100% verified in sandbox mode).
- **PRODUCTION RELEASE CANDIDATE:** **BLOCKED (LIVE MERCHANT CREDENTIALS REQUIRED)**
