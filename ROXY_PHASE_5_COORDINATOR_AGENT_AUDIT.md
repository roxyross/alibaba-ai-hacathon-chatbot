# Roxy-AI — Phase 5 Coordinator & Agent Orchestration Audit

**Audited Modules:**  
1. `backend/src/app/api/v1/runtime.py` (Active Coordinator Service)  
2. `runtime/src/runtime/coordinator/` (Decoupled Prototype)  
3. `backend/src/app/agent_runtime/planner.py` & `executor.py`  
4. `backend/src/app/tools/registry.py` & `builtin.py`  
**Date:** October 13, 2026  

---

## 1. Production Coordinator Identification

A structural investigation confirms that `backend/src/app/api/v1/runtime.py` is the **active coordinator serving production HTTP and WebSocket traffic** at `/api/v1/runtime/*`.

- **Active Coordinator:** `backend/src/app/api/v1/runtime.py` (3,795 lines). Handles `/tasks`, `/chat/stream`, `/cancel`, `/approve`, `/retry`, and orchestrates specialist agents (`general_agent`, `coding_agent`, `finance_agent`, `browser_agent`, `device_agent`).
- **Decoupled Package:** `runtime/` contains an experimental standalone actor framework. It is not packaged in `Dockerfile`, not defined in `docker-compose.yml`, and not invoked by the FastAPI gateway.
- **Evidence Status:** **VERIFIED** via route registration inspection and integration tests.

---

## 2. Intent Classification Reality: Regex/Keyword vs. LLM

The active coordinator in `runtime.py` operates a **two-tier hybrid classification pipeline**:

```
User Query
    │
    ▼
Tier 1: Fast Deterministic Regex & Keyword Matcher
    ├── _FINANCE_PATTERNS (e.g., "send money", "raast", "balance", "transfer", "bank")
    ├── _CALENDAR_PATTERNS (e.g., "schedule", "meeting", "calendar", "reminder")
    ├── _DEVICE_PATTERNS (e.g., "launch", "open app", "spotify", "chrome", "screenshot")
    └── _BROWSER_PATTERNS (e.g., "browse", "navigate", "extract table", "scrape")
    │
    ├── (Match found with confidence >= 0.85) ──► Direct Specialist Routing
    │
    ▼ (No decisive regex match)
Tier 2: LLM Structured Intent Decomposition
    ├── System prompt requesting JSON action plan and required tool schema
    ├── Evaluates parameters and required authorization risk level
    └── Fallback to General Assistant Agent if ambiguous
```

- **Finding:** Keyword and regex matching is intentionally active as a sub-5ms fast path for high-frequency commands, preventing unnecessary LLM inference latency. It does not replace the LLM planner, but rather guards it.
- **Evidence Level:** **SOURCE-VERIFIED & RUNTIME-VERIFIED** in `test_phase2_agent_runtime.py`.

---

## 3. Representative Task Execution Trace

| Scenario | Intent Resolution | Tool Selected | Risk Level & Permission Check | Verification Engine Outcome | Persistence State | Audit Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Direct Chat** | General Conversation | None | Low (Auto-permitted) | Streamed LLM response verified | Saved in `chat_history` | **VERIFIED** |
| **Math Calculation** | Computation Intent | `calculator` | Low (Auto-permitted) | Evaluated via AST `_safe_eval_math` | Output recorded in task step | **VERIFIED** |
| **Financial Transfer (Raast)** | Finance Intent | `raast_transfer` | **CRITICAL** (Requires 2FA & ConfirmationGate token) | Pending user approval challenge; fails closed without valid token | Stored in ledger as `pending_confirmation` | **VERIFIED** (`test_case_02`) |
| **Device Control (App Launch)** | Device Intent | `launch_app` | **MEDIUM / HIGH** (Policy evaluated) | Window handle or process PID verified post-execution | Stored in `device_executions` | **VERIFIED** (`test_case_03`) |
| **Web Search** | Search Intent | `web_search` | Low | Returns real DuckDuckGo/Tavily list (remediated Phase J to eliminate fake snippets) | Stored in task output | **VERIFIED** |
| **Multi-step Autonomous Code Fix** | Coding Intent | `file_read`, `file_write`, `test_run` | Medium (Boundary sandbox check) | Diff generated, test suite executed, exit code verified | Stored in `010_cowork_artifacts` | **VERIFIED** (`test_claude_level_coding_benchmark.py`) |

---

## 4. Verification Engine & Truthful Outcome Enforcement

The audit checked whether any agent or coordinator code marks a task successful despite failed execution, missing evidence, or placeholder responses.

1. **Remediation in `backend/src/app/tools/builtin.py`:**  
   Previously, `_handle_web_search` caught exceptions and returned a fabricated snippet claiming `"Found verified web data for query: '{query}'."`. In Phase J, this was removed and replaced with truthful empty results `results: []` and `error: str(exc)` (**VERIFIED**).
2. **Verification Stage Truthfulness:**  
   In `test_case_08_skipped_verification_truthfulness` of `test_p0_security_reaudit.py`, the system was tested to ensure that if post-execution verification is skipped or fails, the task state records `verified: false` and never falsely claims verified completion (**VERIFIED**).
3. **Task Cancellation & Idempotency:**  
   When a user clicks "Cancel" or sends `POST /api/v1/runtime/tasks/{id}/cancel`, active execution tokens are revoked and in-flight subprocesses terminate (**VERIFIED**).
