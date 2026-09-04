---
name: sp-analyze
description: Non-destructive cross-artifact consistency and quality analysis across spec.md, plan.md, and tasks.md for a ROXY JARVIS feature (spec-kit workflow). Use after /sp-tasks and before implementation, or when the user invokes /sp.analyze.
---

# Spec-kit: Analyze

Run the canonical `/sp.analyze` workflow to find inconsistencies, duplications, ambiguities, and underspecified items across the three core artifacts before implementation.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` and `backend/`; governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Run `.specify/scripts/powershell/*.ps1` from the repo root.

## Procedure

1. Read the canonical workflow `.claude/commands/sp.analyze.md` at the repo root and execute it faithfully.
2. **STRICTLY READ-ONLY** — it analyzes spec.md, plan.md, and tasks.md and reports findings; it must not modify any artifact.
3. Only run it after /sp-tasks has produced a complete tasks.md.

## Extra constitution lens

While analyzing, also flag:
- Missing ADR callouts for non-trivial decisions (§2, §8.1).
- Tasks that violate the 10-layer dependency rule or feature-first organization (§1.4, §2.1).
- Missing test/doc/a11y/observability/i18n tasks required by the Definition of Done (§16), or missing test tasks per §7.3.
- Any artifact drift into the constitution's explicitly-deferred feature list (§18 Hackathon Scope).
- AI features not routed through the multi-provider abstraction (§1.3, §5).
- Unreconciled toolchain deviations that the plan did not explicitly resolve (npm `package-lock.json` vs the §14.1 pnpm mandate; no committed `uv.lock`). The frontend/backend stack itself (Vite + React SPA; SQLAlchemy 2.0 async + Alembic) is ratified by Constitution v2.0.0 + ADR-001 and is NOT a deviation.

Report findings grouped by severity (critical / warning / info) with the artifact and section each refers to, then recommend whether to proceed to /sp-implement or loop back to /sp-plan or /sp-tasks.
