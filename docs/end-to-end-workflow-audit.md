# ROXY JARVIS — End-to-End Workflow Audit

**Audit Date:** 2026-10-18  
**Branch:** `design/roxy-ui-ux-redesign`  

---

## 1. Authentication & Account Management

- **Registration / Login:** Evaluated `POST /api/v1/auth/login` and `POST /api/v1/auth/register`. Authentication sets HTTP-only secure cookie and returns Bearer access token.
- **Session Restoration:** On reload, `AuthProvider` reads stored credentials / token and populates user session. Unauthenticated users see guest state with local storage fallback.
- **Step-Up 2FA & Sensitive Actions:** High-risk actions (e.g. key rotation, account deletion) require cryptographic confirmation challenges backed by durable table `confirmation_challenges`.

---

## 2. Chat & Conversations

- **Prompt Submission & Streaming:** Submitting a prompt initiates `POST /api/v1/runtime/stream`. Response chunks stream back in real-time, parsing code blocks, markdown tables, and reasoning blocks.
- **Session Mutation Actions:**
  - *Rename:* Calls `PATCH /sessions/{id}` with `title`. UI updates immediately and confirms server truth.
  - *Pin / Unpin:* Calls `PATCH /sessions/{id}` with `pinned`. Reconciles on error.
  - *Archive / Restore:* Calls `PATCH /sessions/{id}` with `archived`. Filtered views display archived sessions only when requested.
  - *Delete:* Triggers explicit modal confirmation, calls `DELETE /sessions/{id}`, and removes session from UI.
  - *Copy Conversation:* Formats entire dialogue into clean Markdown with timestamps and copies to clipboard.

---

## 3. Project Assignment & Backend Persistence

- **Previous Defect:** Project assignment was purely stored in browser `localStorage['roxy_session_projects']`.
- **Remediated State:**
  - Added `project_id` column to `chat_sessions` database table (migration 014).
  - Pydantic models `SessionCreateRequest`, `SessionUpdateRequest`, and `SessionResponse` validate `project_id`.
  - Frontend `useSessions` exposes `moveToProject(id, projectId)`.
  - `SessionSidebar.tsx` executes asynchronous persistence call before displaying success feedback. If backend fails, error toast is displayed and state rolls back.

---

## 4. Secure Conversation Sharing

- **Previous Defect:** Clicking "Share" constructed `?session={id}` and copied to clipboard, exposing raw session IDs without server authorization.
- **Remediated State:**
  - `SessionSidebar.tsx` calls `POST /api/v1/sessions/{id}/share`.
  - Backend verifies caller owns the session and computes an unpredictable 24-character SHA256 snapshot token: `hashlib.sha256(f"share:{session.id}:{current_user.id}".encode()).hexdigest()[:24]`.
  - Endpoint returns `{ "url": "/share/{token}" }`.
  - Clipboard receives the full secure URL `${window.location.origin}/share/${token}`.

---

## 5. Dynamic Model Catalogue & Inference Routing

- **Provider Resolution:** Priority: Gemini (1) → DashScope/Qwen (2) → Groq (3) → Grok (4) → DeepSeek (5) → OpenAI (6) → Anthropic (7).
- **Gemini & Grok Protection:** Code paths in `adapters/gemini.py` and `adapters/grok.py` are strictly untouched.
- **Qwen / DashScope Completion:** Implemented `DashScopeAdapter` matching Alibaba Cloud's OpenAI-compatible endpoint with streaming and pricing calculation.
- **Catalogue Verification:** Verified via `test_model_catalog_and_failover.py` and `test_dashscope_adapter.py`.

---

## 6. Payment Gateways (Stripe, Safepay, NayaPay, SadaPay)

- **Stripe:** International USD/EUR/GBP subscriptions and top-up credits.
- **Safepay:** Pakistani Rupee (PKR) domestic gateway with 3DS2 cards and mobile wallets.
- **NayaPay:** Native Pakistani EMI wallet and Visa debit checkout adapter (`nayapay_provider.py`) with HMAC-SHA256 signature verification.
- **SadaPay:** Native Pakistani EMI / SadaBiz invoicing and checkout adapter (`sadapay_provider.py`) with HMAC-SHA256 signature verification.
- **Idempotency:** Webhooks processed through atomic `payment_events` table deduplication (`ON CONFLICT DO NOTHING`).
