# ROXY-AI — SEC-03 OAuth State, Browser Binding & Replay Protection Remediation Report

**Document ID:** `ROXY-SEC-03-REV3`  
**Date:** October 14, 2026  
**Target Release:** Consolidated Launch Candidate (LC-1)  
**Branch:** `release/audit-remediation`  
**Author:** AppSec & Principal Identity Architect  
**Classification:** Technical Remediation & Verification Audit  

---

## 1. Executive Summary

During the security audit of `backend/src/app/auth/oauth_state.py`, two critical vulnerabilities were identified in the OAuth 2.0 CSRF mitigation and replay prevention subsystem:
1. **Inverted Production Cookie Check:** The state validation logic previously contained an inverted condition (`if not _is_production() and not cookie_value: return False`), which inadvertently allowed production callbacks to proceed with a signed state parameter *without* requiring the corresponding browser-binding cookie (`roxy.oauth_state`). This broke the session binding between the user's browser and the incoming OAuth callback.
2. **Process-Local Replay Tracking:** Replay protection relied exclusively on an in-memory Python `set` with a process-local `threading.Lock`. In horizontally scaled deployments (such as multi-worker Uvicorn configurations, container fleets, or serverless functions), a captured OAuth state could be replayed against an alternate worker instance before expiration.

Both vulnerabilities have been completely remediated through architectural redesign. The new implementation enforces strict browser-cookie binding across all environments, uses constant-time cryptographic verification, and implements a distributed atomic single-use replay store backed by Redis (`SET ... EX ... NX`) with a fail-closed posture when production distributed storage is absent or unreachable.

---

## 2. Vulnerability Analysis & Threat Model

### Threat Vector 1: Cross-Site State Injection & Login CSRF
- **Mechanism:** An attacker initiates an OAuth authorization flow on their own device, captures the provider authorization code and server-signed `state`, and tricks a victim into clicking the callback URL (`/api/v1/auth/oauth/google/callback?code=...&state=...`).
- **Impact under Prior Code:** Because production did not reject requests missing the browser cookie, the victim's browser would process the callback, tying the victim's session to the attacker's Google account or logging the victim into an attacker-controlled workspace.
- **Remediation:** In `consume_state()`, the browser-bound cookie `roxy.oauth_state` is now unconditionally required. If the cookie is missing or does not match the request query state under constant-time `secrets.compare_digest()`, the request is immediately rejected (`False`).

### Threat Vector 2: Multi-Worker Race & State Replay
- **Mechanism:** An attacker attempts to submit the same valid OAuth callback multiple times concurrently or across different worker processes behind a load balancer.
- **Impact under Prior Code:** Worker A recorded consumption in its local heap memory. A concurrent or subsequent request routed to Worker B had no visibility into Worker A's consumed set, permitting state reuse.
- **Remediation:** Replay tracking has been elevated to an atomic distributed store (`RedisReplayStore`). Using `client.set(key, "1", ex=STATE_TTL_SECONDS, nx=True)`, the first worker to write the key atomically claims the state; all subsequent or concurrent attempts return `False`. If Redis is unavailable or unconfigured in production, the system fails closed (`FailClosedReplayStore`).

---

## 3. Architecture & Implementation Specification

### 3.1. Browser-Bound Cookie Security
State cookies are configured with strict defensive flags:
- `HttpOnly=True`: Prohibits client-side JavaScript access via `document.cookie`.
- `Secure=True`: Enforced in production or HTTPS environments.
- `SameSite="none"`: Used in production HTTPS to permit top-level cross-site provider redirects (Google/GitHub), combined with mandatory `Secure`. In development, defaults to `"lax"`.
- `Path="/"`: Bound to root so that all redirect callbacks receive the cookie.
- `Max-Age=600`: 10-minute time-to-live matching token expiration.

### 3.2. Cryptographic Token Format & Validation
The state token is structured as:
```
<raw_entropy_hex>_<timestamp_unix>_<hmac_sha256_sig_24>
```
1. `raw_entropy_hex`: 16 bytes of cryptographically secure random entropy (`secrets.token_hex(16)`).
2. `timestamp_unix`: Epoch timestamp of issuance.
3. `sig`: 24-character hex HMAC-SHA256 signature calculated over `<raw_entropy>_<timestamp>` using the production `JWT_SECRET`.

Validation rules:
- Format verification (minimum 3 segments).
- Timestamp freshness check: `0 <= (_now() - ts) <= STATE_TTL_SECONDS`. Tokens older than 600s or future-dated by more than 5 seconds are rejected.
- HMAC verification: Constant-time comparison (`secrets.compare_digest`) against expected signature computed from `_secret()`. If `JWT_SECRET` is missing, insecure, or shorter than 32 characters in production, `_secret()` raises a critical error and `consume_state()` fails closed.

