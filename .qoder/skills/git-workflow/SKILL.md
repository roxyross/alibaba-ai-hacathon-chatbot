---
name: git-workflow
description: Autonomous git workflow for ROXY JARVIS per Constitution §13 — commit work, create/sync branches, squash or rebase before merge, push, and open PRs. Use when the user wants to commit, branch, sync with main, or create a pull request.
---

# Git workflow (Constitution §13)

Intelligently execute the git workflow to commit work and create PRs. The user provides intent; you execute autonomously and only ask when judgment is genuinely needed.

## Canonical workflow

Read and execute `.claude/commands/sp.git.commit_pr.md` at the repo root — the project's agentic git workflow (Phases 1-5: context gathering, strategy decision, content generation, execution, outcome validation). Apply these Constitution §13 overrides on top of it.

## Repository scope

The repo root is the single git repository and contains everything — `frontend/`, `backend/`, `specs/`, `history/`, `.specify/`, `.claude/`, `.qoder/`. One `main` branch; no `develop`, no long-lived feature branches (§13.2).

## §13 rules (override defaults)

1. **main is always deployable** — never commit directly to main; move stray changes to a new branch. Short-lived branches (≤ 3 days) from `main`.
2. **Branch naming (§13.1)** — `feature/<number>-<short-desc>`, `fix/<number>-<short-desc>`, `hotfix/<number>-<desc>`, `chore/<short-desc>`, `docs/<short-desc>`. The constitution's scheme takes precedence over any example names in the command file. Take `<number>` from the `specs/<feature>` id when present.
3. **Conventional Commits (§13.5)** — `type(scope): subject` + a body explaining WHY. Types: feat, fix, docs, style, refactor, test, chore, perf, ci, hotfix.
4. **Squash or rebase before merge** — no noisy merge commits on main.
5. **PR size limits (§13.3)** — < 200 lines preferred; 200–500 needs justification; > 500 MUST be split (large PRs need architect approval before review).
6. **Required reviews (§13.4)** — ≥ 1 reviewer; security-sensitive (auth/payment/deletion) ≥ 2 incl. a senior; architecture/infra ≥ 2 incl. architect; hotfix 1 with justification.

## Safety gates

- Only git commands — never run builds, tests, servers, or watchers inside this workflow.
- Stage specific files by name; review what is staged; STOP and flag anything resembling secrets or credentials (§3.4), or a forbidden lockfile (`package-lock.json`, `yarn.lock` — §14.1 requires pnpm/uv).
- No destructive commands (reset --hard, push --force, branch -D), no --no-verify, no amending published commits without explicit user approval.
- Push and PR creation are shared-state actions: confirm unless the user explicitly requested them.
- Merge conflicts: resolve without discarding either side; ask when unsure.

## Next gates after the PR is open

- Run the security-checklist skill if the diff touches auth, AI paths, tool execution, or data handling.
- Run the definition-of-done skill (§16) before declaring the task complete.
- Delegate review to the pr-reviewer agent.

Report: branch (with its §13.1 name), commit(s) with messages, PR size class, and PR URL (or compare link if `gh` is unavailable).
