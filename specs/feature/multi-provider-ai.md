# Spec: Multi-Provider AI Abstraction

**Branch:** feature/multi-provider-ai
**Status:** Draft
**Date:** 2026-09-02
**Author:** AI (sp.specify)

---

## 1. Problem Statement

ROXY JARVIS must not be dependent on a single AI provider. Providers go down, change pricing, or degrade in quality. A multi-provider abstraction layer allows the system to route requests intelligently, fail over automatically, and always attribute responses correctly — with zero changes required to agent or tool code when providers change.

## 2. User Stories

- As the system, I want to route a request to the most appropriate available provider so that users get responses with minimal latency and cost.
- As the system, I want to automatically fail over to the next provider when one is unavailable so that uptime is maintained.
- As a user, I want every response to clearly show which model produced it so that I can evaluate trust and quality.
- As the system, I want to log token usage per provider so that cost tracking is possible.
- As an operator, I want to add a new provider by changing configuration only so that no agent code changes.
- As an operator, I want to disable a provider without redeploying agents so that I can respond to outages instantly.

## 3. Acceptance Criteria

- [ ] All AI requests go through a single Provider Abstraction Interface; agents never call providers directly.
- [ ] Adding or removing a provider requires only configuration changes, zero code changes in agents or tools.
- [ ] Requests include task metadata (type, urgency, cost-sensitivity) that the router uses to select provider.
- [ ] Automatic failover: if primary provider fails or times out (>10s), the request is retried with the next provider.
- [ ] Every response includes attribution metadata: { provider, model, agent }.
- [ ] Token usage per request is logged with provider and model identifiers.
- [ ] Providers supported at launch: DeepSeek, Grok (xAI), ChatGPT/OpenAI, Gemini.
- [ ] Provider health status is observable via health endpoint.
- [ ] Circuit breaker pattern prevents sustained calls to a failing provider.
- [ ] When all providers fail (all circuits open), the gateway returns a partial response with `provider_error: true` and `failed_provider` fields on the last chunk, rather than a hard 5xx.
- [ ] Prompt injection detection uses blocklist + structured prompt wrapping at the domain layer.
- [ ] Data retention for token logs: 90 days default, GDPR-compliant deletion on user request.

## 4. Out of Scope

- Open-source model integration (Ollama, vLLM, Groq) — secondary priority, deferred.
- Cost dashboard UI — deferred.
- Provider-specific fine-tuning or prompt templates per provider (uniform interface only).
- Automatic provider routing based on historical quality scores (future).
- Adaptive quality-based routing (requires historical data) — deferred post-hackathon.

## 5. Privacy & Security Considerations

- API keys for all providers stored in environment variables, never in code or logs.
- Provider requests are made over HTTPS/TLS 1.3.
- User prompts are not logged in plain text; only anonymized request metadata is stored for debugging.
- Prompt injection sanitization is applied at the domain layer before calling any provider. Detection uses a two-stage approach: (1) blocklist of known injection patterns (e.g., "ignore previous", "disregard instructions", "system prompt override" markers); (2) structured prompt wrapping that isolates user input in a bounded `user` role message, preventing instruction injection from breaking out of the `system` role context. Raises `PromptInjectionError` if blocklist triggers.
- Provider responses are validated (Pydantic model) before being passed to agents or rendered.
- **RBAC for provider management:** Only callers with the `admin` or `operator` role may call `PATCH /api/v1/ai/providers/{name}` to enable or disable a provider. Regular authenticated users may set their own `preferred_provider` but may not alter system-wide provider state.
- **Per-action approval levels:** Sensitive AI actions (executing terminal commands, deleting user data, sending external communications) require user confirmation at the `confirm` level per Constitution §3. The AI gateway propagates the required approval level in request metadata but enforcement is at the agent/tool layer.
- **Data retention for TokenUsageLog:** Logs are retained for 90 days by default. On user account deletion, all associated token logs are permanently deleted within 72 hours (GDPR right to erasure). Operators configure retention via `TOKEN_LOG_RETENTION_DAYS` env var.

## 6. Accessibility Considerations

- Provider attribution is displayed visually and is programmatically available (aria-label on attribution tag).
- If a provider fails, the user-facing error message is human-readable, not a technical code. A "switched to {provider}" event is surfaced in the chat UI only when the initial provider errored; seamless attribution badge update when failover was seamless (no error notification).
- Keyboard navigation for the chat interface must be fully functional (Tab to send, Enter to submit, arrow keys to navigate history).
- WCAG 2.2 AA color contrast is required for the attribution badge in both light and dark modes (minimum 4.5:1 for text).

## 7. Performance & Reliability Requirements

