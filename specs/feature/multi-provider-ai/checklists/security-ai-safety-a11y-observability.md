# Requirements Quality Checklist: Multi-Provider AI Abstraction

**Purpose**: Full non-functional requirements audit — security, AI safety, accessibility, observability
**Created**: 2026-09-03
**Feature**: [spec.md](../multi-provider-ai.md)
**Plan**: [plan.md](../multi-provider-ai/plan.md)

---

## Requirement Completeness

- [ ] CHK001 Are API key storage requirements explicitly stated as "env vars only, never in code or logs"? [Completeness, Spec §5]
- [ ] CHK002 Is the HTTPS/TLS 1.3 requirement formally specified (not just implied by "secure channel")? [Completeness, Spec §5]
- [ ] CHK003 Are the exact categories of sensitive AI actions requiring `confirm` level documented? [Completeness, Spec §5]
- [ ] CHK004 Are harmful request refusal categories (CSAM, malware, weapons) defined with enough specificity to distinguish them from adjacent categories? [Completeness, Spec §8]
- [ ] CHK005 Is the formal `AIProviderAdapter` contract named and its method signatures specified (not just "has methods")? [Completeness, Spec §8, Gap]
- [ ] CHK006 Are all health endpoint response fields formally specified (not just "returns status")? [Completeness, Spec §3/7, Gap]
- [ ] CHK007 Is the retry behavior after a rate limit hit explicitly documented (fail over vs. return 429)? [Completeness, Spec §7, Gap]
- [ ] CHK008 Is the partial response format when all providers fail formally specified (schema, fields, HTTP status code)? [Completeness, Spec §3, Gap]

---

## Requirement Clarity

- [ ] CHK009 Is "human-readable error message" quantified with guidance (max length, tone, whether to show provider name)? [Clarity, Spec §6]
- [ ] CHK010 Is the blocklist injection pattern list closed (exhaustive) or open-ended (can grow)? [Clarity, Spec §5]
- [ ] CHK011 Are the specific regex patterns for injection detection documented, or only described as "regex"? [Clarity, Spec §5, Gap]
- [ ] CHK012 Is the HITL confirmation mechanism described (modal, inline, API-driven)? [Clarity, Spec §5, Gap]
- [ ] CHK013 Is "prominent display" of attribution quantified with specific sizing or positioning? [Clarity, Spec §6]
- [ ] CHK014 Is the failover event message format specified (text, icon, timing, dismissal)? [Clarity, Spec §6]
- [ ] CHK015 Are the exact env var names for all provider config options documented in one place? [Clarity, Gap]
- [ ] CHK016 Does the spec clarify whether `latency_ms` in observability logs is wall-clock or provider-reported? [Clarity, Spec §7]

---

## Requirement Consistency

- [ ] CHK017 Is the circuit breaker "open" definition consistent between §7 (5 failures) and plan.md (5 failures)? [Consistency]
- [ ] CHK018 Are RBAC roles (admin, operator) consistent in naming across all spec sections? [Consistency, Spec §5]
- [ ] CHK019 Does the partial response acceptance criteria (§3) align with the clarification answer (§10)? [Consistency]
- [ ] CHK020 Is the "human-readable error" requirement consistent with the "error code is technical" anti-pattern? [Consistency, Spec §6]
- [ ] CHK021 Is the data retention period (90 days) consistent between §5 and the acceptance criteria (§3)? [Consistency]

---

## Acceptance Criteria Quality

- [ ] CHK022 Is the "zero agent code changes" acceptance criterion (§3) matched by an explicit operator action checklist in §8? [Acceptance Criteria, Gap]
- [ ] CHK023 Are acceptance criteria individually testable (not compound sentences with multiple "and" conditions)? [Acceptance Criteria, Spec §3]
- [ ] CHK024 Does the attribution acceptance criterion (§3) specify both streaming and non-streaming explicitly? [Acceptance Criteria, Spec §3]
- [ ] CHK025 Is "GDPR-compliant deletion" acceptance criterion (§3) traceable to a specific mechanism in §5? [Acceptance Criteria, Spec §3/5]

---

## Scenario Coverage

