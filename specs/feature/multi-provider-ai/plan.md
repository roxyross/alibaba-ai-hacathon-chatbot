# Implementation Plan: Multi-Provider AI Abstraction

**Branch:** `feature/multi-provider-ai` | **Date:** 2026-09-02
**Spec:** `specs/feature/multi-provider-ai.md`

---

## Summary

Build a mandatory multi-provider AI abstraction layer (DeepSeek, Grok, OpenAI, Gemini) with intelligent routing, automatic failover, per-response attribution, token-usage logging, and circuit-breaker protection — all in a Clean Architecture + DDD structure compliant with the ROXY JARVIS constitution.

**Primary goal (hackathon):** A working `AIGateway` service with a FastAPI router, `pybreaker` circuit breakers, streaming SSE responses with attribution, and a live failover demonstration.

---

## Technical Context

**Language/Version:** Python 3.12+ | **Primary Dependencies:** FastAPI, Pydantic v2, httpx, pybreaker | **Storage:** Neon PostgreSQL (Prisma) + Redis | **Testing:** pytest, pytest-asyncio | **Target Platform:** Linux server (Docker) | **Project Type:** Web service (Modular Monolith backend component) | **Performance Goals:** <1.5s TTFT streaming, <300ms p95 non-streaming, 10s per-provider timeout | **Scale/Scope:** Hackathon core, 4 providers

---

## Constitution Check

*Pre-research gate — 2026-09-02*

| Section | Status | Notes |
|---|---|---|
| §1 Hackathon realism | ✅ PASS | Tight scope: abstraction + routing + failover + attribution only |
| §2 Clean Architecture + DDD | ✅ PASS | Domain layer has pure business logic; adapters depend on domain |
| §3 Security (OWASP) | ✅ PASS | API keys via env vars, prompt injection sanitization, output validation, least privilege |
| §4 Privacy-first | ✅ PASS | No plain-text prompt logging, user-scoped preferences, GDPR-design |
| §5 AI multi-provider abstraction | ✅ PASS | All 4 providers, mandatory abstraction, zero agent changes for add/remove |
| §6 TypeScript strict + FastAPI | ✅ PASS | Backend is Python 3.12 + FastAPI + Pydantic v2 |
| §9 Performance budgets | ⚠️ WARN | 10s timeout defined; per-provider latency SLO not enforced in code (deferred) |
| §10 Neon + Redis + pgvector | ✅ PASS | Compatible; AI gateway is a service layer on top |
| §14 Error handling + logging | ✅ PASS | Structured JSON logs, circuit breaker + rate limiting per provider |
| §19 Config + feature flags | ✅ PASS | Per-provider `ENABLED` env vars serve as feature flags |

**Verdict: PASS** (1 warning — per-provider latency SLO not enforced; deferred post-hackathon)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      Agents / Tools                      │
│         (never call AI providers directly)               │
└─────────────────────┬───────────────────────────────────┘
                      │ AIRequest / AIResponse
                      ▼
┌─────────────────────────────────────────────────────────┐
│               AI Gateway Service (Domain)                │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐ │
│  │   Router    │  │  Sanitizer  │  │ TokenUsageLog  │ │
│  │ (task-type  │  │ (prompt     │  │ (audit)        │ │
│  │  routing +  │  │  injection  │  │                │ │
│  │  override   │  │  protection)│  │                │ │
│  │  priority)  │  │             │  │                │ │
│  └──────┬──────┘  └─────────────┘  └────────────────┘ │
└─────────┼───────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────┐
│            Provider Abstraction Layer (Adapters)         │
│  ┌──────────────────────────────────────────────────┐   │
│  │            Circuit Breaker (pybreaker)           │   │
│  │  ┌─────────┐ ┌─────────┐ ┌────────┐ ┌────────┐ │   │
│  │  │ DeepSeek│ │  Grok   │ │ OpenAI │ │ Gemini  │ │   │
│  │  │ Adapter │ │ Adapter │ │ Adapter│ │ Adapter│ │   │
│  │  └─────────┘ └─────────┘ └────────┘ └────────┘ │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
          │
          ▼
   External AI Provider APIs (HTTPS)
