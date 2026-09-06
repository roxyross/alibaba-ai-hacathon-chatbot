# Implementation Plan: Multi-Agent Runtime

**Branch:** `001-runtime-orchestrator` | **Date:** 2026-09-05 | **Spec:** [`./spec.md`](./spec.md)
**ADR:** [`../../history/adr/ADR-003-multi-agent-runtime.md`](../../history/adr/ADR-003-multi-agent-runtime.md)

---

## Summary

Build a user-facing multi-agent runtime as a new top-level Python package `runtime/`. The runtime loads agent and skill definitions from `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` at startup, classifies incoming user queries through a Coordinator, and dispatches them to the right specialist. Eleven specialists and nineteen skills are delivered in three implementation PRs (PR 2/3/4), each independently demonstrable per Constitution §1.1.

The runtime sits alongside the existing AI gateway in `backend/` (which it calls for LLM inference and auth) and the chat UI in `frontend/` (which it adds a second conversation path to). It does not replace either.

**Primary goal:** A working Coordinator that routes a user query to a specialist and returns a labelled response, end-to-end. Hackathon-deliverable by PR 2; full system by PR 4.

---

## Technical Context

- **Language / Version:** Python 3.12+ (per Constitution §6.2)
- **Primary Dependencies:** FastAPI, Pydantic v2, structlog, SQLAlchemy 2.0 async, httpx, APScheduler, PyJWT (shared with `backend/`), python-frontmatter (for parsing `.md` frontmatter), pytest + pytest-asyncio + respx
- **Package Manager:** `uv` (per Constitution §14.1) — a `uv.lock` will be committed in PR 2
- **Storage:** Neon PostgreSQL via SQLAlchemy 2.0 async (same DB as `backend/`; new tables: `memory_entries`, `scheduled_jobs`, `audit_log`). Optional Redis if a job queue becomes necessary (deferred).
- **Testing:** pytest + pytest-asyncio for unit and integration; respx for httpx mocking; Playwright (Python binding) for browser skill tests in PR 4
- **Target Platform:** Linux server (Docker); local dev on Windows + POSIX via `uv run`
- **Project Type:** New top-level Python package `runtime/`, sibling to `backend/` and `frontend/`
- **Performance Goals:**
  - p95 first-token < 1.5s for text-only specialists (per Constitution §9.1)
  - p95 Coordinator handoff < 200ms (classification + registry lookup)
  - p95 sensitive-skill confirmation round-trip < 1s
  - Per-specialist timeout: 30s
- **Constraints:**
  - No new infrastructure beyond the existing Neon DB and (optional) Redis
  - The runtime does not import from `backend/src/app/**` internals; it talks to `backend/` over HTTP at `/api/v1/ai/chat` and `/api/v1/auth/me`
  - All providers go through the existing AI gateway (Constitution §1.3 — no vendor lock-in)
  - Agent and skill definitions are read from `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` at startup; no Python changes needed to add a new agent or skill
- **Scale / Scope:** Matches the existing auth-anchored user model (one user → one session → many turns). 11 specialists + 19 skills across 3 PRs.

---

## Constitution Check

*Pre-research gate — 2026-09-05*

