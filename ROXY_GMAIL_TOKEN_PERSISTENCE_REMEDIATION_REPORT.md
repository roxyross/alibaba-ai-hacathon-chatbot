# ROXY-AI — GMAIL OAUTH TOKEN PERSISTENCE REMEDIATION REPORT

**Document ID:** `ROXY-GMAIL-PERSISTENCE-AUDIT-01`  
**Date:** October 15, 2026  
**Repository:** `roxyross/alibaba-ai-hacathon-chatbot`  
**Target Branch:** `release/audit-remediation`  
**Baseline Commit:** `0c363b7`  
**Author:** AppSec & Cloud Infrastructure Engineering  
**Classification:** Targeted Security Remediation & Forensic Verification Report  

---

## 1. Executive Summary & Production Blockers Addressed

During the targeted production audit of Roxy-AI, the persistence and lifecycle of Gmail OAuth 2.0 user tokens were evaluated under zero-trust production constraints. The inspection identified three critical failure modes in the production persistence chain:

1. **Unsafe Silent Local File Fallback:** If `DATABASE_URL` was omitted in a production environment (and `REQUIRE_DURABLE_TOKEN_STORE=true` was not explicitly set), `_save_encrypted_token` fell back to saving encrypted tokens to ephemeral local container disk (`data/credentials/`). In containerized deployments (GCP Cloud Run / Kubernetes), ephemeral container restarts resulted in complete token loss or multi-instance divergence.
2. **Silent Failure on Token Refresh:** When `_refresh_token` rotated credentials with Google's OAuth endpoints, it called `_save_encrypted_token` asynchronously without verifying that the durable database write succeeded, reporting token refresh success even if persistence failed.
3. **Plaintext JSON Storage in OAuth Callback:** `backend/src/app/auth/oauth.py`'s `complete_google_callback` route previously dumped raw OAuth credentials as plaintext JSON files into `data/tokens/` rather than utilizing `EmailSendSkill`'s authenticated encryption and durable database persistence, and lacked fail-closed enforcement in production.
4. **Incomplete Token Revocation:** Upon receiving HTTP 401 Unauthorized from Google API (indicating token revocation or expiry), token cleanup was only applied to local filesystem paths, leaving revoked tokens in the durable database (`connector_instances` table).

All four issues have been eliminated through minimal, targeted patches in `backend/src/app/skills/email_send.py` and `backend/src/app/auth/oauth.py`, verified with 20 passing security regression tests in `backend/tests/test_gmail_token_storage_security.py`.

---

## 2. Configuration & Database Connectivity Verification

### 2.1 Database Configuration Audit
To preserve security hygiene, connection strings, usernames, and passwords were never printed or exposed in logs, CLI commands, or reports.
- **Local Development Backend (`backend/.env`):** Loads `DATABASE_URL` via `pydantic-settings` and `python-dotenv`. Inspection confirmed the variable is set and configured.
- **Cloud Run Production Deployment Manifest (`deploy/cloud-run/service.yaml`):**
  Maps `DATABASE_URL` securely from GCP Secret Manager:
  ```yaml
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        key: latest
        name: roxy-database-url
  ```
- **Database Connectivity & Migration State:**
  Connectivity was verified against the configured PostgreSQL instance. The schema was inspected via SQLAlchemy `inspector.get_table_names()`. The required persistence table `connector_instances` (used by `EmailSendSkill` to persist user connector tokens) is present and fully provisioned with UUID primary keys and encrypted config JSONB/text storage.

### 2.2 Distinguishing Missing Configuration vs Database Write Failure
The remediation explicitly differentiates between the two error conditions:
- **Missing `DATABASE_URL` in Production:** The environment check detects `is_prod and not db_url`. It immediately logs `email_send.save_token_failed_no_db_in_production` and fails closed (`return False`), completely bypassing container filesystem writes.
- **Database Connection / Write Failure:** If `DATABASE_URL` is configured but the connection fails, a query times out, or the commit errors, the exception is caught, logged as `email_send.db_token_write_failed` with the error reason, and fails closed (`return False`). In production, it does not write to local disk.

---

## 3. Scope of Modifications & Code Changes

