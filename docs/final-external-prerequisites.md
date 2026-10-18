# ROXY JARVIS — FINAL EXTERNAL PREREQUISITES & OPERATOR ACTIVATION GUIDE

**Audit Standard:** Master Prompt Section 11 (External Prerequisites Must Not Become Fake Success)  
**Branch:** `design/roxy-ui-ux-redesign`  
**Evaluation Date:** October 19, 2026  
**Guiding Principle:** Safe fail-closed defaults; unconfigured external integrations never prevent the core application from starting or functioning.

---

## 1. External Prerequisites Matrix

| Integration / Service | Category | Current Code State | Fail-Closed Fallback Behavior | Exact Environment Variables | Required Owner Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Stripe Live Payments** | Payment Provider | Implemented & sandbox tested | Rejects non-production keys in production; checkouts fail closed; zero subscriptions granted | `STRIPE_SECRET_KEY`<br>`STRIPE_WEBHOOK_SECRET` | Provide live Stripe API credentials in production dashboard. |
| **Safepay Live Payments** | Payment Provider | Implemented & sandbox tested | Rejects sandbox keys in production; checkouts fail closed | `SAFEPAY_API_KEY`<br>`SAFEPAY_SECRET_KEY`<br>`SAFEPAY_WEBHOOK_SECRET`<br>`SAFEPAY_ENVIRONMENT=production` | Complete merchant activation with Safepay Pakistan and configure production keys. |
| **NayaPay Business API** | Payment Provider | Adapter implemented | Fails closed; displays unavailable in production billing UI | `NAYAPAY_CLIENT_ID`<br>`NAYAPAY_CLIENT_SECRET`<br>`NAYAPAY_MERCHANT_ID`<br>`NAYAPAY_WEBHOOK_SECRET` | Apply for NayaPay Business Merchant API agreement and obtain commercial SBP-compliant credentials. |
| **SadaPay Business API** | Payment Provider | Adapter implemented | Fails closed; displays unavailable in production billing UI | `SADAPAY_API_KEY`<br>`SADAPAY_MERCHANT_ID`<br>`SADAPAY_WEBHOOK_SECRET` | Apply for SadaPay Business Merchant API agreement and obtain live credentials. |
| **Google Gemini Live Quota** | LLM Provider | Protected default active | Falls back to static baseline catalog if key missing | `GEMINI_API_KEY` | Ensure Google AI Studio / Vertex AI project has active billing and model quota. |
| **xAI Grok Live Quota** | LLM Provider | Protected default active | Falls back to static baseline catalog if key missing | `GROK_API_KEY` | Configure active xAI Grok API key with inference credits. |
| **Alibaba DashScope / Qwen** | LLM Provider | Protected default active | Falls back to static baseline catalog if key missing | `DASHSCOPE_API_KEY` | Configure Alibaba Cloud DashScope API key. |
| **OpenAI Live Inference** | LLM Provider | Disabled by default | Strictly zero outbound requests; static baseline only | `OPENAI_API_KEY`<br>`OPENAI_ENABLED=true` | Optional: Operator must explicitly set `OPENAI_ENABLED=true` and provide credentials. |
| **Anthropic Claude Inference** | LLM Provider | Disabled by default | Strictly zero outbound requests; static baseline only | `ANTHROPIC_API_KEY`<br>`ANTHROPIC_ENABLED=true` | Optional: Operator must explicitly set `ANTHROPIC_ENABLED=true` and provide credentials. |
| **Production PostgreSQL Database** | Persistence | Async SQLAlchemy ORM active | Falls back to SQLite / dev DB locally; production requires durable Postgres | `DATABASE_URL` (format: `postgresql+asyncpg://...`) | Connect production managed PostgreSQL instance (e.g. Neon, Supabase, AWS RDS, Cloud SQL). |
| **Production JWT Secret** | Authentication | Validated on startup | Startup rejected in production if default/insecure secret used | `JWT_SECRET_KEY` | Set a high-entropy cryptographically random string (e.g. `openssl rand -hex 32`). |
| **Production OAuth Callbacks** | Identity | Google OAuth handler implemented | Fails closed with descriptive error if unconfigured | `GOOGLE_CLIENT_ID`<br>`GOOGLE_CLIENT_SECRET`<br>`AUTH_REDIRECT_BASE_URL` | Add production custom domain to Google Cloud Console Authorized Redirect URIs. |

---

## 2. Safe Shipping Strategy

ROXY JARVIS is engineered with modular resilience:
1. **Core Features Work Immediately:** Chat, Coding Studio, Knowledge Vault, Browser Studio, Multi-Language UI (all 30 locales), and Job Scheduling work completely out of the box using configured LLM providers (Gemini / Grok / DashScope).
2. **Missing Optional Services Degrade Gracefully:** If a payment provider or secondary LLM provider lacks credentials, only that specific payment method or model option is marked disabled/unavailable in the UI.
3. **Zero Crash Guarantee:** A missing API key or network partition never crashes application startup or disrupts core chat capabilities.
