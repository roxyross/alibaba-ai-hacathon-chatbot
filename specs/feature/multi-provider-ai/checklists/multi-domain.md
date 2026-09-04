# Multi-Domain Requirements Quality Checklist: Multi-Provider AI Abstraction

**Purpose**: Validate requirements quality across Security, AI Safety, Accessibility, Mobile/i18n, and Observability domains — "unit tests for requirements written in English."
**Created**: 2026-09-02
**Feature**: [multi-provider-ai](../spec.md)
**Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Tasks**: [tasks.md](../tasks.md)

---

## Security & Privacy Requirements

- [ ] CHK001 - Are API key storage requirements specified as env-only (no keys in code, logs, or client bundles)? [Completeness, Spec §3 / Constitution §3]
- [ ] CHK002 - Is TLS 1.3 enforcement explicitly stated as mandatory for all provider requests? [Completeness, Spec §3]
- [ ] CHK003 - Are prompt injection detection requirements specified with concrete technique or pattern list (not just "sanitization")? [Clarity, Spec §3]
- [ ] CHK004 - Is output validation from provider responses specified as a mandatory step before passing to agents? [Completeness, Spec §3]
- [ ] CHK005 - Is plain-text user prompt logging explicitly prohibited in requirements? [Completeness, Spec §4]
- [ ] CHK006 - Are data retention and deletion requirements for TokenUsageLog records defined (GDPR compliance)? [Gap, Spec §4 / Constitution §4]
- [ ] CHK007 - Is the audit log schema specified with required fields (request_id, provider, model, user_id, timestamp)? [Completeness, Constitution §13]
- [ ] CHK008 - Are per-action approval levels (auto / confirm / PIN-biometric) for sensitive operations defined in requirements? [Gap, Constitution §3]
- [ ] CHK009 - Is RBAC or permission scope for the provider enable/disable endpoint specified? [Gap, Spec §3]

---

## AI Safety Requirements

- [ ] CHK010 - Is the multi-provider abstraction interface specified as a formal contract (not just "agents call gateway")? [Completeness, Spec §5 / Constitution §5]
- [ ] CHK011 - Are all four supported providers enumerated with their routing priority documented? [Completeness, Spec §5]
- [ ] CHK012 - Is the attribution metadata schema specified per response (provider, model, agent_id fields)? [Completeness, Spec §5]
- [ ] CHK013 - Is circuit breaker behavior specified with explicit failure thresholds, reset timeouts, and state transitions? [Clarity, Spec §5]
- [ ] CHK014 - Are safety guardrails for clearly harmful request categories defined with refusal behavior? [Gap, Spec §5 / Constitution §5]
- [ ] CHK015 - Is human-in-the-loop required for high-risk AI actions (finance, IoT control, data deletion)? [Completeness, Constitution §5]
- [ ] CHK016 - Is "zero changes to agent code" for adding a provider specified as a measurable acceptance criterion? [Clarity, Spec §5]

---

## Accessibility Requirements

- [ ] CHK017 - Are attribution display requirements specified with visual and programmatic accessibility criteria? [Completeness, Spec §6 / Constitution §11]
- [ ] CHK018 - Are user-facing error messages required to be human-readable (not technical codes)? [Completeness, Spec §6 / Constitution §11]
- [ ] CHK019 - Are keyboard navigation requirements for chat interface defined? [Gap, Constitution §11]
- [ ] CHK020 - Are WCAG 2.2 AA color contrast requirements specified for the attribution badge in both light and dark modes? [Gap, Constitution §11]

---

## Mobile & i18n Requirements

- [ ] CHK021 - Are streaming response requirements specified for mobile network conditions (partial failure, reconnect)? [Gap, Constitution §22]
- [ ] CHK022 - Is provider attribution display specified for mobile viewport constraints? [Gap]

---

## Observability & Audit Requirements

- [ ] CHK023 - Are structured JSON log fields specified as mandatory (request_id, provider, model, latency_ms)? [Completeness, Constitution §13]
- [ ] CHK024 - Is per-agent token cost tracking specified as a metric requirement? [Completeness, Constitution §13]
- [ ] CHK025 - Is the "What did Jarvis do today" audit view specified with data requirements? [Gap, Constitution §13]
- [ ] CHK026 - Are health check endpoint requirements specified (what constitutes healthy vs degraded vs unavailable)? [Clarity, Spec §5]

---

## Performance & Reliability Requirements

- [ ] CHK027 - Is the 10s per-provider timeout specified with behavior on timeout (failover vs error)? [Clarity, Spec §4]
- [ ] CHK028 - Are p95 latency targets for non-streaming AI endpoints specified? [Gap, Constitution §9]
- [ ] CHK029 - Is time-to-first-token (TTFT) target specified for streaming responses? [Gap, Constitution §9]
- [ ] CHK030 - Is token usage per request logging specified as mandatory (not optional)? [Completeness, Spec §4]
- [ ] CHK031 - Is the behavior when all providers are unavailable specified (error message, retry guidance)? [Gap, Spec §4]

---

## Scenario & Edge Case Requirements

- [ ] CHK032 - Is failover behavior when a provider times out mid-stream specified (graceful close vs retry)? [Edge Case, Spec §4]
- [ ] CHK033 - Is partial provider failure (one provider returns partial response then fails) specified? [Edge Case, Gap]
- [ ] CHK034 - Are rate limiting requirements specified per provider? [Gap, Constitution §22]
- [ ] CHK035 - Is provider health probe frequency specified (how often does health endpoint refresh state)? [Gap]
- [ ] CHK036 - Is there a recovery behavior specified when a failed provider becomes healthy again? [Gap]

---

## Dependency & Assumption Requirements

- [ ] CHK037 - Are httpx version requirements specified for connection pooling compatibility? [Dependency]
- [ ] CHK038 - Is pybreaker version or configuration specified for circuit breaker behavior? [Dependency]
- [ ] CHK039 - Is the assumption that all four providers expose OpenAI-compatible APIs validated? [Assumption, Spec §5]
- [ ] CHK040 - Are Neon PostgreSQL connection requirements specified for token log persistence? [Dependency, Constitution §10]

---

## Notes

- Items marked [Gap] indicate missing requirements that should be added to spec.md before implementation.
- Items marked [Ambiguity] or [Clarity] indicate requirements that need quantification or clearer definition.
- Items marked [Assumption] indicate technical assumptions that should be validated or documented.
- Each `/sp.checklist` run creates a new file — this file is not overwritten.
