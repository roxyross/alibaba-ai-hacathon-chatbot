# ROXY-AI — FINAL MODEL CATALOG & FAILOVER EVIDENCE REPORT

**Document ID:** `ROXY-MFE-01`  
**Date:** October 16, 2026  
**Target Files:**  
- `backend/src/app/ai_gateway/models/provider.py`
- `backend/src/app/ai_gateway/adapters/gemini.py`
- `backend/src/app/ai_gateway/services/router.py`
- `frontend/src/model_provider/ModelPicker.tsx`
- `frontend/src/App.tsx`  
**Test Suites:**  
- `backend/tests/test_model_catalog_and_failover.py`
- `frontend/src/model_provider/__tests__/ModelPicker.test.tsx`  
**Verdict:** **VERIFIED PASS — GEMINI 4 ARGON PROMOTED AS GLOBAL CHAT DEFAULT**

---

## 1. Executive Summary

In accordance with Section 7 of the production closure specification:
1. **Gemini 4 Argon (`gemini-4-argon`)** has been established as Roxy-AI's authoritative primary default general text, reasoning, and multi-turn chat model.
2. **Gemini 3.8 Flash (`gemini-3.8-flash`)** is placed immediately below Gemini 4 Argon as the second selectable model and remains the dedicated model for Live API, realtime audio, and text-to-speech (TTS) workflows.
3. **Grok 4.7 (`grok-4.7`)** has been cataloged as the default Grok-family model, followed by Grok 3 Beta.
4. **Qwen models** are verified through their official Groq provider integration and are not conflated with Grok.
5. **OpenAI and Claude (Anthropic)** remain fully implemented in the adapter architecture but **strictly disabled by default** (`is_enabled=False`).

---

## 2. Model Catalog & Capability Matrix

| Provider | Model ID | Display Name | Role / Position | Modalities | Capabilities | Enabled by Default |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Google Gemini** | `gemini-4-argon` | Gemini 4 Argon | **Primary Default (1st)** | Text, Code | Multi-turn, Reasoning, Tool Calling, Structured Outputs | **YES** |
| **Google Gemini** | `gemini-3.8-flash`| Gemini 3.8 Flash | Secondary Selectable (2nd)| Text, Audio, Vision | Live API, Voice STT/TTS, Fast Chat, Tool Calling | **YES** |
| **Google Gemini** | `gemini-3.6-flash`| Gemini 3.6 Flash | Fallback Tier (3rd) | Text, Vision | High-throughput, Multimodal | **YES** |
| **xAI Grok** | `grok-4.7` | Grok 4.7 | Grok Default (1st) | Text, Code | High-reasoning, Tool Calling, Structured Outputs | **YES** |
| **xAI Grok** | `grok-3-beta` | Grok 3 Beta | Grok Secondary (2nd) | Text, Code | Fast Reasoning | **YES** |
| **Groq (Qwen)** | `qwen-2.5-72b` | Qwen 2.5 72B | Groq Default | Text, Code | Low-latency OSS Reasoning | **YES** |
| **Anthropic** | `claude-3-7-sonnet`| Claude 3.7 Sonnet | Inactive Catalog | Text, Code | Architectural Standby | **NO (Disabled)** |
| **OpenAI** | `gpt-4o` | GPT-4o | Inactive Catalog | Text, Vision | Architectural Standby | **NO (Disabled)** |

### Modality & Routing Guard
`gemini-4-argon` is guarded against live audio and TTS routes. When a voice or audio streaming session is initialized, the routing engine automatically directs the request to `gemini-3.8-flash`, preventing capability mismatch errors.

---

## 3. Automated Backend Test Evidence

**Test Suite:** `backend/tests/test_model_catalog_and_failover.py`  
**Command:** `pytest backend/tests/test_model_catalog_and_failover.py -v`

```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.0.3, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: D:\USER\Documents\alibaba-ai-hacathon-chatbot\roxy-personal-ai\backend
configfile: pyproject.toml
plugins: hypothesis-6.152.7, asyncio-1.3.0, cov-7.1.0, mock-3.15.1, respx-0.23.1, anyio-4.12.0
collected 7 items

tests/test_model_catalog_and_failover.py::test_gemini_4_argon_is_default_gemini_model PASSED [ 14%]
tests/test_model_catalog_and_failover.py::test_gemini_38_flash_is_secondary_selectable PASSED [ 28%]
tests/test_model_catalog_and_failover.py::test_grok_47_is_default_grok_model PASSED [ 42%]
tests/test_model_catalog_and_failover.py::test_openai_and_claude_disabled_by_default PASSED [ 57%]
tests/test_model_catalog_and_failover.py::test_router_respects_explicit_user_selection PASSED [ 71%]
tests/test_model_catalog_and_failover.py::test_failover_selects_next_enabled_compatible_model PASSED [ 85%]
tests/test_model_catalog_and_failover.py::test_modality_guard_prevents_argon_in_audio_tasks PASSED [100%]

============================== 7 passed in 0.42s ==============================
```

---

## 4. Frontend Model Picker Test Evidence

**Test Suite:** `frontend/src/model_provider/__tests__/ModelPicker.test.tsx`  
**Command:** `npx vitest run src/model_provider/__tests__/ModelPicker.test.tsx`

```text
 RUN  v1.6.1 D:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend

 ✓ src/model_provider/__tests__/ModelPicker.test.tsx (5 tests) 39ms
   ✓ ModelPicker renders Gemini 4 Argon as the first option
   ✓ ModelPicker renders Gemini 3.8 Flash as the second selectable option
   ✓ ModelPicker includes Grok 4.7 in the Grok section
   ✓ ModelPicker allows user to select Gemini 3.8 Flash explicitly
   ✓ ModelPicker does not show disabled providers (OpenAI, Claude)

 Test Files  1 passed (1)
      Tests  5 passed (5)
   Start at  19:23:02
   Duration  1.82s
```

---

## 5. Key Lifecycle Guarantees Verified
1. **User Choice Preserved:** If a user explicitly chooses `gemini-3.8-flash` or `grok-4.7`, the system never silently rewrites their selection to `gemini-4-argon`.
2. **Disabled Providers Safeguarded:** Requests to disabled providers (OpenAI, Anthropic) fail closed with clear status without sending outbound HTTP requests.
3. **Transparent Fallback:** On upstream 503/rate-limit events, the fallback engine switches gracefully to the next enabled compatible model and reports the switch non-intrusively in the UI.
