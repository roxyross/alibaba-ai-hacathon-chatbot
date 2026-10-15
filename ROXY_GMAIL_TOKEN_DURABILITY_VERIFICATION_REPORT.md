# ROXY-AI — GMAIL OAUTH TOKEN DURABILITY & PERSISTENCE REPORT

## 1. Executive Summary

This report documents the security audit, fail-closed remediation, and durable real-PostgreSQL verification of Roxy-AI's Gmail OAuth token persistence subsystem.

All verification criteria have passed with zero mocked database calls in the integration suite:
- **Persistence Mechanism:** Tokens are durably persisted in the `connector_instances` PostgreSQL table with AES-Fernet encryption at rest.
- **Fail-Closed in Production:** In production environments (`ENVIRONMENT=production` or `VERCEL=1`), missing `DATABASE_URL` or database write/connection failures immediately raise a fail-closed exception. Under no circumstances are tokens written to local plaintext or unencrypted files in production.
- **Tenant Isolation:** Multi-tenant separation is strictly enforced at the SQL query and session levels (`WHERE user_id = :uid AND connector_type = 'gmail'`).
- **Idempotent Upserts:** Repeated OAuth authorizations cleanly update the existing token record for that user without creating duplicate rows.
- **Revocation Safety:** Token deletion and revocation cleanly wipe persisted credentials from PostgreSQL.

---

## 2. Threat Model & Remediation Architecture

### 2.1 Threat: Ephemeral Local File Fallback in Multi-Instance Production
In earlier revisions, when `DATABASE_URL` was absent or a database write threw an exception, the system fell back to writing credentials to a local token file (`token.json` or `.credentials/`). In multi-container or serverless deployments (e.g. Cloud Run, Kubernetes, Vercel):
1. Local disk storage is ephemeral and unshared across replicas, causing subsequent requests on other instances to fail authentication or trigger repeated OAuth re-prompts.
2. Writing tokens to container filesystems risks leaking credentials in container snapshots or unauthorized volume mounts.

### 2.2 Remediation
In `backend/src/app/skills/email_send.py`:
```python
def _is_production() -> bool:
    env = os.environ.get("ENVIRONMENT", "").lower()
    return env in ("production", "prod") or bool(os.environ.get("VERCEL"))

# Fail closed when saving in production
if _is_production():
    if not os.environ.get("DATABASE_URL"):
        logger.error("Production requires DATABASE_URL for durable Gmail token storage.")
        return False
    # If DB write fails, immediately return False and abort OAuth flow:
    if not success:
        logger.error("Production database write failed. Refusing fallback to local file.")
        return False
```
In `backend/src/app/auth/oauth.py`:
OAuth callback handler checks the boolean result of token persistence. If persistence returns `False` in production, the callback raises HTTP 500 / redirects to an explicit error rather than granting a session with an unsaved or unpersisted token.

### 2.3 Encryption at Rest
Tokens are encrypted using AES-128-CBC with HMAC-SHA256 authenticated encryption via `cryptography.fernet.Fernet` and `MultiFernet` for key rotation:
- Key loaded securely from `GMAIL_TOKEN_ENCRYPTION_KEY` or Secret Manager.
- Production startup validates that the encryption key is not a known weak placeholder (e.g. `dev_secret_key_...`) and is a valid 32-byte url-safe base64 string.
- Ciphertext tampering is detected and rejected with authentication failure.

---

## 3. Real PostgreSQL Verification Evidence

### 3.1 Test Configuration
- **Database Engine:** PostgreSQL 16.0 (Docker container `roxy-isolated-test-postgres` on `127.0.0.1:5433`)
- **Database Name:** `roxy_isolated_test_db`
- **Driver:** `asyncpg` via SQLAlchemy 2.0 AsyncEngine (`NullPool`)
- **Isolation:** Dedicated database, fresh async sessions, transaction isolation with rollback and explicit cleanup fixtures.

### 3.2 Real PostgreSQL Integration Test Results
File: `backend/tests/integration/test_gmail_token_real_postgres_integration.py`
Command: `pytest tests/integration/test_gmail_token_real_postgres_integration.py -v`
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

======================= 9 passed in 6.35s ========================
```

### 3.3 Security Suite Coverage
File: `backend/tests/test_gmail_token_storage_security.py`
Command: `pytest tests/test_gmail_token_storage_security.py -v`
```
20 passed in 1.48s
- test_tokens_are_encrypted_at_rest_not_plaintext: PASSED
- test_authorized_user_can_decrypt_token: PASSED
- test_wrong_key_fails_closed: PASSED
- test_missing_production_key_fails_closed: PASSED
- test_vercel_environment_detection_fails_closed_when_key_missing: PASSED
- test_insecure_development_key_rejected_in_production: PASSED
- test_short_encryption_key_rejected_in_production: PASSED
- test_cross_user_tenant_isolation: PASSED
- test_ciphertext_tampering_rejected: PASSED
- test_key_rotation_via_multifernet: PASSED
- test_development_mode_allows_local_fallback: PASSED
- test_durable_multi_instance_token_persistence: PASSED
- test_database_write_failure_returns_false_and_does_not_claim_success: PASSED
- test_production_fails_closed_without_database_url_even_when_strict_flag_omitted: PASSED
- test_strict_durable_storage_fails_closed_without_database_url: PASSED
- test_container_restart_restores_token_from_db: PASSED
- test_db_session_factory_unavailable_fails_closed: PASSED
- test_refreshed_token_persistence_failure_fails_closed: PASSED
- test_revocation_clears_database_and_local_token: PASSED
- test_oauth_callback_fails_closed_in_production_when_token_persistence_fails: PASSED
```

---

## 4. Operational & Deployment Verification

1. **Environment Variables Required for Production:**
   - `DATABASE_URL`: Must point to the production PostgreSQL cluster.
   - `GMAIL_TOKEN_ENCRYPTION_KEY`: 32-byte url-safe base64-encoded key. Must be persistent across container restarts.
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Configured in Google Cloud Console with authorized redirect URIs.
2. **Post-Deployment Verification:**
   - Ensure table `connector_instances` exists and has index on `(user_id, connector_type)`.
   - Ensure health endpoint `/health` and `/api/v1/billing/config` confirm database readiness.
