<!--
SYNC IMPACT REPORT
==================
Version change: 1.1.0 → 2.0.0 (MAJOR — redefinition of mandated technology; unanimous consent per Amendment Procedure)
Date amended: 2026-09-03
Rationale: Reconcile the Constitution with the actual implementation stack ratified in
           history/adr/ADR-001-implementation-stack-reconciliation.md and the in-code T027 decision.

Modified sections:
  - §9.2 Horizontal Scalability — "Next.js (SSR)" row → "Vite + React SPA (static)" (CDN edge, no SSR)
  - §15.1 CI Build stage — "Next.js production build" → "Vite production build"
  - §18 Hackathon Must-Ship — frontend "Next.js App Router" → "Vite 5 + React 18 + TypeScript SPA";
    backend "Neon PostgreSQL + Prisma" → "Neon PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic" (ratifies T027)

Unchanged (deliberately):
  - §14.1 Package Managers — pnpm + uv stay mandated; package-lock.json stays forbidden.
    The code will COMPLY (switch npm → pnpm, add uv.lock) rather than amend. Tracked as a follow-up task.
  - §9.1 client budgets (LCP < 2.5s, initial JS < 300KB gz) and §10 Accessibility (WCAG 2.1 AA) intact.
  - No §3 Security, §4 Privacy, or §5 AI-safety control weakened.

Templates / artifacts status:
  - .specify/templates/plan-template.md      ⚠ pending review for stack references
  - .specify/templates/spec-template.md      ⚠ pending review for stack references
  - .specify/templates/tasks-template.md     ⚠ pending review for stack references
  - .qoder + .claude agents (frontend-specialist, backend-specialist, constitution-guardian, pr-reviewer)  ⚠ pending: drop "known deviation" callouts
  - .qoder + .claude skills (sp-plan, sp-implement, sp-adr, constitution-check)  ⚠ pending: drop stack-conflict notes
  - CLAUDE.md / AGENTS.md                    ⚠ pending: update stack references
  - history/adr/ADR-001-...md                ⚠ pending: Proposed → Accepted
  - backend/prisma/ (dead scaffold)          ⚠ pending: delete + fix stale T027 comments
-->

# ROXY JARVIS — Project Constitution

**Codename**: ROXY JARVIS  
**Version**: 2.0.0  
**Status**: Permanent Rulebook — All future work must comply

This Constitution is the non-negotiable governing document for the entire project. Every specification, architectural decision, task, pull request, and line of code MUST align with it. Deviations require explicit written amendment and team approval.

**Ratification Date**: 2026-09-03  
**Last Amended**: 2026-09-03  
**Amendment Procedure**: Any addition, removal, or redefinition of a principle requires a team-approved PR. Major version bumps (backward-incompatible governance changes) require unanimous consent. Minor versions (new or materially expanded sections) require at least two approvals. Patches (clarifications only) require one approval.

---

## 1. Engineering Principles

### 1.1 Core Axioms

- **Clarity over cleverness**: Code must be readable by a new contributor in under 15 minutes.
- **Simplicity first**: Prefer the simplest solution that satisfies the current milestone. Complexity is only added when proven necessary and documented.
- **Fail fast, fail loud**: Invalid states are detected early at the boundary and reported clearly with typed errors.
- **Immutable by default**: Prefer immutable data structures and pure functions. Mutable state must be contained and documented.
- **Explicit over implicit**: No magic. Configuration, dependencies, and side-effects must be visible in code.
- **Incremental delivery**: Every merged change MUST leave the system in a deployable, demonstrable state.

### 1.2 Architecture Philosophy

- **Modular Monolith (Phase 1)**: The application starts as a Modular Monolith. Every module boundary MUST be drawn as if that module will become a microservice. No module may import from another module's internals — only from its public interface.
- **Domain-Driven Design (DDD)**: The codebase follows DDD with explicit Bounded Contexts per feature. Domain logic lives in the Domain layer and is framework-agnostic.
- **SOLID Principles**:
  - **S**ingle Responsibility: Each class/module has one reason to change.
  - **O**pen/Closed: Open for extension, closed for modification.
  - **L**iskov Substitution: Subtypes must be substitutable for their base types.
  - **I**nterface Segregation: Prefer small, specific interfaces over large ones.
  - **D**ependency Inversion: Depend on abstractions, not concretions.
- **Composition over inheritance**: Use composition to share behavior; inheritance is permitted only within a single Domain aggregate.
- **Dependency Injection**: All external service dependencies (AI providers, databases, caches, tool executors) MUST be injected, never instantiated inline.

### 1.3 AI Provider Abstraction (No Vendor Lock-In)

The system MUST support multiple AI providers simultaneously. Provider switching MUST NOT require changes to agent code, tool code, or business logic.

