# ROXY JARVIS — Master vs. Redesign Branch Comparison

**Base Reference Branch:** `master` (`166216515d00b3d263078473a1e7ed7727b34204`)  
**Target Feature Branch:** `design/roxy-ui-ux-redesign`  
**Comparison Date:** 2026-10-18  

---

## 1. Branch Summary & Git Safety Status

- `master` is **strictly protected** and unmodified.
- `design/roxy-ui-ux-redesign` contains all redesign enhancements and workflow remediations.
- No merges, rebases, or destructive actions have occurred against `master`.

---

## 2. High-Level Comparison Matrix

| Domain | `master` Baseline | `design/roxy-ui-ux-redesign` | Improvement & Verification |
|---|---|---|---|
| **Design System** | Basic styles, scattered CSS, inconsistent dark mode | Unified design tokens, glassmorphism, responsive sidebar rails, high contrast | Complete visual consistency; verified across 14 screenshots |
| **Protected AI (Gemini & Grok)**| Functional in master | **100% PRESERVED & UNTOUCHED** | Zero regressions; 13/13 regression tests pass |
| **Qwen / DashScope** | Configured in discovery & provider models, but lacked adapter in `_get_adapter` | **COMPLETED**: Dedicated `DashScopeAdapter` with streaming | 5/5 unit tests pass (`test_dashscope_adapter.py`) |
| **Session Project Assignment** | Stored purely in `localStorage['roxy_session_projects']` | **BACKEND PERSISTED**: `project_id` column in `chat_sessions`, migration 014, API support | Survives device switch, reload, and sign-in |
| **Session Pin Consistency** | Split between localStorage and backend without sync | Server-persisted pin state with authoritative rollback on error | Optimistic UI with server truth |
| **Conversation Sharing** | Plain `?session={id}` URL copying without token security | **SECURE SHARE**: Unpredictable 24-char SHA256 snapshot token via API (`/share/{token}`) | Server permission validation, no private leak |
| **Billing: NayaPay & SadaPay** | Documented in assessment but missing provider adapters | **IMPLEMENTED**: `NayaPayProvider` & `SadaPayProvider` adapters with HMAC signatures | 9/9 tests pass (`test_nayapay_sadapay_adapters.py`) |
| **Multilingual (i18n)** | Only 6 locales | **30 LOCALES**: Extensible catalogue, Roman Urdu LTR, Urdu/Arabic/Persian RTL | 5/5 tests pass (`i18n.test.ts`) |
| **Code Studio & Workspaces** | Fragmented views | Cohesive workspace hub, 7 navigation groups | Full keyboard shortcut navigation & responsive rails |

---

## 3. Detailed Changed Files

### 3.1 Backend Files
1. `backend/src/app/ai_gateway/adapters/dashscope.py` (New): Alibaba DashScope OpenAI-compatible inference adapter.
2. `backend/src/app/ai_gateway/services/router.py`: Registered `DashScopeAdapter` in `_get_adapter(name)` without touching Gemini or Grok.
3. `backend/src/app/session/models.py`: Added `project_id` column to `ChatSession` model.
4. `backend/src/app/session/schemas.py`: Added `project_id` to `SessionCreateRequest`, `SessionUpdateRequest`, and `SessionResponse`.
5. `backend/src/app/session/repository.py`: Supported `project_id` in `_MemSession`, `create`, and `update`.
6. `backend/src/app/session/router.py`: Passed `project_id` through `_to_response`, `create_session`, and `update_session`.
7. `backend/alembic/versions/014_chat_session_project_id.py` (New): Migration adding `project_id` with index to `chat_sessions`.
8. `backend/src/app/billing/providers/nayapay_provider.py` (New): Dedicated NayaPay provider adapter with HMAC-SHA256 verification.
9. `backend/src/app/billing/providers/sadapay_provider.py` (New): Dedicated SadaPay provider adapter with HMAC-SHA256 verification.
10. `backend/src/app/billing/providers/__init__.py`: Exported `NayaPayProvider` and `SadaPayProvider`.
11. `backend/src/app/billing/service.py`: Registered NayaPay and SadaPay in `PaymentService`.
12. `backend/src/app/api/v1/billing.py`: Added webhook endpoints `/webhook/nayapay` and `/webhook/sadapay`.
13. `backend/tests/test_dashscope_adapter.py` (New): 5 unit tests for DashScope adapter.
14. `backend/tests/test_nayapay_sadapay_adapters.py` (New): 9 unit tests for NayaPay and SadaPay adapters.
15. `backend/tests/test_alembic_migrations.py`: Updated single-head assertion for revision 014.

### 3.2 Frontend Files
1. `frontend/src/session/useSessions.ts`: Added `project_id` to interfaces and implemented `moveToProject` API call.
2. `frontend/src/session/SessionSidebar.tsx`: Wired `handleAssignProject` to backend `moveToProject` and `handleShare` to secure API share endpoint.
3. `frontend/src/i18n/types.ts`: Expanded to 30 locales with direction metadata and extensible union type.
4. `frontend/src/i18n/I18nContext.tsx`: Loaded new dictionaries and implemented Roman Urdu LTR and browser language detection.
5. `frontend/src/i18n/locales/ur-Latn.json` (New): Authentic Latin script Roman Urdu translation dictionary.
6. `frontend/src/i18n/locales/ja.json` (New): Japanese translation dictionary.
7. `frontend/src/i18n/locales/zh-Hant.json` (New): Traditional Chinese translation dictionary.
8. `frontend/src/i18n/locales/fr.json` (New): French translation dictionary.
9. `frontend/src/i18n/locales/fa.json` (New): Persian RTL translation dictionary.
10. `frontend/src/i18n/__tests__/i18n.test.ts`: Expanded test suite testing all 30 locales and RTL/LTR rules.
