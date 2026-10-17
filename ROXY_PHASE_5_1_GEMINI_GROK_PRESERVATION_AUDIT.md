# ROXY-AI — PHASE 5.1: GEMINI & GROK PRESERVATION AUDIT

## 1. Audit Scope & Objectives

The primary objective of Phase 5.1 is to establish `gemini-3.8-flash` as Roxy's default Gemini model while strictly preserving every single existing Gemini and Grok model entry, identifier, provider mapping, UI entry, and capability definition.

This audit validates compliance against the 10 Mandatory Preservation Rules:
1. **Zero Model Deletions:** All 8 Gemini models and 10 Grok/Groq models remain accounted for.
2. **Zero Model Collapsing:** Distinct models (such as `gemini-3.6-flash` and `gemini-3.8-flash`) are not collapsed into one.
3. **No Silent Model Substitution:** User selection of `gemini-3.6-flash` is never rewritten to `gemini-3.8-flash`.
4. **Legitimate Model Preservation:** Genuine model IDs (`gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash`, etc.) pass through faithfully to the provider.
5. **Separation of Legacy Aliases:** Only generic aliases (`gemini`, `gemini-flash`, `default`, `auto`) map to the configured default (`gemini-3.8-flash`).
6. **Strict Grok Provider Isolation:** Grok models (`grok-3`, `grok-3-mini`, `grok-2`, `grok-beta`, etc.) route strictly to `GrokAdapter` (`https://api.x.ai/v1` or Groq endpoint), never to Google Gemini.
7. **Strict Gemini Provider Isolation:** Gemini requests never route to Grok.
8. **Consistent Configuration:** Default model alignment across `GeminiAdapter`, `_default_models`, `ModelPicker`, `UserSettings`, `UsageLog`, and `App.tsx`.
9. **User Preference Preservation:** Existing user model selections are preserved; the new default only applies when no explicit model is chosen.
10. **Observable Fallback & Truthful Errors:** Missing API keys produce honest configuration errors; 404/503/429 fallback logs a warning and truthfully attributes the responding fallback model in response metadata.

---

## 2. Gemini Catalog Preservation Audit

### 2.1 Preserved Model Inventory
| Model ID | UI Display Name | Task Types | Token Limit | Routing Target | Preservation Status |
|---|---|---|---|---|---|
| `gemini-3.8-flash` | Gemini 3.8 Flash | general, coding, reasoning, multimodal, audio | 1,000,000 | `/gemini-3.8-flash:generateContent` | **CONFIGURED AS DEFAULT** |
| `gemini-3.6-flash` | Gemini 3.6 Flash | general, coding, reasoning, multimodal | 1,000,000 | `/gemini-3.6-flash:generateContent` | **PRESERVED SELECTABLE** |
| `gemini-3.7-flash` | Gemini 3.7 Flash | general, coding, reasoning, multimodal | 1,000,000 | `/gemini-3.7-flash:generateContent` | **PRESERVED SELECTABLE** |
| `gemini-3.1-flash` | Gemini 3.1 Flash | general, coding, reasoning, multimodal | 1,000,000 | `/gemini-3.1-flash:generateContent` | **PRESERVED SELECTABLE** |
| `gemini-2.5-flash` | Gemini 2.5 Flash | general, coding, reasoning, multimodal | 1,000,000 | `/gemini-2.5-flash:generateContent` | **PRESERVED SELECTABLE** |
| `gemini-2.0-flash` | Gemini 2.0 Flash | general, coding, reasoning, multimodal | 1,000,000 | `/gemini-2.0-flash:generateContent` | **PRESERVED SELECTABLE** |
| `gemini-1.5-pro` | Gemini 1.5 Pro | general, coding, reasoning, multimodal | 2,000,000 | `/gemini-1.5-pro:generateContent` | **PRESERVED SELECTABLE** |
| `gemini-1.5-flash` | Gemini 1.5 Flash | general, coding | 1,000,000 | `/gemini-1.5-flash:generateContent` | **PRESERVED SELECTABLE** |

