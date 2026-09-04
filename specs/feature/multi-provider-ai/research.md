# Research: Multi-Provider AI Abstraction

**Feature:** multi-provider-ai | **Date:** 2026-09-02

---

## Decision 1: Circuit Breaker Library

**Decision:** Use `pybreaker` (Python circuit breaker library).

**Rationale:**
- Battle-tested, widely used in production FastAPI/FinTech contexts
- Configurable failure thresholds, reset timeout, and exception filtering per circuit
- Integrates cleanly with `httpx` async clients used by all provider SDKs
- Does NOT require rewriting async call sites; wraps cleanly via context manager or decorator
- Supports manual `half_open` state for operator-triggered probe calls

**Alternatives considered:**
- `opencensus-resolve` — too heavy, more suited for observability than fault tolerance
- Custom ad-hoc flag (`if provider.is_available and not provider.circuit_open`) — reinvents the wheel, easy to get wrong
- `slowapi` — rate limiting focus, not circuit breaking

**Constitution impact:** None. §3 (security) and §9 (performance) both satisfied.

---

## Decision 2: Streaming Response Attribution

**Decision:** Inject attribution metadata as SSE comment lines (`: provider=deepseek`) before the first `data:` block, and include attribution in the final `data: [DONE]` event.

**Rationale:**
- SSE spec allows comment lines (prefixed `:`) that clients can consume without breaking JSON parsing
- Attribution in the terminal event is the most reliable place for post-stream attribution
- Avoids injecting metadata inside JSON data chunks (would require client to parse every chunk)
- Works with all major SSE client libraries without custom parsing

**Alternatives considered:**
- Prefix every chunk with attribution — bloats response, complicates client parsing
- Separate `/v1/attribution` endpoint polled after stream — adds latency and complexity
- HTTP header — not available mid-stream in chunked transfer

**Constitution impact:** §5 (attribution must be per-response).

---

## Decision 3: Failover Mid-Stream

**Decision:** Failover mid-stream is NOT supported in v1. The circuit breaker trips before the next chunk is emitted. If a provider times out mid-stream, the stream terminates and an error event is sent.

**Rationale:**
- Switching providers mid-SSE stream is architecturally complex (provider responses are not deterministic)
- Retrying a partial stream would deliver incomplete/inconsistent responses
- Better UX: close stream gracefully with error event, let client decide to retry
- The 10s timeout applies per-request; streaming requests still respect it

**Alternatives considered:**
- Buffer first chunk before streaming — adds latency, defeats streaming purpose
- Provider affinity per session — possible future enhancement, out of scope

**Constitution impact:** None.

---

## Decision 4: Routing Priority Order

**Decision:** Default routing order: DeepSeek → Grok → ChatGPT → Gemini. User/operator override always takes precedence. Task-type routing (code vs general) is the second dimension.

**Rationale:**
- DeepSeek first (constitution §5 priority order, and typically cost-effective)
- Grok second (xAI partnership, low latency)
- ChatGPT third (broad capability, fallback)
- Gemini fourth (multimodal but higher latency/cost)
- Task-type routing: if request is coding task → prefer DeepSeek (strong code perf) or Grok
- User override via `X-Provider-Preference` header or request body `provider` field
- Operator override via feature flag (per-provider enable/disable) takes highest priority

**Alternatives considered:**
- Pure latency-based routing — cost unpredictable, possible bill shock
- Pure cost-based routing — latency unacceptable for interactive chat
- Quality-based adaptive routing — requires historical data, deferred post-hackathon

**Constitution impact:** §5 (multi-provider abstraction mandatory, user override required).

---

## Decision 5: Per-Request / Per-User Override Mechanism

**Decision:** Three-tier override hierarchy:

1. **Operator/Admin disable** — feature flag per provider (`PROVIDER_{NAME}_ENABLED=false`) takes absolute precedence
2. **User preference** — stored in user profile DB field `preferred_provider`, respected unless provider is disabled
3. **Request-level override** — `provider` field in request body or `X-Provider-Preference` header, highest specificity

**Rationale:**
- Clean precedence: operator > user > system
- Each tier is independently useful
- Feature flag disables are instantaneous (no redeploy)
- User preference is persistent and scoped to user (privacy §4 compliant)
- Request override is ad-hoc and does not persist

**Alternatives considered:**
- Single override mechanism — too blunt
- Override via config file only — requires redeploy, too slow for outages
- No user preference (operator only) — degrades user agency

**Constitution impact:** §5, §19 (feature flags).

---

## Decision 6: Prompt Injection Sanitization

**Decision:** Sanitization at the domain layer (service class), not at the provider interface. Two-stage: (1) blocklist of known injection patterns, (2) structured prompt wrapping that isolates user input from system prompt.

**Rationale:**
- Provider interfaces should remain thin (single responsibility)
- Domain-level sanitization keeps business logic in the domain layer (constitution §2 dependency rule)
- Structured prompt wrapping (e.g. `system: ... | user: ...`) is the standard OWASP mitigation
- Blocklist catches the obvious cases; structured wrapping handles the rest

**Alternatives considered:**
- Sanitization in provider adapter — mixes domain logic with infrastructure
- LLM-based sanitization (use an LLM to detect injection) — overkill for v1, adds latency and cost

**Constitution impact:** §3 (prompt injection protection mandatory), §5.

---

## Open Questions Resolved

| Question | Resolution |
|---|---|
| Routing priority when cost and latency conflict | Cost first for batch/background tasks; latency first for interactive chat; configurable via task-type metadata |
| User override mechanism | Three-tier hierarchy: operator flag > user preference > request field |
| Circuit breaker library | `pybreaker` |
| Streaming attribution | SSE comment lines + final event |
| Failover mid-stream | Not supported; stream closes with error event |
| Prompt injection | Domain-layer blocklist + structured prompt wrapping |
