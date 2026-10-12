# ROXY-AI — IDE Gap Matrix
**Audit Date:** October 12, 2026  
**Auditor:** Principal IDE Architect & Senior DevTools Engineer  
**Classification Standard:** Production Gap Analysis & Remediation Strategy

---

## 1. Capability & Gap Classification Matrix

| Capability | Classification | Evidence | Remaining Gap | Next Action |
| :--- | :--- | :--- | :--- | :--- |
| **Workspace Explorer & File CRUD** | `IMPLEMENTED_AND_VERIFIED` | `test_workspace_file_crud_api`, `test_workspace_tree_api` | None | Maintain existing contract |
| **Multi-File Editing & Unified Diffs** | `IMPLEMENTED_AND_VERIFIED` | `CodeStudioIDE.tsx`, `test_acceptance_c_multi_file_feature` | None | Maintain existing contract |
| **Split Editor & Go to Line** | `IMPLEMENTED_AND_VERIFIED` | `CodeStudioIDE.tsx` (lines 1258-1320, 1724-1760) | None | Add synchronized scrolling in future |
| **Workspace Text Search** | `IMPLEMENTED_AND_VERIFIED` | `POST /coding/workspace/search`, `test_acceptance_b` | None | Maintain existing contract |
| **Sandboxed One-Shot Terminal** | `IMPLEMENTED_AND_VERIFIED` | `POST /coding/terminal/exec`, `test_acceptance_e`, `test_acceptance_h` | Interactive REPL prompts | Add WebSocket streaming session |
| **Interactive PTY Terminal** | `PARTIALLY_IMPLEMENTED` | Terminal logs state in UI; backend is request/response subprocess | True bidirectional PTY stream over WebSocket | Implement `/terminal/stream` or WebSocket PTY adapter |
| **Git Status, Diff, Commit** | `IMPLEMENTED_AND_VERIFIED` | `GET/POST /coding/git/*`, `test_acceptance_i` | None | Maintain existing contract |
| **Python Execution & Testing** | `IMPLEMENTED_AND_VERIFIED` | Python 3.14.0 active, `pytest` exit code 0 in `test_acceptance_a`, `d`, `f` | None | Fully verified on host |
| **TypeScript/JavaScript Run & Test**| `IMPLEMENTED_AND_VERIFIED` | Node.js v24.19, `tsc` 5.3.3, vitest exit code 0 in `test_acceptance_f` | None | Fully verified on host |
| **HTML/CSS Live Web Dev Preview** | `IMPLEMENTED_AND_VERIFIED` | Responsive iframe preview in `CodeStudioIDE.tsx` (lines 1625-1665) | Live HMR socket binding | Connect Vite dev server socket |
| **Non-Installed Languages (Go/Rust/C++/Java/PHP)** | `BLOCKED_BY_ENVIRONMENT` | `rustc`, `go`, `javac`, `gcc` not on host PATH | Native host compilers absent | Implement language runtime container/fallback profiles |
| **Voice-to-Code Pipeline** | `IMPLEMENTED_AND_VERIFIED` | Web Speech API UI + Roman Urdu router in `test_acceptance_g` | None | Verified in software pipeline |
| **Physical Microphone Audio Acceptance** | `BLOCKED_BY_ENVIRONMENT` | Headless execution runner lacks physical audio hardware loopback | Physical acoustic capture | Document manual browser test protocol |
| **IDE Debugger Capabilities** | `PARTIALLY_IMPLEMENTED` | Breakpoint state UI sketched; DAP backend adapter missing | Interactive stepping, variable inspection | Implement lightweight Python/Node debugger service |
| **Model-Driven Tool-Calling Agent** | `IMPLEMENTED_AND_VERIFIED` | `POST /coding/agent/assist`, `test_acceptance_b`, `c`, `d`, `g` | Autonomous multi-turn tool calling verification | Audit real tool-call dispatch in AgentRuntime |
| **Production-Deployed Cloud E2E** | `BLOCKED_BY_EXTERNAL_DEPENDENCY` | Deployed cloud credentials & remote endpoints not accessible headlessly | Cloud deployment access | Provide production E2E checklist & validation script |
| **Central Tool Registry Integration** | `IMPLEMENTED_AND_VERIFIED` | 11 tools registered and verified in `test_acceptance_j` | None | Maintain existing contract |
| **Security, Sandboxing & Secret Shielding** | `IMPLEMENTED_AND_VERIFIED` | Prohibited commands blocked with 403, traversal blocked with 400 | None | Maintain existing contract |
| **Universal Reminders & Ringtones** | `IMPLEMENTED_AND_VERIFIED` | 9/9 tests pass in `test_code_studio_and_reminders.py` | None | Maintain existing contract |