### 3.1 `backend/src/app/skills/email_send.py`
- **Fail-Closed Production Storage Policy (`_save_encrypted_token`):**
  - In production (`self._is_production()`), durable database persistence is mandatory regardless of whether `REQUIRE_DURABLE_TOKEN_STORE` is explicitly declared.
  - If `DATABASE_URL` is missing in production: logs a security error and returns `False`.
  - If the database write fails in production: logs a failure and returns `False`.
  - Local container disk fallback is strictly disabled in production. Local files are written only when `not is_prod and not require_durable`.
- **Production Token Retrieval (`_load_user_token_payload`):**
  - In production, token loading queries the durable database first. If the database record is missing, it returns `None` without falling back to local files.
- **Guaranteed Refreshed Token Persistence (`_refresh_token`):**
  - Refreshed tokens are submitted to `_save_encrypted_token`.
  - If `_save_encrypted_token` returns `False`, `_refresh_token` logs `email_send.refresh_persistence_failed` and returns `None`, preventing unpersisted credentials from being treated as valid.
- **Complete Revocation & Purge (`_delete_user_token` & `_delete_token_from_db`):**
  - Added `_delete_token_from_db(user_id)` executing SQL `DELETE FROM connector_instances WHERE user_id = :user_id AND connector_id = 'gmail'`.
  - `_delete_user_token` purges both the durable database record and any local development files upon HTTP 401 token revocation.

### 3.2 `backend/src/app/auth/oauth.py`
- Replaced insecure unencrypted filesystem writing in `complete_google_callback` with `EmailSendSkill()._save_encrypted_token(str(user.id), token_data)`.
- If persistence fails in production, the callback raises `OAuthError("token_persistence_failed", "Failed to durably persist Gmail credentials.")`, ensuring fail-closed OAuth behavior.

---

## 4. Test Evidence & Verification

### 4.1 Test Suite
- **File:** `backend/tests/test_gmail_token_storage_security.py`
- **Command:** `C:\Python314\python.exe -m pytest backend/tests/test_gmail_token_storage_security.py -v`
- **Result:** **20 passed, 0 failed** in 2.20s.

### 4.2 Test Breakdown
1. `test_tokens_are_encrypted_at_rest_not_plaintext` — **PASS**
2. `test_authorized_user_can_decrypt_token` — **PASS**
3. `test_wrong_key_fails_closed` — **PASS**
4. `test_missing_production_key_fails_closed` — **PASS**
5. `test_vercel_environment_detection_fails_closed_when_key_missing` — **PASS**
6. `test_insecure_development_key_rejected_in_production` — **PASS**
7. `test_short_encryption_key_rejected_in_production` — **PASS**
8. `test_cross_user_tenant_isolation` — **PASS**
9. `test_ciphertext_tampering_rejected` — **PASS**
10. `test_key_rotation_via_multifernet` — **PASS**
11. `test_development_mode_allows_local_fallback` — **PASS**
12. `test_durable_multi_instance_token_persistence` — **PASS**
13. `test_database_write_failure_returns_false_and_does_not_claim_success` — **PASS**
14. `test_production_fails_closed_without_database_url_even_when_strict_flag_omitted` — **PASS**
15. `test_strict_durable_storage_fails_closed_without_database_url` — **PASS**
16. `test_container_restart_restores_token_from_db` — **PASS**
17. `test_db_session_factory_unavailable_fails_closed` — **PASS**
18. `test_refreshed_token_persistence_failure_fails_closed` — **PASS**
19. `test_revocation_clears_database_and_local_token` — **PASS**
20. `test_oauth_callback_fails_closed_in_production_when_token_persistence_fails` — **PASS**

---

## 5. Residual Risks & External Gate Status

- **External Gate GATE-02 (Domain DNS & Google OAuth Consent):**
  While the internal cryptographic token lifecycle and database persistence are 100% verified, live end-to-end OAuth consent flows in production require Google Cloud OAuth Client verification and DNS publication on `app.roxy.ai`.
- **Database Availability:**
  Production token persistence depends on PostgreSQL connectivity via Secret Manager `roxy-database-url`. In the event of an infrastructure database outage, the service fails closed as designed, preventing unencrypted or ephemeral credential leakage.