**Supported Provider Tiers**:
| Priority | Provider | Use Case |
|----------|----------|----------|
| Primary | DeepSeek | Cost-efficient reasoning |
| Primary | Grok (xAI) | Creative/informal tasks |
| Primary | ChatGPT / OpenAI | General-purpose, fallbacks |
| Primary | Gemini (Google) | Long-context, multimodal |
| Secondary | Ollama / vLLM / Groq | Local/offline, cost optimization |

**Rules**:
- All providers MUST implement a shared `AIProvider` interface with: `chat(messages, options)`, `embeddings(text, options)`, `token_count(text)`.
- Model routing logic MUST be externalized (configurable, not hardcoded). Users can see and override which model handles their request.
- Adding a new provider requires zero changes to any agent, tool, or memory component.
- Removing a provider MUST be handled gracefully with a fallback to the next priority.

### 1.4 Feature-First Organization

Source code is organized by **feature** (Bounded Context), not by technical layer:

```
src/
  auth/                 # Auth feature — all code for this context
    domain/             # Entities, value objects, domain events
    application/       # Use cases, services, DTOs
    infrastructure/    # Provider implementations, repositories
    interface/         # Controllers, API routes, adapters
  chat/
  memory/
  agents/
  planning/
  tools/
  knowledge/
  security/
shared/                 # Truly cross-cutting code only (errors, logging, tracing)
```

---

## 2. Architecture Principles

### 2.1 System Layers

The system is divided into the following layers. **No layer may skip another** — all communication flows through the defined hierarchy:

```
┌─────────────────────────────────────────────────────────────────┐
│  INTERFACE LAYER      │ External consumers (UI, API, webhooks)  │
├─────────────────────────────────────────────────────────────────┤
│  INPUT LAYER          │ Input validation, sanitization, parsers  │
├─────────────────────────────────────────────────────────────────┤
│  BRAIN LAYER          │ Orchestration, decision-making          │
├─────────────────────────────────────────────────────────────────┤
│  MEMORY LAYER         │ Short-term + long-term memory, RAG      │
├─────────────────────────────────────────────────────────────────┤
│  PLANNING LAYER       │ Goal decomposition, task scheduling       │
├─────────────────────────────────────────────────────────────────┤
│  TOOL LAYER           │ Tool definitions, sandboxing, execution  │
├─────────────────────────────────────────────────────────────────┤
│  AGENT LAYER          │ Specialist agents, role definitions     │
├─────────────────────────────────────────────────────────────────┤
│  AUTOMATION LAYER     │ Scheduled jobs, webhooks, triggers      │
├─────────────────────────────────────────────────────────────────┤
│  KNOWLEDGE LAYER      │ Knowledge bases, vector search, RAG     │
├─────────────────────────────────────────────────────────────────┤
│  SECURITY LAYER       │ AuthN/AuthZ, audit logging, isolation   │
└─────────────────────────────────────────────────────────────────┘
```

**Layer Communication Rules**:
1. Layers communicate **only downward** (Interface → Input → Brain → Memory → ...).
2. **No circular dependencies** between layers or between features.
3. Each layer exposes a **public interface** (abstract class or protocol). Internal implementation details are private.
4. Cross-feature communication happens via **Domain Events** or **Application Services**, never via direct imports.
5. The Security Layer is **special**: it wraps every layer as middleware, never the reverse.

### 2.2 Contract-First Design

**Frontend ↔ Backend Contract**:
- All API contracts MUST be defined using OpenAPI 3.1 (YAML) before implementation begins.
- The backend generates server stubs from the OpenAPI spec; the frontend generates type-safe clients.
- Contract changes require a version bump following the API Versioning policy (§12).
- The `contracts/` directory holds all shared API schemas as the **single source of truth**.

**Provider Abstraction Contract**:
- Every AI provider implements `src/ai/providers/base.py` (Python) / `src/ai/providers/base.ts` (TypeScript).
- Provider-specific code lives exclusively in the provider implementation; no business logic references a specific provider.

---

## 3. Security Principles

### 3.1 OWASP Top 10 Compliance

All code MUST comply with OWASP Top 10 (2021) as a minimum baseline:

| OWASP Category | ROXY Rule |
|----------------|-----------|
| A01 Broken Access Control | Every endpoint enforces AuthZ. Role-based and attribute-based access control (RBAC/ABAC) MUST be implemented. |
| A02 Cryptographic Failures | TLS 1.3 mandatory. Data at rest encrypted via Neon PostgreSQL encryption. No custom cryptography. |
| A03 Injection | Parameterized queries only. LLM prompt injection defended per §3.3. |
| A04 Insecure Design | Threat modeling required for every new feature. Secure design review in PR. |
| A05 Security Misconfiguration | Hardened defaults. Auto-configured CSP, CORS, rate limiting. No debug mode in production. |
| A06 Vulnerable Components | Dependency scanning in CI (Dependabot or equivalent). No component with known CVSS > 6.0. |
| A07 Auth & AuthZ Failures | MFA required for privileged accounts. Session tokens expire. |
| A08 Data Integrity Failures | Immutable audit log for all sensitive actions. Tamper-evident logging. |
| A09 Logging & Monitoring | All security events logged with user ID, IP, action, timestamp. Alerting on anomalies. |
| A10 SSRF | All outbound requests from tools validated against allowlists. No direct user input to internal services. |

