# ROXY-AI — MIGRATION 012 SAFETY AND DATA PRESERVATION REPORT

## 1. Executive Summary

This report documents the remediation, safety hardening, and data-preservation verification of Alembic migration `012_billing_connectors` in Roxy-AI. The revision was executed and verified against an isolated, production-grade PostgreSQL 16 instance (`roxy_isolated_test_db` on `127.0.0.1:5433`).

All migration safety gates have passed with 100% verified evidence:
- **Revision ID length:** Truncated and renamed from 39 chars (`012_billing_and_connectors_persistence`) to 22 chars (`012_billing_connectors`), fitting strictly within the standard `VARCHAR(32)` column limit of `alembic_version`.
- **Migration Graph:** Single head (`012_billing_connectors`), 12 contiguous revisions, validated by `backend/scripts/validate_migrations.py`.
- **Safe Downgrade:** Replaced destructive blanket `op.drop_table` calls with explicit creation tracking (`_alembic_012_created_tables`). Pre-existing tables and customer records are 100% preserved.
- **Fail-Closed Inspection:** If schema inspection fails, the migration aborts immediately with a `RuntimeError` rather than assuming an empty schema.
- **Data Preservation Verified:** Synthetic records across all billing and connector entities survived repeated migrations without row loss or provider overwrites.

---

## 2. Alembic Revision Length and Chain Integrity Audit

### 2.1 Schema Column Constraint Analysis
The default Alembic version table schema defines:
```sql
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
```
The previous revision identifier `012_billing_and_connectors_persistence` comprised 39 characters, exceeding the 32-character database column constraint.

### 2.2 Remediation
1. Renamed migration file to: `backend/alembic/versions/012_billing_connectors.py`
2. Revision identifier updated to `012_billing_connectors` (22 characters, <= 32).
3. Backwards-compatibility shim registered in `backend/alembic/env.py` to reconcile any historical or development instances that recorded `012_billing_and_connectors_persistence`:
```python
connection.execute(
    text(
        "UPDATE alembic_version SET version_num = '012_billing_connectors' "
        "WHERE version_num = '012_billing_and_connectors_persistence'"
    )
)
```
4. Added validation assertion in `backend/scripts/validate_migrations.py`:
```python
assert len(rev.revision) <= 32, f"Revision ID '{rev.revision}' exceeds 32-char alembic_version column limit!"
```

### 2.3 Verified Migration Chain
Validation executed via `python scripts/validate_migrations.py`:
```
SUCCESS: Single Alembic migration head detected: 012_billing_connectors
SUCCESS: Migration chain verified with 12 revisions:
  - [001_initial_models] Initial models (down: None)
  - [002_auth_sessions_messages] Auth, sessions, and chat history (down: 001_initial_models)
  - [003_session_settings] Session settings and preferences (down: 002_auth_sessions_messages)
  - [004_extra_settings] Add extra_settings JSON column (down: 003_session_settings)
  - [005_session_type] Add session_type column (down: 004_extra_settings)
  - [006_trust_and_reliability] Trust events, recovery jobs (down: 005_session_type)
  - [007_target_scoped_permissions] Target-scoped permissions (down: 006_trust_and_reliability)
  - [008_device_agent_enrollment] Standalone device agent enrollment (down: 007_target_scoped_permissions)
  - [009_deep_app_catalog] Local Application Discovery Engine (down: 008_device_agent_enrollment)
  - [010_cowork_artifacts_open_work] Cowork Artifacts and Open Work Tasks (down: 009_deep_app_catalog)
  - [011_trust_reliability_hardening] Trust & Reliability hardening (down: 010_cowork_artifacts_open_work)
  - [012_billing_connectors] Billing Subsystem and Connectors Persistence (down: 011_trust_reliability_hardening)
```

---

## 3. Safe Upgrade, Downgrade & Data Preservation Architecture

