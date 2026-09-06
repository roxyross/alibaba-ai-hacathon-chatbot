# ADR-003: Multi-Agent Runtime as a Separate Top-Level Python Package

> **Scope**: Where the multi-agent runtime (the system that loads `.claude/agents/*.md` and `.claude/skills/*/SKILL.md`, classifies user queries, and dispatches them to specialist agents) lives in the monorepo. This is a platform-level architectural decision, not a feature-internal choice.

- **Status:** Accepted
- **Date:** 2026-09-05
- **Feature:** Coordinator + Specialist Agents (see `specs/feature/coordinator-specialist-agents.md`)
- **Context:** ROXY JARVIS is shipping a user-facing multi-agent runtime alongside the existing AI gateway in `backend/`. The runtime has a fundamentally different shape from the gateway: stateful sessions, a scheduler, a browser driver, voice WebSockets, and a registry that is loaded from `.md` files at startup. Where this runtime lives in the repo is a long-term decision that affects deployment, scaling, hiring, and the boundary between the AI gateway and the agent layer.

<!-- Significance checklist — ALL true:
     1) Impact: long-term consequence for architecture, deployment, and team boundaries. YES
     2) Alternatives: multiple viable options with real tradeoffs. YES
     3) Scope: cross-cutting, not an isolated detail. YES
     → Justified as an ADR (not a PHR note). -->

## Current state (evidence)

- The existing `backend/` (FastAPI + SQLAlchemy 2.0 async on Neon Postgres) is the **AI gateway**: it forwards chat requests to multi-provider LLMs, logs token usage, and applies circuit breakers. It is stateless request/response. ADR-001 ratified this stack in 2026-09-03.
- The existing `frontend/` is the chat UI: Vite 5 + React 18 + TypeScript SPA. It talks to the gateway at `/api/v1/ai/chat` and to the auth endpoints at `/api/v1/auth/*`.
- The user has approved writing 11 runtime agent definitions (`.claude/agents/{coordinator,research,files,coding,planner,automation,study,voice,security-privacy,memory-curator,browser}.md`) and 19 runtime skill definitions (`.claude/skills/*/SKILL.md`). These are role contracts and skill contracts — they do not implement anything. A runtime is needed to load them and execute them.
- The runtime must read `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` at startup, build a registry, classify user queries, and dispatch them. The user is the developer, the user is the operator; the runtime is a long-lived service.

## Decision

**Adopted:** Add the multi-agent runtime as a **new top-level Python package** `runtime/`, sibling to `backend/` and `frontend/`. Own `pyproject.toml`, own `uv`-managed venv, own tests, own Dockerfile. It binds to `:8001` and is reached from the frontend via a Vite proxy entry `/api/v1/runtime/*` → `http://localhost:8001`.

The runtime is a thin orchestration layer:

- It **does not import** from `backend/src/app/**` internals.
- It **calls** the existing AI gateway at `/api/v1/ai/chat` for LLM inference (preserving Constitution §1.3 — no vendor lock-in).
- It **validates** magic-link JWTs issued by `backend/` (shared secret via `.env`); it does not duplicate the magic-link issuance logic.
- It **shares** the Neon Postgres database with `backend/` (new tables: `memory_entries`, `scheduled_jobs`, `audit_log`); it does not modify any existing `backend/` tables.
- It **loads** agent and skill definitions from `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` at startup. Adding a new agent or skill is a `.md` file change, not a Python change.

The deployment topology is two Python services side-by-side:

```
frontend  (Vite SPA, :5173)
  │
  ├─ /api/v1/auth/*   ─►  backend  (AI gateway, :8000)
  ├─ /api/v1/ai/*     ─►  backend
  └─ /api/v1/runtime/* ─►  runtime (multi-agent runtime, :8001)  ◄── NEW
                                  │
                                  └─ /api/v1/ai/chat  ─►  backend
```

## Consequences

### Positive

