# ROXY JARVIS — Provider Preservation & Non-Regression Audit

**Protected Providers:** Google Gemini, xAI Grok  
**Preserved & Completed Provider:** Alibaba DashScope / Qwen  
**Audit Date:** 2026-10-18  

---

## 1. Compliance Statement on Non-Regression Rules

### 1.1 Google Gemini (Protected)
- **Status:** **WORKING AND PROTECTED**
- **Files Inspected:**
  - `backend/src/app/ai_gateway/adapters/gemini.py`
  - `backend/src/app/ai_gateway/models/provider.py`
- **Actions Taken:** **ZERO CHANGES**. No refactoring, no model ID modifications, no changes to endpoints (`https://generativelanguage.googleapis.com/v1beta`), streaming, tokens, or retries.
- **Verification Evidence:**
  - `tests/test_model_catalog_and_failover.py::test_gemini_4_argon_is_default_in_adapter` PASSED
  - `tests/test_model_catalog_and_failover.py::test_gemini_model_ordering_and_preservation` PASSED
  - `tests/test_universal_adapter_resilience.py::test_cross_provider_failover_gemini_to_grok` PASSED

### 1.2 xAI Grok (Protected)
- **Status:** **WORKING AND PROTECTED**
- **Files Inspected:**
  - `backend/src/app/ai_gateway/adapters/grok.py`
  - `backend/src/app/ai_gateway/models/provider.py`
- **Actions Taken:** **ZERO CHANGES**. No refactoring, no endpoint changes (`https://api.x.ai/v1`), no header or payload format alterations.
- **Verification Evidence:**
  - `tests/test_model_catalog_and_failover.py::test_grok_catalog_includes_grok_4_7` PASSED
  - `tests/test_model_catalog_and_failover.py::test_seeds_provider_gemini_and_grok` PASSED

### 1.3 Alibaba DashScope / Qwen (Completed)
- **Status:** **COMPLETED & OPERATIONAL**
- **Files Implemented:**
  - `backend/src/app/ai_gateway/adapters/dashscope.py` (New dedicated adapter)
  - `backend/src/app/ai_gateway/services/router.py` (Registered `DashScopeAdapter` in `_get_adapter(name)` for `dashscope`, `qwen`, `alibaba`)
- **Integration Mechanics:**
  - Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - Auth: `Authorization: Bearer DASHSCOPE_API_KEY`
  - Models: `qwen-max`, `qwen-plus`, `qwen-turbo`, `qwen-2.5-coder-32b`, `qwen-2.5-72b-instruct`
  - Full streaming SSE support (`data: {"choices": [{"delta": {"content": "..."}}]}`)
  - Cost tracking based on official DashScope pricing per 1k input/output tokens.
- **Verification Evidence:**
  - `tests/test_dashscope_adapter.py::test_router_get_adapter_dashscope` PASSED
  - `tests/test_dashscope_adapter.py::test_dashscope_payload_building` PASSED
  - `tests/test_dashscope_adapter.py::test_dashscope_parse_response` PASSED
  - `tests/test_dashscope_adapter.py::test_dashscope_completion_success` PASSED
  - `tests/test_dashscope_adapter.py::test_dashscope_error_handling` PASSED

---

## 2. Full Provider Status Classification

| Provider Name | Architectural Classification | Credential Environment Variable | Endpoints / Protocol | Test Pass Rate |
|---|---|---|---|---|
| **Google Gemini** | Working and protected | `GEMINI_API_KEY` | GenerativeLanguage v1beta | 100% |
| **xAI Grok** | Working and protected | `GROK_API_KEY` / `XAI_API_KEY` | api.x.ai/v1 | 100% |
| **Alibaba DashScope (Qwen)** | Completed and working | `DASHSCOPE_API_KEY` / `QWEN_API_KEY` | dashscope.aliyuncs.com/compatible-mode/v1 | 100% |
| **Groq** | Working | `GROQ_API_KEY` | api.groq.com/openai/v1 | 100% |
| **DeepSeek** | Implemented but blocked by credentials | `DEEPSEEK_API_KEY` | api.deepseek.com | 100% (mock) |
| **OpenAI** | Implemented (Disabled by default) | `OPENAI_API_KEY` | api.openai.com/v1 | 100% (mock) |
| **Anthropic** | Implemented (Disabled by default) | `ANTHROPIC_API_KEY` | api.anthropic.com/v1 | 100% (mock) |
