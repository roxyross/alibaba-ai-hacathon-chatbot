---
name: sp-constitution
description: Create or update the ROXY JARVIS project constitution through the formal amendment workflow (spec-kit workflow). Use ONLY when the user explicitly wants to amend the constitution, or invokes /sp.constitution.
---

# Spec-kit: Constitution amendment

Run the canonical `/sp.constitution` workflow to update `.specify/memory/constitution.md` at the repo root.

## Environment

- The repo root is a monorepo and the single git repository: application code in `frontend/` and `backend/`; governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
- Constitution file: `.specify/memory/constitution.md` (currently v2.0.0).

## Procedure

1. Read the canonical workflow `.claude/commands/sp.constitution.md` at the repo root and execute it faithfully.
2. Apply the user's principle inputs as a formal amendment, keeping dependent templates (`.specify/templates/*`) and agent/skill context files in sync.

## Strict rules

- The constitution is the PERMANENT rulebook; all specs, decisions, tasks, PRs, and code must comply. Deviations require explicit written amendment and team approval — so confirm the user explicitly approves each change before writing it.
- Follow the amendment procedure and bump the version accordingly: **major** (backward-incompatible governance change) = unanimous consent; **minor** (new or materially expanded section) = ≥ 2 approvals; **patch** (clarification only) = 1 approval. Record the rationale and the "Last Amended" date.
- After amending, check for conflicts with: existing ADRs (`history/adr/`), open specs (`specs/`), the `.qoder/` + `.claude/` agents and skills, and AGENTS.md/CLAUDE.md context files; report anything that now needs updating.
- Never weaken or remove a security (§3), privacy (§4), or AI-safety (§5) control without the user explicitly acknowledging the risk.

Report: sections changed, new version, sync status of templates/agents/skills, and any downstream artifacts that need follow-up.
