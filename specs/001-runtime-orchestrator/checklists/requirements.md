# Specification Quality Checklist: Multi-Agent Runtime

**Purpose:** Validate the completeness, clarity, and consistency of the requirements in `specs/001-runtime-orchestrator/spec.md` and `specs/001-runtime-orchestrator/plan.md` before implementation begins.
**Created:** 2026-09-05
**Spec:** [`../spec.md`](../spec.md)
**Plan:** [`../plan.md`](../plan.md)
**ADR:** [`../../../history/adr/ADR-003-multi-agent-runtime.md`](../../../history/adr/ADR-003-multi-agent-runtime.md)

> This is a "unit tests for requirements" document. Items ask about the *quality of the requirements as written*, not whether the implementation works. CHK### IDs are stable; the checklist is a new file per `sp.checklist` run.

---

## Requirement Completeness

- [ ] CHK001 — Are all 11 runtime agents in the registry (coordinator, research, files, coding, planner, automation, study, voice, security-privacy, memory-curator, browser) named in the spec, including the user-routable vs. internal distinction? [Completeness, Spec §3.10]
- [ ] CHK002 — Are all 19 runtime skills named in the spec, including which are sensitive, internal, or neither? [Completeness, Spec §3.10]
- [ ] CHK003 — Are the two P1 acceptance criteria (fallback behavior and per-specialist timeout) explicitly stated with their resolution? [Completeness, Spec §3.1, §3.2]
- [ ] CHK004 — Are the boundaries of the runtime's interaction with the existing `backend/` AI gateway specified (i.e. that the runtime calls the gateway, not provider APIs directly)? [Completeness, Plan §"Architecture Overview"]
- [ ] CHK005 — Are the new database tables (`memory_entries`, `scheduled_jobs`, `audit_log`) named and attributed to the runtime? [Completeness, Plan §"Project Structure"]
- [ ] CHK006 — Are deployment-topology decisions (separate `:8001` process, Vite proxy entry) explicit, or are they left implicit? [Completeness, Plan §"Architecture Overview"]
- [ ] CHK007 — Is the open-question about STT/TTS provider choice (ADR-004) marked as deferred to a later PR, not hidden as "TBD"? [Completeness, Spec §9, Plan §"Open Decisions"]
- [ ] CHK008 — Are the two "security-*" agent definitions (project-internal auditor vs. runtime gate) distinguished in the spec? [Completeness, Spec §9]

## Requirement Clarity

- [ ] CHK009 — Is "30-second per-specialist budget" quantified and unambiguous (does the budget cover only the LLM call, or also skill invocations the agent makes)? [Clarity, Spec §3.2]
- [ ] CHK010 — Is the Coordinator's "re-prompt" behavior specified — what does the re-prompt look like to the user, and how many re-prompts before the Coordinator gives up and handles the query directly? [Clarity, Spec §3.1, §8 Q1]
- [ ] CHK011 — Is "plain language" for the sensitive-skill confirmation quantified (length cap, format requirements, what is and is not acceptable)? [Clarity, Spec §3.3, §5]
- [ ] CHK012 — Is "explicit user confirmation" defined precisely — does it require a typed "yes", a click, an out-loud "yes" in voice mode, or any of those? [Clarity, Spec §3.3]
- [ ] CHK013 — Is the v1 classifier ("keyword + description-similarity matching") described with enough specificity that two engineers would build the same thing? [Clarity, Plan §"Coordinator"]
- [ ] CHK014 — Is the runtime's auth model specified — what JWT validation is required, and what is the consequence of an invalid/expired token? [Clarity, Plan §"Cross-Cutting Concerns"]
- [ ] CHK015 — Is the "sensitive skill cannot be invoked without confirmation" requirement applicable to a job that is fired by the scheduler (not by the user directly)? Spec §3.4 mentions `confirm_on_fire: true`, but the relationship to §3.3 needs to be consistent. [Clarity, Spec §3.3 vs §3.4]

## Requirement Consistency

- [ ] CHK016 — Do the three PR-deliverable sections (§7 PR 2, PR 3, PR 4) agree with the API contract section in the plan about which endpoints exist at each PR boundary? [Consistency, Plan §"API Contract"]
- [ ] CHK017 — Is the agent count consistent across spec §1 ("11 specialists"), §3.10 (acceptance criteria), and the plan's "Project Structure" (`coordinator/`, `agents/`, ...)? [Consistency, Spec §1 vs §3.10 vs Plan]
- [ ] CHK018 — Is the skill count consistent (19 in spec §1, 19 in spec §3.10, and the directory tree in the plan reflects the same set)? [Consistency]
- [ ] CHK019 — Do the data-model references in the plan (`memory_entries`, `scheduled_jobs`, `audit_log`) appear in the spec's acceptance criteria for the relevant PRs (PR 4 for memory_entries and scheduled_jobs, PR 2 onwards for audit_log)? [Consistency, Plan vs Spec §7]
- [ ] CHK020 — Is the §3.3 requirement that "`block` verdict is not bypassable" consistent with the §3.4 requirement that a user can override a `block`? If both are intended, the override path needs to be specified. [Consistency, Spec §3.3 vs §3.4]

## Acceptance Criteria Quality