| Section | Status | Notes |
|---|---|---|
| §1.1 Incremental delivery | ✅ PASS | The spec is delivered in 3 PRs (PR 2/3/4), each independently demonstrable. PR 2 ships a working Coordinator + Research Agent. |
| §1.1 Simplicity first | ✅ PASS | v1 classifier is keyword + description similarity, not an LLM call. Real classification is a v2 follow-up. |
| §1.3 No vendor lock-in | ✅ PASS | The runtime calls the existing `backend/` AI gateway at `/api/v1/ai/chat`. It does not import provider SDKs. |
| §1.4 Feature-first organization | ✅ PASS | `runtime/src/runtime/<feature>/` layout: `coordinator/`, `agents/`, `skills/`, `security/`, `automation/`, `memory/`, `voice/`, `browser/`, `email/`, `files/`, `study/`, `api/`. |
| §2 Clean Architecture + DDD | ✅ PASS | Each feature follows `domain/`, `application/`, `infrastructure/`, `interface/`. No cross-feature internals imports. |
| §3 Security (OWASP) | ✅ PASS | API keys via env vars. The sensitive-skill gate is mandatory. CSP/CORS handled by the existing gateway. |
| §4 Privacy-first | ✅ PASS | Memory entries are user-scoped. The Memory Curator is internal; user cannot trigger it. Soft-delete window for reversibility. |
| §5 AI safety | ✅ PASS | The Security/Privacy Agent produces a `block` verdict that is not bypassable without explicit user override. |
| §6.2 Python 3.12+ + FastAPI + Pydantic v2 | ✅ PASS | Match the existing `backend/` stack. |
| §9.1 Performance budgets | ✅ PASS | First-token < 1.5s, handoff < 200ms — both measured in integration tests. |
| §9.2 Horizontal scalability | ✅ PASS | Stateless FastAPI workers; sessions stored in DB; scheduler state in DB. |
| §11 Observability | ✅ PASS | structlog with the existing schema (timestamp, level, service, trace_id, event, duration_ms). `/health/live` + `/health/ready` on the runtime service. |
| §12 API versioning | ✅ PASS | New routes under `/api/v1/runtime/...`; same versioning scheme as the gateway. |
| §14.1 Package manager (uv) | ⚠️ ACTION | `uv` not yet in use for `backend/`; the existing `pip + venv` setup is a known deviation. For `runtime/`, we will use `uv` from the start and commit `uv.lock`. |
| §15.1 CI | ✅ PASS | The runtime's test suite runs in the existing CI pipeline; one new stage for `runtime/`. |
| §18 Hackathon must-ship | ✅ PASS | PR 2 is the hackathon-deliverable: working Coordinator + Research, demoable end-to-end. PR 3 and PR 4 are post-hackathon. |

**Verdict: PASS** (1 action — use `uv` for the new `runtime/` package from day 1, to comply with §14.1 ahead of the existing `backend/` follow-up).

---

## Project Structure

### Documentation (this feature)

```text
specs/001-runtime-orchestrator/
├── plan.md              # This file
├── research.md          # Phase 0 output (provider choices, ADR candidates) — written in PR 2
├── data-model.md        # memory_entries, scheduled_jobs, audit_log — written in PR 2
├── quickstart.md        # How to run the runtime locally — written in PR 2
├── contracts/           # API contract (OpenAPI 3.1 fragment for /api/v1/runtime/...) — written in PR 2
└── tasks.md             # Per-PR task breakdown — written in PR 2 (and updated in PR 3, PR 4)
```

### Source Code

A new top-level Python package, sibling to `backend/` and `frontend/`:

```text
runtime/
├── pyproject.toml               # uv-managed; depends on backend/ via PyJWT + httpx only
├── uv.lock                      # committed
├── README.md
├── .env.example
├── src/
│   └── runtime/
│       ├── __init__.py
│       ├── main.py              # FastAPI app factory; binds :8001
│       ├── config.py            # Pydantic Settings; reads .env
│       ├── logging.py           # structlog config (mirrors backend/src/app/logging.py)
│       ├── domain/              # Cross-feature domain types
│       │   ├── agent.py         # AgentDef dataclass; AgentSlug enum
│       │   ├── skill.py         # SkillDef dataclass; Sensitivity enum
│       │   ├── session.py       # Session, Turn dataclasses
│       │   └── events.py        # AgentHandoffEvent, SkillInvokedEvent, etc.
│       ├── agents/
│       │   ├── loader.py        # parse .claude/agents/*.md → AgentDef
│       │   ├── registry.py      # discover + lookup; mark internal: true as not-routable
│       │   └── executor.py      # invoke a model with the agent's system prompt
│       ├── skills/
│       │   ├── loader.py        # parse .claude/skills/*/SKILL.md → SkillDef
│       │   ├── registry.py      # discover + lookup; mark sensitive + internal
│       │   └── executor.py      # dispatch by slug to the registered implementation
│       ├── coordinator/
│       │   ├── classifier.py    # v1: keyword + description-similarity matching
│       │   ├── router.py        # take user query + agent slug, hand off
│       │   └── timeout.py       # 30s per-specialist budget
│       ├── security/
│       │   ├── gate.py          # Security/Privacy Agent's verdict logic
│       │   └── confirm.py       # sensitive-skill confirmation prompt
│       ├── automation/
│       │   └── scheduler.py     # APScheduler; polls scheduled_jobs table
│       ├── memory/
│       │   ├── store.py         # wraps store_memory + retrieve_memory
│       │   └── curator.py       # nightly pass; calls memory_summarize_prune
│       ├── email/
│       │   └── gmail.py         # email_draft + email_send; gated
│       ├── calendar/
│       │   └── google.py        # calendar_read; Google Calendar OAuth
│       ├── files/
│       │   └── rag.py           # document_rag_query; pgvector or in-memory embeddings
│       ├── browser/
│       │   └── driver.py        # Playwright; browser_navigate + browser_fill_form
│       ├── voice/
│       │   └── session.py       # WebSocket; STT/TTS streaming; turn-taking
│       ├── api/
│       │   ├── chat.py          # POST /api/v1/runtime/chat
│       │   ├── voice.py         # WebSocket /api/v1/runtime/voice
│       │   ├── scheduler.py     # GET/POST/DELETE /api/v1/runtime/jobs
│       │   └── health.py        # /health/live, /health/ready
│       └── infrastructure/
│           ├── db.py            # SQLAlchemy async engine; shares connection string with backend/
│           ├── gateway_client.py # httpx client for backend /api/v1/ai/chat + /api/v1/auth/me
│           └── auth.py          # extract_user_from_jwt (decodes the magic-link JWT)
└── tests/
    ├── unit/
    │   ├── agents/
    │   │   ├── test_loader.py
    │   │   └── test_registry.py
    │   ├── skills/
    │   │   ├── test_loader.py
    │   │   └── test_executor.py
    │   └── coordinator/
    │       ├── test_classifier.py
    │       └── test_router.py
    ├── integration/
    │   ├── test_vertical_slice.py   # POST /api/v1/runtime/chat end-to-end with a real DB
    │   ├── test_sensitive_gate.py   # confirms email_send / browser_fill_form gate
    │   └── test_scheduler.py        # job fires, confirm_on_fire triggers
    └── contract/
        └── test_openapi_matches.py  # locks /api/v1/runtime/... shape
```

