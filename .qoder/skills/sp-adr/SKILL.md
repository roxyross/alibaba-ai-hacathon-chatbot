---
name: sp-adr
description: Review planning artifacts for architecturally significant decisions and create Architecture Decision Records for ROXY JARVIS (spec-kit workflow, Constitution §2). Use after /sp-plan, or when the user invokes /sp.adr.
---

# Spec-kit: ADR

Run the canonical `/sp.adr` workflow to document architecturally significant decisions as ADRs.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` and `backend/`; governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Run `.specify/scripts/powershell/*.ps1` from the repo root.
- ADR template: `.specify/templates/adr-template.md`. ADRs live under `history/adr/` (create the directory if it does not yet exist).

## Procedure

1. Read the canonical workflow `.claude/commands/sp.adr.md` at the repo root and execute it faithfully.
2. Flow: load planning context via `check-prerequisites.ps1 -Json` (plan.md required) → extract decision CLUSTERS → check existing ADRs for coverage/conflicts → apply the significance test → create ADRs with all placeholders filled → report.

## Rules

- Cluster related decisions (frontend stack = 1 ADR; frontend vs backend = 2 ADRs). Never one ADR per library.
- Significance test — all three must pass: impacts how engineers write/structure software; notable tradeoffs or alternatives; will be questioned later.
- Every ADR must cover what Constitution §2 / §8.1 requires: Rationale, Advantages, Trade-offs, Alternatives considered, and impact on Scalability / Security / Performance / Maintainability.
- The implementation-stack decision is already captured in `history/adr/ADR-001-implementation-stack-reconciliation.md` and ratified by Constitution v2.0.0 (Vite 5 + React 18 SPA; Neon PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic). Check new plans against ADR-001 for conflicts rather than re-opening it; the remaining npm→pnpm / `uv.lock` toolchain switch is a follow-up task, not a new ADR.
- Flag conflicts with existing ADRs; never silently overwrite.

Report: created ADR ids/titles, referenced existing ADRs, conflicts detected, and next steps.
