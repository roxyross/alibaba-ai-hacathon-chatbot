# ADR-001: Implementation Stack — Reconcile the Codebase with Constitution Mandates

> **Scope**: This is a decision *cluster* covering the whole implementation stack (frontend framework, backend persistence, package managers) that the Constitution mandates one way but the code currently implements another. These decisions share a single root cause and are recorded together.

- **Status:** Accepted
- **Date:** 2026-09-03
- **Resolution:** Ratified by Constitution amendment **v2.0.0** (2026-09-03, MAJOR / unanimous consent). §18/§9.2/§15.1 now mandate **Vite 5 + React 18 + TypeScript SPA** (frontend) and **Neon PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic** (backend, ratifying the in-code T027 decision) behind a clean repository/UoW boundary. §14.1 (pnpm + uv) is **unchanged**. Open follow-ups: switch npm → pnpm and commit `uv.lock`; remove the dead `backend/prisma/` scaffold and fix stale "until Prisma migration" comments.
- **Feature:** Cross-cutting / platform foundation (not tied to a single feature spec)
- **Context:** Constitution v1.1.0 mandates a specific stack, but the scaffolded code diverges from it. Rather than let governance and code drift silently (which the Constitution forbids: deviations require an explicit written amendment), this ADR records the de-facto decisions already made in the codebase and proposes how to reconcile them with the Constitution.

<!-- Significance checklist — ALL true:
     1) Impact: platform-wide, long-term consequence for architecture and governance. YES
     2) Alternatives: multiple viable options with real tradeoffs (migrate vs amend). YES
     3) Scope: cross-cutting, not an isolated detail. YES
     → Justified as an ADR (not a PHR note). -->

## Current state (evidence)

| Concern | Constitution mandates | Code actually has | Evidence |
|---------|-----------------------|-------------------|----------|
| Frontend framework | Next.js App Router (§18, §9.2, §15.1) | **Vite 5 + React 18 + TypeScript** | `frontend/vite.config.ts`, `frontend/src/{App.tsx,main.tsx,components,hooks}`; 0 `next` deps in `frontend/package.json` |
| Backend persistence | Neon PostgreSQL + **Prisma** (§18) | **SQLAlchemy 2.0 async ORM + Alembic** | `backend/src/app/db.py` ("T027: Replaces Prisma with SQLAlchemy 2.0 async ORM", `create_async_engine`, `async_sessionmaker`); `backend/alembic/versions/001_initial_models.py` |
| Legacy Prisma scaffold | — | Dead `prisma-client-js` schema (wrong client for a Python service) | `backend/prisma/schema.prisma` (generator `prisma-client-js`); stale "until Prisma migration" comments in `backend/src/app/api/v1/ai.py:324`, `backend/src/app/ai_gateway/services/token_logger.py:52-53` |
| Package managers | pnpm + uv only; `package-lock.json` forbidden (§14.1) | npm (`frontend/package-lock.json`); no committed `uv.lock` | `frontend/package-lock.json` present |
| Database engine | Neon PostgreSQL (§18, §9.2) | PostgreSQL (no conflict) | `backend/prisma/schema.prisma` datasource `postgresql`; asyncpg in `backend/pyproject.toml` |

**Key finding:** the backend divergence is *not* accidental drift. An in-code decision marker (**T027**) deliberately replaced Prisma with SQLAlchemy 2.0 async + Alembic. That decision was never captured in an ADR or reflected in the Constitution. The `backend/prisma/` directory is leftover scaffold from the pre-T027 plan and is a second, conflicting source of truth for the schema.

## Decision

**Recommended (Proposed):** Adopt the *actual* stack as the standard, amend the Constitution to match, and comply on the one cheap item.