### 3.2 Prompt Injection Defense

Because ROXY processes user-controlled text that may contain malicious prompts, the following rules are **mandatory** for every AI interaction:

1. **Input Sanitization**: User input is pre-processed to detect and escape common prompt injection patterns (e.g., "ignore previous instructions", "system prompt override attempts").
2. **Tool Call Allow-listing**: Agents may only call tools enumerated in an explicit allowlist. Dynamic tool construction from user input is forbidden.
3. **Output Validation**: AI responses that would trigger tool execution MUST pass output filtering before execution.
4. **Structural Isolation**: User messages are never prepended to system prompts without clear demarcation and escaping.
5. **Content Classification**: All tool-callable responses are classified before execution; actions above the user's approval tier are held for confirmation.

### 3.3 Sandboxed Tool Execution

Any tool that touches the filesystem, terminal, or smart-home devices **MUST** run in a sandboxed environment:

| Tool Category | Sandbox Required | Execution Mode |
|--------------|------------------|----------------|
| Read-only file operations | Yes | Firecracker microVM or gVisor |
| Write file operations | Yes + immutability verification | Firecracker microVM |
| Terminal/shell commands | Yes | Nested container with seccomp + sysbox |
| Browser automation | Yes | Dedicated browser process with isolated profile |
| Smart-home / IoT | Yes + network isolation | Separate VLAN + device-level approval |
| Network requests | Yes | Egress allowlist only; no direct IP targets |

**Tool execution MUST NOT**:
- Access the host filesystem outside the designated workspace
- Establish direct network connections to internal services
- Execute code not bundled in the tool definition
- Persist state between invocations without explicit memory layer integration

### 3.4 Secrets Management

| Rule | Enforcement |
|------|-------------|
| Secrets NEVER in code | Static analysis scan in CI |
| Secrets NEVER in logs | Structured logging auto-redacts known secret field names |
| Secrets NEVER in client bundles | Bundle size + content scan in CI |
| Secrets in `.env` files only | `.env.example` committed; `.env` in `.gitignore` |
| Production secrets in secret manager | HashiCorp Vault or AWS Secrets Manager; injected at runtime |

### 3.5 Per-Action Approval Tiers

Every action the agent can take falls into one of three tiers:

| Tier | Name | Trigger Condition | Behavior |
|------|------|------------------|----------|
| **T1** | Auto-run | Read-only, no side effects, no cost | Executes immediately; logged |
| **T2** | Confirm-tap | Side effects limited to user context (e.g., send message, save file) | Shows user a confirmation prompt; waits for explicit approval |
| **T3** | PIN-or-biometric | High-stakes actions (finance, IoT control, data deletion, external API calls) | Requires PIN entry or biometric confirmation |

**Default Assignments** (overridable per-user, per-session):

| Action Category | Default Tier |
|-----------------|--------------|
| Read news, weather, web search | T1 |
| Compose and send email | T2 |
| Write to filesystem | T2 |
| Execute terminal command | T3 |
| Control smart-home devices | T3 |
| Delete user data | T3 |
| Make payments / financial actions | T3 |
| Grant app permissions | T3 |

### 3.6 Audit Logging

All T2 and T3 actions produce an **immutable audit log entry** containing:
- `timestamp`, `user_id`, `session_id`, `action_type`, `action_detail`, `approval_tier`, `approved_by`, `model_used`, `provider`, `outcome`

Audit logs are stored in an append-only table (no UPDATE/DELETE permissions) in Neon PostgreSQL.

---

## 4. Privacy-First Design

### 4.1 Data Minimization

- Collect only the minimum data required for each feature to function.
- Data that is not strictly required for a feature MUST NOT be collected.
- Every data field MUST have a documented retention policy.

### 4.2 Explicit Consent for Memory Storage

- Before any conversation content is stored for long-term memory, **explicit user consent is required** (opt-in, not opt-out).
- Users can revoke memory consent at any time; upon revocation, all user-scoped memory is permanently deleted within 72 hours.
- Short-term conversation context (session-scoped) does not require consent but is automatically purged when the session ends.

### 4.3 User Data Rights

| Right | Requirement |
|-------|-------------|
| **Export** | One-click full data export in JSON within 48 hours of request |
| **Delete everything** | "Delete my account and all data" MUST permanently delete all user data within 30 days |
| **Portability** | Export format MUST be importable by the user into a competing service |

### 4.4 Rules for Third-Party LLM Providers

