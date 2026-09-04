---
name: constitution-check
description: Audit a change, decision, or artifact against the ROXY JARVIS project constitution (v2.0.0) and get a section-by-section compliance verdict. Use before merging, before accepting a design decision, or when the user asks "does this comply with the constitution?".
---

# Constitution compliance check

Audit any change, decision, or artifact against the ROXY JARVIS constitution and produce a compliance verdict.

## Procedure

1. Read `.specify/memory/constitution.md` at the repo root in full — it is the only source of truth.
2. Identify the audit target:
   - Code or artifact change → `git diff main...HEAD` (or the range the user names); read whole files where diff context is insufficient. Application code lives in `frontend/` and `backend/`; governance artifacts in `specs/`, `history/`, `.specify/`, `.claude/`.
   - Decision or artifact → read the spec/plan/ADR/proposal the user points to.
3. Walk every constitution section and record PASS / WARNING / VIOLATION:
   - §1 Engineering principles (incl. §1.3 provider abstraction, §1.4 feature-first), §2 architecture (10-layer §2.1, contract-first §2.2) + ADRs, §3 security, §4 privacy, §5 AI safety, §6 coding standards, §7 testing (coverage §7.1), §8 docs (docs-in-same-PR §8.2), §9 performance & scalability, §10 accessibility (WCAG 2.1 AA), §11 observability & error handling, §12 API versioning, §13 git workflow & code review, §14 dependencies & environments (pnpm/uv §14.1), §15 CI/CD, §16 Definition of Done, §17 non-functional summary, §18 hackathon scope guardrails.
4. Pay special attention to §18 scope creep: any work on the explicitly-deferred list (full IoT/Matter/Thread + geofencing, screen-watching, plugin marketplace, bank/health aggregation, advanced cross-device handoff, wake-word, cost-dashboard polish, multi-region deployment, advanced rate limiting/quotas) is a VIOLATION during the hackathon window unless formally amended.
5. Stack status: the frontend/backend stack is **ratified** by Constitution v2.0.0 + ADR-001 (Vite 5 + React 18 SPA; Neon PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic, the in-code T027 decision) — do NOT report these as violations. Still report the remaining deviations: `frontend/package-lock.json` (npm) violates §14.1 (pnpm only, `package-lock.json` forbidden) and no `uv.lock` is committed; the dead `backend/prisma/` scaffold is a conflicting second source of truth for the schema and should be removed (ADR-001 follow-up); `docs/` (§8.1) is not yet populated.

## Output

One finding per issue: severity, §section, evidence (file:line or quote), required action. End with a verdict:

- **PASS** — compliant.
- **PASS WITH WARNINGS** — compliant but with drift risks to fix soon.
- **BLOCK** — at least one violation; list exactly what must change.

For deep audits, delegate the specialized slices to the security-privacy-auditor, ai-safety-reviewer, or pr-reviewer agents instead of duplicating their work.