- **Per-provider timeout:** 10 seconds per request; on timeout the request fails over to the next provider.
- **p95 latency (non-streaming):** <300ms for the gateway's own routing and validation overhead (provider inference time is excluded — it varies by provider and model).
- **Time-to-first-token (streaming):** <1.5s from request receipt to first emitted chunk (Constitution §9). Provider inference time is included in this budget.
- **Circuit breaker parameters:** 5 consecutive failures opens the circuit; 30-second reset timeout; half-open state allows 1 probe request. Circuit closes after 2 consecutive successes. Configurable via `CIRCUIT_BREAKER_FAILURES`, `CIRCUIT_BREAKER_RESET_SECONDS` env vars.
- **Concurrency limit:** 50–100 concurrent requests per AI gateway instance. Horizontal scaling requires Redis-backed circuit breaker state (post-hackathon; in-memory only for hackathon).
- **Rate limiting:** Per-provider rate limits enforced by the AI gateway using a Redis token bucket (10,000 tokens/minute default). When a provider's rate limit is hit, the gateway fails over to the next available provider. If Redis is unavailable, rate limiting is disabled (fail-open for availability).
- **Health probe frequency:** The circuit breaker state is re-evaluated on every request; there is no background polling. The `/providers/health` endpoint reflects current state without triggering a probe.
- **Observability log fields (Standard):** Every AI gateway log line contains `request_id`, `provider`, `model`, `latency_ms`, `status` (pass/fail), `user_id`, `agent_id`, `input_tokens`, `output_tokens`. Prompt contents are never logged.

## 8. AI Safety Requirements

- **Multi-provider abstraction interface:** Formal `AIProviderAdapter` contract with `chatCompletion()` and `chatCompletionStream()` methods. Agents must use the abstraction interface exclusively; direct provider calls are prohibited.
- **Attribution metadata:** Every response (streaming and non-streaming) includes `provider`, `model`, and `agent_id` fields.
- **Safety guardrails for harmful requests:** The following categories of requests are refused at the domain layer with a `HarmfulRequestRefused` error before any provider is called:
  - Requests containing verified CSAM or content that violates national laws.
  - Requests to generate malware, exploits, or attack tooling.
  - Requests for detailed instructions on weapons synthesis or dangerous chemicals.
  Detection is rule-based (hash matching + regex) at v1; LLM-based detection is post-hackathon.
- **Human-in-the-loop (HITL):** For high-risk actions triggered by AI responses (finance, IoT control, data deletion), the agent layer enforces a `confirm` approval level requiring explicit user consent before execution. The AI gateway propagates this metadata but does not enforce it.
- **Zero-agent-change criterion:** Adding or removing any provider requires only: (1) adding/removing the provider's API key env var, (2) enabling/disabling via `PROVIDER_{NAME}_ENABLED` env var, and (3) if a new adapter is needed, adding one file in `adapters/`. No changes to router, sanitizer, or any agent code.

## 9. Open Questions / Needs Clarification

- [RESOLVED: What is the routing priority order? — DeepSeek → Grok → OpenAI → Gemini (Constitution §5 priority). User override always takes precedence (three-tier hierarchy: operator flag > user preference > request field).]
- [RESOLVED: Is there a per-user or per-request override mechanism? — Yes. Three-tier override: operator/feature-flag > user preference (DB) > request-level override (header/body).]

## 10. Clarifications

### Session 2026-09-03

- **Q: Should there be a concurrency limit per AI gateway instance?** → A: Conservative per-instance limit (50–100 concurrent requests) with explicit documentation that horizontal scaling requires Redis-backed circuit breaker state (post-hackathon). Stateless scaling out of scope for hackathon.
- **Q: How many consecutive successes should close the circuit after half-open state?** → A: 2 consecutive successes. Standard pybreaker reset threshold — balanced between fast recovery and avoiding flapping.
- **Q: What should the gateway return if all providers fail (all circuits open)?** → A: Partial response + error flag on the last streaming chunk. Return what was streamed so far with a `provider_error: true` flag and `failed_provider` field; client can display a clear message and offer retry.
- **Q: Should users be notified when a provider failover occurs mid-request?** → A: Notify on errors only. Surface a "switched to {provider}" event in the chat UI only when the initial provider failed; seamless attribution badge update when no error occurred.
- **Q: What structured fields should every AI gateway log line contain?** → A: Standard — request_id, provider, model, latency_ms, status, user_id, agent_id, input_tokens, output_tokens. Full audit trail without logging prompt contents.

## 11. Hackathon Scope Note

**In scope:** Provider abstraction layer, routing with failover, attribution, token logging, circuit breaker, prompt injection sanitization, rate limiting via Redis.
**Deferred:** Open-source model integration, cost dashboard, quality-based adaptive routing, per-user provider preferences UI, LLM-based harmful-content detection, Redis-backed circuit breaker state (in-memory is fine for hackathon).
