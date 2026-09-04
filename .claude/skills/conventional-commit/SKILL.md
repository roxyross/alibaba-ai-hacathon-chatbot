---
name: conventional-commit
description: ROXY JARVIS git workflow per Constitution §13 — numbered branch naming, Conventional Commits, PR size limits, squash/rebase before merge, and PR creation. Use when committing work, creating a branch, or opening a PR.
---

# Git workflow & Conventional Commits (§13)

Execute the project's git workflow. The repo root is the single git repository (contains `frontend/`, `backend/`, and governance artifacts). Confirm with the user before pushing or opening PRs, since those are shared-state actions.

## Branch strategy (§13.1, §13.2)

- `main` is the single source of truth and ALWAYS deployable — never commit directly to it; move stray changes to a new branch.
- Trunk-based: short-lived branches (≤ 3 days) from `main`, merged via PR. No `develop` branch, no long-lived feature branches.
- Branch naming:
  - Feature → `feature/<number>-<short-description>` (e.g. `feature/042-user-auth`)
  - Bug fix → `fix/<number>-<short-description>`
  - Hotfix → `hotfix/<number>-<description>`
  - Chore → `chore/<short-description>`; Docs → `docs/<short-description>`
  - Take `<number>` from the relevant `specs/<feature>` id when one exists.
- Check `git status` and `git log` before any operation that could discard work.

## Commits (§13.5)

Conventional Commits format: `<type>(<scope>): <description>`

- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `hotfix`.
- Message focuses on WHY; body for details; reference the feature/spec where useful.
- Stage specific files by name — never `git add -A` without reviewing what gets included; never commit secrets, `.env` files, or credentials (§3.4). Also stop and flag any forbidden lockfile (`package-lock.json`, `yarn.lock`) — §14.1 requires pnpm (`pnpm-lock.yaml`) and uv (`uv.lock`).

## Before merge (§13.2, §13.3, §15.1)

- Squash or rebase before merge — no noisy merge commits on `main`.
- Automated checks must pass first (CI Stage 1–2): lint, type-check, tests, coverage gate (§7.1), secret scan.
- PR size limits: < 200 lines preferred; 200–500 needs justification in the description; > 500 MUST be split into multiple PRs (large PRs need architect approval before review).
- Required reviews (§13.4): ≥ 1 reviewer for any change; security-sensitive (auth/payment/deletion) ≥ 2 incl. a senior; architecture/infra ≥ 2 incl. architect; hotfix 1 with documented justification.

## PR creation

1. Verify branch state: `git status`, `git log main..HEAD`, remote tracking status.
2. Title: Conventional-Commit style, under 70 characters.
3. Body: Summary (what + why), affected constitution sections if notable, PR size class, test plan checklist, and link to the spec (`specs/<feature>/spec.md`) when one exists.
4. After opening, suggest the next gate: run the pr-reviewer agent or the security-checklist / definition-of-done skills.

Report: branch, commits, and PR URL (or compare link if `gh` is unavailable).