- **Clean separation of concerns.** The AI gateway and the agent runtime have different lifecycles. The gateway is stateless and request/response; the runtime has long-lived state (sessions, scheduler tick, browser driver, voice WebSocket). Coupling them in one process would force them to scale together and share failures.
- **Independent scaling.** The runtime can be deployed and scaled independently of the gateway. PR 2 (Coordinator + Research only) is a small service; PR 4 (full system with browser + voice) is a larger one. Different scaling profiles are easy to express.
- **Independent tech stack evolution.** The runtime is free to adopt new dependencies (Playwright, Deepgram, ElevenLabs, APScheduler) without bloating the gateway's deployable. The gateway stays lean and stable.
- **Cleaner onboarding.** A new contributor working on the runtime does not need to understand the AI gateway's multi-provider routing internals; they read `runtime/src/runtime/agents/loader.py` and start. A contributor working on the gateway is unaffected by the runtime's churn.
- **Constitution compliance on day 1.** New package uses `uv` from the start (Constitution §14.1). The existing `backend/` deviation (no committed `uv.lock`) is unchanged but is a separate, tracked follow-up.
- **Test isolation.** Runtime tests can mock the gateway at the HTTP boundary without touching gateway internals; gateway tests don't need to know the runtime exists.

### Negative

- **Operational cost of a third deployable.** Two Python services, two Dockerfiles, two CI stages, two log streams, two health endpoints. For a hackathon project, this is more surface area to maintain.
- **Cross-service auth is more complex.** The runtime and the gateway share a JWT secret; rotation requires care. (Mitigation: read the secret from a single env var loaded by both services.)
- **Database table ownership boundaries are now explicit.** `memory_entries`, `scheduled_jobs`, `audit_log` belong to the runtime; existing tables belong to the gateway. A migration that touches a shared concept (e.g. user identity) needs both services to coordinate.
- **The "smallest possible change" rule (Constitution §1.1) is bent.** Mounting the runtime as a sub-app of the existing FastAPI app would be smaller. The user explicitly chose not to do this; this ADR records why.

## Alternatives Considered

### Alternative A — Mount the runtime as a sub-app of the existing `backend/` FastAPI app

Add `backend/src/app/runtime/` and a `runtime_app = FastAPI()` that the main `app.mount("/api/v1/runtime", runtime_app)` calls. One process, one port, one Docker image.

- **Why rejected:** The runtime has a different lifecycle from the gateway. The scheduler ticks every minute; the browser driver holds long-lived Playwright sessions; the voice WebSocket holds connections. Running these inside the gateway's request/response process means they share a worker pool with LLM-bound requests — a single hung voice session can starve chat traffic. The user explicitly chose to keep these concerns separate in the design discussion. Recorded here for the record so a future contributor who proposes this knows it was considered.

### Alternative B — Two services in one `backend/src/app/` package

Same as A, but split into two `FastAPI()` apps that share the `backend/` package. Reuses the existing venv and config but runs as two processes.

- **Why rejected:** Marginal improvement over A (process isolation) but still couples the runtime to the gateway's dependency tree. Adding Playwright + Deepgram + APScheduler to `backend/pyproject.toml` bloats the gateway's install size and slows its cold start. The runtime's distinct dependency profile is a stronger argument for separation than its distinct lifecycle.

### Alternative C — Standalone microservice with its own API gateway

Spin up a third API gateway (e.g. Kong, an nginx sidecar) in front of `backend` and `runtime`. Enterprise-grade.

- **Why rejected:** Out of proportion for a hackathon. The frontend's Vite proxy already gives us routing at the dev tier. Revisit post-hackathon if traffic patterns justify a real gateway.

## References

- Feature Spec: [`specs/001-runtime-orchestrator/spec.md`](../../specs/001-runtime-orchestrator/spec.md)
- Implementation Plan: [`specs/001-runtime-orchestrator/plan.md`](../../specs/001-runtime-orchestrator/plan.md)
- Related ADRs:
  - [ADR-001](./ADR-001-implementation-stack-reconciliation.md) — ratifies Vite + SQLAlchemy 2.0 async as the platform stack
  - [ADR-002](./ADR-002-oauth-identity-provider-integration.md) — Google OAuth integration in `backend/`
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md) — especially §1.1 (incremental delivery), §1.3 (no vendor lock-in), §2 (clean architecture), §6.2 (Python 3.12+ + FastAPI + Pydantic v2), §14.1 (uv)