| Data Type | May Send to Third-Party LLM Provider? |
|-----------|--------------------------------------|
| Conversation text (user query + agent response) | Only if user has not opted out of cloud AI processing |
| User profile metadata (name, email, preferences) | Never — only anonymized user ID passed as context |
| File contents provided by user | Only if user explicitly attaches file to the conversation |
| System prompt / agent configuration | Never — server-side only |
| Tool execution results (file reads, command output) | Only when user initiated the tool call |
| Memory context | Only with explicit memory consent |
| Any data the user has not seen or approved | Never |

**Data Residency**: Users in regulated jurisdictions may opt for data residency guarantees. Third-party LLM calls MUST route through regions chosen by the user.

---

## 5. AI Safety

### 5.1 Agent Autonomy Limits

Agents operate within defined autonomy boundaries:

| Autonomy Level | Definition | Requires Human-in-the-Loop? |
|----------------|-----------|---------------------------|
| **Unattended** | Agent acts autonomously within its defined role and tier constraints | No (within T1 actions) |
| **Supervised** | Agent plans and executes but T2/T3 actions require approval | Yes (for T2/T3) |
| **Ask-First** | Agent MUST describe intended action and wait for explicit approval before any tool execution | Always |

**Override Rules**:
- Users can always reduce autonomy (force Ask-First mode for all actions).
- Users can increase autonomy (Auto-run for T2) only for specific trusted sessions.
- IoT control, financial actions, and data deletion are **never fully unattended**.

### 5.2 Model Routing Transparency

- The user MUST be able to see which model and provider handled each response (visible in the UI).
- The user MUST be able to override model selection per-conversation or per-message.
- When automatic routing selects a different model than requested, the UI displays: "Routed to [model] ([provider]) for [reason]".

### 5.3 Guardrails Against Unsafe Tool Execution

- Any tool call that would result in data deletion, system-wide changes, or external network calls is blocked unless the user's approval tier is satisfied.
- A **kill switch** is available to the user at any time: immediately revokes all pending approvals and suspends the session.
- Tools that return error responses are logged; repeated failures from the same tool trigger automatic circuit-breaker suspension.

---

## 6. Coding Standards

### 6.1 TypeScript (Frontend)

| Rule | Requirement |
|------|-------------|
| `strict` mode | MUST be enabled in `tsconfig.json` |
| `noImplicitAny` | `true` — no `any` types allowed |
| Explicit return types | All function and method return types MUST be declared |
| Naming conventions | `camelCase` for variables/functions; `PascalCase` for types/classes/interfaces; `SCREAMING_SNAKE_CASE` for constants |
| Imports | Absolute imports via `@/` alias; no relative import depth > 3 |
| Error handling | All async code wrapped in try/catch; custom `AppError` types |
| File naming | `kebab-case.ts` for files; `PascalCase.tsx` for React components |
| Folder structure | Feature-first (per §1.4); no generic `utils/` or `helpers/` directories at the root level |

**Forbidden**: `any`, `as any`, `// @ts-ignore`, non-explicit `any` return types, barrel imports that import more than needed.

### 6.2 Python (Backend)

| Rule | Requirement |
|------|-------------|
| Type hints | Mandatory on all function signatures (including private methods) |
| Pydantic v2 | All request/response models, configuration, and domain objects use Pydantic v2 |
| Async-first | All I/O operations use `async`/`await`; sync code only when async is not available |
| Error handling | Custom exception classes per module; no bare `except:` |
| Logging | Use `structlog` for structured JSON logs; no `print()` statements |
| File naming | `snake_case.py` |
| Import ordering | Standard library → third-party → local (enforced by isort) |

**Forbidden**: Untyped Python, bare `except Exception:`, synchronous blocking I/O in request handlers.

### 6.3 Linting and Formatting

| Layer | Tools | Configuration |
|-------|-------|---------------|
| Frontend | ESLint (flat config) + Prettier | `.eslintrc.cjs` + `.prettierrc`; zero tolerance for errors in CI |
| Backend | Ruff + Black | `pyproject.toml`; Ruff for linting + import sorting, Black for formatting |

CI pipeline MUST fail if any linting or formatting errors are present.

---

## 7. Testing Requirements

### 7.1 Coverage Thresholds

| Layer | Metric | Minimum Coverage |
|-------|--------|-----------------|
| Domain / Business Logic | Line coverage | ≥ 90% |
| Application Services | Line coverage | ≥ 85% |
| Infrastructure (repositories, providers) | Line coverage | ≥ 75% |
| API Endpoints | Line coverage | ≥ 80% |
| Frontend UI components | Statement coverage | ≥ 70% |
| Critical paths (auth, payments, data deletion) | Branch coverage | ≥ 95% |

Coverage reports are generated in every CI run and published to the PR. Coverage MUST NOT decrease below the threshold without documented justification.

