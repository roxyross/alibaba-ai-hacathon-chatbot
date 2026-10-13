# ROXY-AI — Payment Gateways & Sandbox Acceptance Report

**Document ID:** `ROXY-RC-11`  
**Date:** October 14, 2026  
**Target Release:** Post-Phase 5.1 Release Candidate (RC-1)  
**Branch:** `release/audit-remediation`  
**Verification Verdict:** `PASS` (Sandbox Mode) / `BLOCKED` (Production Merchant Live Keys)

---

## 1. Executive Summary

This report evaluates payment gateway integrations (Stripe, Safepay, Raast instant transfers), webhook signature verification, subscription checkout workflows, and high-impact transaction safety interlocks.

---

## 2. Payment Architecture & Supported Rails

Roxy-AI supports dual international and regional payment processing:
1. **Stripe (Global Rails):**
   - Credit / Debit Cards, Apple Pay, Google Pay.
   - Subscription lifecycle management (`tier_pro`, `tier_enterprise`).
   - Webhook processing: Thin events and full snapshot payloads with cryptographic signature verification.
2. **Safepay (Pakistan / Regional Rails):**
   - Raast instant bank settlement, 1Link, debit cards.
   - Local PKR currency conversion and mobile wallet transactions.
3. **Plaid Integration:**
   - Financial account aggregation and read-only balance verification.

---

## 3. Sandbox Verification Results

| Payment Workflow | Test Suite Reference | Result | Notes |
| :--- | :--- | :--- | :--- |
| **Stripe Checkout Session** | `test_phase8_payments.py` | **PASS** | Session created with valid metadata |
| **Stripe Webhook Verification** | `test_phase8_payments.py` | **PASS** | Rejects invalid HMAC-SHA256 signatures |
| **Safepay Payment Intent** | `test_phase8_payments.py` | **PASS** | Generates valid tracker token |
| **Idempotency Guard** | `test_phase23_trust_and_reliability.py::test_03` | **PASS** | Non-reversible payment rejected from auto-retry queue |
| **Usage-Based Cost Labeling** | `test_phase23_trust_and_reliability.py::test_10` | **PASS** | Cost labeled as `"Estimated"` |

---

## 4. Financial Safety & Recovery Interlock

A critical security principle enforced in `app/trust/service.py` is the prevention of automated retries on financial transactions:
- When a payment operation fails (e.g., `raast_payment`), it cannot be queued into the automatic recovery queue.
- Submitting a recovery job with `action_type="raast_payment"` triggers HTTP 400 Bad Request:
  `"Cannot queue high-impact non-retryable action: raast_payment"`.
- This guarantees that automated network retries never cause duplicate credit card charges or duplicate bank debits.

---

## 5. Production Payment Blocker (BLK-03)

Operating in sandbox mode is mandatory for staging and integration testing. Live commercial transactions remain blocked until:
1. Production Stripe account is activated with business entity documentation.
2. Restricted API key `rk_live_...` with minimal necessary permissions is generated.
3. Webhook endpoint `https://app.roxy.ai/api/v1/payments/stripe/webhook` is configured in Stripe Dashboard and the live secret is stored in KMS.
4. Safepay live merchant account is activated with State Bank of Pakistan compliance sign-off.

---

## 6. Acceptance Sign-off

Payment processing in sandbox mode passes all security and functional requirements.
**STATUS: ACCEPTED FOR STAGING RELEASE.**
