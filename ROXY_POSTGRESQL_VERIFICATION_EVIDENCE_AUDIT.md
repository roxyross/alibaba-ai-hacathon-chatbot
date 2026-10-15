# ROXY-AI — POSTGRESQL VERIFICATION EVIDENCE AUDIT & PRODUCTION READINESS GATE

**Audit Date:** 2026-10-15  
**Auditor:** Antigravity Code & Evidence Auditor  
**Target Branch:** `release/audit-remediation`  
**Audited Commit SHA:** `236537ac5bedad4d97c1aab6ec38b6a6c1bfe6db`  
**CI Workflow Run:** [Run 38748355689](https://github.com/roxyross/alibaba-ai-hacathon-chatbot/actions/runs/38748355689) (Conclusion: `success`, Duration: `4m 0s`)  
**Working Tree Status:** Clean (`## release/audit-remediation...origin/release/audit-remediation`)

---

## 1. EXECUTIVE AUDIT VERDICT

| Evaluation Area | Status | Summary |
| :--- | :--- | :--- |
| **Isolated PostgreSQL Integration** | **PASS** | Real PostgreSQL write, commit, retrieval, decryption, tenant isolation, upsert, refresh persistence, and deletion verified on PostgreSQL 16 container (`127.0.0.1:5433`) with **zero mocked database methods**. |
| **Existing Unit Test Suite (`test_gmail_token_storage_security.py`)** | **AUDITED / MOCK-BASED** | All 20 tests pass, but all database tests within this file use in-memory dictionaries or mocked helper functions (`_mock_save`, `_mock_load`, `_mock_delete_from_db`). |
| **Production Fail-Closed Enforcement (SEC-06)** | **PASS** | Verified that in production mode, missing `DATABASE_URL` and database write failures fail closed (`False`), raising `OAuthError` in OAuth callback and writing zero disk files. |
| **Configuration Path & Fallback Risks** | **LOW RISK (Documented)** | `app/db.py` contains a fallback to `localhost:5432/roxy_dev` if `raw` is empty, but `EmailSendSkill` defends against this with explicit `os.environ.get("DATABASE_URL")` guards. |
| **Cloud SQL / Cloud Run Production DB Connectivity** | **NOT VERIFIED** | **Strict Safety Boundary:** Zero connection to production DB from this environment. |
| **Real Google OAuth & Live Token Exchange** | **NOT VERIFIED** | **Strict Safety Boundary:** Zero real Google API calls or token exchanges executed. |
| **Production Email Delivery** | **NOT VERIFIED** | **Strict Safety Boundary:** Zero live emails sent. |

**Final Honest Verdict:**  
The evidence gap regarding **PostgreSQL driver compatibility, ORM schema alignment, transactional commit, AES-Fernet encryption/decryption, and query-level tenant isolation** is **fully resolved**. However, this pass applies strictly to the **isolated local database tier**. Roxy-AI as a whole is **NOT** declared production-ready until the distinct staging/production cloud gates (Secret Manager, Cloud SQL network peering, and Google OAuth credentials) are verified in authorized runtime environments.

---

## 2. CLAIM-BY-CLAIM VERIFICATION MATRIX

Audit of every claim stated in `ROXY_ISOLATED_POSTGRES_VERIFICATION_REPORT.md`:

| # | Claim in Verification Report | Verification Status | Exact Evidence / Line Reference |
| :--- | :--- | :---: | :--- |
| **1** | Static type & linter diagnostics resolved in `test_gmail_token_storage_security.py` lines 445–491. | **PASS** | [`test_gmail_token_storage_security.py:441-509`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/tests/test_gmail_token_storage_security.py#L441-L509). Mypy passed (`Success: no issues found`), Ruff passed (`All checks passed!`), Pytest passed 20/20 in 2.87s. Committed as `236537a`. |
| **2** | Docker engine active and container bound strictly to localhost loopback. | **PASS** | Docker Engine `29.7.2`, Docker Desktop `4.87.0`. Container `roxy-isolated-test-postgres` ran on `127.0.0.1:5433->5432/tcp`. Zero public exposure. |
| **3** | Database identity verified as isolated test database. | **PASS** | Executed SQL `SELECT current_database(), inet_server_port()`. Confirmed database name `roxy_isolated_test_db` on server version PostgreSQL `16.15`. |
| **4** | `connector_instances` table and all 14 ORM columns present and compatible. | **PASS** | Verified against [`app/models/connector.py:20-61`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/models/connector.py#L20-L61). All 14 columns confirmed: `id`, `user_id`, `workspace_id`, `connector_type`, `name`, `description`, `auth_type`, `config_json`, `encrypted_credentials_json`, `status`, `last_health_check_at`, `error_message`, `created_at`, `updated_at`. |
| **5** | Real PostgreSQL write and commit (`_save_encrypted_token`). Plaintext absent. | **PASS** | Verified via direct SQL query with `AsyncSession`. Row persisted in `connector_instances` with `status='active'`, `connector_type='gmail'`. Full-text scan across row confirmed raw token plaintext was absent. |
| **6** | Separate-session retrieval and AES-Fernet decryption. | **PASS** | Fresh `EmailSendSkill` instance with empty disk directory loaded ciphertext from PostgreSQL, decrypted payload, and matched synthetic tokens. |
| **7** | Multi-tenant isolation and identity tampering protection. | **PASS** | Unregistered user received `None`; distinct users retrieved only their own tokens; injected row with mismatched user_id in ciphertext was blocked (`email_send.cross_user_token_access_blocked`). |
| **8** | Token upsert updates single row without duplicate records. | **PASS** | Second save for same user updated existing row in-place; `SELECT COUNT(*)` confirmed exactly 1 row. |
| **9** | Expired token refresh flow commits refreshed credentials to PostgreSQL. | **PASS** | Mocked only external Google HTTP endpoint; real `_save_encrypted_token` committed refreshed token to PostgreSQL. Direct database query verified updated row. |
| **10**| Token revocation physically deletes row from PostgreSQL. | **PASS** | `_delete_user_token` executed SQL `DELETE FROM connector_instances WHERE user_id = ...`. Direct query confirmed `SELECT COUNT(*) == 0`. |
| **11**| Production fail-closed rules (SEC-06) enforced. | **PASS** | Under `ENVIRONMENT=production`, missing `DATABASE_URL` and simulated DB write failure returned `False` with zero local disk writes. |
| **12**| Disposable container teardown and clean working tree. | **PASS** | `docker stop` and `docker rm` returned exit code 0. `docker ps -a` returned 0 containers. `git status` confirmed clean working tree. |

---

## 3. CODE TRACING & TEST METHODOLOGY AUDIT ("MOCK VS. REAL")

### 3.1 Trace of Critical Functions in [`app/skills/email_send.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/skills/email_send.py)

#### 1. `_save_token_to_db(user_id, container)` (Lines 184–233)
- **Database Layer:** Calls `app.db.get_session_factory()`. Creates an `AsyncSession`, executes `select(ConnectorInstance).where(...)`, and either updates `existing.encrypted_credentials_json` or inserts a new `ConnectorInstance` object.
- **Commit Verification:** Executes `await session.commit()` (Line 226).
- **Error Handling:** Wraps execution in `try ... except Exception as exc: log.warning(...); return False` (Lines 231–233).
- **Safety Gate:** Checks `if not os.environ.get("DATABASE_URL"): return False` (Line 186).

#### 2. `_save_encrypted_token(user_id, payload)` (Lines 273–349)
- **Encryption:** Encrypts `json.dumps(payload_to_encrypt)` via Fernet authenticated cipher (Line 283).
- **Production Gate (`is_prod`):**
  - If `not has_db`: logs `production_missing_database_url` and returns `False` (Lines 298–304).
  - If `not db_saved`: logs `durable_db_write_failed` and returns `False` (Lines 307–313).
  - On success: returns `True` immediately (Line 316). **Never writes to local disk in production.**
- **Development Fallback:** Only if `not is_prod` and `not has_db` and `REQUIRE_DURABLE_TOKEN_STORE` is not set, persists to `gmail_token_{user_id}.json` (Lines 337–344).

#### 3. `_load_token_from_db(user_id)` (Lines 235–271)
- **Database Layer:** Calls `app.db.get_session_factory()`. Creates an `AsyncSession`, executes `select(ConnectorInstance).where(user_id == ..., connector_type == 'gmail')`, and extracts `item.encrypted_credentials_json`.
- **Safety Gate:** Checks `if not os.environ.get("DATABASE_URL"): return None` (Line 237).

#### 4. `_load_user_token_payload(user_id)` (Lines 350–417)
- **Primary Source:** Queries `_load_token_from_db(user_id)` (Line 356).
- **Production Guard:** Local disk fallback is strictly wrapped in `if not data and not is_prod:` (Line 361).
- **Tenant Isolation Enforcement:** Decrypts ciphertext and checks `if payload.get("user_id") and payload["user_id"] != user_id: return None` (Lines 397–399).

#### 5. `_refresh_token(user_id, refresh_token)` (Lines 430–470)
- **Refresh Execution:** Makes HTTP POST to `https://oauth2.googleapis.com/token`.
- **Durable Persistence Requirement:** Calls `self._save_encrypted_token(...)` (Line 455). If save fails, logs `token_refresh_persistence_failed` and returns `None` (Lines 463–465). **Does not return success if database persistence fails.**

#### 6. `_delete_token_from_db(user_id)` (Lines 471–501)
- **Database Layer:** Issues `delete(ConnectorInstance).where(user_id == ..., connector_type == 'gmail')` and executes `await session.commit()`.

#### 7. `_delete_user_token(user_id)` (Lines 503–510)
- Calls `_delete_token_from_db(user_id)` and deletes local file if present.

---

### 3.2 Audit of Tests in [`test_gmail_token_storage_security.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/tests/test_gmail_token_storage_security.py)

| Test Name | Lines | Real DB or Mocked? | Mocking Details & Assessment |
| :--- | :---: | :---: | :--- |
| `test_durable_multi_instance_token_persistence` | 269–314 | **MOCKED** | Replaces `_save_token_to_db` and `_load_token_from_db` with an in-memory dictionary `shared_db_store`. Does not test real PostgreSQL. |
| `test_database_write_failure_returns_false_and_does_not_claim_success` | 316–335 | **MOCKED** | Replaces `_save_token_to_db` with a lambda returning `False`. Tests control-flow only. |
| `test_container_restart_restores_token_from_db` | 376–413 | **MOCKED** | Replaces `_save_token_to_db` and `_load_token_from_db` with an in-memory dictionary `db_storage`. Does not test real PostgreSQL. |
| `test_db_session_factory_unavailable_fails_closed` | 415–430 | **MOCKED** | Replaces `app.db.get_session_factory` with lambda returning `None`. Tests fallback suppression. |
| `test_refreshed_token_persistence_failure_fails_closed` | 432–456 | **MOCKED** | Mocks `httpx.post` and `_save_encrypted_token`. Tests error propagation only. |
| `test_revocation_clears_database_and_local_token` | 458–480 | **MOCKED** | Replaces `_delete_token_from_db` with a list tracking deleted IDs. |
| `test_oauth_callback_fails_closed_in_production_when_token_persistence_fails` | 483–515 | **MOCKED** | Mocks `_save_encrypted_token` to return `False`. Tests `complete_google_callback` raises `OAuthError`. |

**Auditor Finding:**  
While [`test_gmail_token_storage_security.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/tests/test_gmail_token_storage_security.py) provides 100% test pass rates in CI, **none of its tests exercise a real PostgreSQL connection**.

### 3.3 Audit of Scratch Script `test_real_postgres_token_persistence.py`

- **Execution Mode:** Executed directly via `.venv\Scripts\python.exe` against Docker container `roxy-isolated-test-postgres` on `127.0.0.1:5433`.
- **Database Calls:** **100% REAL.** No database mocks. All writes, commits, updates, queries, and deletions used genuine SQLAlchemy `AsyncSession` transactions against PostgreSQL 16.
- **Verification Result:** All 8 integration stages passed cleanly with exit code 0.

---

## 4. AUDIT OF CONFIGURATION PATH & FAIL-CLOSED RISKS

### 4.1 Investigation: `normalize_database_url("")` in [`backend/src/app/db.py`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/db.py)

```python
# Lines 47-48:
if not raw:
    return ("postgresql+asyncpg://postgres:postgres@localhost:5432/roxy_dev", {})
```

**Risk Assessment:**
- **Could `EmailSendSkill` accidentally connect to `localhost:5432/roxy_dev`?**
  **NO.** `EmailSendSkill` performs an explicit pre-check:
  ```python
  if not os.environ.get("DATABASE_URL"):
      return False / return None
  ```
  Furthermore, `get_session_factory()` (Line 111) checks `if not os.environ.get("DATABASE_URL"): return None`. Thus, `_session_factory()` is never called by `EmailSendSkill` when `DATABASE_URL` is empty.
- **Could other parts of the application connect to `roxy_dev`?**
  **YES (Architectural Risk).** FastAPI routes using `get_db()` dependency (Line 120) call `_session_factory()` directly without checking `os.environ.get("DATABASE_URL")`. If `DATABASE_URL` is completely absent in an environment, `get_engine()` will attempt to connect to `localhost:5432/roxy_dev`.

### 4.2 Investigation: Environment Detection (`_is_production`)

[`app/skills/email_send.py:104-117`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/skills/email_send.py#L104-L117):
- Evaluates `APP_ENV`, `ENV`, `ENVIRONMENT`, Vercel environment flags, and HTTPS URL prefixes.
- **Robustness:** High. Setting `ENVIRONMENT=production` or `APP_ENV=production` triggers the production branch.

### 4.3 Investigation: Can a DB Error Trigger Local File Fallback in Production?

- In [`_save_encrypted_token`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/skills/email_send.py#L296-L316):
  ```python
  if is_prod:
      if not has_db:
          return False
      db_saved = self._save_token_to_db(user_id, container)
      if not db_saved:
          return False
      return True
  ```
- **Conclusion:** **IMPOSSIBLE.** If `is_prod` is `True`, code execution terminates at Line 304, Line 313, or Line 316. Lines 337–344 (local file write) are strictly unreachable in production mode.

---

## 5. ARTIFACT & CLEANUP AUDIT

- **Container Removal Verification:**
  - `docker ps -a --filter "name=roxy-isolated-test-postgres"`: Executed, output was empty (0 containers).
- **Database Records Cleanup:**
  - Test synthetic users (`test_user_synthetic_alpha_1`, `test_user_synthetic_beta_2`, `test_user_synthetic_refresh_4`, `test_user_synthetic_gamma_3`) were deleted via SQL `DELETE` during Test 7.
  - Final query confirmed `SELECT COUNT(*) == 0`.
- **Working Tree Cleanliness:**
  - Branch: `release/audit-remediation`
  - Commit SHA: `236537ac5bedad4d97c1aab6ec38b6a6c1bfe6db`
  - Git status: Clean working tree (untracked `roxy-slim.zip` packaging bundle only).
- **CI Verification:**
  - GitHub Actions Workflow Run `38748355689` confirmed `success` on commit `236537a`.

---

## 6. PRODUCTION READINESS BOUNDARY & GATES

To ensure complete production integrity, the following gates remain strictly separated:

```
[GATE 1: Local Isolated PostgreSQL Integration]
    ├── Status: PASSED (100% verified via real AsyncSession transactions)
    └── Scope: Driver, ORM models, SQL syntax, encryption/decryption, tenant isolation

[GATE 2: Production Cloud SQL & Secret Manager Configuration]
    ├── Status: NOT VERIFIED (Strict safety rule: zero live production DB access)
    └── Scope: VPC connector, Secret Manager IAM bindings, Cloud Run environment mapping

[GATE 3: Real Google OAuth & Live Token Exchange]
    ├── Status: NOT VERIFIED (Strict safety rule: zero real OAuth code exchanges)
    └── Scope: Google Cloud Console authorized redirect URIs, OAuth consent screen verification

[GATE 4: Production Gmail API Email Delivery]
    ├── Status: NOT VERIFIED (Strict safety rule: zero live emails sent)
    └── Scope: Real Gmail API scopes, live mailbox quota, production deliverability
```

---

## 7. SMALLEST NEXT ACTIONS FOR UNRESOLVED ITEMS

1. **Formalize Permanent Integration Test in Repo:**
   - **Action:** Convert the scratch integration test into a permanent test file at `backend/tests/integration/test_gmail_token_real_postgres_integration.py`.
   - **Implementation:** Guard with `@pytest.mark.skipif(not _is_isolated_test_db(os.environ.get("DATABASE_URL")), reason="Requires isolated test database")`. This allows CI service containers (which already spin up PostgreSQL on 5432) to execute real database integration tests on every commit without touching developer machines.

2. **Harden `normalize_database_url` in `app/db.py`:**
   - **Action:** In [`backend/src/app/db.py:47-48`](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/db.py#L47-L48), if `raw` is empty and `EmailSendSkill._is_production()` is True, raise `ValueError("DATABASE_URL must be configured in production mode")` instead of silently returning `localhost:5432/roxy_dev`.

3. **Stage-Gate Production Promotion:**
   - **Action:** Retain `release/audit-remediation` until staging environment validation (Cloud Run test revision with Secret Manager integration) is authorized and executed.