### 7.2 Testing Tools

| Layer | Tool | Scope |
|-------|------|-------|
| Frontend unit | Vitest | Component logic, hooks, utilities |
| Frontend e2e | Playwright | Critical user journeys, authentication flows |
| Backend unit | pytest + pytest-asyncio | Domain logic, services, edge cases |
| Backend integration | pytest + Testcontainers | API boundaries, database, AI provider abstraction |
| Contract testing | Pact or equivalent | Frontend ↔ Backend API contracts |
| Load testing | k6 or locust | p95 latency targets, throughput |

### 7.3 Independently Testable Tasks

A task is **independently testable** if:
1. It can be implemented and validated without requiring any other incomplete task.
2. It has a clear input → output contract that can be verified by a test.
3. It does not modify shared infrastructure (DB schema, auth system) that other stories depend on.

Every implementation task MUST have a corresponding test task in the same or a directly related file.

### 7.4 Test Quality Rules

- Tests are **deterministic**: no flaky tests; no tests that depend on time, random values, or external network calls without mocking.
- Tests run **fast**: unit tests < 200ms each; integration tests < 5s each.
- Every bug fix MUST include a regression test that fails before the fix and passes after.
- Mock external services (AI providers, third-party APIs) in unit and integration tests.

---

## 8. Documentation Standards

### 8.1 Required Documentation

| Document | Location | Owner | Update Frequency |
|----------|----------|-------|-----------------|
| README | `README.md` | All contributors | Every PR that changes setup |
| Architecture Decision Records | `history/adr/*.md` | Architect | Every significant decision |
| API documentation | `docs/api/` (OpenAPI YAML) | Backend | Every API change |
| Schema documentation | `docs/database/` | Backend | Every schema migration |
| Component library | `docs/components/` | Frontend | Every UI component change |
| Deployment guide | `docs/deployment/` | DevOps | Every infrastructure change |
| Troubleshooting guide | `docs/troubleshooting.md` | All | Every support ticket with new root cause |

### 8.2 Docs-in-Same-PR Rule

**CRITICAL**: Documentation MUST be updated in the **same PR** as the code that makes the change. PRs that change behavior or configuration without updating relevant documentation are **NOT mergeable**.

- If you change an API endpoint, update the OpenAPI spec in the same PR.
- If you change a configuration option, update the deployment guide in the same PR.
- If you introduce a new tool, add it to the tool documentation in the same PR.
- Documentation-only changes are exempt from this rule (they ARE the change).

### 8.3 README Requirements

The README MUST allow a new developer to:
1. Understand the project in under 5 minutes.
2. Run the project locally with `docker compose up` in under 10 minutes.
3. Run the test suite in under 5 minutes.

---

## 9. Performance & Scalability Requirements

### 9.1 Latency Budgets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Time-to-first-token (streaming chat) | < 1.5 s average; < 3 s p95 | End-to-end from user request to first token received |
| API p95 latency (non-AI endpoints) | < 300 ms | Backend request → response, excluding AI processing |
| API p95 latency (AI chat, non-streaming) | < 5 s for 512-token response | Measured at p95 across all providers |
| Page load (LCP) | < 2.5 s on mid-range mobile (Moto G Power) | Lighthouse mobile, simulated 4G |
| Page Interactive (TTI) | < 3.5 s on mid-range mobile | Lighthouse mobile |
| Vector search (RAG retrieval) | < 200 ms p95 | pgvector/Qdrant query time |

### 9.2 Horizontal Scalability

| Component | Scaling Strategy |
|-----------|-----------------|
| FastAPI workers | Stateless; scale behind load balancer; target ≤ 1000 requests/worker |
| Vite + React SPA (static) | Static hosting / CDN edge caching; no SSR; auto-scale via CDN |
| Redis | Cluster mode for cache and queue; read replicas for read-heavy workloads |
| Neon PostgreSQL | Connection pooling via PgBouncer; auto-scale compute |
| Vector search | pgvector (≤ 1M embeddings) or Qdrant (≥ 1M embeddings) |
| Background workers | Redis Queue (RQ) or Celery; scale workers independently |

### 9.3 Resource Budgets

- Backend worker memory ceiling: 512 MB per worker (enforced via container limits).
- Frontend bundle size: < 300 KB initial JS (gzipped); code-split beyond that.
- Token budget: Every AI call MUST log token usage; monthly budget alerts at 80% of plan limit.

---

## 10. Accessibility

### 10.1 WCAG 2.1 AA Baseline

All UI MUST meet WCAG 2.1 AA:

| Criterion | Rule |
|-----------|------|
| Perceivable | All images have alt text; videos have captions; color is not the only indicator of state |
| Operable | Full keyboard navigation; no keyboard traps; visible focus indicators; no time limits without escape |
| Understandable | Consistent navigation; error messages with suggestions; labels on all form inputs |
| Robust | Valid HTML; ARIA roles where native semantics are insufficient |

