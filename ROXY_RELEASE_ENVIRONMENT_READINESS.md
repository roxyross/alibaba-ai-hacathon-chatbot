# ROXY-AI — Environment Readiness & Configuration Report

**Document ID:** `ROXY-RC-03`  
**Date:** October 14, 2026  
**Target Release:** Post-Phase 5.1 Release Candidate (RC-1)  
**Branch:** `release/audit-remediation`  
**Staging Environment State:** `READY & VERIFIED`

---

## 1. Executive Summary

This report assesses the configuration, environment variable parity, secrets handling, database connectivity, and runtime settings across Roxy-AI's deployment targets. It confirms that the staging environment is fully configured, secure, and operational, while establishing the necessary template and guidelines for production deployment.

---

## 2. Environment Variables & Secret Masking

All sensitive secrets are sanitized in structured logs via `structlog` and the AI Gateway `PromptSanitizer`. Raw API keys, tokens, and passwords are never output in terminal logs, JSON responses, or generated documentation.

### Configuration Inventory

| Variable Name | Staging Status | Production Target | Sanitization Policy |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | Verified (NeonDB Cloud Postgres) | Managed Postgres Cluster | URL masked; password hidden |
| `REDIS_URL` | Configured / Graceful Fallback | Managed Redis Cluster | Host/Auth hidden |
| `JWT_SECRET` | Configured (Development key) | 64-char Cryptographic Random | Fully hidden |
| `GEMINI_API_KEY` | Present (Auto-failover active) | Production Google AI Studio Key | `[REDACTED_SECRET]` |
| `GROQ_API_KEY` | Verified Live (Groq/Qwen 27B) | Production Groq API Key | `[REDACTED_SECRET]` |
| `GROK_API_KEY` | Present (x.ai fallback) | Production x.ai Key | `[REDACTED_SECRET]` |
| `OPENAI_API_KEY` | Present (Flagged false) | Optional tertiary fallback | `[REDACTED_SECRET]` |
| `DEEPSEEK_API_KEY` | Present (Flagged false) | Optional reasoning fallback | `[REDACTED_SECRET]` |
| `TAVILY_API_KEY` | Verified Live (Web search) | Production Tavily / Bing Key | `[REDACTED_SECRET]` |
| `STRIPE_SECRET_KEY` | Verified (Sandbox `sk_test_...`) | Live Stripe Restricted Key | `[REDACTED_SECRET]` |
| `SAFEPAY_API_KEY` | Verified (Sandbox key) | Live Safepay Key | `[REDACTED_SECRET]` |
| `SMTP_HOST` / `SMTP_USER` | Configured (Gmail SMTP) | Dedicated transactional ESP | Password masked |

---

## 3. Database Connectivity & Connection Pooling Architecture

### Live NeonDB Configuration
- **Host:** `ep-crimson-water-a17p7h8h-pooler.ap-southeast-1.aws.neon.tech`
- **Database:** `neondb`
- **Engine Version:** PostgreSQL 16.6
- **SSL Requirement:** `sslmode=require`

### PgBouncer & Statement Cache Hardening
NeonDB serverless architecture relies on PgBouncer connection poolers in transaction pooling mode. Under transaction pooling, prepared statement reuse can cause PostgreSQL `InvalidCachedStatementError`.
- **Remediation Implemented:**
  - `backend/src/app/db.py`: Added `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` in `create_async_engine`.
  - `backend/alembic/env.py`: Added `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` in `run_async_migrations`.
  - Added explicit `await connection.commit()` in `alembic/env.py` to ensure schema revision metadata persists in Postgres.

### Migration State
Alembic migration suite was verified both online and offline:
- **Offline Script Generation (`--sql`):**  
  `alembic upgrade head --sql` exits with code 0 without requiring live DB locks.
- **Online Execution (`alembic upgrade head`):**  
  Target database is confirmed at revision `011_trust_reliability_hardening (head)`.
- **Table Schema Integrity:**  
  Verified tables include `users`, `chat_sessions`, `chat_messages`, `documents` (with `chunk_count`, `summary`, `status`, `tags`, `updated_at`), `generated_images` (with `revised_prompt`, `style_preset`, `width`, `height`, `seed`, `is_favorite`, `vault_document_id`), `trust_audit_events`, `recovery_jobs`, and `personalization_proposals`.

---

## 4. Frontend Environment Readiness

- **API Base URL:** Configured via Vite environment variable `VITE_API_BASE_URL` (defaults to `/api/v1` proxy in dev/staging).
- **TypeScript Strictness:** Full compliance (`tsc --noEmit` returns 0 warnings/errors).
- **Bundle Optimization:** Code-splitting enabled with dynamic imports for heavy components (`CodingStudio`, `TrustCenter`, `DeviceHub`).
- **PWA Manifest & Service Worker:** Manifest configured with app identity, standalone display mode, and offline asset caching.

---

## 5. Security Posture & Isolation

1. **CORS Policy:** Strict origin allowlists configured in `FastAPI` middleware (`app/main.py`), preventing unauthorized cross-origin credential harvesting.
2. **Rate Limiting:** In-memory token bucket rate limiter with sliding window protects authentication and AI generation endpoints.
3. **Data Loss Prevention (DLP):** Automatic pattern scanning for credit cards, SSNs, API tokens, and private keys blocks exfiltration before requests reach external AI providers.

---

## 6. Staging Readiness Verdict

**STAGING ENVIRONMENT: 100% READY.** All backend database connections, migration revisions, frontend client builds, and security filters meet or exceed release criteria.
