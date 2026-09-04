---
name: sp-clarify
description: Identify underspecified areas in the current ROXY JARVIS feature spec by asking up to 5 targeted clarification questions and encoding answers back into the spec (spec-kit workflow). Use after /sp-specify when a spec still has ambiguity, or when the user invokes /sp.clarify.
---

# Spec-kit: Clarify

Run the canonical `/sp.clarify` workflow to reduce ambiguity in the active feature specification.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` and `backend/`; governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Run `.specify/scripts/powershell/*.ps1` from the repo root.

## Procedure

1. Read the canonical workflow `.claude/commands/sp.clarify.md` at the repo root and execute it faithfully.
2. It locates the current feature (via `check-prerequisites.ps1 -Json`), analyzes `spec.md` for underspecified areas, asks up to 5 highly targeted questions, and writes the answers back into the spec.
3. Ask the questions through the user-interaction mechanism, then update the spec file with the resolved answers.

## Constitution constraints

- Keep the spec WHAT/WHY only — clarification answers must not introduce implementation details.
- Prioritize questions by impact: scope (§18) > security/privacy (§3-§4) > AI safety/autonomy (§5) > user experience > technical details.
- If a clarification reveals the feature touches the constitution's deferred list (§18), stop and surface the hackathon scope conflict instead of continuing.

Next phase: /sp-plan once no material ambiguity remains.
