# ROXY-AI — SEC-06 Gmail OAuth Token Encryption at Rest Remediation Report

**Document ID:** `ROXY-SEC-06-REV3`  
**Date:** October 14, 2026  
**Target Release:** Consolidated Launch Candidate (LC-1)  
**Branch:** `release/audit-remediation`  
**Author:** AppSec & Principal Cryptographic Architect  
**Classification:** Technical Remediation & Verification Audit  

---

## 1. Executive Summary

During the security audit of `backend/src/app/skills/email_send.py`, the storage mechanism for user Gmail OAuth 2.0 refresh and access tokens was evaluated against zero-trust standards. The audit revealed two primary vulnerabilities in the token encryption lifecycle:
1. **Incomplete Production Detection (Vercel Blindspot):** The environment check in `_get_cipher()` inspected only `APP_ENV` and `ENV`, omitting deployment indicators such as `VERCEL`, `VERCEL_ENV`, `VERCEL_URL`, and `ENVIRONMENT`. Consequently, serverless functions executing on Vercel could be treated as non-production environments.
2. **Predictable Key Derivation Fallback:** When a dedicated `GMAIL_TOKEN_ENCRYPTION_KEY` was not configured, the cipher silently fell back to deriving a key from `JWT_SECRET` or `SECRET_KEY`. If those variables defaulted to known developer strings (`roxy-dev-secret-do-not-use-in-prod`), production OAuth tokens would be encrypted using a publicly known key.
3. **Absence of Cryptographic Key Rotation:** The subsystem lacked a structured rotation mechanism, preventing administrators from cycling encryption keys without invalidating existing stored user tokens.

These vulnerabilities have been eliminated. The updated implementation enforces strict production detection across all environments (including Vercel), requires a dedicated 32+ character `GMAIL_TOKEN_ENCRYPTION_KEY`, rejects development keys, fails closed if cryptographic keys are missing or invalid, and implements transparent authenticated key rotation via `cryptography.fernet.MultiFernet`.

---

## 2. Vulnerability Analysis & Risk Matrix

| Risk Dimension | Pre-Remediation State | Post-Remediation Hardened State |
| :--- | :--- | :--- |
| **Production Key Enforcement** | Permitted silent fallback to derived `JWT_SECRET` | Mandatory `GMAIL_TOKEN_ENCRYPTION_KEY` (min 32 chars) |
| **Vercel Deployment Detection** | Ignored `VERCEL`, `VERCEL_ENV`, `VERCEL_URL` | Full inspection of all Vercel and production flags |
| **Dev Key Rejection** | Known dev keys accepted if `JWT_SECRET` matched | Explicit rejection of `roxy-dev-secret-do-not-use-in-prod` |
| **Ciphertext Integrity** | Basic Fernet decryption | Authenticated decryption with strict `InvalidToken` trap |
| **Key Rotation** | None (key change broke all existing tokens) | `MultiFernet` primary + fallback with auto re-encryption |
| **Tenant Isolation** | Verified user_id in payload | Payload user_id checked; cross-user copy fails closed |
| **Filesystem Security** | Standard file permissions | `0o600` user-only permissions, encrypted JSON container |

---

## 3. Cryptographic Design & Implementation

### 3.1. Production Environment Detection
The `_is_production()` static method consolidates all platform indicators:
```python
@staticmethod
def _is_production() -> bool:
    app_env = os.environ.get("APP_ENV", "").lower()
    env = os.environ.get("ENV", "").lower()
    environment = os.environ.get("ENVIRONMENT", "").lower()
    return (
        app_env in ("production", "prod")
        or env in ("production", "prod")
        or environment in ("production", "prod")
        or bool(os.environ.get("VERCEL"))
        or bool(os.environ.get("VERCEL_ENV"))
        or bool(os.environ.get("VERCEL_URL"))
        or os.environ.get("APP_BASE_URL", "").startswith("https://")
    )
```

### 3.2. Fail-Closed Key Resolution (`_get_cipher`)
- **Production Mode:** If `GMAIL_TOKEN_ENCRYPTION_KEY` is missing, shorter than 32 characters, or matches any known developer key (`roxy-dev-secret-do-not-use-in-prod`, `test_key`, `development`, etc.), the function logs a security error and returns `None`. No token saving or loading is permitted.
- **Non-Production Mode:** If no key is set, allows derivation from `JWT_SECRET` or local dev fallback to enable offline testing without compromising production security.