1. **Frontend — keep Vite 5 + React 18 + TypeScript.** Do not migrate to Next.js during the hackathon. Amend Constitution §18 (must-ship), §9.2 (scaling row "Next.js (SSR)"), §15.1 (CI "Next.js production build"), and any §2.2/§8.1 Next.js references to read "Vite + React SPA". The SPA must still meet the §9.1 client-side budgets (LCP < 2.5 s, initial JS < 300 KB gz) and §10 accessibility.
2. **Backend — ratify SQLAlchemy 2.0 async ORM + Alembic (T027) as the persistence layer.** Amend Constitution §18 ("Neon PostgreSQL + Prisma") to "Neon PostgreSQL + SQLAlchemy 2.0 async + Alembic". Keep the repository/Unit-of-Work boundary clean so an ORM swap remains possible post-hackathon.
3. **Remove the dead `backend/prisma/` scaffold** and update the stale "until Prisma migration" comments, so there is exactly one source of truth for the schema (SQLAlchemy models + Alembic migrations).
4. **Package managers — comply with §14.1 rather than amend it.** Switch `frontend/` to pnpm (delete `package-lock.json`, commit `pnpm-lock.yaml`) and adopt `uv` for `backend/` (commit `uv.lock`). This is low-cost and §14.1 is a sound rule, so no constitutional change is needed here.
5. **Governance —** items 1–2 change mandated technology, so they require a formal amendment via `/sp-constitution`. Because they redefine mandated principles, treat the amendment as **major (unanimous)** to be safe; item 4 needs no amendment.

**Status is Proposed** — it takes effect only after the team ratifies it and the Constitution amendment lands. Until then, the auditors (constitution-guardian, pr-reviewer) will keep flagging the divergence.

## Consequences

### Positive

- Zero migration risk in a 3–4 day window; preserves a working Vite frontend and a deliberately-chosen async SQLAlchemy backend.
- Python-native async ORM matches the FastAPI async-first rule (§6.2); avoids the `prisma-client-js`-in-a-Python-service mismatch.
- One source of truth for the schema after removing the Prisma scaffold.
- pnpm/uv compliance gives faster, reproducible installs and satisfies §14.1 with committed lockfiles.
- Governance and code become consistent, so audits stop producing false-positive violations.

### Negative

- Requires a formal constitutional amendment (approval overhead) for items 1–2.
- Forgoes Next.js SSR/RSC and the §9.2 scaling assumptions built around it; the SPA must hit performance budgets client-side, and future SSR needs would require a later migration.
- Diverges from the "designed for" post-hackathon expansion (§18) that assumed Next.js/Prisma; expansion plans should be re-checked against this stack.
- Removing `backend/prisma/` is a (small) destructive change and the comment cleanup touches a few files — must be done in a reviewed PR (§13).

## Alternatives Considered

- **Alternative A — Full compliance (migrate code to Constitution):** rewrite the frontend to Next.js App Router and the backend to Prisma. *Rejected for the hackathon:* high time/risk cost, discards a working Vite scaffold and the deliberate T027 SQLAlchemy decision, and Prisma's scaffolded `prisma-client-js` doesn't fit a Python service (would require re-generating with `prisma-client-py`). Revisit only if SSR becomes a hard requirement post-hackathon.
- **Alternative B — Keep the actual stack, amend nothing (silent divergence):** *Rejected:* violates the Constitution's rule that deviations require an explicit written amendment; leaves governance and code permanently inconsistent and every audit noisy.
- **Alternative C — Keep actual stack + amend Constitution + comply on package managers + remove dead scaffold (CHOSEN):** lowest risk, makes code and governance consistent, keeps the door open for a later Next.js/Prisma migration behind clean boundaries.

## References

- Constitution: `.specify/memory/constitution.md` — §2.2, §8.1, §9.2, §14.1, §15.1, §18.
- In-code decision markers (T027): `backend/src/app/db.py`, `backend/alembic/env.py`; stale Prisma references: `backend/src/app/api/v1/ai.py:324`, `backend/src/app/ai_gateway/services/token_logger.py:52-53`.
- Superseded artifact: `backend/prisma/schema.prisma` (to be removed).
- Related ADRs: none (this is the first ADR; establishes `history/adr/`).
- Follow-ups: run `/sp-constitution` to ratify the amendment; a small PR to remove the Prisma scaffold + fix stale comments and to switch to pnpm/uv.
