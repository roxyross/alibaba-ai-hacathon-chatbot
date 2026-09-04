# Tasks: Multi-Provider AI Abstraction

**Feature:** multi-provider-ai | **Date:** 2026-09-02
**Plan:** `specs/feature/multi-provider-ai/plan.md` | **Spec:** `specs/feature/multi-provider-ai.md`

---

## Dependency Graph

```
Phase 1 ──────────────────────────────────────────────────────────────┐
  T001 → T002 → T003 → T004 → T005 ───────────────────────────────────→ T006 → T007 → T008 → T009
                                                                                │
Phase 2 ───────────────────────────────────────────────────────────────────────┘
  T010 → T011 → T012 → T013 → T014 → T015 → T016 → T017

Phase 3 ────────────────────────────────────────────────────────────────────────→ T018 → T019 → T020 → T021 → T022 → T023 → T024 → T025
```

**Parallel opportunities:** T002 + T003 (config + base models), T004 + T005 (adapters in parallel), T010–T013 (all 4 provider adapters in parallel).

**MVP scope:** Phase 1 (T001–T009) = demoable core: single DeepSeek adapter, non-streaming chat, attribution, circuit breaker, unit tests.

---

## Phase 1 – Setup

*Backend project initialization and shared tooling.*

- [x] T001 [P] Create `backend/src/app/ai_gateway/` directory structure
  `backend/src/app/ai_gateway/__init__.py`
  `backend/src/app/ai_gateway/models/__init__.py`
  `backend/src/app/ai_gateway/services/__init__.py`
  `backend/src/app/ai_gateway/adapters/__init__.py`
  `backend/src/app/ai_gateway/domain/__init__.py`

- [x] T002 [P] Add dependencies to `backend/pyproject.toml`
  `pybreaker>=1.0.2`, `httpx>=0.27.0`, `pydantic-settings>=2.0.0`
  Run `uv sync` after editing

- [x] T003 [P] Add provider feature flag env vars to `backend/.env.example`
  `PROVIDER_DEEPSEEK_ENABLED=true`, `PROVIDER_GROK_ENABLED=true`, `PROVIDER_OPENAI_ENABLED=true`, `PROVIDER_GEMINI_ENABLED=true`
  `DEEPSEEK_API_KEY=`, `XAI_API_KEY=`, `OPENAI_API_KEY=`, `GEMINI_API_KEY=`

---

## Phase 2 – Foundational

*Core domain interfaces and provider abstraction — all user stories depend on this.*

- [x] T004 [P] Implement `backend/src/app/ai_gateway/models/schemas.py`
  Pydantic v2 models: `AIRequest`, `AIResponse`, `StreamingChunk`, `Message`, `ProviderStatus`, `ProviderHealthResponse`, `TokenUsageLog`, `ErrorResponse`
  Exact field definitions per `data-model.md`

- [x] T005 [P] Implement `backend/src/app/ai_gateway/models/provider.py`
  `ProviderConfig` Pydantic model reading from env vars (`PROVIDER_*_ENABLED`, `PROVIDER_*_API_KEY`)
  `ModelConfig` dataclass

- [x] T006 Implement `backend/src/app/ai_gateway/adapters/base.py`
  Abstract base class `AIProviderAdapter` with methods:
  `async def chatCompletion(request: AIRequest) -> AIResponse`
  `async def chatCompletionStream(request: AIRequest) -> AsyncGenerator[StreamingChunk, None]`
  `property def provider_name(self) -> str`
  `property def circuit_breaker(self) -> pybreaker.CircuitBreaker`
  Raise `ProviderUnavailableError` on timeout or HTTP 5xx

- [x] T007 Implement `backend/src/app/ai_gateway/adapters/deepseek.py`
  `DeepSeekAdapter(AIProviderAdapter)`
  Uses `httpx.AsyncClient` with base URL `https://api.deepseek.com`
  Maps `AIRequest` → DeepSeek chat completion payload
  Maps DeepSeek response → `AIResponse`
  Circuit breaker: 5 failures, 30s reset timeout
  Reads `DEEPSEEK_API_KEY` from env

- [x] T008 Implement `backend/src/app/ai_gateway/services/sanitizer.py`
  `PromptSanitizer` class
  Blocklist-based injection detection (known patterns: "ignore previous", "disregard instructions", etc.)
  `def sanitize(user_input: str, system_prompt: str) -> list[Message]` — wraps in structured `user`/`system` message pair
  Raises `PromptInjectionError` if blocklist triggered

- [x] T009 Implement `backend/src/app/ai_gateway/services/router.py`
  `AIRouter` class
  Default priority: DeepSeek → Grok → OpenAI → Gemini
  Three-tier override resolution: operator flag > user preference > request field
  `async def route(request: AIRequest) -> AIResponse`
  Iterates providers in priority order, skips disabled/unavailable
  Tracks `request_id` (UUID) through the call chain

---

## Phase 3 – Endpoint (US1, US2, US3)

*FastAPI router and non-streaming chat — delivers US1 (routing), US2 (failover), US3 (attribution).*

