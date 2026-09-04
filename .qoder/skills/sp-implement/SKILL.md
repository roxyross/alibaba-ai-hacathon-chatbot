---
name: sp-implement
description: Execute the implementation plan by processing and completing all tasks in the current ROXY JARVIS feature's tasks.md (spec-kit workflow). Use when the user wants to start building, or invokes /sp.implement.
---

# Spec-kit: Implement

Run the canonical `/sp.implement` workflow to execute the feature's tasks.md.

## Environment

- The repo root is a monorepo and the single git repository. Code changes go in `frontend/` (React + Vite + TS) and `backend/` (FastAPI, Python ≥ 3.12); spec/task artifacts stay in `specs/`.
- Run `.specify/scripts/powershell/*.ps1` from the repo root (the workflow starts with `check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks`).
- Package managers (§14.1): `pnpm` for `frontend/`, `uv` for `backend/`.

## Procedure

1. Read the canonical workflow `.claude/commands/sp.implement.md` at the repo root and execute it faithfully.
2. It loads tasks.md and available design artifacts, checks checklist status, and executes tasks in phases, marking progress in tasks.md.

## Implementation rules (Constitution)

- §6.1 frontend: TypeScript strict, no `any`, explicit return types, `@/` absolute imports, feature-first folders. The frontend is a **Vite 5 + React 18 SPA** — this is the §18-ratified stack (Constitution v2.0.0 + ADR-001), so build in it directly and do not import Next.js-only APIs (RSC/Server Actions) that don't exist here.
- §6.2 backend: Python 3.12+, FastAPI, Pydantic v2, type hints everywhere, structlog (no `print`), async-first, no bare `except`.
- §1.3 / §5: all AI calls go through the multi-provider abstraction; never call a provider SDK directly from agent or tool code.
- §3: sanitize AI inputs, validate outputs, allow-list tool calls; sandbox all tool execution; honor T1/T2/T3 approval tiers; secrets only via environment variables.
- §11: structured JSON logs with trace_id, metrics, health checks, and the error taxonomy (`AUTH_ERROR`, `VALIDATION_ERROR`, `PROVIDER_ERROR`, `TOOL_ERROR`, `INTERNAL_ERROR`) with circuit breakers.
- §7: unit tests with the domain logic; regression test for every bug fix; run tests + lint + typecheck (`pnpm lint`/`pnpm typecheck`, `uv run pytest`, ruff/mypy) before marking a task complete; meet §7.1 coverage.
- §16 Definition of Done per task where applicable: docs updated in the same PR (§8.2), no new lint/type errors, light/dark + i18n (en/ur/ar, RTL) checked, accessibility (§10), observability in place, demonstrable live.
- §1: incremental delivery — commit-ready, demonstrable state after every task; simplest solution that satisfies the milestone.

## Guardrails

- Never implement tasks labeled post-hackathon/deferred (§18) unless the user explicitly amends scope.
- Report per task: what changed, tests run with actual results, and anything deferred (with the reason) or any constitution deviation encountered.