### 3.3. Distributed Replay Store Engine
The `ReplayStore` protocol defines:
- `mark_consumed(state_value: str) -> bool`: Atomically marks state consumed. Returns `True` if consumed for the first time, `False` if already consumed or if store fails.
- `is_consumed(state_value: str) -> bool`: Query consumption status.

Three implementations are provided:
1. `RedisReplayStore`: Connects via `REDIS_URL`. Uses SHA-256 hashed state keys (`roxy:oauth:consumed:<digest>`) with `SET ... EX 600 NX`. Handles connection drops by logging errors and failing closed.
2. `InMemoryReplayStore`: Thread-safe in-memory store utilizing `threading.Lock` and TTL eviction. Permitted exclusively in non-production environments (`APP_ENV=development` or `test`).
3. `FailClosedReplayStore`: Active when in production and `REDIS_URL` is omitted or unconfigured. Rejects all state consumption attempts to prevent insecure distributed fallback.

---

## 4. Automated Regression Test Evidence

The regression suite `backend/tests/test_auth_oauth_state_security.py` validates all 14 required security invariants:

| Test Case | Scenario / Invariant | Result |
| :--- | :--- | :--- |
| `test_valid_oauth_state_with_browser_binding_succeeds` | Legitimate flow: fresh state + matching browser cookie | **PASSED** |
| `test_missing_browser_cookie_in_production_fails_closed` | Production callback missing `roxy.oauth_state` cookie | **PASSED** |
| `test_missing_cookie_in_non_prod_fails_closed` | Development callback missing cookie fails closed | **PASSED** |
| `test_mismatched_cookie_and_state_rejected` | Cookie from Session A paired with state from Session B | **PASSED** |
| `test_dev_secret_forged_state_rejected_in_production` | Attacker forges HMAC using known dev secret | **PASSED** |
| `test_forged_random_state_rejected` | Random garbage signature rejected | **PASSED** |
| `test_expired_state_rejected` | State token older than 600 seconds rejected | **PASSED** |
| `test_future_timestamp_rejected` | State with future timestamp (> 5s skew) rejected | **PASSED** |
| `test_replay_state_rejected` | Single-use invariant: second consumption returns False | **PASSED** |
| `test_concurrent_replay_race_condition_prevented` | 5 concurrent threads race: exactly 1 True, 4 False | **PASSED** |
| `test_consumption_across_simulated_independent_workers` | Worker A consumes state; Worker B rejects replay | **PASSED** |
| `test_shared_store_outage_fails_closed_in_production` | Store connection timeout / failure fails closed | **PASSED** |
| `test_missing_shared_store_in_production_fails_closed` | Production without REDIS_URL rejects state | **PASSED** |
| `test_cookie_security_attributes` | Validates HttpOnly, Secure, SameSite=none, Max-Age, Path | **PASSED** |

**Execution Output:**
```
tests/test_auth_oauth_state_security.py::test_valid_oauth_state_with_browser_binding_succeeds PASSED
tests/test_auth_oauth_state_security.py::test_missing_browser_cookie_in_production_fails_closed PASSED
tests/test_auth_oauth_state_security.py::test_missing_cookie_in_non_prod_fails_closed PASSED
tests/test_auth_oauth_state_security.py::test_mismatched_cookie_and_state_rejected PASSED
tests/test_auth_oauth_state_security.py::test_dev_secret_forged_state_rejected_in_production PASSED
tests/test_auth_oauth_state_security.py::test_forged_random_state_rejected PASSED
tests/test_auth_oauth_state_security.py::test_expired_state_rejected PASSED
tests/test_auth_oauth_state_security.py::test_future_timestamp_rejected PASSED
tests/test_auth_oauth_state_security.py::test_replay_state_rejected PASSED
tests/test_auth_oauth_state_security.py::test_concurrent_replay_race_condition_prevented PASSED
tests/test_auth_oauth_state_security.py::test_consumption_across_simulated_independent_workers PASSED
tests/test_auth_oauth_state_security.py::test_shared_store_outage_fails_closed_in_production PASSED
tests/test_auth_oauth_state_security.py::test_missing_shared_store_in_production_fails_closed PASSED
tests/test_auth_oauth_state_security.py::test_cookie_security_attributes PASSED

============================= 14 passed in 0.73s ==============================
```

---

## 5. Deployment & Configuration Guidance

1. **Production Infrastructure:** Ensure `REDIS_URL` (e.g. `rediss://default:<password>@<host>:<port>`) is populated in the production environment variables (e.g. AWS ElastiCache, Upstash, or Redis Cloud).
2. **Secret Entropy:** Confirm `JWT_SECRET` is at least 32 characters of high entropy.
3. **No Migration Necessary:** OAuth state tokens are ephemeral (10-minute lifetime). No database migration or persistent data transformation is required.

---

## 6. Audit Verdict

**SEC-03 STATUS: RESOLVED (PASS)**  
The OAuth state generation, browser binding, and distributed replay protection mechanisms are fully hardened, statically typed, and verified by 14 targeted automated tests.
