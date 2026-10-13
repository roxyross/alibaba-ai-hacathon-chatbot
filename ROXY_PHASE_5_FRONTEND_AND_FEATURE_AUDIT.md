# Roxy-AI — Phase 5 Frontend & Feature Audit

**Target Applications:** `frontend/` (Production Vite/React SPA) & `nextjs-frontend/` (Auxiliary prototype)  
**Date:** October 13, 2026  
**Auditor:** Roxy-AI Quality & Release Remediation Team  

---

## 1. Executive Summary

A comprehensive, evidence-based inventory was conducted across every page, route, view, modal, command surface, and tool panel in both `frontend/` and `nextjs-frontend/`. 

The production frontend (`frontend/`) is a comprehensive Single Page Application with 13 top-level views, 5 specialized studios/hubs, and full bidirectional multilingual support. However, several critical disparities between UI claims and backend implementations were discovered, including simulated tokenization in the billing UI, non-functional desktop file bridges from web context, and experimental mock surfaces in `nextjs-frontend/`.

---

## 2. Feature & Page Inventory Matrix (`frontend/`)

| Page / Route / Component | Primary Backend Endpoint | Real Data Status | Loading / Empty / Error States | State Persistence | Auth & Permissions | Keyboard / Mobile Usability | Audit Conclusion & Evidence Level |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Chat & New Task** (`App.tsx`, `NewTaskModal.tsx`) | `POST /api/v1/ai/chat/stream`, `POST /api/v1/runtime/tasks` | Real streaming SSE & JSON response | Full skeleton loading, empty greeting, error retry toast | Persisted via `chat_history` repository | Bearer JWT required | Enter to send, Shift+Enter newline; touch targets $\ge 44$px | **VERIFIED** — tested via Vitest & Playwright |
| **Conversation History** (`HistoryView.tsx`) | `GET /api/v1/chat/sessions`, `GET /api/v1/chat/messages` | Real PostgreSQL / SQLite session data | Loading spinner, empty session prompt, error retry | Persisted in database | Strict user isolation | Accessible list item keyboard navigation | **VERIFIED** — confirmed multi-tenant isolation |
| **Settings (All 15 Sections)** (`SettingsView.tsx`) | `GET/PATCH /api/v1/settings/*` | Real database preferences | Section loading, validated form inputs, error toasts | Persisted per user | Bearer JWT required | Full tab navigation and form controls | **VERIFIED** — tested via `test_phase34_settings_all_15_sections.py` |
| **Knowledge Vault** (`VaultView.tsx`) | `GET/POST /api/v1/vault/*` | Real vector embedding & file chunks | File dropzone, upload progress, chunk preview | Persisted in PostgreSQL pgvector | Multi-tenant tenant ID isolation | Drag & drop and keyboard file selection | **VERIFIED** — verified upload and similarity search |
| **Tools, MCP & Plugins** (`PluginsView.tsx`, `McpHub.tsx`) | `GET /api/v1/mcp/*`, `GET /api/v1/plugins/*` | Real discovered servers & registry tools | Discovered, connecting, failed states | Stored in plugin registry | Permission policy gate enforced | Configurable JSON input | **VERIFIED** — tested in `test_phase15_mcp_connector_discovery.py` |
| **Cowork & Open Work Agent** (`CoworkWorkspace.tsx`) | `GET/POST /api/v1/open_work/*` | Real multi-agent workflow tree | Step execution indicators, log viewer, cancel | Stored in Alembic `010_cowork_artifacts` | User ownership check | Accessible layout with task cancellation | **VERIFIED** — tested in `test_open_work_agent.py` |
| **Coding Studio & CodeStudioIDE** (`CodingStudio.tsx`) | `GET/POST /api/v1/coding/*`, `GET/POST /api/v1/files/*` | Real sandboxed repo filesystem access | File tree loading, Monaco editor, terminal logs | Local workspace / repo | User authenticated, sandbox path validation | Monaco full keybindings, Go to Line | **PARTIAL** — Real editor and file tree; terminal runs host commands (see Phase G audit) |
| **Study Studio & Quiz Generator** (`StudyStudio.tsx`) | `GET/POST /api/v1/study/*` | Real AI flashcard & quiz generation | Generation loading skeleton, score summary | Stored in study repository | Multi-tenant isolated | Keyboard shortcut choice selection | **VERIFIED** — tested in study integration suite |
| **Image & Media Studio** (`MediaView.tsx`, `VideoStudio.tsx`) | `POST /api/v1/images/generate`, `POST /api/v1/media/*` | Real provider dispatch (OpenAI DALL-E / Gemini) | Prompt spinner, thumbnail grid, error notice | Metadata saved in media registry | Rate limit & token consumption tracked | Responsive thumbnail grid with modal preview | **VERIFIED** — tested in `test_phase35_media_registry_and_jobs.py` |
| **Finance & Raast Billing** (`FinanceView.tsx`, `BillingView.tsx`) | `GET /api/v1/finance/*`, `GET/POST /api/v1/billing/*` | Real bank mock & Safepay/Stripe session | Transaction list, invoice table, checkout modal | Persisted in ledger | Strict user isolation | Tabbed currency toggle (USD / PKR) | **PARTIAL** — Real checkout generation; card tokenization in UI is simulated (see Finding B-1) |
| **Device & App Hub** (`DeviceHub.tsx`) | `GET/POST /api/v1/device/*` | Real local/remote device discovery | Scanning animation, device cards, app list | Persisted device registry | Policy check with confirmation challenges | Action buttons with confirmation modal | **VERIFIED** (Desktop) / **BLOCKED** (Physical mobile devices) |
| **Notifications & Reminders** (`RemindersView.tsx`) | `GET/POST /api/v1/reminders/*` | Real scheduler & job cron jobs | Scheduled, active, completed tabs | Database job scheduler | Strict user isolation | Date/time picker and recurrence selector | **VERIFIED** — tested in `test_code_studio_and_reminders.py` |
| **Authentication & Onboarding** (`AuthModal.tsx`) | `POST /api/v1/auth/request-link`, `POST /api/v1/auth/verify` | Real magic link & JWT generation | Email input, sending spinner, verification token | JWT stored in localStorage | Single-use token, expiry enforcement | Form autofocus, accessible alerts | **VERIFIED** — tested in `test_phase1_auth_session.py` |

