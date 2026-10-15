# ROXY-AI — BILLING SCHEMA MIGRATION REMEDIATION REPORT

**Date:** 2026-10-15  
**Branch:** `release/audit-remediation`  
**Starting Commit SHA:** `236537ac5bedad4d97c1aab6ec38b6a6c1bfe6db`  
**Repository:** `roxyross/alibaba-ai-hacathon-chatbot`  
**Scope:** Workstream B — Corrective Alembic Migration & Durable Persistence Safeguards  
**Overall Status:** PASS  

---

## 1. Executive Summary

To remediate the schema drift and the reported defect (`UndefinedColumnError: column subscriptions.provider does not exist`), a safe, deterministic Alembic migration was authored, tested, and verified:
`backend/alembic/versions/012_billing_and_connectors_persistence.py`

This migration attaches cleanly to the migration head (`011_trust_reliability_hardening`), preserving linear determinism. In addition, unsafe production in-memory fallbacks were eliminated from `BillingRepository` and `PaymentService`, ensuring financial operations fail closed rather than silently losing state.

---

## 2. Migration Architecture & Details

### 2.1 Metadata & Revision Chain
- **File:** `backend/alembic/versions/012_billing_and_connectors_persistence.py`
- **Revision ID:** `012_billing_and_connectors_persistence`
- **Revises (down_revision):** `011_trust_reliability_hardening`
- **Single Head Confirmed:** Verified via `python scripts/validate_migrations.py` with 12 contiguous revisions.

### 2.2 Tables & Columns Provisioned
The migration ensures complete alignment between SQLAlchemy ORM models and PostgreSQL schema:

1. **`connector_instances` Table:**
   - Columns: `id` (PK), `user_id` (indexed), `connector_type` (indexed), `encrypted_credentials_json`, `auth_status`, `scopes_json`, `error_message`, `created_at`, `updated_at`.
   - Constraints: `uq_connector_instances_user_type` UNIQUE (`user_id`, `connector_type`).
2. **`subscriptions` Table:**
   - Columns: `id` (PK), `user_id` (indexed), `plan`, `provider` (indexed, default `'stripe'`), `status` (indexed), `amount_usd`, `amount_pkr`, `provider_customer_id`, `provider_subscription_id`, `current_period_end`, `cancel_at_period_end`, `created_at`, `updated_at`.
3. **`payments` Table:**
   - Columns: `id` (PK), `user_id` (indexed), `provider` (indexed), `amount`, `currency`, `status`, `plan_id`, `provider_transaction_id`, `invoice_id`, `created_at`.
4. **`payment_events` Table:**
   - Columns: `id` (PK), `provider` (indexed), `provider_event_id` (indexed), `event_type`, `processed` (default `True`), `raw_payload_json`, `created_at`.
   - Constraints: `uq_payment_events_provider_event` UNIQUE (`provider`, `provider_event_id`).
5. **`payment_methods` Table:**
   - Columns: `id` (PK), `user_id` (indexed), `brand`, `last4`, `exp_month`, `exp_year`, `is_default`, `provider`, `created_at`.
6. **`credit_wallets` Table:**
   - Columns: `id` (PK), `user_id` (indexed, UNIQUE), `remaining_credits`, `used_this_month`, `estimated_cost_usd`, `estimated_cost_pkr`, `created_at`, `updated_at`.
7. **`usage_logs` Table:**
   - Columns: `id` (PK), `user_id` (indexed), `session_id`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `credits_deducted`, `created_at`.

### 2.3 Safe Backfill & Existing Data Preservation
If `subscriptions` already exists from a previous partial schema:
- The migration checks for missing columns using `inspector.get_columns("subscriptions")`.
- Adds `provider` as nullable `VARCHAR(32)`, executes an explicit backfill:
  ```sql
  UPDATE subscriptions SET provider = 'stripe' WHERE provider IS NULL
  ```
  Then alters `provider` to `NOT NULL` with a server default of `'stripe'`.
- Adds `amount_pkr` as nullable `DOUBLE PRECISION` without inventing fake rupee amounts for historical dollar transactions.
- Adds missing indexes and unique constraints safely.

### 2.4 Reversibility (Safe Downgrade)
The migration implements a defensive `downgrade()` function that drops newly added tables and constraints cleanly in reverse order.

---

## 3. Migration Validation Evidence

### 3.1 Chain Validation Command
```bash
python scripts/validate_migrations.py
```
**Output:**
```
SUCCESS: Single Alembic migration head detected: 012_billing_and_connectors_persistence
SUCCESS: Migration chain verified with 12 revisions
```

### 3.2 Upgrade / Downgrade / Re-upgrade Lifecycle
Executed against isolated PostgreSQL test container on port 5433:
- Upgrade to head: `alembic upgrade head` -> **Exit Code 0**
- Downgrade one step: `alembic downgrade -1` -> **Exit Code 0**
- Re-upgrade to head: `alembic upgrade head` -> **Exit Code 0**

### 3.3 Historical Row Data Preservation Verification
Synthetic pre-existing rows were created in an unmigrated database and tested through migration execution:
- Script: `scratch/test_migration_data_preservation.py`
- Pre-existing subscription rows without `provider` were preserved.
- Post-migration query confirmed `provider='stripe'` was cleanly backfilled and existing fields remained intact.

---

## 4. Elimination of Production In-Memory Fallback

### 4.1 Modifications in `backend/src/app/billing/repository.py`
- Added production environment detection `_is_production()`.
- Gated write operations (`update_or_create_subscription`, `cancel_subscription`, `record_payment`, `record_webhook_event`, `credit_wallet`, `deduct_credits`, `add_payment_method`, `delete_payment_method`):
  * If in production mode and `DATABASE_URL` is unset, raises `RuntimeError("Durable database persistence required in production, but DATABASE_URL is not configured.")`.
  * If a database error occurs during write in production, logs error and raises `RuntimeError`, strictly preventing fallback to in-memory dictionaries.
- Fixed a double-credit calculation bug in `credit_wallet` where credits were added to both PostgreSQL and the in-memory return object.

### 4.2 Modifications in `backend/src/app/billing/service.py` & API Routes
- Webhook processor wraps repository writes in `try...except` and returns error status on persistence failure.
- In `backend/src/app/api/v1/billing.py`, webhook persistence failures return HTTP 500 so payment gateways (Stripe/Safepay) retry the webhook delivery rather than falsely assuming success.