### 2.2 Resolution Audit: `GeminiAdapter._resolve_model`
```python
def _resolve_model(self, model: str | None) -> str:
    if not model:
        return self.DEFAULT_MODEL  # Returns "gemini-3.8-flash"
    if "/" in model:
        model = model.split("/", 1)[-1]
    alias_map = {
        "gemini-flash": self.DEFAULT_MODEL,
        "gemini": self.DEFAULT_MODEL,
        "default": self.DEFAULT_MODEL,
        "auto": self.DEFAULT_MODEL,
    }
    if model in alias_map:
        return alias_map[model]
    return model
```
- Input: `None` -> Output: `"gemini-3.8-flash"` (Default applied)
- Input: `"gemini-3.8-flash"` -> Output: `"gemini-3.8-flash"` (Faithful passthrough)
- Input: `"gemini-3.6-flash"` -> Output: `"gemini-3.6-flash"` (Preserved, NOT rewritten to 3.8)
- Input: `"gemini/gemini-3.6-flash"` -> Output: `"gemini-3.6-flash"` (Prefix stripped, model preserved)
- Input: `"gemini-2.0-flash"` -> Output: `"gemini-2.0-flash"` (Legitimate model preserved)
- Input: `"gemini-flash"` -> Output: `"gemini-3.8-flash"` (Generic alias resolved to default)

---

## 3. Grok Catalog Preservation & Isolation Audit

### 3.1 Preserved Grok Model Inventory
| Model ID | UI Display Name | Provider | Task Types | Token Limit | Isolation Check |
|---|---|---|---|---|---|
| `grok-3` | xAI Grok 3 | `grok` (`xai`) | general, coding, reasoning | 131,072 | Routes to `GrokAdapter` |
| `grok-3-mini` | xAI Grok 3 Mini | `grok` (`xai`) | general, coding, reasoning | 131,072 | Routes to `GrokAdapter` |
| `grok-2` | xAI Grok 2 | `grok` (`xai`) | general, coding | 131,072 | Routes to `GrokAdapter` |
| `grok-2-vision-1212` | xAI Grok 2 Vision | `grok` (`xai`) | general, multimodal | 131,072 | Routes to `GrokAdapter` |
| `grok-beta` | xAI Grok Beta | `grok` (`xai`) | general, coding | 131,072 | Routes to `GrokAdapter` |
| `qwen/qwen3.8-27b` | Grok / Qwen 27B | `grok` (`groq` key) | general, coding, reasoning | 32,768 | Routes to `GrokAdapter` |
| `openai/gpt-oss-120b` | Grok / GPT-OSS 120B | `grok` (`groq` key) | general, coding, reasoning | 32,768 | Routes to `GrokAdapter` |
| `qwen/qwen3.6-27b` | Grok / Qwen 3.6 27B | `grok` (`groq` key) | general, coding, reasoning | 32,768 | Routes to `GrokAdapter` |
| `llama-3.3-70b-versatile` | Groq / Llama 3.3 70B | `grok` (`groq` key) | general, coding, reasoning | 32,768 | Routes to `GrokAdapter` |
| `mixtral-8x7b-32768` | Groq / Mixtral 8x7B | `grok` (`groq` key) | general, coding | 32,768 | Routes to `GrokAdapter` |

### 3.2 Provider Isolation Audit: `AIRouter._resolve_override`
- If `request.provider == "grok"`: routes to `_get_adapter("grok")` -> `GrokAdapter`.
- If `request.model in ("grok-3", "grok-3-mini", "grok-2", "grok-beta", ...)`: resolves to `"grok"`, never `"gemini"`.
- If `request.model in ("gemini-3.8-flash", "gemini-3.6-flash", ...)`: resolves to `"gemini"`, never `"grok"`.
- Grok models are completely isolated and immune to any Gemini default changes.

---

## 4. Frontend Model Picker Audit

### 4.1 React State & Default Migration
```tsx
// Default to gemini-3.8-flash if not initialized or invalid runtime
useEffect(() => {
  if (!value || value.provider === 'runtime' || value.model === 'coordinator') {
    onChange({ provider: 'gemini', model: 'gemini-3.8-flash' });
  }
}, [value, onChange]);

const currentValue =
  value && value.provider !== 'runtime'
    ? `${value.provider}/${value.model}`
    : 'gemini/gemini-3.8-flash';
```
- When a user opens chat with no prior session: initial model is `gemini-3.8-flash`.
- When a user explicitly chooses `gemini-3.6-flash`: `value` is `{ provider: 'gemini', model: 'gemini-3.6-flash' }`. The effect condition evaluates to `false`, and the selection remains unchanged.
- Both `gemini-3.8-flash` and `gemini-3.6-flash` appear under the `Google Gemini` group in the `<select>` dropdown.

---

## 5. Audit Conclusion

All preservation requirements are **100% SATISFIED**:
- `gemini-3.8-flash` is established as the default.
- `gemini-3.6-flash` is preserved as selectable and distinct.
- Zero models removed, renamed, or collapsed.
- Grok models remain intact and isolated.