- [ ] CHK026 Are requirements specified for the primary flow (happy path with DeepSeek as primary)? [Coverage]
- [ ] CHK027 Are alternate flow requirements specified for user-level provider override? [Coverage, Gap]
- [ ] CHK028 Are exception flow requirements specified for when a provider times out mid-stream? [Coverage, Spec §7]
- [ ] CHK029 Are recovery flow requirements specified for circuit breaker reset after a successful probe? [Coverage, Gap]
- [ ] CHK030 Are requirements specified for when Redis is unavailable (fail-open behavior already specified, confirm consistency)? [Coverage, Spec §7]

---

## Edge Case Coverage

- [ ] CHK031 Is behavior specified when the blocklist triggers on a false positive (can users bypass)? [Edge Case, Gap]
- [ ] CHK032 Is behavior specified when a provider API returns a non-5xx error (e.g., 400 bad request)? [Edge Case, Gap]
- [ ] CHK033 Is behavior specified when the request `timeout_seconds` exceeds the circuit breaker timeout? [Edge Case, Gap]
- [ ] CHK034 Is behavior specified when a provider returns a response that fails Pydantic validation? [Edge Case, Gap]
- [ ] CHK035 Is behavior specified when the concurrency limit (50–100) is reached? [Edge Case, Spec §7, Gap]

---

## Non-Functional Requirements

- [ ] CHK036 Is the p95 latency target (<300ms) specified for which component boundary (gateway in, provider out)? [NFR, Spec §7]
- [ ] CHK037 Is TTFT (<1.5s) boundary clearly stated as provider inference included? [NFR, Spec §7]
- [ ] CHK038 Is the concurrency limit (50–100) stated as a hard cap or a recommendation? [NFR, Spec §7]
- [ ] CHK039 Is horizontal scaling stated as out-of-scope with a named post-hackathon milestone? [NFR, Spec §7]
- [ ] CHK040 Is the fail-open vs. fail-closed posture for each safety mechanism specified (Redis unavailable, CB state, rate limit)? [NFR, Gap]

---

## Dependencies & Assumptions

- [ ] CHK041 Is the assumption that `DEEPSEEK_API_KEY`, `XAI_API_KEY`, etc. env vars exist at startup validated? [Assumption, Gap]
- [ ] CHK042 Is the Prisma schema dependency for `TokenUsageLog` persistence documented as a Phase 3 deliverable? [Dependency, Plan]
- [ ] CHK043 Is the Redis dependency for rate limiting documented as a Phase 3 deliverable? [Dependency, Plan]
- [ ] CHK044 Is the dependency on httpx for provider adapters stated as a given (not a decision to make)? [Dependency, Gap]

---

## Ambiguities & Conflicts

- [ ] CHK045 Is "operator" role distinguished from "admin" role with separate permission scopes? [Ambiguity, Gap]
- [ ] CHK046 Does "circuit breaker state is re-evaluated on every request" conflict with "no background polling"? [Ambiguity, Spec §7]
- [ ] CHK047 Is the `provider` field in `AIResponse` the provider name (deepseek) or adapter name (deepseek_adapter)? [Ambiguity, Gap]
- [ ] CHK048 Is the distinction between `latency_ms` (gatekeeper) and `provider_response_ms` (TokenUsageLog) clear to implementers? [Ambiguity, Data Model]
- [ ] CHK049 Is the `stream` parameter in `AIRequest` differentiated from the `stream` query parameter on the POST endpoint? [Ambiguity, Gap]
- [ ] CHK050 Are there any open TODO markers or placeholder "TBD" items in security, safety, a11y, or observability sections? [Ambiguity, Gap]

---

## Notes

- CHK001–CHK008: Completeness gaps are addressable by expanding spec sections with explicit enumerated requirements.
- CHK009–CHK016: Clarity gaps are addressable by quantifying vague adjectives with specific metrics or enumerations.
- CHK017–CHK025: Consistency issues are addressable by cross-referencing and unifying terminology.
- CHK026–CHK035: Edge case gaps represent post-clarification task for spec authors.
- CHK036–CHK040: NFR gaps should be resolved before /sp-implement to avoid rework.
- CHK041–CHK049: Ambiguities should be resolved before implementation to prevent incorrect assumptions.
- CHK050: TODO/TBD scan — any hits should be resolved before Phase 1 tasks begin.
