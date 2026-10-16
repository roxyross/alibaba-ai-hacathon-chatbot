# ROXY-AI — FINAL DATABASE SCHEMA AND MIGRATION EVIDENCE REPORT

**Document ID:** `ROXY-DSE-01`  
**Date:** October 16, 2026  
**Alembic Head:** `012_billing_connectors` (12 revisions total)  
**Database Target Tested:** Isolated PostgreSQL 16 on `127.0.0.1:5433` (`roxy_isolated_test_db`)  
**Verdict:** **VERIFIED PASS — 100% SCHEMA CONSISTENCY & DATA PRESERVATION**

---

## 1. Executive Summary

Previous forensic inspection identified schema discrepancies between Alembic migration revision `012_billing_connectors.py` and the SQLAlchemy ORM models in `backend/src/app/models/subscription.py`. Specifically:
1. `payment_events.raw_payload` (Text) in the migration vs `PaymentEvent.payload` (JSONB) in the ORM.
2. `payment_events.processed_at` was missing or non-nullable in earlier versions.
3. `subscriptions.stripe_customer_id` and `subscriptions.stripe_subscription_id` were referenced in ORM repositories but omitted in migration DDL.
4. `payments.provider_session_id`, `payments.metadata_json`, and `payment_methods.stripe_payment_method_id` needed strict reconciliation.

All discrepancies were reconciled. The migration and ORM models now share an identical schema contract. All migration states (fresh install, legacy upgrade, data preservation, and repeat execution) were tested and verified against real PostgreSQL 16.

---

## 2. Schema Reconciliation Table

| Table | Column Name | Migration DDL Type | ORM Model Type | Nullable | Description / Constraint |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `payment_events` | `id` | `VARCHAR(36)` / UUID | `String(36)` | NO | Primary Key |
| `payment_events` | `provider` | `VARCHAR(32)` | `String(32)` | NO | `stripe`, `safepay`, etc. |
| `payment_events` | `event_id` | `VARCHAR(128)` | `String(128)` | NO | Idempotency Key (Unique) |
| `payment_events` | `event_type` | `VARCHAR(64)` | `String(64)` | NO | e.g. `payment_intent.succeeded` |
| `payment_events` | `payload` | `JSONB` / `JSON` | `JSONB` / `JSON` | NO | Full signed provider payload |
| `payment_events` | `processed` | `BOOLEAN` | `Boolean` | NO | Default `False` on insertion |
| `payment_events` | `processed_at` | `TIMESTAMP WITH TIME ZONE` | `DateTime(timezone=True)` | YES | Timestamp when financial mutations committed |
| `payment_events` | `created_at` | `TIMESTAMP WITH TIME ZONE` | `DateTime(timezone=True)` | NO | Server default `now()` |
| `subscriptions` | `stripe_customer_id` | `VARCHAR(128)` | `String(128)` | YES | Indexed Stripe Customer identifier |
| `subscriptions` | `stripe_subscription_id`| `VARCHAR(128)` | `String(128)` | YES | Indexed Stripe Subscription identifier |
| `subscriptions` | `current_period_start` | `TIMESTAMP WITH TIME ZONE` | `DateTime(timezone=True)` | YES | Billing cycle start |
| `payments` | `provider_session_id` | `VARCHAR(128)` | `String(128)` | YES | Stripe checkout session / Safepay tracker |
| `payments` | `metadata_json` | `JSONB` / `JSON` | `JSONB` / `JSON` | YES | Contextual financial metadata |
| `payment_methods` | `stripe_payment_method_id` | `VARCHAR(128)` | `String(128)` | YES | Card / Token representation |

---

## 3. Migration Chain & Determinism Verification

**Script:** `backend/scripts/validate_migrations.py`  
**Command:** `python backend/scripts/validate_migrations.py`

```text
Found 12 migration revisions.
Single Alembic head verified: 012_billing_connectors
All revision IDs fit Alembic's version_num column (max 32 chars).
Migration chain determinism PASSED:
  base -> 001_initial_schema -> 002_user_management -> 003_knowledge_vault ->
  004_agent_tools -> 005_chat_sessions_session_type -> 006_trust_and_reliability ->
  007_target_scoped_permissions -> 008_device_agent_enrollment -> 009_deep_app_catalog ->
  010_cowork_artifacts_open_work -> 011_trust_reliability_hardening ->
  012_billing_connectors (HEAD)
```
**Exit Code:** `0`

---

## 4. Real PostgreSQL 16 Test Evidence

**Database:** PostgreSQL 16 (`roxy_isolated_test_db` on `127.0.0.1:5433`)

### 4.1 Migration Graph & Upgrade Tests (`test_alembic_migrations.py`)
**Command:** `pytest backend/tests/test_alembic_migrations.py -v`
```text
tests/test_alembic_migrations.py::test_single_alembic_head PASSED [ 50%]
tests/test_alembic_migrations.py::test_upgrade_and_downgrade_cycle PASSED [100%]
============================== 2 passed in 1.42s ==============================
```

### 4.2 Data Preservation & Legacy Upgrade Tests (`test_alembic_data_preservation.py`)
**Command:** `pytest backend/tests/integration/test_alembic_data_preservation.py -v`
```text
tests/integration/test_alembic_data_preservation.py::test_pre_existing_data_preserved_across_012_upgrade PASSED [ 33%]
tests/integration/test_alembic_data_preservation.py::test_partial_schema_reconciliation_preserves_rows PASSED [ 66%]
tests/integration/test_alembic_data_preservation.py::test_repeated_upgrade_is_idempotent PASSED [100%]
============================== 3 passed in 1.86s ==============================
```

### 4.3 Key Data Preservation Guarantees
- Historical rows inserted before migration 012 (wallets, subscriptions, legacy connector tokens) remain 100% intact after upgrading to head.
- Partial schema reconciliation uses `ADD COLUMN IF NOT EXISTS` and does not drop tables or overwrite existing valid customer data.
- Running `alembic upgrade head` multiple times consecutively is strictly idempotent.
