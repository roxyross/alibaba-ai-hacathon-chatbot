# ROXY-AI — PHASE 5.1: MODEL BASELINE INVENTORY

## 1. Executive Summary & Verification Context

- **Repository:** `roxyross/alibaba-ai-hacathon-chatbot`
- **Branch:** `release/audit-remediation`
- **Reported Phase 5 Commit:** `571ebaf`
- **Pre-Phase-5 Baseline Commit:** `c06675c`
- **Phase 5.1 Working Head:** Verified on `release/audit-remediation`
- **Scope:** Complete pre-change and post-change inventory of all Gemini and Grok model definitions across backend, frontend, adapters, and registries.

---

## 2. Gemini Model Baseline Catalog (Pre-Change vs. Post-Change)

All 8 Gemini models from the original catalog are completely preserved. `gemini-3.8-flash` is established as the primary default model, while `gemini-3.6-flash` is preserved as a distinct, selectable model without alias rewriting or collapsing.

| Model Identifier | Display Name | Role in Roxy | Pre-Phase 5.1 Status | Phase 5.1 Configured Status | Capabilities & Metadata |
|---|---|---|---|---|---|
| `gemini-3.8-flash` | Gemini 3.8 Flash (Multimodal Audio & Modulation) | **Roxy Default Gemini Model** | Listed in UI; mapped to 2.0-flash in adapter | **PRIMARY DEFAULT** (Restored direct route) | General, coding, reasoning, multimodal, audio, steerable modulation |
| `gemini-3.6-flash` | Gemini 3.6 Flash (Fast & Full Reasoning) | **Selectable Model** | Listed in UI; mapped to 2.0-flash in adapter | **PRESERVED SELECTABLE** (Direct route, never rewritten) | General, coding, reasoning, multimodal |
| `gemini-3.7-flash` | Gemini 3.7 Flash | Selectable Model | Listed in UI; mapped to 2.0-flash in adapter | **PRESERVED SELECTABLE** | General, coding, reasoning, multimodal |
| `gemini-3.1-flash` | Gemini 3.1 Flash | Selectable Model | Listed in UI; mapped to 2.0-flash in adapter | **PRESERVED SELECTABLE** | General, coding, reasoning, multimodal |
| `gemini-2.5-flash` | Gemini 2.5 Flash | Selectable Model | Listed in UI | **PRESERVED SELECTABLE** | General, coding, reasoning, multimodal |
| `gemini-2.0-flash` | Gemini 2.0 Flash | Selectable Model | Previous interim default | **PRESERVED SELECTABLE** | General, coding, reasoning, multimodal |
| `gemini-1.5-pro` | Gemini 1.5 Pro | Selectable Model | Listed in UI | **PRESERVED SELECTABLE** | General, coding, reasoning, 2M context |
| `gemini-1.5-flash` | Gemini 1.5 Flash | Selectable Model | Listed in UI | **PRESERVED SELECTABLE** | General, coding, 1M context |

---

## 3. Grok / xAI Model Baseline Catalog (Pre-Change vs. Post-Change)

All 10 Grok and Groq models from the baseline are 100% accounted for and preserved with strict provider isolation from Gemini.

| Model Identifier | Display Name | Provider | Pre-Phase 5.1 Status | Phase 5.1 Configured Status | Routing Path |
|---|---|---|---|---|---|
| `grok-3` | xAI Grok 3 (Flagship Reasoning & Coding) | `xai` / `grok` | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` (`https://api.x.ai/v1`) |
| `grok-3-mini` | xAI Grok 3 Mini (High-Speed Reasoning) | `xai` / `grok` | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |
| `grok-2` | xAI Grok 2 | `xai` / `grok` | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |
| `grok-2-vision-1212` | xAI Grok 2 Vision | `xai` / `grok` | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |
| `grok-beta` | xAI Grok Beta | `xai` / `grok` | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |
| `qwen/qwen3.8-27b` | Groq Qwen 27B (Fast Inference) | `xai` / `grok` (Groq fallback) | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` (OTPM capped <= 1000) |
| `openai/gpt-oss-120b` | Groq GPT-OSS 120B | `xai` / `grok` (Groq fallback) | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |
| `qwen/qwen3.6-27b` | Groq Qwen 3.6 27B | `xai` / `grok` (Groq fallback) | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |
| `llama-3.3-70b-versatile` | Groq Llama 3.3 70B | `xai` / `grok` (Groq fallback) | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |
| `mixtral-8x7b-32768` | Groq Mixtral 8x7B | `xai` / `grok` (Groq fallback) | Active in catalog | **PRESERVED** | Routed to `GrokAdapter` |

---

## 4. Sources of Truth Across Codebase

| Location | Source of Truth | Verification Status |
|---|---|---|
| `backend/src/app/ai_gateway/adapters/gemini.py` | `DEFAULT_MODEL = "gemini-3.8-flash"` | Verified; `_resolve_model` preserves `gemini-3.8-flash` & `gemini-3.6-flash` |
| `backend/src/app/ai_gateway/models/provider.py` | `_default_models("gemini")` | Verified; `gemini-3.8-flash` is #1, `gemini-3.6-flash` is #2 |
| `backend/src/app/model_provider/router.py` | `GET /models` API fallback | Verified; `gemini-3.8-flash` is #1, `gemini-3.6-flash` is #2 |
| `backend/src/app/settings/schemas.py` | `default_chat_model: str = "gemini-3.8-flash"` | Verified |
| `backend/src/app/models/subscription.py` | `UsageLog.model default="gemini-3.8-flash"` | Verified |
| `backend/src/app/seeds/providers.py` | Provider seed database records | Verified; all 8 Gemini and 10 Grok models seeded |
| `frontend/src/model_provider/ModelPicker.tsx` | UI Model Picker Default Providers & Hook | Verified; `gemini-3.8-flash` default; `gemini-3.6-flash` selectable |
| `frontend/src/App.tsx` | Initial React Model Selection & New Task | Verified; defaults to `gemini-3.8-flash` |
| `frontend/src/components/SettingsModal/SettingsModal.tsx` | Settings default & placeholder | Verified; `gemini-3.8-flash` |