- [x] T010 Implement `backend/src/app/api/v1/ai.py`
  `router = APIRouter(prefix="/ai", tags=["AI"])`
  `POST /chat` — accepts `AIRequest`, calls `AIRouter.route()`, returns `AIResponse`
  `GET /providers` — lists all `ProviderStatus` objects
  `PATCH /providers/{name}` — enables/disables provider (operator)
  `GET /providers/health` — unauthenticated health check
  `GET /usage` — returns last N `TokenUsageLog` entries
  All endpoints use `AIRequest`/`AIResponse` models; errors return `ErrorResponse`

- [x] T011 Register `ai.py` router in `backend/src/app/main.py`
  `app.include_router(api.v1.ai.router, prefix="/api/v1")`

- [x] T012 Write unit tests for `backend/tests/unit/test_router.py`
  Test: default priority order
  Test: request-level override (`provider=grok`) skips others
  Test: disabled provider is skipped
  Test: all providers disabled → raises `AllProvidersUnavailableError`
  Use `pytest-asyncio` + `pytest-mock`

- [x] T013 Write unit tests for `backend/tests/unit/test_sanitizer.py`
  Test: clean input passes through unchanged
  Test: blocklisted phrase raises `PromptInjectionError`
  Test: structured wrapping preserves message order
  Use `pytest`

- [x] T014 Write unit tests for `backend/tests/unit/test_deepseek_adapter.py`
  Test: successful response maps to `AIResponse`
  Test: timeout raises `ProviderUnavailableError`
  Test: circuit breaker opens after 5 consecutive failures
  Use `pytest-asyncio` + `respx` for HTTP mocking

- [x] T015 Write integration tests for `backend/tests/integration/test_chat_endpoint.py`
  Test: `POST /api/v1/ai/chat` returns 200 with attribution fields
  Test: `POST /api/v1/ai/chat` with `provider=grok` override uses Grok
  Test: `GET /api/v1/ai/providers/health` returns 200 without auth
  Use `pytest`, `httpx.AsyncClient` with `app` fixture

---

## Phase 4 – Streaming + All Providers (US2, US3)

*Streaming SSE and remaining provider adapters.*

- [x] T016 [P] Implement `backend/src/app/ai_gateway/adapters/grok.py`
  `GrokAdapter(AIProviderAdapter)`, same pattern as DeepSeek
  Base URL `https://api.x.ai`, reads `XAI_API_KEY` from env

- [x] T017 [P] Implement `backend/src/app/ai_gateway/adapters/openai.py`
  `OpenAIAdapter(AIProviderAdapter)`, OpenAI-compatible endpoint
  Base URL `https://api.openai.com/v1`, reads `OPENAI_API_KEY` from env

- [x] T018 [P] Implement `backend/src/app/ai_gateway/adapters/gemini.py`
  `GeminiAdapter(AIProviderAdapter)`, reads `GEMINI_API_KEY` from env
  Maps to Gemini `/v1beta/models/...:generateContent` endpoint

- [x] T019 Implement streaming in `backend/src/app/api/v1/ai.py`
  `POST /chat` with `stream: true` → `StreamingResponse`
  SSE format: `: provider={name} model={model}\n` as first comment line
  Each chunk: `data: {"delta": "...", "provider": "...", "model": "...", "done": false}`
  Final chunk: `data: [DONE]` with attribution metadata event
  Use `ai_gateway.adapters.base.AIProviderAdapter.chatCompletionStream()`

- [x] T020 Write unit tests for `backend/tests/unit/test_grok_adapter.py`
  Same pattern as DeepSeek adapter tests (T014)

- [x] T021 Write unit tests for `backend/tests/unit/test_openai_adapter.py`
  Same pattern as DeepSeek adapter tests (T014)

- [x] T022 Write unit tests for `backend/tests/unit/test_gemini_adapter.py`
  Same pattern as DeepSeek adapter tests (T014)

- [x] T023 Write integration test for streaming `backend/tests/integration/test_chat_stream.py`
  Test: streaming response is valid SSE with attribution comment line
  Test: streaming response includes `done: true` final event
  Use `pytest` + `httpx.AsyncClient`
  ✅ Created `backend/tests/integration/test_chat_stream.py` — 6 streaming tests covering SSE format, attribution header, data events, done flag, error events, and response headers

- [x] T024 Write integration test for failover `backend/tests/integration/test_failover.py`
  Test: primary provider disabled → routes to next available
  Test: primary provider times out → routes to next available
  Test: all providers fail → returns 503 with `ErrorResponse`
  Mock adapter `chatCompletion` to raise `ProviderUnavailableError`

---

## Phase 5 – Observability + Polish (US4, US5, US6)

*Token logging, feature flags, structured logs, frontend attribution.*

- [x] T025 Add `backend/src/app/ai_gateway/services/token_logger.py`
  `TokenUsageLogger` class
  `async def log(request_id, provider_name, model_name, input_tokens, output_tokens, latency_ms)`
  Persists to `TokenUsageLog` table via SQLAlchemy repository
  Called at the end of every `AIRouter.route()` call