- [ ] CHK021 — Are the spec's acceptance criteria objectively verifiable (each `[ ]` maps to a binary test or a measurable check)? [Measurability, Spec §3]
- [ ] CHK022 — Are the spec's success criteria expressed in user-facing terms (not implementation terms)? The plan has perf budgets like "p95 handoff < 200ms" — are these in the spec's acceptance criteria or only the plan? [Measurability, Spec §3 vs Plan §"Performance Goals"]
- [ ] CHK023 — Is the "five of eleven agents are real" milestone (PR 3 demoable) named in the spec's success criteria, or only in the plan? [Measurability, Spec §7 vs Plan §"Verification"]

## Scenario Coverage

- [ ] CHK024 — Is the scenario "user query matches no specialist" (the §8 Q1 fallback) explicitly covered as a flow, not just a behavior? [Coverage, Spec §3.1]
- [ ] CHK025 — Is the scenario "user's first message in a new session" covered (no prior context, no memory entries) — is the cold-start experience specified? [Coverage, Gap]
- [ ] CHK026 — Is the scenario "specialist crashes mid-response" covered? Spec §3.2 covers timeout but not crash. [Coverage, Gap]
- [ ] CHK027 — Is the scenario "user revokes a connected account (Google, calendar, etc.)" covered — what happens to skills that depend on it? [Coverage, Gap]
- [ ] CHK028 — Is the scenario "scheduled job fails to fire" covered — what is the user's notification? [Coverage, Gap]
- [ ] CHK029 — Is the scenario "two requests arrive concurrently" covered — is the runtime's session state safe under concurrency? [Coverage, Gap]
- [ ] CHK030 — Is the scenario "memory curator's run overlaps with the next run" covered? [Coverage, Gap]
- [ ] CHK031 — Is the scenario "user in voice mode invokes a sensitive skill" covered? The voice agent and the security gate need a defined handoff. [Coverage, Spec §2.5 + §3.3]

## Edge Case Coverage

- [ ] CHK032 — Is the edge case "user spams the same query" covered? Is there rate limiting? [Edge Case, Gap]
- [ ] CHK033 — Is the edge case "an agent's `.md` file is malformed" covered? The loader should fail loud, but the user-facing message needs specification. [Edge Case, Gap]
- [ ] CHK034 — Is the edge case "a skill's `SKILL.md` references an agent slug that doesn't exist" covered? [Edge Case, Gap]
- [ ] CHK035 — Is the edge case "the gateway `/api/v1/ai/chat` is down" covered — what's the runtime's user-facing error? [Edge Case, Gap]
- [ ] CHK036 — Is the edge case "user has no `confirm_on_fire` preference set for a scheduled job" covered? [Edge Case, Gap]

## Non-Functional Requirements

- [ ] CHK037 — Are the plan's performance budgets (p95 first-token < 1.5s, handoff < 200ms) reflected in the spec's acceptance criteria or only in the plan? [NFR, Spec vs Plan §"Performance Goals"]
- [ ] CHK038 — Are observability requirements (structlog schema, trace_id propagation, /health/live, /health/ready) explicit in the spec or only in the plan? [NFR, Plan §"Cross-Cutting Concerns"]
- [ ] CHK039 — Are accessibility requirements for the runtime (not the existing UI) specified — e.g. agent attribution, confirmation readability? [NFR, Spec §6]
- [ ] CHK040 — Is data retention specified for `memory_entries`, `audit_log`, and `scheduled_jobs`? Constitution §4 (privacy-first) implies a retention policy; the spec doesn't state one. [NFR, Gap]
- [ ] CHK041 — Is the "agents and skills are loaded from `.md` files at startup" requirement explicitly tied to a hot-reload behavior or only to cold-start? The spec says "at startup" — what if an operator edits a `.md` after startup? [NFR, Spec §3.10]

## Dependencies & Assumptions

- [ ] CHK042 — Is the assumption "the AI gateway at `:8000` is reachable from the runtime at `:8001`" stated? [Assumption, Plan §"Cross-Cutting Concerns"]
- [ ] CHK043 — Is the assumption "Neon Postgres is the runtime's storage" stated, and is the alternative (no DB / in-memory for dev) addressed? [Assumption, Plan §"Technical Context"]
- [ ] CHK044 — Is the dependency on the existing `backend/` OAuth flow (for calendar, email) explicit? The spec defers provider choice but assumes the gateway's auth is reusable. [Dependency, Plan §"Cross-Cutting Concerns"]

## Ambiguities & Conflicts

- [ ] CHK045 — Is the term "specialist" used consistently to mean "agent" throughout? Spec §2.1 says "specialist" in user-story language; spec §3.1 says "specialist" in acceptance criteria; the agent `.md` files use "agent". Is the distinction intentional? [Ambiguity, Spec §2–§3]
- [ ] CHK046 — Is "real implementation" (used in PR 3 / PR 4 deliverable descriptions) defined? A skill with a mock that returns canned data could be called "real" by some readers. [Ambiguity, Spec §7]
- [ ] CHK047 — Is "v1 vs v2" in the plan's "Coordinator" section (v1: keyword + similarity, v2: LLM-based) treated as a follow-up or as a hard requirement? [Ambiguity, Plan §"Component Breakdown"]
- [ ] CHK048 — Is the "internal: true" requirement for `memory-curator` and `memory_summarize_prune` enforced at runtime (the loader rejects the call) or only at routing time (the Coordinator just doesn't send users there)? [Ambiguity, Spec §3.10]

## Notes

Items marked `Gap` need spec updates before implementation begins. Items marked `Clarity` / `Consistency` / `Ambiguity` need spec edits but won't block a PR. Items marked `Coverage` / `Edge Case` / `NFR` should be addressed in either the spec or the per-PR task breakdown.
