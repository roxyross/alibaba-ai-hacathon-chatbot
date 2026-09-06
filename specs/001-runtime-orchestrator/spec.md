# Spec: Coordinator + Specialist Agents (Multi-Agent Runtime)

**Branch:** `001-runtime-orchestrator`
**Status:** Draft (revised 2026-09-05 — scope expanded from MVP to full runtime)
**Date:** 2026-09-01 (original) | 2026-09-05 (revised)
**Author:** AI (sp.specify) | revised by Claude
**Related artifacts:** [`plan.md`](./plan.md), [`ADR-003-multi-agent-runtime.md`](../../history/adr/ADR-003-multi-agent-runtime.md)

---

## 1. Problem Statement

ROXY JARVIS needs a Coordinator Agent that understands a user's request and delegates to the right specialist. Without delegation, a single monolithic agent becomes bloated, slow, and unable to use domain-specific tools. The Coordinator ensures requests reach the right specialist so users get domain-expert responses rather than generic ones, and so the runtime can grow by adding specialists (and skills) without rewriting the routing layer.

This spec originally covered a minimal MVP — Coordinator + Coding + Research. After the 2026-09-05 revision, it covers the **full multi-agent runtime**: 11 specialists, 19 skills, a scheduler, a security gate, a memory curator, and the cross-cutting infrastructure (session manager, registry, loaders) that ties them together. Scope expansion is delivered in three implementation PRs (PR 2/3/4) so each PR is independently demonstrable (Constitution §1.1).

---

## 2. User Stories

User stories are listed in priority order. Each is independently testable; a working MVP at any PR boundary is shippable.

### 2.1 Coordinator routes requests to the right specialist (P1)

- As a user, I want to ask a coding question and get a response from a Coding Agent so that I get expert-level help.
- As a user, I want to ask a research question and get a response from a Research Agent so that I get thorough, cited help.
- As a user, I want to ask a general question and have the Coordinator handle it directly so that I don't need to know which agent exists.
- As a user, I want the agent to explain which specialist handled my request so that I understand the system.
- As a system operator, I want new specialists to be addable without modifying the Coordinator so that the system scales.

### 2.2 Security/Privacy gate before sensitive actions (P1)

- As a user, before the runtime sends an email on my behalf, submits a form, or makes a payment, I want a plain-language confirmation of exactly what will happen so that I can stop a mistake before it costs me.
- As a user, if I say "just do it" once, I still want a fresh confirmation for each new sensitive action so that I never lose agency over a different recipient or amount.

### 2.3 Scheduled and recurring jobs (P1)

- As a user, I want to set a daily morning briefing and trust the runtime to run it at my local 8am, every day, without me re-asking.
- As a user, I want to see all my active scheduled jobs and cancel any of them so that I retain control over what runs.

### 2.4 Files over uploaded documents (P2)

- As a user, I want to ask a question grounded in a document I uploaded and get a quoted, cited answer so that I can trust the response is from my file, not general knowledge.

### 2.5 Voice sessions (P2)

- As a user, when I switch to voice mode, I want the runtime to handle the full voice lifecycle (transcribe, route, speak back) without dropping the conversation context.

### 2.6 Browser automation (P2)

- As a user, I want the runtime to log in to a website, fill a form, and download a file for me so that I don't have to drive the browser myself.

### 2.7 Study aids (P2)

- As a learner, I want flashcards and quizzes generated from material I'm studying so that I can retain it.

### 2.8 Long-term memory and pruning (P3)

- As a user, I want the runtime to remember things I tell it to remember and to forget things that are no longer useful, with a soft-delete window in case I change my mind.

### 2.9 Calendar and email integration (P3)

- As a user, I want the runtime to read my calendar and draft email so that I can plan and communicate without leaving the conversation.

---

## 3. Acceptance Criteria

### 3.1 Routing (P1)

