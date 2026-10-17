# ROXY-AI — POST-PHASE 5.1: SETTINGS, AUTH & GOOGLE OAUTH AUDIT
*(Workstream K Deliverable)*

## 1. 15-Section Global Settings Architecture

Roxy-AI's settings subsystem was unified in Phase 34 into a comprehensive 15-section architecture managed via [SettingsModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/SettingsModal/SettingsModal.tsx) and [backend/src/app/settings/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/settings/):

| Tab Key | Label | Scope & Managed Properties | Default Value | Verification |
| :--- | :--- | :--- | :--- | :---: |
| `profile` | Profile | Full name, avatar URL, bio, display timezone | Default User, `UTC` | **PASS** |
| `appearance` | Appearance | Color theme (light/dark), font scale, high contrast | `light`, `100%`, `false` | **PASS** |
| `persona` | AI Persona | System instructions, persona presets (Staff Eng, Executive, etc.) | Staff Engineer prompt | **PASS** |
| `models` | Models & Providers | Preferred provider, default chat model, streaming speed | `gemini`, `gemini-3.8-flash`, `fast` | **PASS** |
| `image` | Image Studio | Image provider, default model, aspect ratio, quality | `google`, `imagen-3.0-generate-002`, `1:1` | **PASS** |
| `video` | Video Studio | Video provider, default model, resolution, duration | `google`, `veo-3.1-generate-preview`, `720p` | **PASS** |
| `voice` | Voice & Audio | Default voice persona, speech speed, autoplay toggle | `aura-asteria-en`, `1.0x`, `true` | **PASS** |
| `notifications`| Notifications | Email digests, job completion alerts, budget warnings | `true`, `true`, `true` | **PASS** |
| `privacy` | Data & Privacy | AI learning opt-in, retention days, prompt storage | `true`, `90 days`, `true` | **PASS** |
| `security` | Security & Sessions | Two-factor toggle, session timeout minutes | `false`, `1440 min (24h)` | **PASS** |
| `accounts` | Connected Accounts | Google, GitHub, Apple OAuth link status | Disconnected | **PASS** |
| `billing` | Billing & Credits | Plan tier, auto top-up threshold, credit balance | `Free Starter`, `$0`, `$50` | **PASS** |
| `byok` | API Keys (BYOK) | Custom Gemini, OpenAI, Anthropic, Flux keys | Empty / Masked | **PASS** |
| `memory` | Memory & Context | Automatic memory extraction, context window length | `true`, `32k` | **PASS** |
| `danger` | Danger Zone | Clear chat history, purge memories, delete account | Requires double confirmation | **PASS** |

---

## 2. Forensic Investigation: Former Settings HTTP 500 Issue

- **Historical Symptom:** Earlier audit cycles reported occasional `HTTP 500 Internal Server Error` when saving global settings.
- **Root Cause Identified:** Missing JSON keys in `user_preferences.extra_settings` triggered schema validation failures in Pydantic when reading unmigrated rows.
- **Remediation Implemented:**
  - Alembic revision `004_extra_settings` and `006_trust_and_reliability` defaulted `extra_settings` to empty JSON dict `{}`.
  - [SettingsResponse](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/settings/schemas.py) provides safe fallbacks for all 15 sections.
  - Partial PATCH requests now merge shallow dict keys rather than overwriting the entire JSON column.
- **Verification Evidence:** `test_phase34_settings_all_15_sections.py` executed successfully (**1 passed in 17.86s**), verifying the full lifecycle across GET defaults, PATCH 15 sections, and GET verified.

---

## 3. Authentication & Google OAuth Verification

The auth engine ([backend/src/app/auth/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/auth/)) supports two production-ready flows:

1. **Magic Link Authentication:**
   - User inputs email in [AuthModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/AuthModal/AuthModal.tsx).
   - Backend creates single-use magic token with 15-minute expiry.
   - User clicks verify link or submits token to receive JWT (`access_token`).
2. **Google OAuth 2.0:**
   - Initiates consent redirect to `accounts.google.com/o/oauth2/v2/auth`.
   - Validates CSRF `state` parameter and PKCE code challenge.
   - Exchanges code for Google User Profile, upserting user in `users` table.

### Live OAuth Production Prerequisites
- **Status:** **BLOCKED IN LOCAL SANDBOX** (requires external Google Cloud Console project).
- **Required Environment Variables:**
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REDIRECT_URI` (must match registered production domain).
- Codebase tested with deterministic mock responses in `test_oauth_google.py` (**PASS**).