**Structure Decision:** A new top-level Python package, **not** a module under `backend/`. The reasoning is in `history/adr/ADR-003-multi-agent-runtime.md`: the runtime has a different lifecycle (stateful sessions, scheduler, browser driver, voice WebSockets) from the AI gateway, and adding a third top-level Python project to the monorepo is a smaller operational cost than coupling two distinct concerns in one process.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Frontend (existing Vite + React SPA)              │
│   Existing /api/v1/ai/chat unchanged; adds /api/v1/runtime/chat    │
└────────────┬───────────────────────────────────┬────────────────────┘
             │ /api/v1/ai/chat (LLM inference)   │ /api/v1/runtime/*
             │ /api/v1/auth/me (JWT validation)  │ (routing, scheduler, voice WS)
             │                                   │
             ▼                                   ▼
┌─────────────────────────────┐    ┌────────────────────────────────────┐
│   backend/  (AI gateway)     │    │   runtime/  (new)                  │
│                             │    │                                    │
│   - Multi-provider routing  │    │   ┌──────────────────────────┐    │
│   - Token usage logging     │    │   │     Coordinator          │    │
│   - Auth (magic link/OAuth) │    │   │  - classifier            │    │
│   - Existing /api/v1/ai/*   │    │   │  - router                │    │
│                             │    │   │  - timeout (30s)         │    │
│   The runtime does NOT      │    │   └──────────┬───────────────┘    │
│   import from backend/.     │    │              │                    │
│   It calls backend/ over    │    │   ┌──────────▼───────────────┐    │
│   HTTP.                     │    │   │  Agent Registry          │    │
└─────────────────────────────┘    │   │   (loads .md at startup) │    │
                                   │   └──────────┬───────────────┘    │
                                   │              │                    │
                                   │   ┌──────────▼───────────────┐    │
                                   │   │  Skill Registry          │    │
                                   │   │   (loads SKILL.md)        │    │
                                   │   └──────────┬───────────────┘    │
                                   │              │                    │
                                   │   ┌──────────▼───────────────┐    │
                                   │   │  Security Gate           │    │
                                   │   │   (sensitive: true)      │    │
                                   │   └──────────────────────────┘    │
                                   │                                    │
                                   │   ┌──────────────────────────┐    │
                                   │   │  Scheduler (APScheduler) │◄───┼─── daily tick
                                   │   │   (PR 3+)                │    │
                                   │   └──────────────────────────┘    │
                                   │                                    │
                                   │   ┌──────────────────────────┐    │
                                   │   │  Memory Curator (nightly)│    │
                                   │   │   (PR 4)                 │    │
                                   │   └──────────────────────────┘    │
                                   └────────────────────────────────────┘
```

---

## Component Breakdown

### Coordinator (`runtime/src/runtime/coordinator/`)

- **`classifier.py`**: Takes a user query, returns the best-matching agent slug. v1: keyword match + cosine similarity over the agent's `description` field (computed once at startup). v2: LLM-based classification. The classifier never invents an agent — it returns one of the registered slugs or signals "uncertain."
- **`router.py`**: Takes a query + the chosen agent slug, hands off to the agent's executor. If the executor returns a sensitive action (i.e. the agent wants to invoke a `sensitive: true` skill), the router pauses and calls the Security gate before invoking the skill.
- **`timeout.py`**: 30-second per-specialist budget. Wraps the agent's executor; on timeout, returns a "specialist is taking too long" message + alternatives.

### Agents (`runtime/src/runtime/agents/`)

- **`loader.py`**: Parses `.claude/agents/*.md` using `python-frontmatter`. Extracts the YAML frontmatter (name, description, tools, sensitive, internal) and the body (Markdown after the frontmatter). Returns an `AgentDef` dataclass.
- **`registry.py`**: Discovers all `.claude/agents/*.md` at startup. Builds a `dict[slug, AgentDef]`. Excludes agents marked `internal: true` from the routable set (they exist but the Coordinator will never send user queries to them).
- **`executor.py`**: Invokes a model with the agent's system prompt + the user query. v1: calls `backend/`'s `/api/v1/ai/chat` with the agent's body as the system message. v2: per-agent model selection (some agents may prefer a faster/cheaper model).

### Skills (`runtime/src/runtime/skills/`)

- **`loader.py`**: Parses `.claude/skills/*/SKILL.md`. Same shape as the agent loader.
- **`registry.py`**: Discovers + looks up. Marks skills as `sensitive: true` or `internal: true`. Internal skills are only callable by their corresponding internal agent.
- **`executor.py`**: Dispatches by slug to the registered implementation. The implementation is a Python function (e.g. `def web_search(query: str, num_results: int = 10) -> list[SearchResult]`) that is registered in a code map at startup. Skills that don't have a registered implementation (yet) return a clear "not yet implemented" error rather than a 500.

### Security (`runtime/src/runtime/security/`)

- **`gate.py`**: The Security/Privacy Agent's verdict logic. Takes a proposed action, returns `{verdict: clear|caution|block, warning: str, blocking: bool}`. v1: a checklist-based heuristic (e.g. "is the recipient new?", "is the amount > 0?", "is the action irreversible?"). v2: invoke the agent as a sub-agent.
- **`confirm.py`**: Surfaces the proposed action to the user in plain language. Sensitive skills call this *before* invoking the executor; the executor refuses to run if the confirmation is missing.

### Automation (`runtime/src/runtime/automation/`)

- **`scheduler.py`** (PR 3+): APScheduler with a SQLAlchemy job store. Polls the `scheduled_jobs` table; fires due jobs by calling the registered agent + skill chain. Jobs with `confirm_on_fire: true` go through the Security gate at each fire.

### Memory (`runtime/src/runtime/memory/`)

- **`store.py`**: Wraps the `store_memory` and `retrieve_memory` skills with the actual storage backend (Neon DB; new `memory_entries` table).
- **`curator.py`** (PR 4): Runs on a daily cron. Applies the pruning policy from `.claude/agents/memory-curator.md`. Calls `memory_summarize_prune` with the batch of decisions.

---

## API Contract (PR 2 surface; PR 3/4 extend)

```
POST /api/v1/runtime/chat
  Body: { "message": "what's the weather in Tokyo" }
  Auth: Bearer <magic-link JWT>
  Response: { "agent_slug": "research", "response": "...",
              "citations": [...], "next_actions": [...] }

GET  /api/v1/runtime/agents
  Auth: Bearer <JWT>
  Response: { "agents": [{slug, description, routable, sensitive}, ...] }