- [x] T026 Add `backend/src/app/repositories/token_usage.py`
  `TokenUsageRepository` with `create(log: TokenUsageLogCreate)` and `find_recent(limit: int, provider: str | None)`
  SQLAlchemy async implementation; in-memory fallback when DATABASE_URL not set

- [x] T027 [T027] Replace Prisma with SQLAlchemy ORM ✅ COMPLETE
  Created `backend/src/app/models/` (Provider, Model, TokenUsageLog, UserPreference)
  `backend/src/app/db.py` — SQLAlchemy async engine + `get_db()` session dependency
  `backend/src/app/repositories/token_usage.py` — SQLAlchemy async with in-memory fallback
  `backend/src/app/seeds/providers.py` — updated to SQLAlchemy upsert
  `backend/alembic/` — Alembic async migration setup with initial revision
  `backend/pyproject.toml` — `sqlalchemy[asyncio]` + `asyncpg` (prisma removed)
  `backend/.env.example` — added `DATABASE_URL`
  `backend/prisma/schema.prisma` — retained for reference; Prisma no longer used

- [x] T028 Seed provider configuration `backend/src/app/seeds/providers.py`
  Script to upsert `Provider` records for DeepSeek, Grok, OpenAI, Gemini
  Run: `uv run python -m app.seeds.providers`

- [x] T029 Add structured JSON logging to `backend/src/app/api/v1/ai.py`
  Every request logs: `request_id`, `user_id`, `provider`, `model`, `latency_ms`
  Use `structlog.get_logger()` per §13 observability

- [x] T030 Add circuit breaker metrics to health endpoint `backend/src/app/api/v1/ai.py`
  `GET /providers/health` includes `circuit_state` per provider

- [x] T031 [P] Add provider attribution badge to `frontend/src/components/ChatMessage.tsx`
  Badge showing `{provider} · {model}` in muted text below message
  `aria-label` with full attribution string for accessibility
  ✅ Implemented: `ChatMessage.tsx` renders provider · model badge with aria-label

- [x] T032 [P] Handle SSE streaming in `frontend/src/hooks/useChat.ts`
  Parse SSE comment lines for attribution
  Accumulate deltas and display streaming text
  Show attribution badge on stream completion
  ✅ Implemented: `useChat.ts` parses SSE `: provider=X model=Y` comment, accumulates streaming deltas, sets attribution on completion

- [x] T033 [P] Write E2E test `frontend/tests/e2e/ai-chat.spec.ts`
  Test: user sends message, receives streamed response
  Test: provider attribution badge is visible after stream completes
  Test: failover scenario (mock primary down, verify fallback)
  Use `playwright`
  ✅ Implemented: `ai-chat.spec.ts` — 4 tests covering streaming response, attribution badge visibility, failover, and health endpoint

- [x] T034 Update `frontend/README.md` and `backend/README.md`
  Document multi-provider setup, provider override, failover testing
  Backend portion already done; frontend `README.md` + `package.json` scaffold created
  ✅ Complete: `frontend/README.md`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/playwright.config.ts`, `frontend/.env.example` all created

---

## Post-Hackathon (Labeled, Not for 3-Day Window)

*These are designed for but not built during the hackathon.*

- [ ] T035 [post-hackathon] Redis-backed circuit breaker state (shared across workers)
- [ ] T036 [post-hackathon] Per-user `preferred_provider` persistence and UI toggle
- [ ] T037 [post-hackathon] Task-type routing (coding vs general vs reasoning → different providers)
- [ ] T038 [post-hackathon] Open-source provider adapters (Ollama, vLLM, Groq)
- [ ] T039 [post-hackathon] Cost dashboard UI

---

## Task Summary

| Phase | Count | User Stories |
|---|---|---|
| Phase 1 – Setup | 3 | — |
| Phase 2 – Foundational | 6 | All |
| Phase 3 – Endpoint | 6 | US1, US2, US3 |
| Phase 4 – Streaming + All Providers | 9 | US2, US3 |
| Phase 5 – Observability + Polish | 10 | US4, US5, US6 |
| **Phase 5 Frontend (T031–T034)** | **4** | **US3, US6** |
| **Total** | **34** | |
| Post-hackathon | 5 | Future |

**MVP scope (Phase 1–3):** T001–T015 = 15 tasks = demoable core with DeepSeek + non-streaming chat + attribution + circuit breaker.

---

## Definition of Done Checklist (per task)

Every task is Done only when:
- [ ] Code written and passing
- [ ] Unit/integration tests added
- [ ] No new lint or type errors (`uv run ruff check`, `uv run mypy`)
- [ ] Constitution compliance confirmed (§3 prompt injection sanitization, §5 attribution)
- [ ] Structured JSON log entry added for observable AI calls
- [ ] Provider health state machine transitions verified

---

## Constitution Verdict: PASS

All tasks respect Clean Architecture + DDD (adapters → domain), FastAPI + Pydantic v2 (§6), OWASP prompt injection protection (§3), multi-provider abstraction (§5), and hackathon realism (§1). Post-hackathon items are explicitly labeled.

---

**Next command:** `/sp.implement` — Begin red/green/refactor loop following tasks.md in phase order. Start with Phase 1 tasks (T001–T009) for the demoable core.