- [ ] All user requests enter through the Coordinator Agent.
- [ ] Coordinator analyzes the request and routes to the appropriate specialist (Coding, Research, Files, Planner, Automation, Study, Voice, Browser, or Security/Privacy) based on intent classification.
- [ ] If intent classification is uncertain, the Coordinator re-prompts the user with a short clarification rather than routing to a default specialist. *(Resolves the prior version's open question Q1, now §8.)*
- [ ] Coordinator and each specialist are separate execution contexts with distinct system prompts derived from the agent's `.md` definition.
- [ ] Every response is labeled with the handling agent name (e.g. "Coding Agent").
- [ ] Adding a new specialist requires only registering it in the agent registry — no changes to Coordinator routing logic.
- [ ] Each agent call is logged with: user ID, request timestamp, agent name, model used, routing rationale.

### 3.2 Timeouts (P1)

- [ ] Each specialist gets a 30-second response budget.
- [ ] On timeout, the Coordinator returns a "specialist is taking too long" message and offers the user the option to try a different specialist. *(Resolves the prior version's open question Q2, now §8.)*
- [ ] Timeouts are logged with the agent name, user ID, and elapsed time.

### 3.3 Security/Privacy gate (P1)

- [ ] Before any agent invokes a `sensitive: true` skill (`email_send`, `browser_fill_form`), the runtime surfaces the action in plain language and waits for explicit user confirmation.
- [ ] A user saying "just do it" once does not extend to a different action; each new sensitive action requires a fresh confirmation.
- [ ] The Security/Privacy Agent produces a verdict (`clear` / `caution` / `block`) for proposed actions; a `block` verdict is not bypassable without an explicit user override.

### 3.4 Scheduler (P1)

- [ ] The Automation Agent can create a job from a natural-language schedule ("every weekday at 8am", "in 3 hours", "tomorrow morning").
- [ ] Created jobs are listed by job ID; the user can pause, resume, modify, or cancel any of them.
- [ ] A job whose action includes a sensitive skill is flagged `confirm_on_fire: true`; the runtime re-confirms each fire.

### 3.5 Files (P2)

- [ ] The Files Agent RAGs over the user's uploaded documents and returns quoted passages with `[doc, location]` citations.
- [ ] If a question isn't grounded in the documents, the agent says so rather than filling the gap with general knowledge.

### 3.6 Voice (P2)

- [ ] The Voice Agent owns the full lifecycle: streaming STT in, streaming TTS out, turn-taking, interruption handling.
- [ ] The agent handles end-of-session by summarizing (if substantive) and asking before storing in long-term memory.

### 3.7 Browser (P2)

- [ ] The Browser Agent drives a real browser via the `browser_navigate` (read-only) and `browser_fill_form` (sensitive) skills.
- [ ] Form submissions involving payment, deletion, sending a message, or account-setting changes are gated by the Security/Privacy Agent.

### 3.8 Study (P2)

- [ ] The Study Agent generates flashcards and quizzes with a documented quality bar (one thing per card, unambiguous answer, plausible distractors).

### 3.9 Memory curator (P3)

- [ ] The Memory Curator Agent runs on a daily schedule (not on user request).
- [ ] It applies the pruning policy in `.claude/agents/memory-curator.md`: keep verbatim (explicit "remember this"), summarize clusters of 3+ related entries older than 30 days, soft-delete never-retrieved entries older than 180 days, hard-delete soft-deleted entries older than 30 days.
- [ ] The user can adjust any threshold.
- [ ] A run report is produced and stored in the runtime's job log; the user is notified on their next session if the "notify on memory changes" preference is on.

### 3.10 Cross-cutting (P1)

- [ ] Agent and skill definitions are loaded from `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` at startup; no Python changes are required to add a new agent or skill.
- [ ] Agents marked `internal: true` (`memory-curator`) are not routable from the Coordinator.
- [ ] Skills marked `sensitive: true` (`email_send`, `browser_fill_form`) are gated as in §3.3.
- [ ] Skills marked `internal: true` (`memory_summarize_prune`) are only callable by the corresponding internal agent.

---

## 4. Out of Scope

- **IoT / home automation routing.** Not part of the user stories; the runtime is conversational and document-centric.
- **Native mobile apps.** The voice session is reachable via the existing web SPA; a native iOS/Android client is a separate effort.
- **Cross-user shared sessions.** Sessions are per-user; multi-user rooms are deferred.
- **Agent-to-agent direct calls.** Specialists hand off back to the Coordinator, which may route to a second specialist. Specialists do not call other specialists directly in v1.
- **Modifying the existing AI gateway's chat endpoint.** The runtime adds a second conversation path; it does not replace `/api/v1/ai/chat`.

---

## 5. Privacy & Security Considerations

- **Agent prompts are not exposed to users.** The body of an agent's `.md` file is the agent's system context; only the response reaches the user.
- **Tool calls go through the sandboxed skill execution layer.** Skills are not arbitrary code; each has a documented contract in its `SKILL.md`.
- **Sensitive skills are gated.** `email_send` and `browser_fill_form` cannot be invoked without explicit user confirmation in plain language.
- **All agent actions produce audit log entries** (user ID, agent name, action, timestamp, decision).
- **The Memory Curator cannot modify `importance: forever` entries** and cannot hard-delete within the soft-delete grace window.
- **The runtime does not bypass the existing AI gateway's provider abstraction** (Constitution §1.3); the runtime calls the gateway at `/api/v1/ai/chat`, never provider APIs directly.

---

## 6. Accessibility Considerations

- **Agent attribution is visually distinct and programmatically available to screen readers.** Every response includes the agent name as both visible text and a label.
- **Voice mode respects interruptibility.** A user can interrupt the agent mid-utterance; the agent stops TTS immediately.
- **Loading states are announced** for long-running specialists.
- **Sensitive-action confirmations are presented in plain language** (not as JSON, raw error codes, or "click here").

---

## 7. Phased Rollout

The full scope is delivered in three implementation PRs after PR 1 (this spec + plan + ADR). Each PR is independently demonstrable per Constitution §1.1.

### PR 2 — Vertical slice (P1 subset)

**Delivers:** Coordinator + Research Agent + the `web_search` skill (stubbed), running on a new top-level `runtime/` Python package. FastAPI app on `:8001`. Agent and skill loaders; keyword + description-similarity classifier. Real auth via the existing magic-link JWT.

**Demoable:** A user can hit the chat UI, type a research question, and get a labelled "Research Agent" response. The classifier routes; the skill returns a mock result.

### PR 3 — Skills + 5 more agents (P1 + P2)

**Delivers:** Real `web_search` (Brave/SerpAPI — ADR-003 if material), `code_generate` / `code_explain` / `code_debug` (delegate to existing AI gateway), `store_memory` / `retrieve_memory` (backed by Neon DB, new `memory_entries` table), `calendar_read` (read-only Google Calendar OAuth), `calculator` (strict parser, no `eval`), `task_breakdown` (LLM call). Agents `files`, `coding`, `planner`, `automation`, `security-privacy` are now fully wired.

**Demoable:** A user can ask a code question, recall a memory, check a calendar, summarize a document. Five of eleven agents are real.

### PR 4 — Scheduler, Memory Curator, sensitive-skill gate, last agents (P3)

**Delivers:** APScheduler for `schedule_job`; Memory Curator nightly pass; the Security/Privacy gate implemented in code; `email_draft` / `email_send` (Gmail API, gated); `speech_to_text` / `text_to_speech` (Deepgram/ElevenLabs — ADR if material); `voice` session lifecycle (WebSocket); `browser` driver (Playwright, gated); `flashcard_generate` / `quiz_generate`. All eleven agents and nineteen skills are real.

**Demoable:** A user can have a voice session, schedule a daily briefing, get study cards, fill a form on a website, and have the memory curator prune their long-term memory overnight.

---

## 8. Resolved Open Questions

These are the questions the original spec left open; they are now resolved.

### Q1 (was: `[NEEDS CLARIFICATION]`)

> Should the Coordinator fall back to a default specialist if intent classification is uncertain, or respond directly?

**Resolution:** The Coordinator re-prompts the user with a short clarification. It does not route to a default specialist (which would feel arbitrary) and does not respond directly (which would defeat the routing model). The clarification is a single sentence, e.g. "Did you mean: (a) a coding question, or (b) a research question?"

### Q2 (was: `[NEEDS CLARIFICATION]`)

> Is there a timeout per agent response, and what should happen if a specialist times out?

**Resolution:** Yes — a 30-second per-specialist budget. On timeout, the Coordinator returns a "specialist is taking too long" message and offers the user the option to (a) try again, (b) try a different specialist, or (c) let the Coordinator handle it directly. Timeouts are logged with the agent name, user ID, and elapsed time.

---

## 9. Open Follow-up (not blocking)

- **Two `security-privacy*` agents, distinct.** `.claude/agents/security-privacy-auditor.md` is a **project-internal** reviewer that checks code changes against the Constitution. `.claude/agents/security-privacy.md` is a **runtime** agent that reviews proposed user actions before they run. Different concerns, different agents. The spec references both.
- **Two `coordinator*` definitions.** The agent in this spec is the runtime Coordinator. There is no other Coordinator agent in the repo. The branch name `001-runtime-orchestrator` and the original filename `coordinator-specialist-agents.md` both refer to this same spec.
- **Provider choices for STT/TTS/search.** Some skill implementations in PR 3/4 require paid third-party providers. Provider selection is delegated to ADRs (ADR-003, possibly ADR-004) rather than being fixed in this spec, so the decision can be made with up-to-date pricing and feature information closer to implementation time.
- **`email_send` provider.** The current plan is Gmail API (matches the existing Google OAuth flow in `backend/`). If the user wants Outlook, the plan changes.
- **CAPTCHA strategy for the Browser Agent.** Out of scope for the runtime; users approve a CAPTCHA service or solve manually.

---

## 10. Scenarios & Edge Cases

This section addresses the `Gap` items from `checklists/requirements.md` (CHK025–CHK041). Each requirement is a user-visible behavior; implementation lives in the runtime.

### 10.1 Cold-start first message (CHK025)

- When a user sends their first message in a new session, the runtime has no prior context, no memory entries, and no per-user preferences beyond the auth token.
- The Coordinator classifies the message as if the session were any other session. The first-message experience is identical to a return-user experience *except* that long-term memory retrieval returns an empty list — the agent must work without prior context, not pretend to have it.
- The Coordinator's first response labels which agent handled the request, so the user understands the system even on the first turn.

### 10.2 Specialist crash mid-response (CHK026)

- A specialist is a single LLM call plus the skill invocations it triggers. A crash inside the specialist (Python exception, model timeout, OOM) is distinct from the §3.2 budget timeout.
- On a specialist crash, the Coordinator catches the exception, logs the failure with the agent name, user ID, and stack trace, and returns a user-facing message: "The {agent-name} agent ran into an error. Would you like to try again, or route this to a different specialist?" The user is never shown the stack trace.
- A specialist that crashes three times in the same session is auto-disabled for that session, and the user is told: "The {agent-name} agent has been disabled for this session because of repeated errors."

### 10.3 Account revocation (CHK027)

- A user can revoke a connected account (Google for Calendar / Gmail, GitHub for browser sessions) from their account settings.
- The runtime checks, on every skill invocation that requires a provider token, whether the token has been revoked. A revoked token causes the skill to return a `provider_unavailable` error to the agent, which surfaces to the user as: "Your {provider} connection was revoked. Reconnect at {settings-url} and try again."
- The agent does not silently fall back to a different account or a cached token.

### 10.4 Scheduled job fails to fire (CHK028)

- A scheduled job may fail to fire for three reasons: the runtime process was down at the scheduled time, the action raised an exception, or the action required `confirm_on_fire: true` and no user was available to confirm.
- The runtime records every fire attempt (success, failure, no-confirmation) in the `audit_log` table. The user sees missed jobs the next time they open the app, with a clear "this job was missed because {reason}" message and a "run now" button.
- The runtime does not silently re-run missed jobs. Re-running is a user-initiated action.

### 10.5 Concurrent requests (CHK029)

- The runtime is multi-worker. A user can have two browser tabs open and send a message in each; the runtime must not corrupt session state.
- Session state lives in the database (per-user-per-session row). Each request opens a transactional session, reads the current state, computes a new state, and writes atomically. Two concurrent requests for the same session are serialized via row-level locks on the session row.
- The Coordinator is safe under concurrency: a routing decision is computed from a snapshot of the registry (the registry is read-only after startup), and the agent executor is per-request, not shared mutable state.

### 10.6 Memory Curator run overlap (CHK030)

- The Memory Curator runs on a daily schedule. If a previous run is still in progress when the next scheduled tick fires, the new run is skipped, not started in parallel.
- The skip is logged. The user is not notified unless the skip recurs (then it is a runtime issue, not a normal event).
- The Memory Curator is idempotent: re-running after a partial completion picks up where the previous run left off, using the `run_id` audit log.

### 10.7 Query spam / rate limiting (CHK032)

- A user (or a script acting as a user) may send many messages in quick succession.
- The runtime applies a per-user rate limit of 60 messages per minute on `POST /api/v1/runtime/chat`. Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.
- The limit is intentionally generous for human use; a smaller limit (e.g. 10/min) would harm the voice session use case, which can produce high message rates during dictation.
- Scheduled jobs that fire on the user's behalf are not subject to this limit; they have their own budget.

### 10.8 Malformed agent `.md` file (CHK033)

- An agent's `.md` file may be missing required frontmatter keys, have unparseable YAML, or have a body that doesn't start with a heading.
- The loader fails loud at startup: it logs the offending file path and the parse error, and refuses to register the agent. The runtime still starts and serves requests for the other agents.
- An operator who edits a `.md` file and breaks it sees the failure in the runtime's log, not in a user-facing error.

### 10.9 Skill references a non-existent agent (CHK034)

- A `SKILL.md` body may say "Used by the Research Agent" but the research agent's slug may have been renamed.
- The loader does not validate cross-references between skills and agents at load time. The cross-reference is informational prose, not a binding declaration. A skill that an agent cannot actually invoke is a deployment-time bug, caught when the agent tries to invoke it and the skill registry returns "no such skill".
- The error message is: "Skill {slug} is not registered. Available skills: {list}."

### 10.10 Gateway `/api/v1/ai/chat` is down (CHK035)

- The runtime depends on the AI gateway for LLM inference. If the gateway is unreachable, every agent call fails.
- The runtime catches connection errors and returns: "The AI service is temporarily unavailable. Please try again in a moment." The user-facing message is intentionally generic — internal diagnostics (gateway URL, error code) stay in the structured log.
- A circuit breaker wraps the gateway client: after 5 consecutive failures in 30 seconds, the breaker opens, and the runtime returns the same generic message without even attempting a request, until the breaker half-opens after 30 seconds.

### 10.11 No `confirm_on_fire` preference set (CHK036)

- A scheduled job has a `confirm_on_fire: bool` column. The default is `false` (no confirmation needed at fire time).
- A job that includes a sensitive skill in its action chain *must* have `confirm_on_fire: true`; the `schedule_job` skill refuses to create a job with a sensitive-skill action and `confirm_on_fire: false`.
- The default of `false` is appropriate for non-sensitive actions (a daily morning briefing that just reads from `web_search` doesn't need to re-confirm). The runtime's enforcement of the rule at creation time (§3.4) means a job that would have caused a runtime surprise cannot exist.

### 10.12 Data retention (CHK040)

- `memory_entries` follows the user-controlled importance levels: `importance: forever` entries are never deleted by the system; `importance: normal` entries are subject to the Memory Curator's pruning (§3.9); `importance: low` entries are soft-deleted after 90 days of no retrieval.
- `audit_log` is retained for 1 year for compliance and incident response. Operators can shorten this; they cannot lengthen it without a Constitution amendment (§4 privacy-first).
- `scheduled_jobs` is retained for 90 days after the job's last fire (success or failure). The user can cancel a job at any time, which immediately hard-deletes the row.
- All three tables are user-scoped: rows are visible only to the user that owns them.

### 10.13 Hot-reload of `.md` files (CHK041)

- "Loaded at startup" means the runtime reads the `.md` files when the process starts. After startup, the in-memory registry is read-only.
- An operator who edits a `.md` file must restart the runtime process for the change to take effect. The startup log lists the count of agents and skills loaded; the operator can compare before and after.
- Hot-reload is explicitly out of scope for v1. It is a v2 follow-up and will require a watch on the `.md` directory plus a registry swap (a new `dict[slug, AgentDef]` is computed and atomically replaces the old one).

---
