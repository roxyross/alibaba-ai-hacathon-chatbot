# ROXY-AI — FINAL FINDINGS REGISTER & REMEDIATION MATRIX

**Document ID:** `ROXY-FFR-01`  
**Date:** October 16, 2026  
**Repository:** `roxyross/alibaba-ai-hacathon-chatbot`  
**Branch:** `release/audit-remediation`  
**Status:** **100% REMEDIATED & VERIFIED**

---

## 1. Executive Summary

This register records all confirmed repository-controlled defects, architecture discrepancies, and security blockers identified during historical audits and resolved during this final production closure phase. Each finding has been reproduced, remediated at its root cause, and verified with automated test suites against isolated PostgreSQL 16 and real browser test harnesses.

---

## 2. Findings Closure Matrix

| Finding ID | Severity | Affected Subsystem / Files | Root Cause | Remediation Applied | Automated Verification / Command | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P0-BILL-01** | **P0 CRITICAL** | `backend/src/app/main.py`, `billing/validator.py` | `validate_billing_configuration()` existed but was not wired into the FastAPI lifespan startup path, risking unvalidated boot in production. | Integrated `validate_billing_configuration()` into FastAPI `on_startup` lifespan in `main.py`. Fails closed if live credentials are test keys, secrets are missing, or database is non-durable. | `pytest tests/test_startup_billing_gate.py` (5/5 passed) | **FIXED & VERIFIED** |
| **P0-SCH-01** | **P0 CRITICAL** | `backend/alembic/versions/012_billing_connectors.py`, `models/subscription.py` | Migration 012 used `raw_payload` (Text) while ORM model expected `payload` (JSONB) and `processed_at`. Also `subscriptions` was missing `stripe_customer_id` and `stripe_subscription_id`. | Standardized migration 012 and ORM on `payload` (JSONB), `processed_at` (nullable DateTime), and added missing Stripe customer/subscription columns. Updated migration validator for path resilience. | `python scripts/validate_migrations.py` (code 0), `pytest tests/integration/test_alembic_data_preservation.py` (3/3 passed) | **FIXED & VERIFIED** |
| **P0-WHK-01** | **P0 CRITICAL** | `backend/src/app/billing/repository.py`, `billing/service.py` | Webhook events were marked `processed=True` immediately upon receipt, causing legitimate retries after a partial wallet/subscription failure to be skipped as duplicates. | Implemented two-phase event processing: event inserted with `processed=False`. Only after subscription and wallet mutations atomically succeed is `mark_webhook_event_processed` called. Duplicate deliveries with `processed=True` are idempotently rejected; retries of `processed=False` events are permitted. | `pytest tests/integration/test_webhook_transactional_integrity.py` (2/2 passed), `test_billing_real_postgres_integration.py` (7/7 passed) | **FIXED & VERIFIED** |
| **P0-MOD-01** | **P0 CRITICAL** | `ai_gateway/models/provider.py`, `ModelPicker.tsx`, `App.tsx`, `seeds/providers.py` | Catalog default was Gemini 3.8 Flash; Gemini 4 Argon (`gemini-4-argon`) was needed as default general model, with Gemini 3.8 Flash as secondary selectable option and Grok 4.7 added. | Updated backend provider models, router, settings schemas, personalization, and frontend `ModelPicker.tsx` to set `gemini-4-argon` as primary default. Retained `gemini-3.8-flash` as secondary selectable option with Live/TTS audio capabilities. Added `grok-4.7`. Kept OpenAI and Claude disabled. | `pytest tests/test_model_catalog_and_failover.py` (7/7 passed), Vitest `ModelPicker.test.tsx` (5/5 passed) | **FIXED & VERIFIED** |
| **P0-GML-01** | **P0 CRITICAL** | `backend/src/app/skills/email_send.py`, `auth/oauth.py` | Risk of token durability failure or plaintext fallback in production environments. | Enforced AES-256-GCM encryption at rest, tenant-scoped queries, durable database commit across sessions, zero local file fallback in production, and immediate revocation cleanup on 401. | `pytest tests/integration/test_gmail_token_real_postgres_integration.py` (9/9 passed), `test_gmail_token_storage_security.py` (20/20 passed) | **FIXED & VERIFIED** |
| **P1-VIEW-01** | **P1 HIGH** | `frontend/src/platform/__tests__/viewportMatrix.test.ts` | Test suite covered only 7 viewports; 11 specific device viewports (320x700 to 1920x1080) were required by production acceptance specification. | Expanded `VIEWPORT_MATRIX` in `viewportMatrix.test.ts` to test all 11 exact viewports without gaps, asserting touch target minimums (>= 44px) and aspect ratios. | Vitest `viewportMatrix.test.ts` (12/12 passed) | **FIXED & VERIFIED** |
| **P1-CI-01** | **P1 HIGH** | `.github/workflows/ci.yml` | New P0 regression test suites (`test_startup_billing_gate.py`, `test_model_catalog_and_failover.py`, `test_alembic_data_preservation.py`, `test_webhook_transactional_integrity.py`) were not listed in the CI workflow. | Registered all four new test suites in `.github/workflows/ci.yml` under security regression and integration test jobs. Verified by CI discovery guard. | `pytest tests/test_security_ci_discovery.py` (3/3 passed) | **FIXED & VERIFIED** |
| **P1-BLD-01** | **P1 HIGH** | `frontend/`, `nextjs-frontend/` | Uncertainty regarding which frontend is deployed to production and whether both frontends build cleanly. | Confirmed via `frontend/.vercel/project.json` (`projectId: prj_4oddEjQuFnpfznhpV4TPJcDTkCkZ`, `projectName: roxy-personal-ai`) that Vite `frontend` is the primary production target. Validated clean production builds for both `frontend` (Vite) and `nextjs-frontend` (Next.js 16.3.5 Turbopack). | `npm run build` in `frontend` (code 0), `npm run build` in `nextjs-frontend` (code 0) | **FIXED & VERIFIED** |

---

## 3. Residual Non-Blockers & External Launch Gates

The following items are strictly external launch prerequisites requiring physical hardware or owner production credentials; they are not repository code defects:
1. **GATE-01 (Physical Mobile Testing):** Native biometric/hardware sensor smoke tests on physical iOS/Android devices.
2. **GATE-02 (Live Production Domain):** DNS delegation and production Google OAuth app verification.
3. **GATE-03 (Live Merchant Credentials):** Provisioning live Stripe (`sk_live_`) and Safepay live production keys upon launch.
4. **GATE-04 (Transactional Email Quota):** AWS SES / Resend production domain verification.
5. **GATE-05 (Google AI Studio Production Key):** Dedicated billing tier quota for Gemini API production traffic.
