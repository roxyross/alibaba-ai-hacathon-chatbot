# ROXY-AI — FINAL ENVIRONMENT & DEPLOYMENT CONFIGURATION MATRIX

**Document ID:** `ROXY-EDM-01`  
**Date:** October 16, 2026  
**Primary Production Frontend:** `frontend/` (Vite + React deployed to Vercel `https://roxy-personal-ai.vercel.app/`)  
**Primary Production Backend:** `backend/` (FastAPI on Google Cloud Run & Vercel Serverless)  
**Verdict:** **VERIFIED PASS — ZERO LEAKED CREDENTIALS, STRICT FAIL-CLOSED PRODUCTION**

---

## 1. Executive Summary

This matrix establishes the definitive specification of all environment variables across development, staging, and production environments for Roxy-AI. It verifies that zero production secrets are committed to Git, zero backend secrets are bundled into client-side JavaScript, and production startup fails closed if mandatory secrets are missing.

---

## 2. Environment Variables Specification

| Environment Variable | Subsystem | Purpose | Scope / Secret | Required in Prod | Safe Development Default | Production Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | Database | PostgreSQL connection string | Secret | **YES** | `postgresql+asyncpg://postgres:postgres_test_password@localhost:5432/roxy_test` | Must be non-ephemeral PostgreSQL; SQLite rejected. |
| `REDIS_URL` | Cache/State | Distributed state & rate limits | Secret | **YES** | `redis://localhost:6379/0` | Must connect with RESP2 protocol & TTL support. |
| `JWT_SECRET` | Auth | Signs user authentication tokens | Secret | **YES** | None (Auto-generated 32-byte in dev) | Minimum 32 bytes; default demo secret rejected. |
| `JWT_SERVICE_SECRET` | Auth | Internal service-to-service auth | Secret | **YES** | None (Auto-generated 32-byte in dev) | Minimum 32 bytes; distinct from user secret. |
| `GMAIL_TOKEN_ENCRYPTION_KEY` | Skills | AES-256-GCM key for Gmail OAuth | Secret | **YES** | None (Strictly required in prod) | 32-byte key; local plaintext fallback rejected. |
| `GEMINI_API_KEY` | AI Gateway | Google AI Studio inference API key | Secret | **YES** | None | Must be valid Google AI API key format (`AIzaSy...`). |
| `XAI_API_KEY` | AI Gateway | xAI Grok inference API key | Secret | Optional | None | Required only if Grok is enabled. |
| `GROQ_API_KEY` | AI Gateway | Groq fast-inference API key | Secret | Optional | None | Required only if Groq/Qwen is enabled. |
| `STRIPE_SECRET_KEY` | Billing | Stripe live secret key | Secret | Optional | None | Test keys (`sk_test_`) strictly rejected in prod. |
| `STRIPE_WEBHOOK_SECRET` | Billing | Validates Stripe webhook signatures| Secret | Optional | None | Required if Stripe is enabled in production. |
| `SAFEPAY_API_KEY` | Billing | Safepay live merchant secret | Secret | Optional | None | Sandbox keys strictly rejected in prod. |
| `SAFEPAY_WEBHOOK_SECRET` | Billing | Validates Safepay signatures | Secret | Optional | None | Required if Safepay is enabled in production. |
| `APP_ENV` | Global | Runtime environment | Public | **YES** | `development` | `production`, `staging`, `development`, or `test`. |
| `PORT` | Deployment | Dynamic Cloud Run port binding | Public | **YES** | `8000` | Defaults to `${PORT:-8000}`. |

---

## 3. Verified Deployment Targets

### 3.1 Primary Frontend: `frontend/` (Vite)
- **Deployment Platform:** Vercel (`projectId: prj_4oddEjQuFnpfznhpV4TPJcDTkCkZ`, `projectName: roxy-personal-ai`).
- **Live URL:** `https://roxy-personal-ai.vercel.app/`
- **Build Command:** `npm run build` (outputs to `dist/`).
- **Configuration:** `frontend/vercel.json` rewrites `/api/*` to backend and `/*` to `/index.html`.
- **Bundle Audit:** Audited `dist/assets/*.js`; zero backend secrets or environment keys embedded.

### 3.2 Alternative Frontend: `nextjs-frontend/` (Next.js 16.3.5 Turbopack)
- **Status:** Verified clean compilation via `next build` (22/22 static pages generated).
- **Role:** Parallel / next-generation web client; builds cleanly without affecting production Vite deployment.

### 3.3 Primary Backend: `backend/` (FastAPI)
- **Deployment Target 1 (Primary):** Google Cloud Run (`deploy/cloud-run/service.yaml`).
  - Container: `backend/Dockerfile` using dynamic `$PORT` binding and 2 Uvicorn workers.
  - Secret Management: Declarative Google Secret Manager bindings.
- **Deployment Target 2 (Serverless Fallback):** Vercel Python runtime (`backend/vercel.json` pointing to `api/index.py`).