### 10.2 Chat Interface Requirements

- Screen-reader compatible: live regions for streaming responses (`aria-live="polite"`).
- Keyboard navigable: Enter to send, Escape to cancel streaming, Tab through buttons.
- High contrast mode support.
- Adjustable font size (respects `rem` units and browser zoom).

---

## 11. Maintainability & Observability

### 11.1 Structured Logging

All services emit JSON-formatted logs with a consistent schema:

```json
{
  "timestamp": "2026-09-03T12:00:00.000Z",
  "level": "info",
  "service": "backend",
  "trace_id": "abc123",
  "span_id": "def456",
  "user_id": "user_789",
  "event": "ai.chat.response",
  "duration_ms": 1423,
  "provider": "deepseek",
  "model": "deepseek-chat-v2.5",
  "tokens_used": 847
}
```

**Forbidden**: Free-text log messages in production; `console.log` (frontend) without structured logger; f-strings or `%s` formatting in backend logs.

### 11.2 Tracing

- Every request MUST carry a `trace_id` propagated from the frontend (via `X-Trace-ID` header) through all backend services.
- All database queries, AI provider calls, and tool executions create child spans.
- Trace data is exported to a tracing backend (Jaeger, Tempo, or equivalent) in staging and production.

### 11.3 Metrics

Every service MUST expose the following metrics at `/metrics` (Prometheus format):

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency p50, p95, p99 |
| `ai_tokens_used_total` | Counter | Tokens by provider, model, user |
| `ai_request_duration_seconds` | Histogram | AI provider latency |
| `ai_errors_total` | Counter | AI provider errors by provider, error_type |
| `tool_executions_total` | Counter | Tool executions by tool_name, outcome |
| `active_sessions` | Gauge | Current concurrent user sessions |
| `db_connections_active` | Gauge | Active DB connections |
| `cache_hit_ratio` | Gauge | Redis cache hit ratio |

### 11.4 Health Checks

Every service exposes:
- `/health/live` → returns `200 OK` if the process is alive
- `/health/ready` → returns `200 OK` if the service can handle requests (DB connected, cache connected, AI provider reachable)

### 11.5 Error Handling Conventions

| Rule | Enforcement |
|------|-------------|
| No silent failures | Every error MUST be either raised, caught with logging, or returned to the caller |
| Typed errors | Custom exception classes per module; no bare `Exception` catching |
| Error taxonomy | All errors classified as: `AUTH_ERROR`, `VALIDATION_ERROR`, `PROVIDER_ERROR`, `TOOL_ERROR`, `INTERNAL_ERROR` |
| User-facing errors | Friendly, actionable messages in user's language; never leak internal details |
| Internal errors | Full diagnostic context (stack trace, request ID, user ID) logged server-side only |
| Circuit breakers | AI providers and external APIs wrapped in circuit breakers; open after 5 consecutive failures, half-open after 30 s |

---

## 12. API Versioning

### 12.1 Versioning Policy

- **URL-based versioning**: All public APIs are versioned (`/api/v1/`, `/api/v2/`).
- **Version lifecycle**:
  1. **Active**: Fully supported; security patches applied.
  2. **Deprecated**: No new features; security patches applied; sunset date announced.
  3. **Sunset**: Returns `410 Gone` with migration guidance.

### 12.2 Breaking Changes Definition

A **breaking change** (requires major version bump: `v1` → `v2`):
- Removing or renaming an endpoint
- Removing or renaming a required request parameter
- Changing a response shape (removed fields, changed types)
- Changing authentication/authorization requirements
- Increasing rate limits or decreasing resource quotas

A **non-breaking change** (minor version bump):
- Adding new optional request parameters
- Adding new response fields
- Adding new endpoints

### 12.3 Deprecation Timeline

| Phase | Duration | Action |
|-------|----------|--------|
| Announcement | Day 0 | Deprecated version marked in OpenAPI spec with `deprecated: true` |
| Notice period | Minimum 90 days | Response includes `Deprecation: true` header + `Sunset` date header |
| Removal | Day 91+ | Returns `410 Gone` with JSON error: `{"error": "deprecated", "migrate_to": "/api/v2/..."}` |

---

## 13. Git Workflow & Branch Strategy

### 13.1 Branch Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/<number>-<short-description>` | `feature/042-user-auth` |
| Bug fix | `fix/<number>-<short-description>` | `fix/051-chat-scroll-bug` |
| Hotfix | `hotfix/<number>-<description>` | `hotfix/099-security-patch` |
| Chore | `chore/<short-description>` | `chore/update-dependencies` |
| Docs | `docs/<short-description>` | `docs/api-auth-guide` |

### 13.2 Trunk-Based Development

