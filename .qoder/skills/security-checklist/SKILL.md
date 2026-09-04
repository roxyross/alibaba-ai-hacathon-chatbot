---
name: security-checklist
description: Run the pre-merge security and privacy checklist for ROXY JARVIS (Constitution §3 Security, §4 Privacy). Use before opening or approving any PR that touches auth, AI interactions, tool execution, secrets, data storage, or public endpoints.
---

# Pre-merge security & privacy checklist

Run this checklist against the pending change (`git diff main...HEAD` unless a range is given) and report per-item results with file:line evidence for failures.

## Security (§3)

1. **OWASP Top 10 (§3.1)** — no SQL/command/template injection (parameterized queries only); every endpoint enforces AuthZ (RBAC/ABAC); outbound tool requests validated against allowlists (SSRF); inputs validated at system boundaries; no debug mode in prod.
2. **Prompt injection (§3.2)** — EVERY AI interaction has input sanitization, output validation before execution, tool-call allow-listing (no dynamic tool construction from user input), structural isolation of user messages, and content classification before tool calls.
3. **Sandboxing (§3.3)** — terminal/filesystem/browser/IoT tool execution runs sandboxed with explicit permission scopes; no host-FS access outside the workspace; egress allowlist only.
4. **Secrets (§3.4)** — grep the diff for keys/tokens/passwords; nothing sensitive in code, logs, or client bundles; `.env` only (`.env.example` committed, `.env` gitignored); prod via secret manager.
5. **Approval tiers (§3.5)** — T1 auto-run (read-only), T2 confirm-tap (user-context side effects), T3 PIN/biometric (finance, IoT, deletion, external API). Defaults honored; IoT/finance/deletion never fully unattended.
6. **Audit log (§3.6)** — every T2/T3 action writes an immutable, append-only entry with timestamp, user_id, session_id, action_type, action_detail, approval_tier, approved_by, model_used, provider, outcome.
7. **Transport/storage (§3.1 A02)** — TLS 1.3+ in transit; encryption at rest for user data; no custom cryptography.
8. **Resilience (§11.5)** — circuit breakers on AI providers/external APIs (open after 5 failures, half-open after 30 s); rate limiting on public endpoints (§3.1 A05).

## Privacy (§4)

9. **Minimal collection (§4.1)** — the change collects only data the feature requires; every field has a documented retention policy.
10. **Memory consent (§4.2)** — long-term memory storage is opt-in (explicit consent); revocation deletes user-scoped memory within 72 h; session context purged at session end.
11. **Data rights (§4.3)** — affected data remains user-scoped, exportable (one-click JSON ≤ 48 h), and deletable (≤ 30 days); portability preserved.
12. **Third-party LLM rules (§4.4)** — never send user profile metadata (only anonymized user ID), never send system prompt/agent config, memory context only with consent, nothing the user has not seen/approved.

## Verdict

- APPROVE — all applicable items pass.
- APPROVE WITH CONDITIONS — only minor items pending, explicitly listed.
- BLOCK — any of: missing prompt-injection protection on an AI path, secret in code/logs/bundle, unscoped tool execution, a T3 action without approval, missing audit entry on a T2/T3 action, or memory stored without opt-in consent.

State clearly which items were N/A and why. Do not modify code — report and hand fixes back to the implementer.
