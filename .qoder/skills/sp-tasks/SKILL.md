---
name: sp-tasks
description: Generate an actionable, dependency-ordered tasks.md for the current ROXY JARVIS feature from available design artifacts (spec-kit workflow). Use after /sp-plan, or when the user invokes /sp.tasks.
---

# Spec-kit: Tasks

Run the canonical `/sp.tasks` workflow to break the plan into ordered, executable tasks.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` and `backend/`; governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Run `.specify/scripts/powershell/*.ps1` from the repo root (the workflow starts with `check-prerequisites.ps1 -Json`).

## Procedure

1. Read the canonical workflow `.claude/commands/sp.tasks.md` at the repo root and execute it faithfully, passing any user input as `$ARGUMENTS`.
2. It loads the feature's spec.md, plan.md, and design artifacts, then writes `tasks.md` from `.specify/templates/tasks-template.md` in dependency order.

## Constitution constraints

- Every task must leave the system deployable and demonstrable (§1 incremental delivery) — order tasks so a vertical slice works early.
- Each implementation task has a corresponding test task (§7.3); tasks are independently testable with a clear input → output contract.
- Include tasks for the Definition of Done (§16): tests + coverage (§7.1), docs-in-same-PR (§8.2), accessibility (§10), i18n en/ur/ar + RTL (§17), security checklist (§3-§4), observability (§11) — not just code.
- Include a regression-test task for any bug-fix work (§7.4).
- Mark tasks that require an ADR (§2, §8.1) so /sp-adr can capture the decision.
- Respect §18 hackathon scope: tasks for deferred features must be explicitly labeled post-hackathon.

Next phases: /sp-analyze (consistency check) then /sp-implement.
