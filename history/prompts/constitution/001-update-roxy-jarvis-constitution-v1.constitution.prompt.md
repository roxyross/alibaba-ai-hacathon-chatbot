---
id: "001"
title: "Update ROXY JARVIS Constitution v1.1.0"
stage: "constitution"
date: "2026-09-03"
surface: "agent"
model: "minimax/minimax-m2.7:free"
feature: "none"
branch: "master"
user: "local-user"
command: "/sp.constitution update my constitution.md file"
labels: ["constitution", "governance", "project-rules"]
links:
  spec: "null"
  ticket: "null"
  adr: "null"
  pr: "null"
files:
  - ".specify/memory/constitution.md"
  - ".specify/templates/plan-template.md"
  - ".specify/templates/spec-template.md"
  - ".specify/templates/tasks-template.md"
tests: []
---

## Prompt

Update my constitution.md file Create the complete project constitution for ROXY JARVIS, a production-grade, multi-platform AI assistant (Jarvis-style) built with Next.js 15 (TypeScript, App Router) on the frontend and FastAPI (Python) on the backend, using Neon PostgreSQL, Redis, and pgvector/Qdrant. This constitution is the permanent rulebook every later phase (Specify, Plan, Tasks, Implement) must comply with. Do not write any implementation code — only the governing rules and standards.

Cover every section below in full detail, with concrete rules (not vague platitudes) that a team could actually be held to:

1. Engineering Principles
Clean Architecture, Domain-Driven Design, Feature-first organization
Modular Monolith now, explicitly designed to split into microservices later without rewrites
SOLID principles, composition over inheritance, dependency injection conventions
No vendor lock-in for AI providers (OpenAI, Anthropic, Gemini, DeepSeek, local models via Ollama/vLLM)
2. Architecture Principles
Layer boundaries (Interface / Input / Brain / Memory / Planning / Tool / Agent / Automation / Knowledge / Security)
Rules for how layers communicate (no skipping layers, no circular deps)
Contract-first design between frontend (Next.js) and backend (FastAPI)
3. Security Principles
OWASP Top 10 compliance baseline
Prompt-injection defense rules (input sanitization, tool-call allow-lists, output filtering)
Sandboxed execution for any tool that touches filesystem, terminal, or smart-home devices
Secrets management (never in code/env committed, use a secrets manager)
Per-action approval tiers: auto-run / confirm-tap / PIN-or-biometric — define which action categories default to which tier
4. Privacy-First Design
Data minimization, explicit consent for memory storage
User-owned data export and "delete everything" requirement
Rules for what may/may not be sent to third-party LLM providers
5. AI Safety
Rules for agent autonomy limits (what agents can do unattended vs. must ask first)
Model routing transparency (user can see which model handled a request)
Guardrails against unsafe tool execution (e.g., destructive file/terminal ops)
6. Coding Standards
TypeScript conventions (strict mode, no any, naming, folder rules)
Python conventions (PEP8, type hints mandatory, Pydantic models)
Linting/formatting: ESLint + Prettier (frontend), Ruff/Black (backend)
7. Testing Requirements
Minimum coverage thresholds for unit/integration/e2e
Vitest + Playwright (frontend), Pytest (backend)
Definition of "independently testable" for tasks
8. Documentation Standards
README, ADRs, API docs (OpenAPI), schema docs, deployment/setup/troubleshooting guides
Docs must be updated in the same PR as the code that changes them
9. Performance & Scalability Requirements
Target latency budgets (chat first-token time, API p95, streaming)
Horizontal scalability expectations for backend services and workers
10. Accessibility
WCAG 2.1 AA baseline for all UI
11. Maintainability & Observability
Structured logging format, required trace/span conventions
Metrics and health-check requirements per service
Error handling conventions (typed errors, no silent failures)
12. API Versioning
URL or header-based versioning policy, deprecation timeline rules
13. Git Workflow & Branch Strategy
Branch naming, trunk-based vs. GitFlow decision, PR size limits
Required code review approvals before merge
14. Dependency & Environment Management
pnpm for frontend, uv/poetry for backend; lockfile policy
.env conventions per environment (dev/staging/prod)
15. CI/CD Standards
GitHub Actions pipeline stages (lint → test → build → deploy)
Docker/Docker Compose requirements for local parity with prod
16. Definition of Done
Explicit checklist a feature must satisfy before it's considered complete
17. Non-Functional Requirements Summary
Consolidate performance, security, accessibility, i18n (English + Urdu + one more language), mobile-responsiveness, and PWA requirements into one master NFR table

## Response snapshot

Comprehensive rewrite of `.specify/memory/constitution.md` from version 1.0 (hackathon-scoped) to v1.1.0 (production-grade rulebook).

**Version bump**: 1.0 → 1.1.0 (MINOR — expanded sections + materially expanded guidance)

**Key additions**:
- §1 Engineering: DDD, SOLID, Modular Monolith, AI provider abstraction contract, feature-first folder structure
- §2 Architecture: 10-layer system diagram with explicit communication rules, contract-first frontend/backend design
- §3 Security: OWASP Top 10 table, 5 prompt injection defense rules, sandbox matrix per tool category, 3-tier approval system with default assignments, immutable audit log schema
- §4 Privacy: Explicit third-party LLM data rules table, data residency requirements, user data rights
- §5 AI Safety: Autonomy levels (Unattended/Supervised/Ask-First), model routing transparency, kill switch
- §6 Coding: Strict TypeScript rules (no any, explicit return types), Python/Pydantic v2 rules, linting enforcement
- §7 Testing: Coverage thresholds per layer (90%/85%/75%/80%/70%/95%), independently testable definition
- §8 Docs: Required doc inventory, docs-in-same-PR rule (critical gate)
- §9 Performance: Latency budget table, horizontal scaling strategy, resource budgets
- §10 Accessibility: WCAG 2.1 AA with specific criteria
- §11 Observability: JSON log schema, Prometheus metrics inventory, health check endpoints, circuit breaker rules
- §12 API Versioning: URL-based, breaking change definition, 90-day deprecation timeline
- §13 Git Workflow: Branch naming convention, trunk-based development, PR size limits, approval matrix
- §14 Dependencies: pnpm/uv enforced, dependency audit rules
- §15 CI/CD: 4-stage GitHub Actions pipeline with gate criteria
- §16 DoD: 10-category explicit checklist
- §17 NFR Summary: Master table consolidating all NFRs

Templates checked: plan-template.md, spec-template.md, tasks-template.md — all align with updated constitution.

## Outcome

- ✅ Impact: Complete rewrite of project governance document; all future work must comply with v1.1.0 rules
- 🧪 Tests: No tests run (governance document update)
- 📁 Files: Updated `.specify/memory/constitution.md`; templates remain compatible
- 🔁 Next prompts: None — constitution update complete
- 🧠 Reflection: Existing v1.0 constitution was already solid; expanded from 225 lines to ~700 lines with concrete, enforceable rules. Templates verified compatible. Minor version bump (1.0 → 1.1.0) appropriate since all changes are additions/clarifications rather than breaking governance redefinitions.

## Evaluation notes (flywheel)

- Failure modes observed: None — template validation confirmed no broken references
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment (smallest change to try): N/A
