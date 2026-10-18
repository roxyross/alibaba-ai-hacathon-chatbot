# ROXY JARVIS — Complete Repository Inventory

**Audit Date:** 2026-10-18  
**Branch:** `design/roxy-ui-ux-redesign`  

---

## 1. Frontend Architecture & Inventory

### 1.1 Core Layout, Root & State
- `frontend/src/App.tsx`: Main application orchestrator managing view state (`activeView`), authentication modals, command bar, session loading, and responsive drawer toggling.
- `frontend/src/index.css`: Design system foundation defining typography, light/dark theme variables, focus rings, accessibility tokens, and glassmorphic styling.
- `frontend/src/main.tsx`: React DOM entry point wrapping `App` in `AuthProvider`, `I18nProvider`, and error boundaries.

### 1.2 Session Management & Navigation
- `frontend/src/session/SessionSidebar.tsx`: Multi-tier responsive sidebar featuring 7 navigation groups, pinned sessions, search filter, recent history, move to project modal, and share actions.
- `frontend/src/session/useSessions.ts`: Central React hook for session CRUD, optimistic updates, and server reconciliation.
- `frontend/src/session/SessionSidebar.css`: Responsive stylesheet supporting desktop icon-rail, tablet sidebar, and mobile drawer.

### 1.3 Chat, Assistant & Workspaces
- `frontend/src/components/ChatMessage/ChatMessage.tsx`: Message rendering component supporting Markdown, syntax-highlighted code blocks, copy, feedback thumbs, read aloud, and regeneration.
- `frontend/src/components/CodingStudio/CodeStudioIDE.tsx`: Embedded multi-file Code Studio with editor, terminal runner, and checkpoint preservation.
- `frontend/src/components/DeviceHub/DeviceHub.tsx`: Universal app and multi-device fleet manager.
- `frontend/src/components/TrustCenter/TrustCenter.tsx`: Trust, safety, security audit log viewer, and production exit gate monitor.
- `frontend/src/components/CommandBar/RoxyCommandBar.tsx`: Omnipresent keyboard command palette (`Cmd/Ctrl+K`).
- `frontend/src/components/KnowledgeVault/`: Document repository, chunk viewer, and search interface.
- `frontend/src/components/FinanceView/FinanceView.tsx`: Financial tracking, expense logging, and invoice management.
- `frontend/src/components/PricingPage/PricingPage.tsx`: Plan comparison, Stripe/Safepay/NayaPay/SadaPay checkout initiator.

### 1.4 Internationalization & Locales
- `frontend/src/i18n/types.ts`: TypeScript specifications for 30 locales, directional metadata, and language configs.
- `frontend/src/i18n/I18nContext.tsx`: React context for language selection, browser language detection, RTL class injection, and translation key fallback.
- `frontend/src/i18n/locales/`: Dictionaries for `en.json`, `ur.json`, `ar.json`, `zh.json`, `es.json`, `de.json`, `ur-Latn.json`, `ja.json`, `zh-Hant.json`, `fr.json`, `fa.json`.

---

## 2. Backend Architecture & Inventory

### 2.1 Core Application & Gateway
- `backend/src/app/main.py`: FastAPI entry point configuring CORS, middleware, lifecycle events, and API routers.
- `backend/src/app/db.py`: Async SQLAlchemy database engine with automatic in-memory fallback.
- `backend/src/app/auth/`: User authentication, JWT tokens, OAuth providers, and route security dependencies.

### 2.2 AI Gateway & Provider Adapters
- `backend/src/app/ai_gateway/models/provider.py`: Provider configurations, environment variable definitions, circuit breaker settings, and model lists.
- `backend/src/app/ai_gateway/services/router.py`: Domain routing service managing feature flags, user preferences, failover, and adapter instantiation.
- `backend/src/app/ai_gateway/services/catalog_discovery.py`: Dynamic model catalogue discovery for Gemini, Grok, Qwen, Groq, and DeepSeek.
- `backend/src/app/ai_gateway/adapters/gemini.py`: **PROTECTED** Google Gemini integration.
- `backend/src/app/ai_gateway/adapters/grok.py`: **PROTECTED** xAI Grok integration.
- `backend/src/app/ai_gateway/adapters/dashscope.py`: **COMPLETED** Alibaba DashScope (Qwen) integration.
- `backend/src/app/ai_gateway/adapters/groq.py`: Groq LPU integration.
- `backend/src/app/ai_gateway/adapters/deepseek.py`: DeepSeek API integration.
- `backend/src/app/ai_gateway/adapters/openai.py`: OpenAI API integration.
- `backend/src/app/ai_gateway/adapters/anthropic.py`: Anthropic Claude integration.

### 2.3 Session & Conversation Persistence
- `backend/src/app/session/models.py`: `ChatSession` ORM model mapping to `chat_sessions` table with `project_id`.
- `backend/src/app/session/schemas.py`: Pydantic request and response schemas for session CRUD.
- `backend/src/app/session/repository.py`: Async database session repository with in-memory dev fallback.
- `backend/src/app/session/router.py`: API endpoints for session CRUD and secure 24-character snapshot sharing (`POST /{id}/share`).

### 2.4 Billing, Payments & Webhooks
- `backend/src/app/billing/service.py`: Unified billing orchestrator across international and Pakistani providers.
- `backend/src/app/billing/providers/base.py`: Abstract `PaymentProvider` interface and standardized result models.
- `backend/src/app/billing/providers/stripe_provider.py`: Stripe Checkout & Webhook provider.
- `backend/src/app/billing/providers/safepay_provider.py`: Safepay PKR payment provider.
- `backend/src/app/billing/providers/nayapay_provider.py`: **NEW** NayaPay QuickPay PKR provider.
- `backend/src/app/billing/providers/sadapay_provider.py`: **NEW** SadaPay / SadaBiz PKR provider.
- `backend/src/app/api/v1/billing.py`: Billing router handling `/checkout`, `/subscription`, `/wallet`, and cryptographic webhook endpoints.
