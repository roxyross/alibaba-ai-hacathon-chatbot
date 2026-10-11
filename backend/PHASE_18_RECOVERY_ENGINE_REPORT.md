# Phase 18: Recovery & Self-Correction Engine Report
**Fallback Strategies: API Failure $\to$ Browser Route $\to$ Desktop Automation**  
**Execution Date:** October 4, 2026  
**Status:** Completed & Validated (100% Pass Rate, 222/222 Regression Tests Passing)

---

## 1. Executive Summary

Phase 18 implements the **Recovery & Self-Correction Engine** for Roxy AI, establishing an autonomous fallback ladder across execution surfaces:
1. **Tier 1: Direct API / Connector Route**: Fast, low-latency, deterministic execution via direct REST endpoints or MCP connectors.
2. **Tier 2: Web / Browser Route**: Automated browser session execution when APIs are unauthorized (401/403), rate-limited (429), or missing endpoints (404/500).
3. **Tier 3: Native Desktop Automation Route**: Deepest local fallback executing via native operating system UI controls (`DesktopAutomationEngine`, `ProcessLifecycleController`, `pywinauto`, UI Automation) when web sessions are blocked by CAPTCHA/bot challenges or missing DOM elements.

Operating strictly under the **Zero Simulation Doctrine**, the engine integrates empirical postcondition verification from Phase 17's `VerificationEngine`, closing the loop between execution, error classification, dynamic self-correction, and cryptographic proof logging.

---

## 2. Core Architecture & Components

```
+----------------------------------------------------------------------------------------------------+
|                               Recovery & Self-Correction Architecture                              |
|                                                                                                    |
|                                 +----------------------------+                                     |
|                                 |    Incoming Action Goal    |                                     |
|                                 +--------------+-------------+                                     |
|                                                |                                                   |
|                                                v                                                   |
|                               +-------------------------------+                                    |
|                               |   Tier 1: Direct API Route    |                                    |
|                               +---------------+---------------+                                    |
|                                               |                                                    |
|                   [Fail / 401 / 429 / 500]    |   [HTTP 200]                                       |
|               +-------------------------------+---------------+                                    |
|               |                                               |                                    |
|               v                                               v                                    |
|   +-----------------------+                    +-------------------------------+                   |
|   |    ErrorClassifier    |                    |  Verification Engine Gate     |                   |
|   | - Transience Check    |                    | - Window / DOM / OCR / API    |                   |
|   | - Fast Failover Rec.  |                    +---------------+---------------+                   |
|   +-----------+-----------+                                    |                                   |
|               |                               [Passed]         |   [Silent Failure / Unmet]        |
|               v                               +----------------+---------------+                   |
|   +-------------------------------+           |                                |                   |
|   |   Tier 2: Web / Browser Route |           |                                v                   |
|   +---------------+---------------+           |                 +------------------------------+   |
|                   |                           |                 |     SelfCorrectionEngine     |   |
|   [CAPTCHA / DOM] |   [Success]               |                 | - Window Focus Correction    |   |
|   +---------------+---------------+           |                 | - Timing / Settling Delay    |   |
|   |                               |           |                 | - Selector Fallback          |   |
|   v                               v           |                 +--------------+---------------+   |
|   +-------------------------------+           |                                |                   |
|   | Tier 3: Native Desktop Route  |           |                                v                   |
|   | - HWND Window Focus           |           |                 +------------------------------+   |
|   | - UI Automation / pywinauto   |           |                 |  Next Tier Ladder Escalation |   |
|   +---------------+---------------+           |                 +------------------------------+   |
|                   |                           |                                                    |
|                   +---------------------------+                                                    |
|                                               |                                                    |
|                                               v                                                    |
|                            +-------------------------------------+                                 |
|                            |         Cryptographic Ledger        |                                 |
|                            | - Deterministic SHA-256 Proof Hash  |                                 |
|                            | - Audit History & Status Verdict    |                                 |
|                            +-------------------------------------+                                 |
+----------------------------------------------------------------------------------------------------+
```

