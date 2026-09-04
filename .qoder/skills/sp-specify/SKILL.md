---
name: sp-specify
description: Create a feature specification for ROXY JARVIS from a natural-language description (spec-kit workflow). Use when the user wants to start a new feature, write a spec, or invokes /sp.specify.
---

# Spec-kit: Specify

Run the canonical `/sp.specify` workflow to turn a feature description into a branch + spec.md.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` (React + Vite + TS) and `backend/` (FastAPI, Python ≥ 3.12); governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Run all `.specify/scripts/powershell/*.ps1` from the repo root (e.g., `powershell.exe -File .specify/scripts/powershell/create-new-feature.ps1 ...`).

## Procedure

1. Read the canonical workflow `.claude/commands/sp.specify.md` at the repo root and execute it faithfully, treating the user's feature description as `$ARGUMENTS`.
2. Key steps it defines: generate a 2-4 word branch short name; find the next feature number across remote branches, local branches, and `specs/` dirs; run `create-new-feature.ps1` ONCE; write the spec from `.specify/templates/spec-template.md`; generate `checklists/requirements.md` and validate (max 3 iterations); resolve up to 3 NEEDS CLARIFICATION markers with the user.
3. Branch naming must follow §13.1 (`feature/<number>-<short-description>`).
4. Report: branch name, spec file path, checklist results, and readiness for the next phase.

## Constitution constraints

- Specs describe WHAT and WHY only — no tech stack, APIs, or code structure (§1 clarity, spec-kit rules).
- §18 Hackathon Scope Guardrails: if the requested feature is on the constitution's "explicitly deferred" list (full IoT/Matter/Thread + geofencing, screen-watching, plugin marketplace, bank/health aggregation, advanced cross-device handoff, wake-word, cost-dashboard polish, multi-region deployment, advanced rate limiting/quotas), warn the user and propose a hackathon-scoped variant before writing the spec.
- Specs must respect §4 privacy-first and §5 AI-safety expectations where relevant (opt-in deletable data, no vendor lock-in, autonomy limits).

Next phases: /sp-clarify (ambiguity reduction) or /sp-plan (technical plan).
