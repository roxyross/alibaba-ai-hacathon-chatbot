# ROXY-AI — Code Studio Remaining Gaps & Roadmap Report
**Date:** October 12, 2026  
**Auditor:** Principal IDE Architect & Senior Developer Tools Engineer  
**Standard:** Truthful, Evidence-Based Reporting (Zero Fabricated Passes)

---

## 1. Verified Working Baseline

The following capabilities are **fully implemented, tested, and verified**:
- **Core Workspace & Editor:** File tree, open tabs, dirty indicators, save/save-as, Go-to-Line (`Ctrl+G`), Split Editor, breadcrumbs, workspace search.
- **Sandboxed Execution:** Terminal command runner, timeout enforcement, prohibited destructive pattern blocking (`rm -rf /`, `format C:`).
- **Source Control:** Real Git status, unified diff generation, and commit creation.
- **Central Tool Registry:** 11 workspace tools registered in `ToolRegistry` and queryable via `/api/v1/coding/tools`.
- **Multilingual Coding Agent:** 3-step action planning, unified diff synthesis, supervised approval gate, Roman Urdu & English natural language understanding.
- **Python & TypeScript Execution:** Real execution and test running verified on host via Python 3.14.0, Node.js v24.19.0, and `tsc`.

---

## 2. Documented Remaining Gaps & Blockers

In strict compliance with Non-Negotiable Rules 8, 9, 10, and 16, the following items represent real environmental, tooling, or architectural limitations that must not be masked with mocks:

### Gap 1: Host Compilers Absent for Non-Installed Languages
- **Description:** While syntax highlighting, language detection, and Agent code generation work for Go, Rust, C/C++, Java, PHP, and C#/.NET, their native compilers are **not installed on the host system's PATH**.
- **Evidence:** `rustc`, `go`, `javac`, `gcc`, `dotnet`, and `php` return command-not-found when queried.
- **Impact:** Code can be written, viewed, and edited, but cannot be built or executed natively on this host machine.
- **Remediation:** In cloud production deployments, provision a multi-toolchain Docker image containing `golang-go`, `rustc`/`cargo`, `openjdk-17-jdk`, and `build-essential`.

### Gap 2: Physical Hardware Microphone in Headless Test Environments
- **Description:** Headless CI / automated test runner environments lack physical microphone audio hardware devices and OS audio input loopbacks.
- **Evidence:** Web Speech API voice capture is fully implemented in `CodeStudioIDE.tsx` and multilingual voice prompt intent routing is verified by `test_acceptance_g_voice_coding_pipeline`, but automated end-to-end microphone acoustic capture cannot be physically triggered headlessly.
- **Remediation:** Manual verification in a physical browser (Chrome/Edge) with user microphone permissions granted.

### Gap 3: Interactive PTY WebSocket Terminal on Windows
- **Description:** The current integrated terminal uses an asynchronous subprocess request/response execution model (`POST /terminal/exec`).
- **Limitation:** Commands requiring interactive terminal prompts (such as `python -i` or `npm init` interactive questions) time out if they wait for stdin.
- **Remediation:** Implement a bidirectional WebSocket endpoint (`/api/v1/coding/terminal/ws`) backed by `pywinpty` on Windows and `pty` on Linux/macOS for full xterm.js terminal emulation.

### Gap 4: Language Server Protocol (LSP) Daemon
- **Description:** Diagnostics in the Problems tab are currently populated through file linters and project test suite results.
- **Limitation:** In-memory real-time red squiggly error underlines across keystrokes require a running LSP server daemon (e.g. `pyright-langserver` or `typescript-language-server`).
- **Remediation:** Integrate a Monaco-LSP or CodeMirror-LSP WebSocket bridge in a future release.

---

## 3. Recommended Next Implementation Steps

1. **Step 1:** Containerize toolchains by creating a developer environment Dockerfile with pre-installed `go`, `rustc`, and `gcc`.
2. **Step 2:** Add `pywinpty` / `pty` WebSocket route to provide interactive terminal input for REPL sessions.
3. **Step 3:** Hook Monaco/xterm.js frontend components to the WebSocket streams for full terminal cursor navigation.
4. **Step 4:** Deploy to staging and perform manual physical microphone acoustic voice tests in Urdu and English.
