# ROXY-AI — COMBINED GMAIL & BILLING REGRESSION EVIDENCE REPORT

**Date:** 2026-10-15  
**Branch:** `release/audit-remediation`  
**Starting Commit SHA:** `236537ac5bedad4d97c1aab6ec38b6a6c1bfe6db`  
**Tested Commit SHA:** `236537ac5bedad4d97c1aab6ec38b6a6c1bfe6db` (with working tree changes)  
**Database Target:** Isolated PostgreSQL 16 Docker Container (`roxy_isolated_test_db`, Port 5433)  
**Overall Regression Gate:** PASS  

---

## 1. Executive Summary

Both Workstream A (Gmail OAuth Token Persistence) and Workstream B (Stripe/Safepay Billing Persistence & Schema Remediation) have successfully passed all automated regression gates against a real, isolated PostgreSQL database. 

Zero live production credentials, webhook secrets, or live cloud services were used. Real database transactions, commit persistence, independent fresh-session reads, AES-Fernet encryption/decryption, webhook idempotency, multi-tenant financial isolation, and fail-closed behaviors were definitively verified.

---

## 2. Consolidated Test Execution Matrix

| Test Suite File | Test Category | Target Layer | Total Tests | Passed | Failed | Skipped | Blocked |
|---|---|---|---|---|---|---|---|
| `tests/integration/test_gmail_token_real_postgres_integration.py` | Permanent Gmail Integration | Real PostgreSQL (Port 5433) | 9 | 9 | 0 | 0 | 0 |
| `tests/integration/test_billing_real_postgres_integration.py` | Permanent Billing Integration | Real PostgreSQL (Port 5433) | 7 | 7 | 0 | 0 | 0 |
| `tests/test_gmail_token_storage_security.py` | Gmail Security Unit/Regression | Mocked DB & AES Cryptography | 26 | 26 | 0 | 0 | 0 |
| `tests/test_payment_production_security.py` | Billing Production Fail-Closed | Mocked & Isolated Config | 13 | 13 | 0 | 0 | 0 |
| `tests/integration/test_phase8_payments.py` | Payment & Webhook Integration | API Routes & Repositories | 13 | 13 | 0 | 0 | 0 |
| `tests/test_security_ci_discovery.py` | CI Governance & Discovery | File Audit & Manifest | 3 | 3 | 0 | 0 | 0 |
| `scripts/validate_migrations.py` | Alembic Chain Determinism | Alembic Graph & Revisions | 12 revs | 12 revs | 0 | 0 | 0 |
| **Consolidated Total** | | | **71** | **71** | **0** | **0** | **0** |

---

## 3. Real PostgreSQL Execution Evidence

### 3.1 Combined Test Suite Command & Output
- **Command:**
  ```powershell
  $env:DATABASE_URL="postgresql+asyncpg://roxy_test_usr:***@127.0.0.1:5433/roxy_isolated_test_db"
  pytest tests/test_gmail_token_storage_security.py \
         tests/test_payment_production_security.py \
         tests/integration/test_phase8_payments.py \
         tests/integration/test_gmail_token_real_postgres_integration.py \
         tests/integration/test_billing_real_postgres_integration.py -q
  ```
- **Exit Code:** `0`
- **Output:**
  ```
  ....................................................................     [100%]
  68 passed, 24 warnings in 61.98s (0:01:01)
  ```

### 3.2 Specific Real-PostgreSQL Verifications
1. **Gmail Encrypted Persistence:**
   - Real database transaction commit via `AsyncSession`.
   - Fresh session query from PostgreSQL confirming stored `encrypted_credentials_json` contains ciphertext.
   - Successful AES-Fernet decryption matching original access and refresh tokens.
   - Strict tenant isolation: synthetic User A cannot access User B's token.
   - Scoped deletion verified by absence of record in raw PostgreSQL.
2. **Billing Schema & Provider Persistence:**
   - `information_schema.columns` asserts existence of `provider`, `amount_usd`, `amount_pkr` in `subscriptions`.
   - Real subscription commit via `BillingRepository.update_or_create_subscription` with `provider='safepay'`.
   - Direct raw PostgreSQL query via `select(Subscription)` verifying row committed with exact monetary values.
   - Payment event idempotency: first webhook event commits `processed=True`; duplicate event with identical `(provider, provider_event_id)` is rejected as idempotent duplicate.
   - Credit wallet persistence: credit (+50,000) and debit (-1,000) reflect accurately in `credit_wallets` table.
   - Multi-tenant financial isolation: Tenant A Pro plan does not leak to Tenant B (remains Free default).
   - Production fail-closed: missing database configuration or connection errors raise `RuntimeError` and never fall back to in-memory dictionaries.

---

## 4. Worktree & File Changes Summary

| Modified / Created File | Rationale / Change Details |
|---|---|
| `backend/alembic/versions/012_billing_and_connectors_persistence.py` | Corrective Alembic migration creating/updating billing tables and connector persistence. |
| `backend/tests/integration/test_gmail_token_real_postgres_integration.py` | Permanent real PostgreSQL integration test suite for Gmail OAuth token lifecycle (9 tests). |
| `backend/tests/integration/test_billing_real_postgres_integration.py` | Permanent real PostgreSQL integration test suite for billing models, provider columns, and wallet persistence (7 tests). |
| `backend/src/app/billing/repository.py` | Gated writes against production in-memory fallback; fixed double-credit addition bug; ensured durable persistence. |
| `backend/src/app/billing/service.py` | Added fail-closed exception handling to webhook actions. |
| `backend/src/app/api/v1/billing.py` | Gated webhook errors to return HTTP 500 on persistence failure for gateway retry. |
| `.github/workflows/ci.yml` | Added permanent Gmail and Billing integration tests to CI `backend-ci` pipeline. |

---

## 5. Security & Sandbox Credentials Status

- **Production Credentials:** None requested, used, or stored. All production references remain secure and ready for authorized activation at deployment time.
- **Provider Sandbox Testing:** Completed in previous phase (`ROXY_PAYMENT_SANDBOX_E2E_VERIFICATION_REPORT.md`). Safepay sandbox checkout sessions and webhook HMAC signatures were verified. Stripe sandbox checkout remains gated by live network sandbox keys (reported honestly as BLOCKED where external keys are absent).
- **Deployment Status:** No production Cloud Run services were touched, and no live database was modified.