```

---

## Component Breakdown

### Backend (`backend/src/app/`)

| Component | Layer | Responsibility |
|---|---|---|
| `ai_gateway/` | Domain | Core routing logic, sanitization, token logging |
| `ai_gateway/models/` | Domain | Pydantic v2 request/response models |
| `ai_gateway/services/router.py` | Domain | Routing priority, override resolution |
| `ai_gateway/services/sanitizer.py` | Domain | Prompt injection blocklist + structured wrapping |
| `adapters/` | Adapter | Provider-specific HTTP clients (httpx) |
| `adapters/deepseek.py` | Adapter | DeepSeek API adapter |
| `adapters/grok.py` | Adapter | Grok/xAI API adapter |
| `adapters/openai.py` | Adapter | OpenAI-compatible API adapter |
| `adapters/gemini.py` | Adapter | Gemini API adapter |
| `api/v1/ai.py` | Interface | FastAPI router for all /api/v1/ai/* endpoints |
| `domain/events/` | Domain | TokenUsageLogged event, ProviderCircuitOpened event |
| `seeds/providers.py` | Infrastructure | Seed provider + model records to DB |

### Frontend (`frontend/`)

| Component | Change |
|---|---|
| `components/ChatMessage.tsx` | Display provider attribution badge |
| `hooks/useChat.ts` | Handle SSE streaming + attribution metadata |
| `providers/AIProvider.tsx` | Context exposing current provider attribution |

---

## Data Model

Full schema in `data-model.md`. Key entities:

- **Provider** — name, enabled, routing_priority, api_key_env_var, base_url, timeout
- **Model** — provider_id, name, display_name, task_types, cost_per_1k_tokens
- **TokenUsageLog** — immutable, request_id + provider + model + tokens + cost + latency
- **UserPreference** — user_id → preferred_provider (nullable = auto)

---

## API / Contract Summary

Full OpenAPI 3.1 spec in `contracts/openapi.yaml`. Key endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/ai/chat` | Chat completion (streaming + non-streaming) |
| GET | `/api/v1/ai/providers` | List all providers + status (auth required) |
| PATCH | `/api/v1/ai/providers/{name}` | Enable/disable provider (operator) |
| GET | `/api/v1/ai/providers/health` | Health check (no auth) |
| GET | `/api/v1/ai/usage` | Token usage logs (auth required) |

---

## Performance & Security Considerations

**Performance:**
- Streaming: SSE with comment-line attribution headers
- Circuit breaker: `pybreaker` with 5 failures → open, 30s reset
- Connection pooling: `httpx.AsyncClient` with shared connection pool across adapters
- 10s per-provider timeout; global request timeout configurable per-call

**Security:**
- API keys read from env vars only (`os.environ.get()`); never instantiated in code
- Prompt injection: blocklist + structured prompt wrapping in `sanitizer.py`
- Output validation: Pydantic model validation on provider responses before passing to agents
- Rate limiting: per-provider rate limits via Redis token bucket (deferred to post-hackathon)

---

## Phased Delivery Plan

### Phase 1 (Day 1) — Core Infrastructure
- [ ] `AIGateway` domain service with routing logic
- [ ] Provider adapter interface + one working adapter (DeepSeek)
- [ ] `pybreaker` circuit breaker integration
- [ ] `POST /api/v1/ai/chat` (non-streaming) with attribution
- [ ] Unit tests for router + sanitizer

### Phase 2 (Day 2) — All Providers + Failover
- [ ] Grok, OpenAI, Gemini adapters
- [ ] Automatic failover between providers
- [ ] Streaming SSE with attribution
- [ ] `GET /api/v1/ai/providers/health` + `PATCH /providers/{name}`
- [ ] Integration tests for failover

### Phase 3 (Day 3) — Observability + Polish
- [ ] TokenUsageLog persistence (Prisma)
- [ ] `GET /api/v1/ai/usage` endpoint
- [ ] Structured JSON logging (request_id, provider, model, latency)
- [ ] Frontend attribution badge + SSE handling
- [ ] Docker Compose integration (service already uses env vars)
- [ ] E2E test with Playwright (failover scenario)

### Demo-Ready Core (end of Day 3):
Single `POST /api/v1/ai/chat` with DeepSeek → Grok failover, attribution badge, token log.

---

## Open Questions / Risks

| Item | Owner | Risk | Mitigation |
|---|---|---|---|
| Per-provider latency SLO not enforced | backend-specialist | Low | Deferred; add per-call timeout check post-hackathon |
| OpenAI API compatibility layer differences | backend-specialist | Medium | Use provider-specific adapters with unified interface |
| Streaming failover mid-stream not supported | backend-specialist | Low | Documented; client retries on error event |
| Redis not yet available for circuit breaker state | backend-specialist | Medium | Use in-memory state for hackathon; Redis sync post-hackathon |

---

## ADRs Required

| # | Title | Status |
|---|---|---|
| ADR-001 | Use `pybreaker` for circuit breaker per provider | Proposed |
| ADR-002 | SSE comment-line injection for streaming attribution metadata | Proposed |
| ADR-003 | Three-tier override hierarchy (operator > user > request) | Proposed |
| ADR-004 | Domain-layer prompt injection sanitization (not adapter-layer) | Proposed |