### 2.1 Error Classifier (`ErrorClassifier`)
- **Canonical Taxonomy (`ErrorCategory`)**:
  - `AUTH_CREDENTIAL_ERROR`: 401/403, expired OAuth token, missing key $\to$ fast failover to Browser.
  - `RATE_LIMIT_EXCEEDED`: 429 Too Many Requests $\to$ transient retry or failover.
  - `RESOURCE_NOT_FOUND`: 404 endpoint missing $\to$ failover to Browser UI.
  - `SERVER_FAULT`: 500/502/503 backend crash $\to$ failover to client interface.
  - `CAPTCHA_CHALLENGE`: Cloudflare/Turnstile/reCAPTCHA bot challenge $\to$ fast failover to Desktop.
  - `DOM_ELEMENT_NOT_FOUND`: Selector missing $\to$ text search or desktop fallback.
  - `WINDOW_NOT_FOUND`: Target app not running $\to$ launch executable and focus.
  - `POSTCONDITION_FAILED`: Action completed but verification check failed $\to$ self-correction.
  - `NETWORK_UNREACHABLE`: Connection refused/socket timeout.

### 2.2 Self-Correction Engine (`SelfCorrectionEngine`)
- Translates empirical failure details into concrete adjustments:
  - **Window State Discrepancy**: Window not in foreground $\to$ triggers `focus_window` with force foreground.
  - **Target Absent**: Application not running $\to$ triggers `launch_process` before control lookup.
  - **Rendering Lag**: UI not settled $\to$ increases settling delay.
  - **DOM Selector Changed**: CSS ID missing $\to$ falls back to inner text matching.
  - **Bot Mitigation Block**: Web blocked $\to$ escalates directly to native desktop application.

### 2.3 Tier Executors
- **`APITierExecutor`**: High-speed HTTP/REST dispatch with status validation and body snippet extraction.
- **`BrowserTierExecutor`**: Web navigation and DOM form processing with anti-bot challenge detection.
- **`DesktopTierExecutor`**: Native OS application launch, window focus activation, element clicks, text typing, and keyboard hotkeys.

### 2.4 Recovery Coordinator (`RecoveryEngine`)
- **Configurable Fallback Ladder**: Default `[API, BROWSER, DESKTOP]`.
- **Fast Failover**: Skips pointless retries on terminal errors (401 Auth error on API $\to$ Browser; CAPTCHA on Browser $\to$ Desktop).
- **Cryptographic Fingerprint**: Generates SHA-256 hash across complete recovery execution trail.
- **Root Cause Analysis**: Assembles multi-tier diagnostic synthesis when all tiers fail (`FAILED_ALL_TIERS`).

---

## 3. ToolRegistry & Agent Tools

Added 4 agent tools to `ToolRegistry`:
1. `recovery_execute_with_fallback`: Execute an action across multi-tier ladder with automatic fallback and postcondition verification.
2. `recovery_classify_error`: Classify an operational error, detect root cause, transience, and recommended tier.
3. `recovery_suggest_correction`: Formulate concrete self-correction hints given empirical verification failure.
4. `recovery_get_history`: Retrieve recent recovery execution history records and cryptographic proof hashes.

---

## 4. FastAPI REST Endpoints

Exposed 4 REST endpoints under `/api/v1/devices/{device_id}/recovery/`:
- `POST /{device_id}/recovery/execute`: Trigger multi-tier recovery execution.
- `POST /{device_id}/recovery/classify`: Error diagnosis and recommended tier escalation.
- `POST /{device_id}/recovery/self-correct`: Generate self-correction hints.
- `GET /{device_id}/recovery/history`: Audit log query for recovery proofs.

---

## 5. Verification & Test Metrics

- **Phase 18 Test Suite (`tests/test_phase18_recovery_engine.py`)**:
  - `test_error_classifier_taxonomies`: Passed
  - `test_self_correction_engine_hints`: Passed
  - `test_tier1_api_success_no_fallback`: Passed
  - `test_tier1_api_failover_to_tier2_browser`: Passed
  - `test_tier1_api_fail_tier2_captcha_failover_to_tier3_desktop`: Passed
  - `test_recovery_with_verification_gate_and_self_correction`: Passed
  - `test_recovery_failed_all_tiers_rca`: Passed
  - `test_cryptographic_proof_hash_integrity`: Passed
  - `test_device_service_recovery_tools`: Passed
  - `test_api_recovery_endpoints`: Passed
  - **Result: 10/10 Passed (100%)**

- **Full Regression Suite (Phases 7 through 18)**:
  - Total tests collected: 222 items
  - Total tests passing: 222 items (100% Pass Rate)
  - Regressions: **0**
  - Execution Time: 290.21s (4m 50s)

- **Static Type & Lint Validation**:
  - `ruff check`: Passed (0 errors in Phase 18 files)
  - `mypy`: Passed (0 issues in 2 source files)
