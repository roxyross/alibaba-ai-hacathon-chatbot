# ROXY-AI — Security Remediation, Audit Baseline & Release Inventory

**Document ID:** `ROXY-SRB-01`  
**Date:** October 14, 2026  
**Auditor / Roles:** Principal Application Security Engineer, Staff Backend Engineer, QA Lead, Release Manager  
**Repository:** `roxyross/alibaba-ai-hacathon-chatbot`  
**Subdirectory / Project Root:** `roxy-personal-ai`  
**Branch:** `release/audit-remediation`  
**Active HEAD Commit SHA:** `6d8b126a117b38d38bf21b8b8eb7c569ffca3d83` (`6d8b126`)  
**Working Tree State:** Clean (0 uncommitted files, 0 untracked files)  
**Remote URL:** `https://github.com/roxyross/alibaba-ai-hacathon-chatbot.git` (tracked as `origin/release/audit-remediation`)  

---

## 1. Baseline Repository & Commit History Verification

### 1.1 Git Status & Commit Lineage
The repository state has been verified via direct git inspection:
```
On branch release/audit-remediation
Your branch is up to date with 'origin/release/audit-remediation'.
nothing to commit, working tree clean
```

The recent commit lineage on `release/audit-remediation` is strictly linear:
1. `6d8b126` (HEAD) — `docs(release): generate 14 consolidated launch certification and blocker closure reports`
2. `d43569e` — `fix(alembic): resolve inspector None check and column type annotations in 007, 008, 009, 011 migrations`
3. `45024ef` — `fix(release): complete release candidate verification, database sync, and staging acceptance`
4. `ce810ad` — `docs(audit): generate complete 20-report post-phase 5.1 universal quality and readiness audit`
5. `e7e1c87` — `fix(seeds): resolve generic dict type annotations in providers.py lines 26, 265, 314`

### 1.2 Historical References & Tags
- Historical baseline tag `checkpoint/ide-audit-baseline`:
  - Tag Object: `68bd96ac102d2d99ba31004f9cd74f81bc346ac1`
  - Tagged Commit: `de694ac76bedc4510e699a8d57e67a5637902327` (`feat(ide-reminders): implement Roxy Code Studio full IDE and Universal Reminder ringtone system`)
- Audit reports inspected:
  - `ROXY_CONSOLIDATED_BLOCKER_CLOSURE_SUMMARY.md`
  - `ROXY_CONSOLIDATED_FINAL_LAUNCH_CERTIFICATION.md`
  - `ROXY_CONSOLIDATED_MERGE_READINESS.md`
  - `ROXY_CONSOLIDATED_BLOCKER_REGISTER.md`
  - 14 Consolidated Audit Reports (`ROXY_CONSOLIDATED_*.md`) generated at `6d8b126`

---

## 2. Inherited Blocker Register Inventory

Before remediation, the blocker inventory consists of:

| Blocker ID | Gate Reference | Title | Severity | Current Status |
| :--- | :--- | :--- | :--- | :--- |
| **BLK-01** | `GATE-01-PHYSICAL-MOBILE` | Physical iOS & Android Hardware Verification | Critical | **BLOCKED (DEVICE ACCESS REQUIRED)** |
| **BLK-02** | `GATE-02-DOMAIN-OAUTH` | Production Domain DNS & Google OAuth Callback | High | **BLOCKED (DNS & GOOGLE CLOUD)** |
| **BLK-03** | `GATE-03-PAYMENTS` | Live Commercial Payment Provider Credentials | Critical | **BLOCKED (MERCHANT KYC)** |
| **BLK-04** | `GATE-04-TRANSACTIONAL-EMAIL` | Dedicated Transactional Email Provider (SES/Resend) | High | **BLOCKED (DOMAIN DNS & SES)** |
| **BLK-05** | `GATE-05-GEMINI-CAPACITY` | Google AI Studio Dedicated Paid-Tier API Key | High | **BLOCKED (PAID TIER KEY)** |
| **BLK-06** | `INTERNAL-CODE-TYPING` | Alembic Inspector None Type Annotation Mismatch | High | **RESOLVED (PASS in d43569e)** |

---

## 3. Scope of Security Findings & Defects Targeted in this Phase

