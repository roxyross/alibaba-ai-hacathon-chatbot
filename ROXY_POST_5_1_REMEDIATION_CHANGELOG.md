# ROXY-AI — POST-PHASE 5.1: REMEDIATION CHANGELOG
*(Workstream R Deliverable)*

## 1. Summary of Authorized Remediations

This document logs all confirmed, in-scope remediations implemented during the execution of Phase 5.1 and the Post-Phase 5.1 quality hardening program.

---

## 2. Itemized Remediation Log

### Remediation 1: Alembic 011 `TextClause` server_default Typing Bug
- **Issue:** Static type checkers and linters flagged `TextClause is not assignable to dict key server_default with type bool` in [011_trust_reliability_hardening.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/alembic/versions/011_trust_reliability_hardening.py#L54-L56).
- **Root Cause:** A helper dictionary `kw = {"nullable": nullable}` narrowed static typing to `dict[str, bool]`. Assigning `TextClause` to `kw["server_default"]` failed static typing.
- **Fix:** Replaced dictionary assignment with direct keyword arguments:
  ```python
  sa.Column(col_name, cast(Any, col_type), nullable=nullable, server_default=server_default)
  ```
- **Commit:** [`4b6bfe0`](https://github.com/roxyross/alibaba-ai-hacathon-chatbot/commit/4b6bfe0)
- **Verification:** `mypy` passed, `ruff check` passed, `pytest tests/test_alembic_migrations.py` passed (2/2).

---

### Remediation 2: Seeds `providers.py` Missing Generic Dict Type Arguments
- **Issue:** Static type checker flagged `Missing type arguments for generic type "dict"` on lines 26, 265, and 314 of [backend/src/app/seeds/providers.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/seeds/providers.py).
- **Root Cause:** Functions `_seed_data() -> list[dict]`, `_seed_with_sqlalchemy(records: list[dict])`, and `_seed_dry_run(records: list[dict])` used untyped generic `dict`.
- **Fix:** Imported `typing.Any` and updated annotations to `list[dict[str, Any]]`. Cleaned up redundant imports inside `main()`.
- **Commit:** [`e7e1c87`](https://github.com/roxyross/alibaba-ai-hacathon-chatbot/commit/e7e1c87)
- **Verification:** `mypy src/app/seeds/providers.py` exited with `Success: no issues found in 1 source file`. `ruff check` passed with 0 errors.

---

### Remediation 3: Phase 5.1 Gemini 3.8 Flash Default Model Configuration
- **Issue:** Roxy required `gemini-3.8-flash` to be the primary default Gemini model across all configuration paths, replacing historical `gemini-2.0-flash` defaults.
- **Files Modified:**
  - [backend/src/app/ai_gateway/adapters/gemini.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/ai_gateway/adapters/gemini.py): `DEFAULT_MODEL = "gemini-3.8-flash"`. Generic aliases (`gemini-flash`, `default`, `auto`) map to 3.8.
  - [backend/src/app/ai_gateway/models/provider.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/ai_gateway/models/provider.py): `_default_models` orders `gemini-3.8-flash` first.
  - [backend/src/app/models/subscription.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/models/subscription.py): `UsageLog.model` defaults to `"gemini-3.8-flash"`.
  - [backend/src/app/personalization/service.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/personalization/service.py): `preferred_models` defaults to `["gemini-3.8-flash"]`.
  - [frontend/src/model_provider/ModelPicker.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/model_provider/ModelPicker.tsx): `DEFAULT_PROVIDERS` lists 3.8 first; fallback is `'gemini/gemini-3.8-flash'`.
  - [frontend/src/App.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/App.tsx): Initial `modelSelection` is `{ provider: 'gemini', model: 'gemini-3.8-flash' }`.
  - [frontend/src/components/SettingsModal/SettingsModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/SettingsModal/SettingsModal.tsx): `default_chat_model` set to `'gemini-3.8-flash'`.
- **Commit:** [`4262814`](https://github.com/roxyross/alibaba-ai-hacathon-chatbot/commit/4262814)
- **Verification:** 16 backend unit tests + 5 frontend unit tests passed.

---

### Remediation 4: Phase 5.1 Gemini & Grok Catalog Preservation
- **Issue:** Earlier Phase 5 work had temporarily rewritten `gemini-3.6-flash` and `gemini-3.8-flash` to `gemini-2.0-flash`.
- **Fix:** Restored `gemini-3.6-flash` as a separate, selectable model without silent downcasting. Restored all 8 Gemini models and 10 Grok models in `_default_models`, `_seed_data()`, and `router.py`.
- **Verification:** `test_phase5_1_gemini_grok_catalog_and_routing.py` verifies all 18 models are preserved and distinct.

---

### Remediation 5: AI Router Provider Inference & Isolation
- **Issue:** AI Router required strict isolation to prevent Grok requests from reaching the Gemini adapter and vice-versa.
- **Fix:** In [router.py](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/ai_gateway/services/router.py), enhanced `_resolve_override()` to infer provider from `request.model` prefix and maintain strict provider boundary routing.
- **Verification:** Covered by `test_router.py` and `test_phase5_1`.
