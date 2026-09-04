---
name: sp-checklist
description: Generate a custom requirements-quality checklist for the current ROXY JARVIS feature (spec-kit workflow). Use to validate requirement clarity/completeness in a domain before planning or implementation, or when the user invokes /sp.checklist.
---

# Spec-kit: Checklist

Run the canonical `/sp.checklist` workflow to generate a checklist that validates REQUIREMENTS quality — "unit tests for requirements writing", not implementation verification.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` and `backend/`; governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Run `.specify/scripts/powershell/*.ps1` from the repo root.
- Checklist template: `.specify/templates/checklist-template.md`. Checklists are stored under the feature's `checklists/` directory.

## Procedure

1. Read the canonical workflow `.claude/commands/sp.checklist.md` at the repo root and execute it faithfully, using the domain the user names (e.g., security, UX, testing).
2. Checklist items must validate requirement quality (e.g., "Are visual hierarchy requirements specified for both themes?"), NEVER implementation verification (e.g., "Verify the button clicks correctly").

## High-value checklist domains for this project

- **Security & privacy** — mirrors Constitution §3-§4 requirements in the spec (prompt-injection defense, T1/T2/T3 approval tiers, opt-in memory consent, data rights).
- **AI safety** — provider abstraction (§1.3), autonomy levels, routing transparency, guardrails/kill switch, human-in-the-loop (§5).
- **Accessibility** — WCAG 2.1 AA, keyboard, contrast in both themes, screen-reader-friendly chat (§10).
- **Mobile & i18n** — responsive at 375/768/1024 breakpoints, PWA, English + Urdu + Arabic with full RTL (§17).
- **Observability & audit** — structured logs, trace_id, metrics, health checks, "What did Jarvis do today" audit view (§11, §3.6).

Report the checklist path and any requirements that failed validation, so the spec can be fixed before /sp-plan or /sp-implement.
