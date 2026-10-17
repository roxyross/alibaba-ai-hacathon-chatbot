# ROXY-AI — BILLING SCHEMA DRIFT ROOT CAUSE ANALYSIS REPORT

**Date:** 2026-10-15  
**Branch:** `release/audit-remediation`  
**Starting Commit SHA:** `236537ac5bedad4d97c1aab6ec38b6a6c1bfe6db`  
**Repository:** `roxyross/alibaba-ai-hacathon-chatbot`  
**Defect Investigated:** `UndefinedColumnError: column subscriptions.provider does not exist`  
**Status:** ROOT CAUSE IDENTIFIED & PROVEN  

---

## 1. Executive Summary

During real PostgreSQL testing of the billing subsystem, operations against the `subscriptions` table failed with:
`UndefinedColumnError: column subscriptions.provider does not exist`

Investigation into the git history, ORM definitions (`backend/src/app/models/subscription.py`), and Alembic migrations (`backend/alembic/versions/`) revealed that:
1. The billing ORM models and Safepay dual-currency support were introduced in earlier commits (`a2ba5c4` and `297088e`), which defined `Subscription`, `Payment`, `PaymentEvent`, `PaymentMethod`, `CreditWallet`, and `UsageLog`.
2. However, **no Alembic migration was ever created** for the billing models or connectors persistence. The existing migration graph terminated at `011_trust_reliability_hardening.py`.
3. In legacy development databases where a partial `subscriptions` table had been created manually or by an obsolete schema script prior to Safepay integration, the `provider`, `amount_pkr`, and other dual-currency columns were missing entirely.
4. In fresh PostgreSQL instances built from `alembic upgrade head`, the billing tables did not exist at all, causing tests attempting database persistence to fail or fall back silently to in-memory dictionaries.

---

## 2. ORM Model vs Alembic Migrations vs Database Schema Comparison

A comprehensive comparison across the three layers was performed before writing any migrations:

| Entity / Column | ORM Model (`app/models/subscription.py`) | Alembic Migrations (`001` - `011`) | Legacy Dev PostgreSQL (`roxy_isolated_test_db`) | Status / Drift |
|---|---|---|---|---|
| `subscriptions` table | Present | **ABSENT** | Present (Partial) | Table missing from migrations |
| `subscriptions.id` | `String(64), PK` | None | `character varying` | Existed in dev DB |
| `subscriptions.user_id` | `String(64), Indexed` | None | `character varying` | Existed in dev DB |
| `subscriptions.plan` | `String(32)` | None | `character varying` | Existed in dev DB |
| `subscriptions.status` | `String(32)` | None | `character varying` | Existed in dev DB |
| `subscriptions.provider` | `String(32), Default 'stripe'` | None | **MISSING** | **Direct cause of reported error** |
| `subscriptions.amount_usd` | `Float` | None | `double precision` | Existed in dev DB |
| `subscriptions.amount_pkr` | `Float` | None | **MISSING** | Missing column |
| `subscriptions.provider_customer_id` | `String(128), Nullable` | None | `character varying` | Existed in dev DB |
| `subscriptions.provider_subscription_id`| `String(128), Nullable` | None | `character varying` | Existed in dev DB |
| `subscriptions.current_period_end` | `DateTime(timezone=True)` | None | `timestamp with time zone` | Existed in dev DB |
| `subscriptions.cancel_at_period_end` | `Boolean, Default False` | None | `boolean` | Existed in dev DB |
| `payments` table | Present | **ABSENT** | Present | Table missing from migrations |
| `payment_events` table | Present | **ABSENT** | Present | Table missing from migrations |
| `payment_methods` table | Present | **ABSENT** | Present | Table missing from migrations |
| `credit_wallets` table | Present | **ABSENT** | Present | Table missing from migrations |
| `usage_logs` table | Present | **ABSENT** | Present | Table missing from migrations |
| `connector_instances` table | Present (`app/models/connector.py`) | **ABSENT** | Present | Table missing from migrations |

---

## 3. Git Commit History Trace

1. **Commit `a2ba5c4` ("feat: add Stripe subscription billing & webhooks"):**
   - Introduced initial `Subscription` model with Stripe-specific fields.
   - Added `BillingRepository` with in-memory fallback.
   - *Omission:* Did not add an Alembic migration for the `subscriptions` table.
2. **Commit `297088e` ("feat(billing): add dual payment gateway (Stripe + Safepay)"):**
   - Added `provider` ("stripe" | "safepay") and `amount_pkr` fields to `Subscription` model to support Pakistani Rupee transactions via Safepay.
   - *Omission:* Did not create an Alembic migration to add `provider` or `amount_pkr` to existing databases or to provision tables in fresh databases.
3. **Commit `011_trust_reliability_hardening`:**
   - Handled Trust & Reliability persistence (Phase 26), leaving billing and connectors persistence without an Alembic migration.

---

## 4. Why Was This Drift Not Caught Previously?

1. **Unit Test Masking:** Earlier tests in `test_phase8_payments.py` ran with simulated checkout responses or in-memory repositories when `DATABASE_URL` was unset or when running unit mocks.
2. **Silent In-Memory Fallback:** When `BillingRepository` encountered a database exception (such as `UndefinedColumnError`), its exception handler caught the error, logged a warning, and silently populated the `_MEM_SUBSCRIPTIONS` dictionary in memory. To callers, the operation appeared successful, masking the fact that database persistence failed.
3. **Absence of Real PostgreSQL CI Gate:** No automated CI job verified billing persistence against an active PostgreSQL container with `alembic upgrade head`.

---

## 5. Remediation Strategy

1. **Alembic Migration `012_billing_and_connectors_persistence.py`:**
   - Created with down_revision `011_trust_reliability_hardening`.
   - Idempotently provisions all missing billing and connector tables.
   - Idempotently adds missing columns (`provider`, `amount_pkr`, `amount_usd`) to pre-existing tables if they exist, backfilling `provider='stripe'` and `amount_usd=0.0` to preserve historical rows without data loss.
2. **Elimination of Production Fallback:**
   - Modified `BillingRepository` and `PaymentService` to fail closed in production whenever a database exception or missing configuration occurs.
3. **Automated Integration Test:**
   - Authored `backend/tests/integration/test_billing_real_postgres_integration.py` to assert physical columns, real commits, and idempotency in PostgreSQL.
