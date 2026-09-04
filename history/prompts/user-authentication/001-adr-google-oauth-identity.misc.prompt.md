---
id: 001
title: ADR for Google OAuth identity integration
stage: misc
date: 2026-09-04
surface: agent
model: minimax/minimax-m3:free
feature: user-authentication
branch: master
user: USER
command: /sp.adr google-oauth and then GitHub OAuth: same shape, drop in a second provider config and dispatcher
labels: ["auth", "oauth", "google", "adr", "security", "session"]
links:
  spec: specs/feature/user-authentication.md
  ticket: null
  adr: history/adr/ADR-002-oauth-identity-provider-integration.md
  pr: null
files:
  - history/adr/ADR-002-oauth-identity-provider-integration.md
  - backend/src/app/auth/oauth.py
  - backend/src/app/auth/oauth_state.py
  - backend/src/app/auth/router.py
  - backend/.env.example
  - backend/README.md
  - backend/tests/integration/test_oauth_google.py
  - frontend/src/auth/AuthGate.tsx
  - frontend/src/auth/AuthContext.tsx
  - frontend/src/auth/api.ts
  - frontend/src/auth/AuthGate.css
  - specs/feature/user-authentication.md
tests:
  - backend/tests/integration/test_oauth_google.py
---

## Prompt

`/sp.adr google-oauth and then GitHub OAuth: same shape, drop in a second provider config and dispatcher`

Run `/sp.adr` per the sp-adr skill (which loads `.claude/commands/sp.adr.md` and uses `.specify/scripts/powershell/*` from repo root). The user invoked the command after I had already implemented Google OAuth and surfaced the ADR-suggestion text at the end of the plan-mode file (`.claude/plans/merry-hugging-creek.md`).

User-provided follow-up context in the `/sp.adr` command args:
- GitHub OAuth will follow the same shape — second provider config and dispatcher, not a new ADR.
- Frontend unit tests were skipped because `jsdom` is missing from `frontend/package.json` — pre-existing, not from this work; re-enable when added.
- Account merging UX (different Google email than existing magic-link account) is out of scope per the spec.

## Response snapshot

Followed the 6-step sp-adr workflow:

1. **Prerequisites:** `check-prerequisites.ps1 -Json` reports no feature directory under `specs/`. The active plan is the plan-mode file at `.claude/plans/merry-hugging-creek.md`; loaded it directly. The repo only ships PowerShell scripts (no `create-adr.sh`), so I wrote the ADR by hand using `.specify/templates/adr-template.md` and the next available ID.
2. **Decision extraction (Analyze):** Identified one cluster: "OAuth identity-provider integration" (flow + state + handoff + linking + extension pattern). Considered and rejected 3 over-granular splits (test strategy, in-memory/DB parity, session token re-affirmation).
3. **Existing ADRs:** ADR-001 (implementation stack) covers Vite/React/SQLAlchemy — orthogonal. No conflict; reference it.
4. **Significance test (Measure):** all three pass (long-term impact, alternatives, cross-cutting).
5. **Created ADR-002** at `history/adr/ADR-002-oauth-identity-provider-integration.md` with all `{{...}}` placeholders filled: cluster title, context, decision, positive/negative consequences, six alternatives considered (PKCE, Implicit, JSON-via-popup, link-by-sub, Authlib, oauth_identities table), references.
6. **Reported** in the required format with created/referenced/conflicts sections.

Validated: zero `{{...}}` placeholders remain; path under `history/adr/`; status "Accepted" matches the implementation already merged in this session; 9 OAuth backend tests passing (67/67 total).

## Outcome

- ✅ Impact: ADR-002 captures a security-sensitive, cross-cutting decision (new identity surface, new external trust boundary, new env-var contract) and records 6 alternatives considered. Future engineers adding GitHub/Apple/Auth0 won't have to re-litigate the flow choice, handoff, or linking rule.
- 🧪 Tests: 9 OAuth integration tests pass (CSRF state, bad `state`, `email_verified: false`, account linking, single-use state, `?error=` from provider, github 501). Full backend suite: 67/67.
- 📁 Files: 1 new ADR (12 KB); implementation files unchanged in this turn (created in prior turns this session).
- 🔁 Next prompts: implement GitHub OAuth (drop-in second provider, not a new ADR per user's note); add `jsdom` to `frontend/package.json` and re-enable frontend unit tests; consider Authlib migration if a second OIDC provider lands.
- 🧠 Reflection: The repo's spec/ADR toolchain expects a `specs/<feature>/plan.md`, but the OAuth plan lives in `.claude/plans/<id>.md` because the plan was authored in plan mode mid-session. The workflow's `check-prerequisites.ps1` doesn't know about plan-mode plans. This is a process gap worth a small follow-up (either teach the script about plan-mode files, or have plan mode write a symlink/copy to `specs/<feature>/plan.md`). I worked around it by reading the plan file directly; the ADR still references the canonical spec.

## Evaluation notes (flywheel)

- Failure modes observed: `check-prerequisites.ps1` expected `specs/<feature>/`; no `create-adr.sh` in this repo (only PowerShell). Worked around both; the workflow's "use a script" steps don't apply cleanly to a Windows-only repo.
- Graders run and results (PASS/FAIL): N/A — this was a documentation workflow, not a code change. The ADR passes the §2/§8.1 checklist (Rationale ✓, Advantages ✓, Trade-offs ✓, Alternatives considered ✓, Scalability/Security/Performance/Maintainability impact ✓).
- Prompt variant (if applicable): N/A.
- Next experiment (smallest change to try): the next time plan mode produces a plan file, copy it to `specs/<feature>/plan.md` so `check-prerequisites.ps1` finds it without manual override.