- The `main` branch is the single source of truth; it is **always deployable**.
- Feature branches are short-lived (≤ 3 days); branch from `main` and merge via PR.
- No "develop" branch; no long-lived feature branches.
- Hotfixes branch from `main` and merge back with expedited review.

### 13.3 PR Size Limits

| PR Size | Lines Changed | Rule |
|---------|---------------|------|
| Small (Preferred) | < 200 lines | Can be reviewed in < 30 minutes |
| Medium | 200–500 lines | Requires justification in PR description |
| Large | > 500 lines | MUST be broken into multiple PRs before review |

Large PRs require architect approval before review begins.

### 13.4 Required Reviews

| Change Type | Approvals Required |
|-------------|-------------------|
| Any code change | Minimum 1 reviewer |
| Security-sensitive (auth, payment, data deletion) | Minimum 2 reviewers; at least 1 must be a senior engineer |
| Architecture or infrastructure | Minimum 2 reviewers; architect must be one of them |
| Hotfixes | Expedited review; 1 approval sufficient with documented justification |

### 13.5 Commit Convention

All commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `hotfix`

**Examples**:
```
feat(auth): add magic link authentication
fix(chat): resolve streaming response truncation on long messages
docs(api): update /chat/completions endpoint description
perf(memory): optimize vector search query for < 10ms
```

---

## 14. Dependency & Environment Management

### 14.1 Package Managers

| Layer | Tool | Lockfile |
|-------|------|----------|
| Frontend | pnpm | `pnpm-lock.yaml` — committed |
| Backend | uv | `uv.lock` — committed |

**Forbidden**: `npm`, `yarn`, `pip` without `uv`; `package-lock.json`; direct `requirements.txt` commits.

### 14.2 Dependency Rules

- New dependencies MUST be justified in the PR (why needed; alternatives considered).
- Dependencies with known vulnerabilities (CVSS ≥ 7.0) MUST be updated or mitigated within 7 days.
- Monthly dependency audit: `pnpm audit` (frontend) and `pip-audit` / `safety` (backend).
- No transitive dependency may pull in a conflicting version without explicit resolution in `pnpm-overrides` / `uv.lock`.

### 14.3 Environment Management

| Environment | Purpose | Secret Source |
|-------------|---------|---------------|
| `local` | Development on contributor machines | `.env.local` (not committed) |
| `staging` | Pre-production testing | Secret manager injection |
| `production` | Live system | Secret manager injection |

**`.env.example`**: Every environment variable MUST have a commented entry in `.env.example` with its purpose and a placeholder value. This file IS committed.

**Twelve-Factor App**: All configuration via environment variables; no config in code.

---

## 15. CI/CD Standards

### 15.1 GitHub Actions Pipeline

Every PR and merge to `main` triggers the following stages (in order):

```
┌─────────────────────────────────────────────────────────┐
│ Stage 1: LINT                                           │
│   - ESLint (frontend)                                   │
│   - Ruff + Black (backend)                              │
│   - Type-check (tsc --noEmit)                           │
│   - Secret scan (git-secrets or equivalent)            │
├─────────────────────────────────────────────────────────┤
│ Stage 2: TEST                                           │
│   - Unit tests (Vitest frontend / pytest backend)       │
│   - Integration tests                                   │
│   - Contract tests                                      │
│   - Coverage report upload                              │
│   - Coverage gate (fails if below threshold)            │
├─────────────────────────────────────────────────────────┤
│ Stage 3: BUILD                                          │
│   - Docker image build (backend)                         │
│   - Vite production build (frontend)                    │
│   - Bundle size check                                   │
│   - Security scan (Trivy or equivalent)                │
├─────────────────────────────────────────────────────────┤
│ Stage 4: DEPLOY (merge to main only)                    │
│   - Deploy to staging (automatic)                        │
│   - Smoke tests against staging                         │
│   - Deploy to production (manual approval required)     │
└─────────────────────────────────────────────────────────┘
```

### 15.2 Docker & Docker Compose

- `Dockerfile` for backend; `Dockerfile.front` for frontend.
- `docker-compose.yml` for local development — **must exactly mirror production** configuration.
- `docker compose up` MUST bring up a fully functional local environment in under 2 minutes.
- No differences between local and production containers (same base image, same env vars).

---

## 16. Definition of Done

A feature or task is **Done** only when ALL of the following are satisfied:

### Code Quality
- [ ] Code is written, reviewed, and merged to `main`
- [ ] No lint errors, no type errors, no formatting violations
- [ ] Coverage meets or exceeds the threshold (§7.1) for the affected layer

### Testing
- [ ] Unit tests pass for all changed/added code
- [ ] Integration tests pass for all affected API boundaries
- [ ] E2E tests pass for all affected user journeys
- [ ] A regression test exists for every bug fixed

### Documentation
- [ ] README updated if setup or run instructions changed
- [ ] API documentation (OpenAPI) updated for every changed endpoint
- [ ] Database schema docs updated for every migration
- [ ] Tool documentation updated if a new tool was added or behavior changed
- [ ] All documentation changes are in the same PR as the code

