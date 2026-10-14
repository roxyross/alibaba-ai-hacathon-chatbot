# ROXY-AI — Consolidated Production Domain, TLS & OAuth Acceptance Report

**Document ID:** `ROXY-CBC-06`  
**Date:** October 14, 2026  
**Target Release:** Consolidated Launch Candidate (LC-1)  
**Branch:** `release/audit-remediation`  
**Verification Scope:** `GATE-02-DOMAIN-OAUTH` & Workstream 2  
**Verdict:** `STAGING PASS (DEV TOKEN & MOCK VERIFIED)` / `PRODUCTION BLOCKED (DOMAIN & LIVE CALLBACK)`

---

## 1. Executive Summary

This report evaluates Roxy-AI's identity and authentication subsystems, focusing on Google OAuth 2.0 authorization code flows, cryptographic CSRF state parameters, user profile provisioning, and production domain requirements.

---

## 2. Authentication Architecture & Protocol Verification

Roxy-AI implements OpenID Connect (OIDC) / OAuth 2.0 standards across backend endpoints:
1. **Initiation (`GET /api/v1/auth/google`):**
   - Generates Google OAuth authorization URL with requested scopes (`openid`, `email`, `profile`, `calendar.readonly`).
   - Generates cryptographically secure, signed `state` token storing client redirect destination and CSRF nonce.
2. **Callback Handling (`GET /api/v1/auth/google/callback`):**
   - Validates `state` parameter signature and expiration (10-minute TTL). Rejects tampered or replayed states with HTTP 400.
   - Exchanges authorization `code` for Google ID token and access token.
   - Decodes Google user profile and validates token signature against Google public JWKS.
3. **User Account Linking:**
   - Automatically provisions a new user row in `users` table or links to an existing user with matching verified email.
   - Prevents unintended account takeover by requiring email verification.
4. **JWT Session Issuance:**
   - Issues RS256/HS256 signed access tokens and refresh tokens.
   - Embeds user ID, role (`user`, `admin`), and session expiration.
5. **Development & Staging Engine:**
   - `/api/v1/auth/request-link` and `/api/v1/auth/verify` enable automated integration testing without interactive browser login.

---

## 3. Automated Test Evidence

Verified via `tests/integration/test_oauth_google.py` and `tests/integration/test_phase1_auth_session.py`:
- Valid authorization URL construction: **PASS**
- Tampered `state` rejection: **PASS**
- Expired `state` rejection: **PASS**
- Mock code exchange and user provisioning: **PASS**
- Session JWT validation and role enforcement: **PASS**

---

## 4. Production Domain & OAuth Blocker Dossier (`GATE-02-DOMAIN-OAUTH`)

### The Constraint
Google's OAuth 2.0 security policies mandate that Authorized JavaScript Origins and Authorized Redirect URIs must strictly match registered HTTPS domains. In staging and local development, the application operates on `localhost:8000` / `127.0.0.1`.

### Production Prerequisites:
1. **Domain Registration & DNS:**
   - Register the production domain (e.g., `roxy.ai`).
   - Configure DNS A/CNAME records pointing to production load balancers.
   - Provision TLS 1.3 certificates (via Let's Encrypt / AWS Certificate Manager).
2. **Google Cloud Console Configuration:**
   - Add Authorized JavaScript Origin: `https://app.roxy.ai`
   - Add Authorized Redirect URI: `https://app.roxy.ai/api/v1/auth/google/callback`
3. **OAuth Consent Screen Verification:**
   - Submit production branding, privacy policy URL (`https://roxy.ai/privacy`), and terms of service.
   - Complete Google verification for sensitive scopes (Google Calendar).
4. **Environment Secret Injection:**
   - Update `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` with production credentials in production KMS.

---

## 5. Gate Determination

- **STAGING RELEASE ACCEPTANCE:** **PASS** (Identity engine and state validation are fully operational).
- **PRODUCTION RELEASE CANDIDATE:** **BLOCKED (DOMAIN & LIVE CALLBACK REQUIRED)**