### 3.3. Key Rotation via `MultiFernet`
To support key rotation without service interruption:
- `GMAIL_TOKEN_ENCRYPTION_KEY`: Primary key used for all new encryption operations.
- `GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK`: Previous key used exclusively for decrypting older ciphertexts.
- When `_load_user_token_payload()` decrypts a token using a fallback key, it immediately re-encrypts and persists the payload under the primary key, achieving zero-downtime, transparent key migration.

### 3.4. Token Container & Tenant Boundary
On-disk tokens (`gmail_token_<user_id>.json`) contain only metadata and Fernet ciphertext:
```json
{
  "encrypted": true,
  "user_id": "user_alice",
  "ciphertext": "gAAAAABn...",
  "updated_at": "2026-10-14T19:50:00Z"
}
```
No plaintext access tokens or refresh tokens are ever written to disk, logs, or error traces.

---

## 4. Automated Regression Test Evidence

The regression suite `backend/tests/test_gmail_token_storage_security.py` validates 11 security scenarios:

| Test Case | Scenario / Invariant | Result |
| :--- | :--- | :--- |
| `test_tokens_are_encrypted_at_rest_not_plaintext` | Ciphertext envelope verified; no plaintext credentials on disk | **PASSED** |
| `test_authorized_user_can_decrypt_token` | Legitimate owner decrypts token with primary key | **PASSED** |
| `test_wrong_key_fails_closed` | Decryption under unauthorized key returns None | **PASSED** |
| `test_missing_production_key_fails_closed` | Missing key in production returns None; save rejected | **PASSED** |
| `test_vercel_environment_detection_fails_closed_when_key_missing` | Vercel flags trigger strict mode; missing key fails closed | **PASSED** |
| `test_insecure_development_key_rejected_in_production` | Known dev secret rejected in production | **PASSED** |
| `test_short_encryption_key_rejected_in_production` | Key < 32 characters rejected in production | **PASSED** |
| `test_cross_user_tenant_isolation` | User B loading User A's token file is rejected | **PASSED** |
| `test_ciphertext_tampering_rejected` | Bit-flipped ciphertext fails HMAC and returns None | **PASSED** |
| `test_key_rotation_via_multifernet` | Fallback key decrypts token and re-encrypts under primary | **PASSED** |
| `test_development_mode_allows_local_fallback` | Development mode allows local offline execution | **PASSED** |

**Execution Output:**
```
tests/test_gmail_token_storage_security.py::test_tokens_are_encrypted_at_rest_not_plaintext PASSED
tests/test_gmail_token_storage_security.py::test_authorized_user_can_decrypt_token PASSED
tests/test_gmail_token_storage_security.py::test_wrong_key_fails_closed PASSED
tests/test_gmail_token_storage_security.py::test_missing_production_key_fails_closed PASSED
tests/test_gmail_token_storage_security.py::test_vercel_environment_detection_fails_closed_when_key_missing PASSED
tests/test_gmail_token_storage_security.py::test_insecure_development_key_rejected_in_production PASSED
tests/test_gmail_token_storage_security.py::test_short_encryption_key_rejected_in_production PASSED
tests/test_gmail_token_storage_security.py::test_cross_user_tenant_isolation PASSED
tests/test_gmail_token_storage_security.py::test_ciphertext_tampering_rejected PASSED
tests/test_gmail_token_storage_security.py::test_key_rotation_via_multifernet PASSED
tests/test_gmail_token_storage_security.py::test_development_mode_allows_local_fallback PASSED

============================= 11 passed in 4.04s ==============================
```

---

## 5. Key Rotation Operational Runbook

When rotating production encryption keys:
1. Generate a new 32-byte urlsafe base64 key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. In production secrets manager (AWS Secrets Manager / Vercel Environment Variables):
   - Set `GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK` to the current `GMAIL_TOKEN_ENCRYPTION_KEY` value.
   - Set `GMAIL_TOKEN_ENCRYPTION_KEY` to the newly generated key.
3. Deploy the application. All existing user tokens remain readable via the fallback key and are automatically re-encrypted under the new primary key upon next use.
4. After the rotation cycle (e.g. 30 days), remove `GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK`.

---

## 6. Audit Verdict

**SEC-06 STATUS: RESOLVED (PASS)**  
Gmail OAuth token encryption at rest is fully remediated with strict fail-closed production enforcement, MultiFernet rotation, and 11 passing automated regression tests.
