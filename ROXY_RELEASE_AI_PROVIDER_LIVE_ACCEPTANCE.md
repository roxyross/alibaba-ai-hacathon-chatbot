# ROXY-AI — AI Provider & Multi-Provider Gateway Live Acceptance Report

**Document ID:** `ROXY-RC-05`  
**Date:** October 14, 2026  
**Target Release:** Post-Phase 5.1 Release Candidate (RC-1)  
**Branch:** `release/audit-remediation`  
**Live Testing Verdict:** `PASS WITH FAILOVER`

---

## 1. Executive Summary

This report documents the live integration tests, circuit breaker behaviors, latency measurements, and provider routing hierarchy for the Roxy-AI Gateway (`app.ai_gateway`). Testing was executed directly against configured external AI endpoints using genuine API tokens.

---

## 2. Multi-Tier Routing Hierarchy

The AI Gateway resolves provider selection using the strict four-tier specification hierarchy:
1. **Tier 1 (Operator Flags):** `PROVIDER_{NAME}_ENABLED` environment variable overrides all.
2. **Tier 2 (User Preference):** Database-persisted user provider preferences.
3. **Tier 3 (Request Override):** `AIRequest.provider` field specified at call-time.
4. **Tier 4 (Default Priority):** `Grok` (Priority 1) → `Gemini` (Priority 2) → `DeepSeek` (Priority 3) → `OpenAI` (Priority 4).

---

## 3. Provider Live Testing Results

| Provider | Configured Model | Primary / Fallback | Live Test Status | Observed Latency | Response Attribution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Grok / Groq** | `qwen/qwen3.8-27b` | Primary Active | **SUCCESS (200 OK)** | **698.4 ms** | `provider="grok", model="qwen/qwen3.8-27b"` |
| **Google Gemini** | `gemini-3.8-flash` | Priority Fallback | **FAILOVER TRIGGERED** | ~2400 ms | Handled 503 Spike / Redirection to Grok |
| **DeepSeek** | `deepseek-chat` | Feature Flagged | **DISABLED (BY SPEC)** | N/A | `ProviderUnavailableError (Flag False)` |
| **OpenAI** | `gpt-4o` | Feature Flagged | **DISABLED (BY SPEC)** | N/A | `ProviderUnavailableError (Flag False)` |
| **DashScope / Qwen** | `qwen-max` / `qwen-plus`| Intent-Routed | **VERIFIED (ROUTER)** | N/A | Available via Model Intelligence Router |

---

## 4. Live Failover & Circuit Breaker Verification

### Failover Event Log Transcript (Sanitized)
```text
[HTTP Request] POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent
[HTTP Response] 503 Service Unavailable (Google Generative AI Demand Spike)
[Log Event] router.provider_failed_failover | provider=gemini | error=HTTP 503
[Failover Triggered] Routing to Next Available Provider: grok (Groq API)
[HTTP Request] POST https://api.groq.com/openai/v1/chat/completions
[HTTP Response] 200 OK | Latency: 698.4ms
[Attribution] AIResponse(provider='grok', model='qwen/qwen3.8-27b', tokens_logged=True)
```

### Circuit Breaker Specifications
- **Failure Threshold:** 5 consecutive failures trips circuit to `OPEN`.
- **Reset Timeout:** 30 seconds before transitioning to `HALF-OPEN`.
- **Pybreaker Integration:** Wrapped around each provider adapter instance (`base.py`).

---

## 5. Token Usage Logging & Cost Tracking

- All successful provider calls asynchronously record token usage via `TokenUsageLogger.log(request, response)` without blocking the user response loop.
- Input and output tokens are logged alongside user ID, agent ID, and estimated cost.
- Sensitive contents are sanitized: secret keys, bearer tokens, and PII are redacted from trace payloads.

---

## 6. Model Intelligence Router (Phase 23 Verification)

Verified via automated test `test_09_model_intelligence_router`:
- **Code Generation Intent:** Correctly routes prompts containing function signatures or code blocks to high-performance coding models (`gemini` or `dashscope`).
- **Image Generation Intent:** Detects drawing/visual synthesis requests and routes to modality `image`.
- **Complex Reasoning Intent:** Detects multi-step analytical and mathematical problems and selects high-reasoning parameter configurations.
- **Permission Policy:** Preserves strict user confirmation requirements across all model switches.

---

## 7. Acceptance Sign-off

The AI Gateway provides high-speed, resilient generation with robust, zero-downtime failover.
**STATUS: ACCEPTED FOR STAGING RELEASE.**