---

## 3. Critical Findings & Discrepancies

### Finding B-1: Simulated Card Tokenization in `PaymentMethodView.tsx`
- **Location:** `frontend/src/components/PaymentMethodView/PaymentMethodView.tsx` (lines 120–135)
- **Evidence:** The UI displays a card entry form that accepts card number, expiry, and CVC, extracts the last 4 digits locally via substring, and alerts `"Card saved and tokenized securely via Stripe Elements"`. In reality, no Stripe Elements SDK (`@stripe/react-stripe-js` or `stripe.js`) is imported or mounted. Raw card data is processed purely in client-side component state without PCI-compliant iframe isolation.
- **Classification:** **FAILED / MISREPRESENTED CAPABILITY**
- **Disposition:** P1 remediation required before enabling production card-storage features. Checkout sessions redirecting directly to Stripe and Safepay hosted checkout pages remain genuine and secure.

### Finding B-2: Cloud vs. Local Laptop File Editing Assumption
- **Location:** `frontend/src/components/CodingStudio/CodeStudioIDE.tsx`
- **Evidence:** In web browser context, the IDE communicates with `/api/v1/coding/workspace/*`. When deployed to a cloud server, this inspects and edits files on the **backend container's filesystem**, not the end user's local workstation. The UI lacks a prominent indicator informing web users that the workspace is hosted in the remote container rather than their local laptop drive unless connected via desktop Electron bridge.
- **Classification:** **SOURCE-VERIFIED / CLARIFICATION REQUIRED**

### Finding B-3: `nextjs-frontend/` Disconnection
- **Location:** `nextjs-frontend/`
- **Evidence:** Inspection of build scripts, container definitions, and CI pipelines demonstrates that `nextjs-frontend/` is an orphan experimental directory. It has mock chat endpoints and incomplete route handlers. It does not receive production traffic.
- **Classification:** **SOURCE-VERIFIED** — confirmed unlinked.