### 3.1 Defect in Prior Implementation
The previous implementation performed unconditional `op.drop_table("subscriptions")`, `op.drop_table("payments")`, etc., on downgrade. In deployments where `subscriptions` or `payments` pre-existed migration 012, running `downgrade -1` would permanently drop the entire table and destroy all historical customer records.

### 3.2 Implemented Preservation Strategy
1. **Creation Tracking Table (`_alembic_012_created_tables`):**
   During `upgrade()`, each newly created table is recorded in an internal tracking table.
2. **Selective Downgrade:**
   During `downgrade()`, the migration queries `_alembic_012_created_tables`. Only tables explicitly created during revision 012 are dropped. Pre-existing tables are preserved in their entirety.
3. **Safe Column Alterations:**
   Columns added by revision 012 to pre-existing tables (`amount_pkr`, `amount_usd`, `cancel_at_period_end`, `plan`, `provider`) are safely removed only if added during upgrade, preserving the underlying records.
4. **Non-Null Provider Protection:**
   The backfill `UPDATE subscriptions SET provider = 'stripe' WHERE provider IS NULL` strictly targets `NULL` values and never overwrites existing provider references (`safepay`, `enterprise_invoice`, etc.).
5. **Fail-Closed Inspection:**
   ```python
   try:
       existing_tables = set(inspector.get_table_names())
   except Exception as exc:
       raise RuntimeError(f"CRITICAL: Alembic schema inspection failed; aborting to prevent data loss: {exc}")
   ```

---

## 4. Test Execution & Evidence

### 4.1 Test Suite
File: `backend/tests/integration/test_alembic_data_preservation.py`  
Database: `postgresql+asyncpg://roxy_test_usr:***@127.0.0.1:5433/roxy_isolated_test_db` (PostgreSQL 16)

### 4.2 Test Results
```
tests/integration/test_alembic_data_preservation.py::test_01_migration_upgrade_and_single_head_in_postgres PASSED [ 33%]
tests/integration/test_alembic_data_preservation.py::test_02_historical_data_preservation_and_non_null_provider PASSED [ 66%]
tests/integration/test_alembic_data_preservation.py::test_03_downgrade_and_reupgrade_safety PASSED [100%]
============================== 3 passed in 3.34s ==============================
```

### 4.3 Verified Scenarios
1. **Upgrade Head:** Alembic applied revision `012_billing_connectors` successfully to PostgreSQL.
2. **Historical Data Preservation:**
   - Seeded synthetic records in `subscriptions`, `payments`, `payment_events`, `credit_wallets`, and `connector_instances`.
   - Seeded subscription had `provider='safepay'`, `amount_pkr=5700.0`.
   - Re-executed `alembic upgrade head`.
   - Verified that `provider` remained `safepay` (not overwritten by `stripe`).
   - Verified 100% row persistence across all 5 tables.
3. **Downgrade to Revision 011:**
   - Executed `alembic downgrade -1`.
   - Verified `alembic_version` moved cleanly to `011_trust_reliability_hardening`.
   - Verified pre-existing tables were NOT dropped.
4. **Re-Upgrade to Head:**
   - Executed `alembic upgrade head`.
   - Verified `alembic_version` restored to `012_billing_connectors` without table collisions or constraint errors.

---

## 5. Production Migration Runbook

Before applying migration 012 in production:
1. Verify database backup:
   ```bash
   pg_dump -Fc --no-acl --no-owner $DATABASE_URL > pre_migration_012_backup.dump
   ```
2. Verify current database head is `011_trust_reliability_hardening`:
   ```bash
   alembic current
   ```
3. Run migration:
   ```bash
   alembic upgrade head
   ```
4. Post-migration verification:
   ```sql
   SELECT version_num FROM alembic_version;
   -- Must return '012_billing_connectors'
   SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'subscriptions';
   -- Must include provider, amount_pkr, amount_usd, cancel_at_period_end
   ```
