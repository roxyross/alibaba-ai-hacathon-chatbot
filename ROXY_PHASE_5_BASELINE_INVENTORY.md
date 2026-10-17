# Roxy-AI — Phase 5 Baseline Inventory

**Repository:** `roxyross/alibaba-ai-hacathon-chatbot`  
**Branch:** `release/audit-remediation`  
**Current HEAD SHA:** `852901a`  
**Verified Ancestor Commits:** `c06675c` (direct parent), `48facb5` (remediation baseline)  
**Working Tree Status:** Clean  
**Date:** October 13, 2026  

---

## 1. Commit Ancestry & Working Tree Verification

| Item | SHA / Value | Evidence Status | Details |
| :--- | :--- | :--- | :--- |
| **Current Branch Head** | `852901a` | **VERIFIED** | Direct HEAD on `release/audit-remediation`, verified clean via `git status`. |
| **Direct Parent** | `c06675c` | **VERIFIED** | Verified as immediate ancestor (`git merge-base --is-ancestor c06675c HEAD`). |
| **Remediation Base** | `48facb5` | **VERIFIED** | Verified ancestor (`git merge-base --is-ancestor 48facb5 HEAD`). |
| **Lineage Integrity** | Strict linear | **VERIFIED** | Linear commit graph without divergence from release remediation base. |

---

## 2. GitHub Actions Run Audit & Execution Status

All historical and current workflow runs were examined to determine whether jobs executed real builds and test suites or used bypasses/skips.

| Workflow | Run ID | Status | Conclusion | Real Artifacts / Verification | Evidence Level |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CI Pipeline** | `38420356210` | Completed | **Success** | All 4 jobs passed: `security-audit`, `frontend-ci` (typecheck, lint, vitest, build, bundle audit), `backend-ci` (compileall, migrations, pytest), `docker-validation` (docker compose config, backend & frontend Docker builds). Duration: 4m 13s. | **VERIFIED** |
| **CI Pipeline (Prior)** | `38416343556` | Completed | **Success** | Previous base run on commit `c06675c`. All 4 jobs green. | **VERIFIED** |
| **Desktop Distribution** | `38415175730` | Completed | **Success** | Generated real multi-platform installers: `Roxy-AI-Setup.exe` (Windows NSIS), `Roxy-AI.dmg` (macOS), `Roxy-AI.AppImage` (Linux x86_64). Validated stdlib icon check. | **VERIFIED** |
| **iOS Distribution** | `38412454399` | Completed | **Success** | Built `roxy-ios-archive` (690 KB `.xcarchive.zip`) using Xcode 16.2 / iOS 18.2 SDK on `macos-15` runner without provisioning errors. | **VERIFIED** |
| **Android Distribution** | `38412388625` | Completed | **Masked Failure (Remediated)** | Job exited 0, but forensic log analysis revealed R8 failed on missing classes (`javax.annotation.Nullable`, `javax.annotation.concurrent.GuardedBy` from Google Tink). Build was masked by `|| true` on line 75 of `mobile-android.yml`. Remediated in Phase J with `-dontwarn` rules in `proguard-rules.pro` and removal of `|| true`. | **VERIFIED** |

---

## 3. Production Frontend Identification

A deep inspection of Docker configurations, distribution scripts, and reverse proxy settings was conducted to determine which frontend is deployed:

| Frontend Root | Framework | Production Role | Verification Evidence |
| :--- | :--- | :--- | :--- |
| `frontend/` | Vite 5 + React 18 SPA | **ACTIVE PRODUCTION FRONTEND** | Mounted in `frontend/Dockerfile` (multi-stage Nginx production container), targeted by `desktop/` Electron packager, synced to `android/` and `ios/` via Capacitor, tested in CI (`frontend-ci`). Contains all 13 core views, Trust Center, CodingStudio IDE, Cowork, Voice Session, and full i18n support. |
| `nextjs-frontend/` | Next.js 14 App Router | **AUXILIARY / EXPERIMENTAL** | Standalone directory with partial experimental landing and chat pages. Not referenced in `docker-compose.yml`, not referenced in `ci.yml`, not used in desktop, Android, or iOS builds. |

**Conclusion:** `frontend/` is the authoritative production client application.

---

## 4. Backend & Runtime Architecture Identification

| Service Component | File Path | Deployment & Request Routing | Evidence Status |
| :--- | :--- | :--- | :--- |
| **FastAPI Gateway** | `backend/src/app/main.py` | Runs on port 8000 via Uvicorn. Exposes 53 routers mounted at `/api/v1/*`. Loaded with CORS, Correlation Middleware, PostgreSQL asyncpg pool, and Redis connection. | **VERIFIED** |
| **Active Coordinator** | `backend/src/app/api/v1/runtime.py` | Handles live coordinator requests at `/api/v1/runtime/*`. Houses 3,795 lines implementing task decomposition, keyword/regex intent routing (`_FINANCE_PATTERNS`, `_CALENDAR_PATTERNS`, etc.), LLM routing fallback, specialist agent execution, and verification state. | **VERIFIED** |
| **Standalone Runtime Package** | `runtime/src/runtime/` | Standalone Python package containing decoupled coordinator, task planner, and worker architecture. Not referenced in `docker-compose.yml`, not mounted into the backend container, and not receiving client traffic directly. | **SOURCE-VERIFIED** |

---

## 5. Baseline Evidence Summary Table

| Category | Finding | Evidence Level |
| :--- | :--- | :--- |
| Git Ancestry | `852901a` cleanly descends from `c06675c` and `48facb5` | **VERIFIED** |
| Alembic Migrations | Revision `011_trust_reliability_hardening` fixed; clean upgrade on fresh PostgreSQL | **VERIFIED** |
| CI Pipeline | All 4 CI jobs passing green on `852901a` (Run `38420356210`) | **VERIFIED** |
| Desktop Packaging | Executable packaging validated across Windows, macOS, and Linux | **VERIFIED** |
| iOS Packaging | Xcode 16.2 build archive created and uploaded | **VERIFIED** |
| Android Packaging | ProGuard R8 missing class issue identified and patched; `|| true` bypass removed | **VERIFIED** |
| Production Frontend | `frontend/` (Vite + React 18 SPA) confirmed as the sole production target | **VERIFIED** |
| Backend Architecture | FastAPI at `backend/src/app/main.py` serving active runtime at `/api/v1/runtime` | **VERIFIED** |
