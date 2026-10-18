# ROXY JARVIS — Master Workflow Inventory

**Branch:** `design/roxy-ui-ux-redesign`  
**Date:** 2026-10-18  

---

## 1. Complete Workflow Inventory & Status Matrix

| Workflow ID | Workflow Name | User Journey / Trigger | Backend Service / API Route | State Persistence | Verification Status |
|---|---|---|---|---|---|
| **WF-01** | User Registration & Login | User registers / logs in via email + password or Google OAuth | `POST /api/v1/auth/login`, `POST /api/v1/auth/register` | PostgreSQL `users` table; JWT HTTP-only cookies + Bearer token | Verified |
| **WF-02** | Session Creation | Clicking "New Chat" in sidebar or top bar | `POST /api/v1/sessions` | PostgreSQL `chat_sessions` table (`project_id`, `pinned`, `session_type`) | Verified |
| **WF-03** | Chat Streaming Inference | User submits prompt; assistant streams markdown response | `POST /api/v1/runtime/chat` & `POST /api/v1/runtime/stream` | PostgreSQL `chat_messages` table; streaming chunks via SSE/chunked JSON | Verified |
| **WF-04** | Model Selection & Routing | User chooses model from ModelPicker (Gemini, Qwen, Grok, Groq) | `POST /api/v1/models/select`, `POST /api/v1/runtime/chat` | User preference persisted; provider adapter lazily instantiated | Verified |
| **WF-05** | Session Renaming | User edits title via three-dots menu or inline input | `PATCH /api/v1/sessions/{id}` (`{"title": "..."}`) | Server truth persisted in DB; optimistic UI reconciliation | Verified |
| **WF-06** | Session Pin / Unpin | User toggles pin icon | `PATCH /api/v1/sessions/{id}` (`{"pinned": bool}`) | Server truth persisted in DB; optimistic rollback on network failure | Verified |
| **WF-07** | Session Archive & Restore | User clicks Archive in menu | `PATCH /api/v1/sessions/{id}` (`{"archived": bool}`) | Server truth (`archived_at` timestamp); optimistic filter | Verified |
| **WF-08** | Session Deletion | User clicks Delete with explicit confirmation dialog | `DELETE /api/v1/sessions/{id}` | Atomic cascade delete of session and associated chat messages | Verified |
| **WF-09** | Move Session to Project | User clicks "Move to Project" and picks workspace project | `PATCH /api/v1/sessions/{id}` (`{"project_id": ...}`) | Server truth persisted in `chat_sessions.project_id`; cross-surface event dispatched | Verified |
| **WF-10** | Secure Conversation Sharing | User clicks Share in sidebar menu | `POST /api/v1/sessions/{id}/share` | 24-character cryptographic token generated (`/share/{token}`); copied to clipboard | Verified |
| **WF-11** | Code Studio (IDE) Workflow | User opens IDE workspace (`Ctrl+Alt+I`), creates files, tests code | `POST /api/v1/ide/run`, WebSocket `/ws/terminal` | Persistent workspace files on filesystem / DB workspace records | Verified |
| **WF-12** | Universal App Control (Device Hub)| User manages device fleet, executes automation commands | `POST /api/v1/device-hub/command`, `GET /api/v1/devices` | Registered device agent database records | Verified |
| **WF-13** | Knowledge Vault Ingestion | User uploads PDF/DOCX/TXT files into vector memory | `POST /api/v1/documents/upload`, `POST /api/v1/vault/index` | Chunked vector embeddings stored in database/vault | Verified |
| **WF-14** | Billing Checkout (USD - Stripe) | User selects Pro/Team plan or top-up credit pack | `POST /api/v1/billing/checkout` | Stripe Checkout session created; webhook updates subscription | Verified |
| **WF-15** | Billing Checkout (PKR - Safepay)| User selects PKR currency for local domestic payment | `POST /api/v1/billing/checkout` (`provider="safepay"`) | Safepay tracker generated; 3DS2 card/wallet redirection | Verified |
| **WF-16** | Billing Checkout (PKR - NayaPay)| User selects NayaPay wallet / Visa debit card | `POST /api/v1/billing/checkout` (`provider="nayapay"`) | NayaPay QuickPay merchant session created; HMAC-SHA256 signature verified | Verified |
| **WF-17** | Billing Checkout (PKR - SadaPay)| User selects SadaPay / SadaBiz payment link | `POST /api/v1/billing/checkout` (`provider="sadapay"`) | SadaPay invoice generated; webhook verified with HMAC-SHA256 | Verified |
| **WF-18** | Webhook Processing & Idempotency| Provider sends async payment confirmation | `POST /api/v1/billing/webhook/{provider}` | Atomic deduplication via PostgreSQL `payment_events` table (ON CONFLICT DO NOTHING) | Verified |
| **WF-19** | Multilingual Language Switching | User changes locale to any of 30 languages (e.g. Roman Urdu, Japanese)| Localized via `I18nProvider`, `document.documentElement.dir` | Persisted in `localStorage['roxy_locale']`; LTR/RTL applied dynamically | Verified |
| **WF-20** | Theme Switching (Light / Dark) | User switches between Light and Dark mode | Client-side CSS variables in `index.css` | Persisted in `localStorage['roxy_theme']`; zero hydration flicker | Verified |

---

## 2. Navigation Architecture Groups

The application provides seven logical navigation groups, all operating with active view expansion and collapse:

1. **Core Workspaces**: Chat & Assistant, Code Studio (IDE).
2. **Autonomous Workspaces**: Browser Studio, Universal App Control (Device Hub), Deep Research.
3. **Knowledge**: Knowledge Vault, Memory & Curator, Documents & Vault, Study Studio.
4. **Productivity**: Calendar & Agendas, Email Hub, Voice Session, Scheduled Jobs, Calculator.
5. **Business & Account**: Workspace Hub, Finance & Banking, Usage & Telemetry, Billing & Plans, Payment Methods.
6. **System & Trust**: Connectors Hub, Control Center, Trust & Safety Center.
7. **Media & Studios**: Image Studio, Video Studio.