### P0-1: JWT Development-Secret Signature Fallback
- **Target File:** `backend/src/app/auth/jwt.py`
- **Defect:** `decode_session_payload()` catches `jwt.InvalidSignatureError` and falls back to verifying tokens signed with `"roxy-dev-secret-do-not-use-in-prod"`. Furthermore, if `JWT_SECRET` is unset, `_secret()` defaults to this known static string.
- **Impact:** An external attacker can forge a valid JWT session for any `user_id` or `email` simply by signing tokens with the static dev secret, bypassing all authentication in production.

### P0-2: Public Unauthenticated Demo Login
- **Target File:** `backend/src/app/auth/router.py`
- **Defect:** `POST /api/v1/auth/demo` is unconditionally mounted and operational in all environments, minting an active session token for `demo@roxy.ai` without checking environment flags or authentication.
- **Impact:** Any unauthenticated caller can obtain a valid JWT session in production.

### P0-3: OAuth State Signature Fallback & Replay Weakness
- **Target File:** `backend/src/app/auth/oauth_state.py`
- **Defect:** `consume_state()` tests signatures against both `_secret()` and `"roxy-dev-secret-do-not-use-in-prod"`. In production, cookie validation is skipped when cryptographic HMAC verification is attempted, and consumed states are tracked only in process-local memory.
- **Impact:** An attacker can forge OAuth state tokens using the dev secret, leading to potential CSRF login bypass.

### P0/P1-4: OAuth Redirect Origin Open Redirect & Token Exposure
- **Target Files:** `backend/src/app/auth/router.py`, `backend/src/app/auth/oauth.py`
- **Defect:** `_resolve_frontend_base()` blindly accepts any `explicit_origin` starting with `http://` or `https://`, an untrusted `roxy.oauth_origin` cookie, or an arbitrary `Referer`/`Origin` header, without checking against an exact trusted allowlist. The callback then redirects to this destination with the session JWT in the URL hash.
- **Impact:** An attacker can initiate OAuth with `?origin=https://attacker.com`, causing the victim's session JWT to be transmitted directly to the attacker's server upon authentication callback.

### P1-5: Sensitive-Action Confirmation Bypass
- **Target File:** `backend/src/app/skills/router.py`
- **Defect:** `_run_skill()` checks `if not getattr(input_data, "confirm", False):` before raising `403 CONFIRMATION_REQUIRED`. If a client submits `confirm: true` in the JSON request body, the server-side confirmation workflow and token generation are completely bypassed.
- **Impact:** Any client can execute sensitive skills (sending email, modifying external resources, executing financial operations) by passing `confirm: true` without completing the interactive human-in-the-loop server token verification.

### P2-6: Plaintext Storage of Gmail OAuth Tokens
- **Target File:** `backend/src/app/skills/email_send.py`
- **Defect:** Despite claiming `"(encrypted at rest in production)"`, user tokens are stored in plaintext JSON files (`gmail_token_{user_id}.json`).
- **Remediation:** Implement authenticated encryption at rest using AES-GCM or Fernet with server-side key derivation.

### P2-7: AI Gateway Groq vs. Grok Identity Conflation
- **Target Files:** `backend/src/app/ai_gateway/models/provider.py`, `backend/src/app/ai_gateway/adapters/grok.py`
- **Defect:** The `grok` adapter dynamically re-points base URL to `https://api.groq.com/openai/v1` if `api_key.startswith("gsk_")`, conflating xAI (Grok) with Groq and ignoring `GROQ_API_KEY`.
- **Remediation:** Provide explicit provider identification, discrete config variables (`GROQ_API_KEY` vs `GROK_API_KEY`), and clean precedence.

### P2-8: CI/CD Workflow Missing Release Branch Trigger
- **Target File:** `.github/workflows/ci.yml`
- **Defect:** Pushes and pull requests only trigger on `[ master, main ]`, leaving `release/audit-remediation` without automatic GitHub Actions validation.
- **Remediation:** Add `release/**` and `release/audit-remediation` to trigger branches.

---

## 4. Initial Test Baseline Execution Status

- **Frontend TypeScript (`tsc --noEmit`):** Clean (0 errors).
- **Frontend Vitest (`npm test -- --run`):** 14/14 suites passed, 61/61 tests passed.
- **Backend Type-checking (`mypy alembic/versions`):** Clean (0 errors across 11 migrations).
- **Live Database Migrations:** NeonDB PostgreSQL synchronized to `011_trust_reliability_hardening` (head).
- **Backend Integration Tests:** Trust and reliability suite passed (10/10 tests green).
