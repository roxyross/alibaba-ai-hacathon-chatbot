# ROXY AI — Prompt #4 Forensic Baseline Revalidation Report

**Document Version:** 4.0.0-BASELINE  
**Audit Date:** October 9, 2026  
**Auditor:** Independent Senior Production Verification Engineer & AI Coding-Agent Evaluator  
**Governing Doctrine:** Non-Negotiable Zero-Simulation Doctrine (E0–E5 Hierarchy)  

---

## 1. Executive Baseline Assessment

Prior audits and remediations claimed that the Roxy-AI platform had achieved:
- 130 tests passing, 2 truthfully skipped
- Removal of in-process plugin `exec()`
- Real `httpx` HTTP connectors replacing mock/canned responses
- `code_execute` implemented and registered in `ToolRegistry`
- Python, Node.js, Go, Rust execution implemented
- Cowork artifact and Open Work task persistence across process restarts
- Hardened multilingual normalization and application resolution
- Clean frontend production build (TypeScript + Vite)

### Independent Verification Methodology
Following the Zero-Simulation Doctrine, the codebase was inspected statically (E0), tested unit-wise (E1), verified across in-process components (E2), executed against local runtime processes and filesystems (E3), and evaluated against real desktop environments and external APIs (E4/E5).

### Baseline Test Execution Results (Empirical)
- **Pytest Baseline Suite:** 14 test suites executed via `backend/.venv/Scripts/python.exe -m pytest`
  - **Passed:** **130**
  - **Skipped (Truthful):** **2** (`test_real_world_calculator_desktop_window_execution`, `test_real_world_whatsapp_ingest_and_notify`)
  - **Failed:** **0**
  - **Warnings:** 71 (deprecation and JWT key length warnings)
  - **Duration:** 177.39s (wall clock)
- **Frontend Production Build:** Executed `npm run build` in `frontend/`
  - **TypeScript Compilation (`tsc`):** Clean, 0 errors
  - **Vite Production Bundler:** 1,707 modules transformed, bundles emitted to `frontend/dist/` in 9.20s

---

## 2. Forensic Baseline Mapping Table

| Finding ID | Previous Status | Current Code Implementation | Independently Verified? | Evidence Level | Remaining Risk & Observations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01 (Plugin Sandboxing)** | Claimed Resolved (Isolated Subprocess) | `backend/src/app/plugins/manager.py`: `_create_sandboxed_handler` runs `asyncio.create_subprocess_exec` with stripped environment (`PATH`, `SYSTEMROOT`, `TEMP`) and a 4.0-second timeout. Checks for banned module imports via AST / text. | **YES** | **E3** (Local subprocess execution) | Child process still runs in host context. While banned modules (`subprocess`, `ctypes`, etc.) are checked and env vars scrubbed, process isolation is not an OS kernel/container sandbox. Evaluated in Phase 7. |
| **CONN-01 (Cloud Connectors)** | Claimed Resolved (Real HTTP Clients) | `backend/src/app/connectors/`: `GitHubConnector`, `SlackConnector`, `NotionConnector`, `GoogleConnector` construct real `httpx.AsyncClient` instances, send authentic REST payloads, and raise `PermissionError` when credentials are absent. | **YES** | **E2 / E3** (Real client instantiation, truthful auth failure) | No canned responses detected. Requires live third-party tokens for E4/E5 live end-to-end calls. |
| **TOOL-01 (`code_execute` Tool)** | Claimed Resolved (Multi-language Subprocess) | `backend/src/app/tools/builtin.py`: Registered as `code_execute` in `ToolRegistry`. Dispatches to `CodingService.execute_code` or CLI commands via `asyncio.create_subprocess_exec`. | **YES** | **E3** (Real subprocess execution) | CLI test runner executes real commands (`pytest`). Windows backslashes preserved via `shlex.split(posix=False)`. Host toolchain availability limits Go/Rust execution on this machine. |
| **PERS-01 (Cowork & Open Work Persistence)** | Claimed Resolved (Atomic Disk JSON) | `backend/src/app/artifacts/repository.py` and `backend/src/app/open_work/service.py`: Save and load state from `cowork_artifacts.json` and `open_work_tasks.json` in user storage directory with `.tmp` write and atomic replace. | **YES** | **E3** (Filesystem persistence across memory eviction) | Storage is currently local JSON file-based. Production cloud deployments with multiple horizontal workers/containers require PostgreSQL database persistence. Evaluated in Phase 8. |
| **ACC-01 (Section 45 Acceptance Scenarios)** | Claimed Resolved (Three-Tier Tests, Truthful Skips) | `backend/tests/test_real_acceptance_scenarios.py`: 7 Section 45 scenarios tested across Unit (E1), Integration (E2), and Real E2E (E3/E4). Real desktop Calculator and live WhatsApp are skipped when GUI session / live session is inactive. | **YES** | **E1–E4** (Truthful skips verified) | 2 tests truthfully skipped without falsifying pass. Phase 11 & Phase 13 explore deeper real execution paths. |
| **CODE-01 (Coding Agent Intelligence)** | Claimed Resolved (Project Detection & Capabilities) | `backend/src/app/coding/service.py`: `detect_project` inspects files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, etc.). `get_language_capability_matrix` maps capabilities. Multilingual regex uses `\b<word>\b`. | **YES** | **E1–E3** (Inspection & AST parsing) | Does `CodingService` exhibit autonomous Claude Code-style engineering (inspect -> reason -> edit -> test -> diagnose -> fix -> retest) or is it primarily a request/response generation endpoint? Evaluated in Phase 1–4. |
| **HOST-01 (Installed Toolchains)** | Claimed Multi-Language Runtimes | Empirical probe of host PATH: Python 3.14 (Available), Node.js v24 / npm / tsc (Available), Git (Available), Go (Not Found), Rust / Cargo (Not Found), Java / GCC / .NET (Not Found). | **YES** | **E3** (Host command probe) | Under Zero-Simulation Doctrine, Go and Rust must be reported as `NOT_INSTALLED / UNSUPPORTED` on this host. Python and Node.js/TypeScript are `AVAILABLE + VERIFIED`. |

---

## 3. Summary of Baseline Risks & Critical Focus Areas

1. **Autonomous Coding Agent vs Tool Endpoint (Phase 1–4):**
   `CodingService` currently provides `generate_code`, `explain_code`, `debug_code`, and `execute_code`, while `OpenWorkAgentService` provides subtask workflows. To achieve genuine Claude-level autonomous coding, the agent must be able to autonomously orchestrate:
   `Understand -> Inspect -> Search -> Reason -> Plan -> Edit -> Execute -> Test -> Analyze Failure -> Fix -> Retest -> Build -> Verify -> Report`.
2. **Host Language Runtimes (Phase 2):**
   Python and Node.js/TypeScript are fully installed and verified. Go and Rust are not installed on the Windows host. Under Rule 4, no simulated execution of Go or Rust may be claimed.
3. **Desktop Automation (Phase 11 & 12):**
   `pywinauto` is installed and verified. The acceptance test previously skipped because Calculator was not actively in the foreground. We will attempt explicit automated launch and interaction with `calc.exe`.
4. **Authoritative Cloud Persistence (Phase 8):**
   Local disk JSON works for single-node/local desktop installations, but multi-worker cloud setups require database persistence (PostgreSQL/SQLAlchemy).

Baseline verification complete. No implementation files modified during Phase 0 baseline revalidation.
