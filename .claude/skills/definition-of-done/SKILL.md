---
name: definition-of-done
description: Verify a ROXY JARVIS task or milestone against the Constitution §16 Definition of Done before it is declared complete or merged. Use when the user says a feature is done, before merging, or when invoking a DoD check.
---

# Definition of Done verification

Constitution §16: a task/milestone is Done only when ALL applicable items pass. Verify each against the actual state of the code — never take claims at face value. Use the §14.1 package managers: `pnpm` (frontend), `uv` (backend).

## Checklist — verify with commands and file reads

### Code quality (§16)
1. **Code written, reviewed, merged-path clear** — diff inspected; review findings resolved.
2. **No lint/type/format errors** — frontend `pnpm lint` + `pnpm typecheck` (tsc); backend Ruff + Black + mypy. Zero tolerance (§6).
3. **Coverage meets §7.1** for the affected layer — domain ≥ 90%, services ≥ 85%, infra ≥ 75%, API ≥ 80%, UI ≥ 70%, critical-path branch ≥ 95%.

### Testing (§7)
4. **Tests pass** — run them: frontend unit (Vitest), backend (pytest), integration (Testcontainers), relevant e2e (Playwright). Report actual output.
5. **Regression test** exists for every bug fixed (fails before, passes after).

### Documentation (§8)
6. **Docs updated in the SAME PR** (§8.2) — README if setup changed, OpenAPI (`docs/api/`) for every changed endpoint, schema docs (`docs/database/`) for every migration, tool docs if a tool changed. Non-trivial decisions have an ADR in `history/adr/` (§8.1).

### Security & privacy (§3, §4)
7. Run the **security-checklist** skill or confirm it passed — OWASP (§3.1), no secrets (secret scan), prompt-injection defenses on AI paths (§3.2), privacy impact assessed if user-data handling changed (§4).

### Accessibility & UX (§10, §16)
8. WCAG 2.1 AA checklist; keyboard navigation; screen reader for new UI; works in light AND dark; responsive at 375px and 768px.

### Internationalization (§17)
9. All user-facing strings are i18n keys (no hardcoded strings); tested in English + Urdu + Arabic; RTL layout tested for Urdu/Arabic.

### Observability (§11)
10. New endpoints have health checks (`/health/live`, `/health/ready`); structured JSON logs added; new metrics on `/metrics`; `trace_id` propagated through new critical paths.

### Performance (§9)
11. No new N+1 queries; bundle-size impact assessed (no regression > 10 KB gz); latency assessed against §9.1 budgets.

### Demonstrable (hackathon scope, §18)
12. The feature can be shown running — e.g. `pnpm dev` in `frontend/` and the backend service, or `docker compose up`.

## Output

Per item: DONE / NOT DONE / N-A with evidence (command output, file path). Then the verdict:

- **DONE** — every applicable item verified.
- **NOT DONE** — list exactly what remains, ordered by effort.

Never mark DONE on an item you could not actually verify; say what verification was impossible and why.