GET  /api/v1/runtime/skills
  Auth: Bearer <JWT>
  Response: { "skills": [{slug, description, sensitive, internal}, ...] }

GET  /health/live
  Response: { "status": "ok" }

GET  /health/ready
  Response: { "status": "ok", "agents_loaded": 11, "skills_loaded": 19 }
```

PR 3 adds: `POST /api/v1/runtime/memory` (store), `GET /api/v1/runtime/memory?q=...` (retrieve).
PR 4 adds: `GET/POST/DELETE /api/v1/runtime/jobs`, `WebSocket /api/v1/runtime/voice`, `POST /api/v1/runtime/browser/run`.

---

## Cross-Cutting Concerns

- **Auth.** The runtime decodes the magic-link JWT issued by `backend/`. It does not duplicate the magic-link issuance logic; it only validates. Shared secret via `.env`.
- **Configuration.** Pydantic Settings. Reads `RUNTIME_*` env vars; reads `BACKEND_*` for the gateway URL. The runtime's own `.env` is committed as `.env.example` only.
- **Observability.** structlog, same schema as `backend/` (per Constitution §11). `/health/live` and `/health/ready` on the runtime service. `trace_id` propagated via the `X-Trace-ID` header.
- **Error handling.** Custom exception classes per module; the §11.5 error taxonomy (`AUTH_ERROR`, `VALIDATION_ERROR`, `PROVIDER_ERROR`, `TOOL_ERROR`, `INTERNAL_ERROR`) is reused.

---

## Open Decisions (deferred to ADRs in PR 2/3/4)

- **ADR-003 (this PR):** Runtime as a separate top-level package, not a module under `backend/`. **(Drafted in this PR.)**
- **ADR-003 (PR 3):** Web search provider for the `web_search` skill. Candidates: Brave Search API (free tier 2000 queries/month, privacy-friendly), SerpAPI (paid, more features), Google Programmable Search (paid, requires Custom Search Engine). Brave is the recommended default.
- **ADR-004 (PR 4):** STT/TTS provider. Candidates: Deepgram (STT, $0.0043/min), OpenAI Whisper (STT, $0.006/min), ElevenLabs (TTS, $5/month starter), OpenAI TTS ($15/1M chars). Decision deferred to PR 4 so we have up-to-date pricing and feature comparison.
- **ADR-005 (PR 4):** Browser driver. Playwright is the recommended default; the alternative is Selenium (mature, larger ecosystem, more brittle). Not material enough for an ADR unless the user objects.

---

## Verification

End-to-end checks at each PR boundary:

- **After PR 2:** `cd runtime && uv sync && uv run python -m runtime.main` brings up the service on `:8001`. `POST /api/v1/runtime/chat` with a research-style query returns a response labelled "Research Agent." `pytest runtime/tests/integration/test_vertical_slice.py` passes.
- **After PR 3:** Five of eleven agents are real. A user can ask a code question, recall a memory, check a calendar, summarize a document. `pytest runtime/tests/integration/` passes.
- **After PR 4:** All eleven agents and nineteen skills are real. The sensitive-skill gate is enforced. The scheduler fires a job. The memory curator runs nightly. `pytest runtime/tests/` is green.

---

## Out of Scope for This Plan

- **Modifying the existing AI gateway's chat endpoint.** The runtime adds a second conversation path; it does not replace `/api/v1/ai/chat`.
- **Frontend changes beyond a `/api/v1/runtime/...` proxy entry.** The chat UI keeps talking to `/api/v1/ai/chat`; the runtime adds a second tab or a routing toggle in the UI (separate user request).
- **Multi-user shared sessions.** Sessions are per-user; multi-user rooms are deferred.
- **Modifying the existing 8 project-internal agents or 15 spec-driven skills.** Untouched.

---

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| 3rd Python project in the monorepo (`backend/`, `runtime/`, both with own venv) | The runtime has a different lifecycle from the AI gateway: stateful sessions, scheduler, browser driver, voice WebSockets. Coupling them in one process would mean scaling them together and sharing failures. | Mounting the runtime as a sub-app of the existing FastAPI app shares lifecycle, config, and scaling. The user's first design question confirmed this is unwanted — the runtime is its own concern. |
