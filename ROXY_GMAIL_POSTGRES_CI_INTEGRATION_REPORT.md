# ROXY-AI — GMAIL POSTGRESQL CI INTEGRATION & AUDIT REPORT

**Date:** 2026-10-15  
**Branch:** `release/audit-remediation`  
**Starting Commit SHA:** `236537ac5bedad4d97c1aab6ec38b6a6c1bfe6db`  
**Repository:** `roxyross/alibaba-ai-hacathon-chatbot`  
**Scope:** Workstream A — Permanent Real-PostgreSQL Gmail OAuth Token Persistence & CI Integration  
**Overall Status:** PASS  

---

## 1. Executive Summary

Workstream A has been fully completed and verified without mocking the database layer. The temporary scratch script `scratch/test_real_postgres_token_persistence.py` has been formalized into a permanent automated integration test suite located at:
`backend/tests/integration/test_gmail_token_real_postgres_integration.py`

This suite has been wired directly into the authoritative GitHub Actions CI pipeline (`.github/workflows/ci.yml`) under the `backend-ci` job. The test suite connects strictly to an isolated PostgreSQL test database (`roxy_isolated_test_db` / `roxy_test`), executes real commits with SQLAlchemy `AsyncSession` transactions, reads back from independent fresh sessions, decrypts tokens via AES-128 Fernet, tests upsert deduplication, refresh persistence, tenant isolation, revocation, and verifies fail-closed security when database connectivity is severed in production mode.

---

## 2. Test Architecture & Security Governance

### 2.1 Positive Database Guard
The integration test suite enforces strict pre-flight assertions before any database interaction:
- Queries `SELECT current_database(), inet_server_port()` dynamically.
- Requires the database name to match approved test identities (`roxy_isolated_test_db`, `roxy_test`, or `*_test`).
- Rejects any database target containing production markers (`prod`, `production`, `neon.tech`, `aws.neon`, `cloudsql`).
- Uses `poolclass=NullPool` on `create_async_engine` to prevent cross-event-loop connection contamination in `asyncpg`.

### 2.2 Synthetic Data & Zero-Secret Policy
- All test identities use unique UUIDs (e.g., `test_user_synthetic_alpha_<uuid>`).
- Encryption keys are generated dynamically in-memory per test function via `Fernet.generate_key()`.
- Zero real Google OAuth tokens, production credentials, or database passwords are hardcoded or committed.

### 2.3 Scoped Lifecycle & Cleanup
- All writes are committed to the physical `connector_instances` PostgreSQL table.
- Teardown blocks execute scoped `DELETE FROM connector_instances WHERE user_id = :uid`, ensuring zero impact on other records.

---

## 3. Test Cases Implemented

The test suite contains 9 comprehensive automated tests:

| Test Name | Verification Scope | Persistence Target | Result |
|---|---|---|---|
| `test_01_safety_gate_and_schema_verification` | Positive test DB identity check & `connector_instances` table verification | Real PostgreSQL (`roxy_isolated_test_db`) | **PASS** |
| `test_02_real_database_write_commit_and_encryption` | `_save_encrypted_token` commits encrypted ciphertext to `connector_instances` | Real PostgreSQL (`roxy_isolated_test_db`) | **PASS** |
| `test_03_fresh_session_retrieval_and_decryption` | `_load_user_token_payload` reads from independent session & decrypts valid token | Real PostgreSQL (`roxy_isolated_test_db`) | **PASS** |
| `test_04_strict_tenant_isolation_and_tampering_rejection` | Tenant A cannot access Tenant B; tampered ciphertext returns `None` | Real PostgreSQL (`roxy_isolated_test_db`) | **PASS** |
| `test_05_upsert_single_row_no_duplicates` | Multiple token saves for the same user update existing row without duplicates | Real PostgreSQL (`roxy_isolated_test_db`) | **PASS** |
| `test_06_refresh_flow_persists_to_real_postgres` | Expired token refresh persists new access token directly into PostgreSQL | Real PostgreSQL (`roxy_isolated_test_db`) | **PASS** |
| `test_07_revocation_and_scoped_deletion` | `_delete_user_token` removes row from PostgreSQL connector table | Real PostgreSQL (`roxy_isolated_test_db`) | **PASS** |
| `test_08_production_fail_closed_missing_database_url` | Production mode without `DATABASE_URL` fails closed without local disk fallback | Isolated environment / No DB write | **PASS** |
| `test_09_production_fail_closed_database_write_failure` | Production mode with DB connection failure fails closed with `RuntimeError` | Mocked DB failure / Fail-closed assert | **PASS** |

---

## 4. Execution Evidence

### 4.1 Local Isolated PostgreSQL Execution
- **Command:**
  ```powershell
  $env:DATABASE_URL="postgresql+asyncpg://roxy_test_usr:***@127.0.0.1:5433/roxy_isolated_test_db"
  pytest tests/integration/test_gmail_token_real_postgres_integration.py -v
  ```
- **Exit Code:** `0`
- **Output:**
  ```
  tests/integration/test_gmail_token_real_postgres_integration.py::test_01_safety_gate_and_schema_verification PASSED [ 11%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_02_real_database_write_commit_and_encryption PASSED [ 22%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_03_fresh_session_retrieval_and_decryption PASSED [ 33%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_04_strict_tenant_isolation_and_tampering_rejection PASSED [ 44%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_05_upsert_single_row_no_duplicates PASSED [ 55%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_06_refresh_flow_persists_to_real_postgres PASSED [ 66%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_07_revocation_and_scoped_deletion PASSED [ 77%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_08_production_fail_closed_missing_database_url PASSED [ 88%]
  tests/integration/test_gmail_token_real_postgres_integration.py::test_09_production_fail_closed_database_write_failure PASSED [100%]
  ============================== 9 passed in 6.12s ==============================
  ```

---

## 5. CI Workflow Integration (`.github/workflows/ci.yml`)

The permanent integration test has been integrated into `.github/workflows/ci.yml`:
1. **Isolated Service Container:** CI starts `pgvector/pgvector:pg16` with database `roxy_test` on port 5432 with readiness health-checks (`pg_isready`).
2. **Deterministic Migration:** Runs `python -m alembic upgrade head` to apply all 12 migration revisions (including `012_billing_and_connectors_persistence.py`).
3. **Execution Step:** Added `tests/integration/test_gmail_token_real_postgres_integration.py` to `Run backend integration test suite` with `DATABASE_URL` pointing to `roxy_test` and encryption key configured.
4. **CI Discovery Assertion:** `tests/test_security_ci_discovery.py` passed with 3/3 tests confirming workflow coverage.

---

## 6. Remaining Blockers & Next Actions
- **External Blockers:** None for Gmail integration testing. Real Google OAuth user login in production requires authorized production OAuth client credentials at launch.
- **Production Status:** Gated and secure. Fail-closed safeguards prevent unencrypted disk storage in production.
