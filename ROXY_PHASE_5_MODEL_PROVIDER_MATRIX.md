# Roxy-AI — Phase 5 Model & Provider Reality Matrix

**Gateway Implementation:** `backend/src/app/ai_gateway/`  
**API Router:** `backend/src/app/api/v1/ai.py` & `backend/src/app/api/v1/runtime.py`  
**Frontend Model Selector:** `frontend/src/model_provider/ModelPicker.tsx`  
**Date:** October 13, 2026  

---

## 1. End-to-End AI Gateway Pipeline Trace

```
User Prompt
    │
    ▼
[ModelPicker.tsx] (Model selection: provider + model_id)
    │
    ▼
[frontend/src/api/client.ts] (Request payload: { prompt, model, provider, temperature })
    │
    ▼
FastAPI Route: POST /api/v1/ai/chat/stream OR POST /api/v1/runtime/chat/stream
    │
    ▼
[AIGatewayRouter] (Evaluates circuit breaker, rate limit, provider preference)
    │
    ▼
[ProviderAdapter] (Resolves headers, formats system & conversation messages)
    │
    ▼
External Provider REST API (Google / OpenAI / Anthropic / Groq / xAI / DeepSeek)
    │
    ▼
Provider Response Streaming Chunks
    │
    ▼
SSE Formatter (Includes explicit `provider` and `model` attribution metadata)
    │
    ▼
[ChatView.tsx] (Renders live tokens + Attribution Badge with provider icon)
    │
    ▼
Database Persistence (Stores session message with exact generating model ID)
```

---

## 2. Complete Model & Provider Reality Matrix

| UI Advertised Model ID | Underlying Provider | Real API Endpoint | Required Env Var (Names Only) | Local Config Status | Capability Constraints | Real Smoke Test Evidence | Failover / Fallback Behavior | Audit Finding & Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini-2.0-flash` | Google Gemini | `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent` | `GEMINI_API_KEY` | UNCONFIGURED (No live key in env) | Multimodal, audio STT, 1M context | **BLOCKED** (Requires paid/live API key) | Falls back to DeepSeek or Grok if enabled | **VERIFIED** — adapter model mapping preserved in Phase J fix |
| `gemini-1.5-pro` | Google Gemini | `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:streamGenerateContent` | `GEMINI_API_KEY` | UNCONFIGURED | Complex reasoning, 2M context | **BLOCKED** | Falls back to primary enabled provider | **VERIFIED** — code passes model name unaltered |
| `gemini-1.5-flash` | Google Gemini | `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:streamGenerateContent` | `GEMINI_API_KEY` | UNCONFIGURED | Fast general utility | **BLOCKED** | Falls back to primary enabled provider | **VERIFIED** |
| `gemini-3.6-flash` *(Legacy UI Entry)* | Google Gemini | Fictional model name (404 on Google API) | `GEMINI_API_KEY` | UNCONFIGURED | Does not exist upstream | **REMEDIATED** | Phase J mapped to `gemini-2.0-flash` | **PARTIAL** — legacy alias safely sanitized |
| `gpt-4o` | OpenAI | `https://api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | UNCONFIGURED | Multimodal, tool calling, 128k context | **BLOCKED** (Requires live OpenAI key) | Circuit breaker redirects to Anthropic or Gemini | **SOURCE-VERIFIED** |
| `gpt-4o-mini` | OpenAI | `https://api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | UNCONFIGURED | High speed, cost efficient | **BLOCKED** | Falls back to secondary enabled provider | **SOURCE-VERIFIED** |
| `claude-3-5-sonnet-20241022` | Anthropic | `https://api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` | UNCONFIGURED | Advanced coding, computer use | **BLOCKED** (Requires live Anthropic key) | Falls back to OpenAI / DeepSeek | **SOURCE-VERIFIED** |
| `claude-3-5-haiku-20241022` | Anthropic | `https://api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` | UNCONFIGURED | Ultra-fast reasoning | **BLOCKED** | Falls back to secondary provider | **SOURCE-VERIFIED** |
| `grok-beta` / `grok-2` | xAI | `https://api.x.ai/v1/chat/completions` | `GROK_API_KEY` | UNCONFIGURED | Real-time search grounding | **BLOCKED** | Falls back to DeepSeek or Gemini | **SOURCE-VERIFIED** |
| `deepseek-chat` / `deepseek-reasoner` | DeepSeek | `https://api.deepseek.com/v1/chat/completions` | `DEEPSEEK_API_KEY` | UNCONFIGURED | High-performance coding & math | **BLOCKED** | Circuit breaker routes to next provider in ring | **SOURCE-VERIFIED** |
| `llama-3.3-70b-versatile` | Groq | `https://api.groq.com/openai/v1/chat/completions` | `GROQ_API_KEY` | UNCONFIGURED | Ultra-low latency LPUs | **BLOCKED** | Falls back to Gemini Flash | **SOURCE-VERIFIED** |

---

## 3. Provider Routing & Attribution Integrity Rules

1. **Zero Silent Substitution Policy:**  
   The gateway adapter preserves the selected model identifier without stealth clobbering. If a primary provider fails and the circuit breaker engages failover, the streaming SSE chunk and persisted message explicitly declare:
   ```json
   {
     "status": "stream_chunk",
     "metadata": {
       "provider": "deepseek",
       "model": "deepseek-chat",
       "fallback_engaged": true,
       "original_requested_provider": "openai"
     }
   }
   ```
2. **Provider Attribution Badge in UI:**  
   The frontend `ChatMessage` component renders a dedicated badge stating `[Provider] · [Model]`, verified by Playwright E2E assertion `expect(badgeText).toMatch(/\S+ · \S+/)`.

3. **Status of Live Smoke Tests:**  
   All live cloud provider smoke tests requiring external production billing credentials (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GROK_API_KEY`, `GROQ_API_KEY`) are recorded as **BLOCKED** in accordance with Absolute Safety Rule 4 (never commit or request secrets) and Rule 9 (mark tests requiring paid credentials as BLOCKED). Mock/circuit-breaker failover mechanics are **VERIFIED** via automated tests.
