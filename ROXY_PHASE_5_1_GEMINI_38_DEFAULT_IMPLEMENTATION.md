# ROXY-AI — PHASE 5.1: GEMINI 3.8 FLASH DEFAULT IMPLEMENTATION

## 1. Implementation Overview

In accordance with the Phase 5.1 specification, `gemini-3.8-flash` has been configured as Roxy's default Gemini model across all sources of truth, while preserving `gemini-3.6-flash` as an independent, selectable model.

All modifications strictly adhered to the targeted scope:
- **No architectural rebuilds** or redesigns of the model picker.
- **No forced global provider override:** The global routing priority (where operator flags or other configured providers can take precedence) remains intact; when Gemini is selected or defaulted, `gemini-3.8-flash` is the model employed.
- **No loss of metadata or capabilities:** Multimodal audio, steerable modulation, and 1M token contexts are retained.

---

## 2. Files Modified & Technical Details

### 2.1 Backend: `backend/src/app/ai_gateway/adapters/gemini.py`
- **Change:** Updated `DEFAULT_MODEL` from `gemini-2.0-flash` to `gemini-3.8-flash`.
- **Change:** Refactored `_resolve_model`:
  - When `model` is `None` or empty, returns `self.DEFAULT_MODEL` (`"gemini-3.8-flash"`).
  - Statically strips provider prefixes (e.g. `gemini/gemini-3.8-flash` -> `gemini-3.8-flash`).
  - Directly passes through `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.1-flash`, `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`, and `gemini-1.5-flash`.
  - Maps generic legacy aliases (`gemini-flash`, `gemini`, `default`, `auto`) to `self.DEFAULT_MODEL`.
- **Change:** Added structured warning logging (`log.warning("gemini.fallback_triggered", ...)`) in `_complete` and `_stream` when 404/503/429 fallback to `DEFAULT_MODEL` is engaged.
- **Attribution Integrity:** Fallback responses truthfully return `model=self.DEFAULT_MODEL` rather than asserting success on the failed model.

### 2.2 Backend: `backend/src/app/ai_gateway/models/provider.py`
- **Change:** Updated `_default_models("gemini")` to place `gemini-3.8-flash` first as the default model, followed immediately by `gemini-3.6-flash`, preserving all 8 models.
- **Change:** Updated `_default_models("grok")` to include `qwen/qwen3.6-27b`, ensuring all 10 Grok/Groq models are present.

### 2.3 Backend: `backend/src/app/ai_gateway/services/router.py`
- **Change:** Enhanced `_resolve_override`:
  - If `request.provider` is set, uses it directly.
  - If `request.provider` is not set, infers provider from `request.model` (`gemini` models route to `gemini` adapter; `grok` models route to `grok` adapter).
  - Enforces strict isolation: Grok models never route through GeminiAdapter.

### 2.4 Backend: `backend/src/app/seeds/providers.py`
- **Change:** Ensured database seed records contain all 8 Gemini models (`gemini-3.8-flash` first, `gemini-3.6-flash` second) and all 10 Grok models.

### 2.5 Backend: `backend/src/app/models/subscription.py`
- **Change:** Updated `UsageLog.model` default column argument to `"gemini-3.8-flash"`.

### 2.6 Backend: `backend/src/app/personalization/service.py`
- **Change:** Updated default `preferred_models` in personalization profile to `["gemini-3.8-flash"]`.

### 2.7 Frontend: `frontend/src/model_provider/ModelPicker.tsx`
- **Change:** Reordered `DEFAULT_PROVIDERS` so `gemini-3.8-flash` is the first model in the Gemini array, and `gemini-3.6-flash` is preserved as the second.
- **Change:** Updated uninitialized / fallback hook:
  ```tsx
  useEffect(() => {
    if (!value || value.provider === 'runtime' || value.model === 'coordinator') {
      onChange({ provider: 'gemini', model: 'gemini-3.8-flash' });
    }
  }, [value, onChange]);
  ```
- **Change:** Updated fallback `currentValue` string to `'gemini/gemini-3.8-flash'`.

### 2.8 Frontend: `frontend/src/App.tsx`
- **Change:** Initial `modelSelection` state initialized to `{ provider: 'gemini', model: 'gemini-3.8-flash' }`.
- **Change:** `handleLaunchNewTask` defaults to `modelSelection?.model || 'gemini-3.8-flash'`.

### 2.9 Frontend: `frontend/src/components/SettingsModal/SettingsModal.tsx`
- **Change:** Updated `default_chat_model` default value to `'gemini-3.8-flash'`.
- **Change:** Updated input placeholder to `'e.g. gemini-3.8-flash or qwen-max'`.

---

## 3. Parameter Compatibility Verification

In accordance with official Google Gemini REST documentation (`/v1beta/models/{model}:generateContent`):
- **Endpoint Structure:** `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}`
- **Streaming Endpoint:** `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}`
- **Generation Parameters:**
  - `temperature`: float (0.0 to 2.0) — preserved.
  - `maxOutputTokens`: int — preserved.
  - `systemInstruction`: supported and mapped cleanly from system role messages.
  - `contents`: array of `{ role: "user" | "model", parts: [{ text: ... }] }` — preserved.
- **Thinking Budget:** Gemini 3 Flash does not require legacy thinking flags; unsupported parameters like `minimal` are avoided.
