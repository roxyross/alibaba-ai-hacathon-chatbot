# ROXY-AI — OAuth Configuration & Route Reconciliation Report

**Document ID:** `ROXY-OAUTH-REC-01`  
**Date:** October 14, 2026  
**Target Release:** Consolidated Launch Candidate (LC-1)  
**Branch:** `release/audit-remediation`  
**Subsystems:** `backend/src/app/auth/router.py`, `backend/src/app/auth/oauth.py`, `backend/src/app/auth/oauth_state.py`  
**Author:** Principal OAuth/Security Architect & Staff Backend Engineer  

---

## 1. Executive Summary

Previous audit reports noted ambiguity regarding the exact OAuth callback routes, backend redirect URI construction, environment variable naming, and frontend token handoff mechanisms. This document provides a forensic, code-level reconciliation of the OAuth 2.0 authentication architecture across Google and GitHub identity providers.

---

## 2. Authoritative Route Specifications

FastAPI mounts the authentication router in `backend/src/app/main.py`:
```python
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
```

Within `backend/src/app/auth/router.py`, the OAuth handlers are defined as:

| Flow Stage | Route Path | Full HTTP Endpoint | Method | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Start / Consent** | `/oauth/{provider}/start` | `GET /api/v1/auth/oauth/google/start`<br>`GET /api/v1/auth/oauth/github/start` | GET | Initiates OAuth flow, mints CSRF state cookie, records origin, redirects to IdP |
| **IdP Callback (Canonical)** | `/oauth/{provider}/callback` | `GET /api/v1/auth/oauth/google/callback`<br>`GET /api/v1/auth/oauth/github/callback` | GET | Receives authorization code from IdP, consumes state, exchanges code for user profile, mints JWT |
| **Frontend Token Handoff** | Client-side route | `{FRONTEND_BASE}/auth/callback#{fragment}` | Client Redirect (302) | Delivers session JWT in URL hash fragment (`#access_token=...`) |

### Route Reconciliation: `/api/v1/auth/oauth/google/callback` vs `/api/v1/auth/google/callback`
- **Canonical and Active Route:** `/api/v1/auth/oauth/google/callback` is the sole endpoint configured in `GoogleConfig.from_env()` in `backend/src/app/auth/oauth.py` (line 81):
  ```python
  redirect_uri = f"{backend_base}/api/v1/auth/oauth/google/callback"
  ```
- **Resolution:** Any documentation referencing `/api/v1/auth/google/callback` without the `/oauth/` segment is outdated. Google Cloud Console Authorized Redirect URIs **must** be registered as:
  ```
  https://<backend-domain>/api/v1/auth/oauth/google/callback
  ```
  For local development:
  ```
  http://localhost:8000/api/v1/auth/oauth/google/callback
  ```

---

## 3. Environment Variable Precedence & Architecture

The OAuth subsystem distinguishes between **Backend Base URL** (where Google/GitHub sends authorization codes) and **Frontend Base URL** (where the user's browser is redirected with the minted JWT).

### Backend Redirect Base (`OAUTH_REDIRECT_BASE_URL`)
Defined in `backend/src/app/auth/oauth.py` (`GoogleConfig.from_env()` and `GitHubConfig.from_env()`):
1. Reads `os.environ.get("OAUTH_REDIRECT_BASE_URL")`.
2. If unset or pointing to `localhost` while running in production (`APP_ENV=production` or `VERCEL=1`):
   - In production: defaults to `https://roxy-personal-ai-backend.vercel.app` (or custom API domain if set).
   - In development: defaults to `http://localhost:8000`.
3. Appends the canonical callback path: `/api/v1/auth/oauth/google/callback`.

### Frontend Redirect Base (`_resolve_frontend_base`)
Defined in `backend/src/app/auth/router.py`:
1. Checks candidate origin from query parameter `origin` or saved cookie `roxy_oauth_origin`.
2. Validates candidate origin against `_is_origin_trusted()`. If untrusted (e.g. `https://evil.com`), it is **strictly rejected**.
3. Checks environment variables: `APP_BASE_URL`, `FRONTEND_BASE_URL`, `ALLOWED_FRONTEND_ORIGINS`, `CORS_ALLOWED_ORIGINS`.
4. Canonical fallbacks:
   - Production: `https://roxy-personal-ai.vercel.app` (or configured production domain `https://roxy.ai`).
   - Development: `http://localhost:5173`.

---

## 4. Cryptographic State & Anti-CSRF / Anti-Replay Architecture

The OAuth state management in `backend/src/app/auth/oauth_state.py` provides defense against CSRF, origin spoofing, and replay attacks:

```
Browser               Roxy Backend               Google IdP
   |                        |                        |
   |--- GET /oauth/start -->|                        |
   |                        |-- Generate state nonce |
   |                        |-- HMAC-SHA256 sign     |
   |                        |-- Set cookie           |
   |<-- 302 to Google ------|                        |
   |                        |                        |
   |----------------------- GET /o/oauth2/v2/auth -->|
   |                                                 |
   |<---------------------- 302 Callback with code --|
   |                                                 |
   |--- GET /oauth/callback?code=...&state=... ----->|
   |                        |-- Verify HMAC signature|
   |                        |-- Atomically check &   |
   |                        |   consume nonce (Lock) |
   |                        |-- Exchange code        |
   |                        |-- Mint session JWT     |
   |<-- 302 #{fragment} ----|                        |
```

### Security Properties
1. **HMAC Signature Integrity:** State contains `nonce`, `timestamp`, and `signature`. Signature is generated using `SECRET_KEY`. dev secret candidate removed.
2. **Atomic Single-Use Nonce Consumption:** Replaying the same state parameter in a second request fails with `HTTP 400 Bad Request: Invalid or expired OAuth state`.
3. **Thread-Safe Memory Lock:** `_STATE_LOCK = threading.Lock()` guarantees serialized verification and consumption, eliminating concurrent race conditions.
4. **Token Delivery via Hash Fragment:** The session JWT is passed in `#access_token=...` rather than `?access_token=...`. This ensures the token is processed purely by client-side JavaScript and is never sent to third-party referrers.

---

## 5. Google Cloud Console Registration Checklist (Gate BLK-02)

To clear Gate `BLK-02` for public production release, configure Google Cloud Console > APIs & Services > Credentials > OAuth 2.0 Client IDs:

1. **Authorized JavaScript Origins:**
   - `https://roxy.ai`
   - `https://app.roxy.ai`
   - `https://roxy-personal-ai.vercel.app`
   - `http://localhost:5173` (development only)
   - `http://localhost:3000` (development only)

2. **Authorized Redirect URIs:**
   - `https://api.roxy.ai/api/v1/auth/oauth/google/callback` (or backend production domain)
   - `https://roxy-personal-ai-backend.vercel.app/api/v1/auth/oauth/google/callback`
   - `http://localhost:8000/api/v1/auth/oauth/google/callback` (development only)

3. **Required Scopes:**
   - `openid`
   - `https://www.googleapis.com/auth/userinfo.email`
   - `https://www.googleapis.com/auth/userinfo.profile`
