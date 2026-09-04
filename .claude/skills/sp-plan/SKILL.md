---
name: sp-plan
description: Execute the implementation planning workflow for a ROXY JARVIS feature — generates plan.md and design artifacts from the spec (spec-kit workflow). Use after a spec is ready, or when the user invokes /sp.plan.
---

# Spec-kit: Plan

Run the canonical `/sp.plan` workflow to produce the technical plan and design artifacts for the active feature.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` (React + Vite + TS) and `backend/` (FastAPI, Python ≥ 3.12); governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Run `.specify/scripts/powershell/*.ps1` from the repo root (the workflow starts with `setup-plan.ps1 -Json`).

## Procedure

1. Read the canonical workflow `.claude/commands/sp.plan.md` at the repo root and execute it faithfully, passing any user input as `$ARGUMENTS`.
2. It parses `FEATURE_SPEC`, `IMPL_PLAN`, and `SPECS_DIR` from `setup-plan.ps1 -Json`, loads `.specify/templates/plan-template.md`, and generates plan.md plus design artifacts (research, data model, contracts) as needed.

## Constitution constraints the plan MUST satisfy

- §2: Clean Architecture + DDD, modular monolith, 10-layer stack with downward-only dependencies (§2.1), contract-first OpenAPI (§2.2); note which decisions need ADRs.
- §1.3 / §5: AI features go through the multi-provider abstraction (DeepSeek, Grok, OpenAI/ChatGPT, Gemini primary; Ollama/vLLM/Groq secondary) — no vendor lock-in; attribution, routing transparency, autonomy limits, and guardrails planned in.
- §6: TypeScript strict (§6.1); Python 3.12+ FastAPI + Pydantic v2 (§6.2).
- §9.1: performance budgets — TTFT < 1.5 s streaming, LCP < 2.5 s, API p95 < 300 ms (non-AI), vector search p95 < 200 ms; bundle < 300 KB gz.
- §9.2: horizontal scalability — Neon PostgreSQL + PgBouncer pooling, Redis cache/queue, pgvector/Qdrant, stateless FastAPI workers.
- §11: observability plan — structured JSON logs, trace_id propagation, `/metrics`, `/health/live` + `/health/ready`, error taxonomy + circuit breakers.
- §14.3: environment variables via `.env.example` (twelve-factor); feature flags for incomplete post-hackathon features.
- §1: hackathon realism — plan phases so a demonstrable core ships in 3-4 days; defer advanced layers explicitly.

## Stack (ratified — Constitution v2.0.0 + ADR-001)

The plan targets the ratified stack: **Vite 5 + React 18 + TypeScript SPA** on the frontend (§18/§9.2/§15.1) and **Neon PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic** on the backend (§18, the in-code T027 decision), with persistence behind a clean repository / Unit-of-Work boundary so the ORM stays swappable. These are no longer deviations. The one open toolchain item: §14.1 mandates **pnpm/uv**, but the tree still uses an npm `package-lock.json` and has no committed `uv.lock` — if the plan touches dependency setup, include the npm→pnpm switch + `uv.lock` as an explicit task rather than assuming it.

Next phases: /sp-tasks (task breakdown) or /sp-checklist (domain checklist).