### Security & Privacy
- [ ] OWASP checklist completed (per §3.1)
- [ ] No secrets in code (secret scan passes)
- [ ] Prompt injection defenses reviewed for any AI interaction change
- [ ] Privacy impact assessed if user data handling changed

### Accessibility & UX
- [ ] WCAG 2.1 AA checklist completed
- [ ] Keyboard navigation tested
- [ ] Screen reader tested for any new UI
- [ ] Works in both light and dark modes
- [ ] Mobile responsive at 375px and 768px breakpoints

### Internationalization
- [ ] All user-facing strings are i18n keys (no hardcoded strings)
- [ ] Tested in English and at least Urdu and one additional language
- [ ] RTL layout tested for Urdu

### Observability
- [ ] All new endpoints have health check implementations
- [ ] Structured logs added for new operations
- [ ] New metrics added to `/metrics` endpoint if new operations are introduced
- [ ] Distributed tracing propagates `trace_id` through new critical paths

### Performance
- [ ] No new N+1 query patterns introduced
- [ ] Bundle size impact assessed (no regression > 10 KB gzipped)
- [ ] Latency impact assessed against §9.1 budgets

---

## 17. Non-Functional Requirements Summary

| Category | Requirement | Target |
|----------|-------------|--------|
| **Performance** | Chat first-token time | < 1.5 s avg / < 3 s p95 |
| **Performance** | API p95 (non-AI) | < 300 ms |
| **Performance** | Page LCP (mobile) | < 2.5 s |
| **Performance** | Vector search p95 | < 200 ms |
| **Scalability** | Concurrent users | Designed for 10× current load |
| **Security** | OWASP compliance | Top 10 (2021) AA |
| **Security** | Data encryption | TLS 1.3 + at-rest |
| **Security** | Audit log | Immutable; all T2/T3 actions |
| **Privacy** | Data residency | Configurable per user jurisdiction |
| **Privacy** | Data export | One-click JSON within 48 h |
| **Privacy** | Data deletion | Full deletion within 30 days |
| **Privacy** | LLM data rules | Per §4.4 (never send PII without consent) |
| **Accessibility** | WCAG | 2.1 AA minimum |
| **Accessibility** | Keyboard nav | Full support |
| **Accessibility** | Screen reader | Chat interface compatible |
| **i18n** | Languages | English (en), Urdu (ur), Arabic (ar) |
| **i18n** | RTL | Full support for Urdu and Arabic |
| **i18n** | Implementation | next-intl |
| **Mobile** | Responsive | 375px, 768px, 1024px breakpoints |
| **Mobile** | PWA | Service worker, manifest, offline chat core |
| **Reliability** | Uptime (production) | ≥ 99.5% SLO |
| **Observability** | Logging | Structured JSON; all services |
| **Observability** | Tracing | Distributed; trace_id propagation |
| **Observability** | Metrics | Prometheus format; all services |
| **Compatibility** | Browser support | Chrome, Firefox, Safari, Edge (latest 2 versions) |
| **Compatibility** | API versioning | URL-based; 90-day deprecation notice |

---

## 18. Post-Hackathon Expansion

The hackathon scope (3–4 days) covers a solid, working core:

### Hackathon Must-Ship

- Auth (magic link + Google/GitHub OAuth)
- Responsive chat UI with streaming responses
- Multi-provider AI abstraction (DeepSeek, Grok, ChatGPT, Gemini)
- Basic conversation memory + semantic memory (RAG)
- Coordinator + two specialist agents (Coding, Research)
- Neon PostgreSQL + SQLAlchemy 2.0 async ORM + Alembic (backend); Vite 5 + React 18 + TypeScript SPA (frontend)
  - Persistence MUST sit behind a clean repository / Unit-of-Work boundary so the ORM can be swapped later without touching domain or service layers (ratifies the in-code T027 decision; see ADR-001).
- Light/Dark mode
- Basic i18n (English + Urdu + Arabic)
- Docker Compose local setup
- Audit log for sensitive actions
- WCAG 2.1 AA baseline

### Explicitly Deferred (Designed For, Not Built)

- Full Home/IoT + Matter/Thread + geofencing
- Screen-watching mode
- Plugin marketplace
- Bank aggregation / Health wearable deep integration
- Advanced cross-device handoff
- Wake-word activation
- Full cost dashboard polish
- Production multi-region deployment
- Advanced rate limiting and quotas

**Post-hackathon**, the same Constitution continues to govern all expansion without architectural rewrites. Every deferred item above is designed to slot into the existing layer architecture.

---

This Constitution is **living only through formal amendment**. All contributors are bound by it. It is written to be authoritative and detailed enough that every future decision can be checked against it. When in doubt, ask first.
