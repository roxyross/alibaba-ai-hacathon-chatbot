# ROXY-AI — Code Studio / Full IDE Capability Matrix
**Audit Date:** October 12, 2026  
**Auditor:** Principal IDE Architect & Senior DevTools Engineer  
**Standard:** Antigravity / Modern VS Code Production Class

---

## 1. Capability Verification Matrix

| Feature | Status | Evidence | Test Result | Dependencies | Remaining Gap | Next Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Code Editor & Syntax Surface** | IMPLEMENTED & VERIFIED | `CodeStudioIDE.tsx` (lines 1083-1150) | PASS (Vitest & manual test) | React 18, Lucide React | None for core editor | Ready for production |
| **Multi-tab Editing & Dirty Flags** | IMPLEMENTED & VERIFIED | `openTabs`, `isDirty`, save/close | PASS (`CodeStudioIDE.test.tsx`) | React state | None | Ready for production |
| **Split Editor (Side-by-Side)** | IMPLEMENTED & VERIFIED | `isSplitEditor`, secondary pane | PASS (`CodeStudioIDE.test.tsx`) | CSS Flexbox | Independent tab scrolling | Add synched scroll option |
| **Go To Line (`Ctrl+G`)** | IMPLEMENTED & VERIFIED | `isGoToLineOpen` modal + hotkey | PASS (`CodeStudioIDE.test.tsx`) | Keyboard event listener | Line cursor focus API | Wire direct textarea selection range |
| **Workspace File Tree** | IMPLEMENTED & VERIFIED | `GET /coding/workspace/tree` | PASS (`test_acceptance_a`) | `FileSystemService.list_files` | None | Ready for production |
| **File CRUD & Directory Lifecycle** | IMPLEMENTED & VERIFIED | `POST/GET/DELETE /coding/workspace/*` | PASS (`test_workspace_file_crud_api`) | `FileSecuritySandbox` | None | Ready for production |
| **Workspace-Wide Text Search** | IMPLEMENTED & VERIFIED | `POST /coding/workspace/search` | PASS (`test_acceptance_b`) | Python `os.walk`, UTF-8 decoder | Large binary file exclusion | Threshold at 2MB enforced |
| **Integrated Terminal** | IMPLEMENTED & VERIFIED | `POST /coding/terminal/exec` | PASS (`test_acceptance_e`) | `asyncio.subprocess` | Full PTY terminal streaming on Windows | Add WebSocket pseudo-terminal adapter |
| **Dangerous Command Guard** | IMPLEMENTED & VERIFIED | Prohibited pattern blocker (403) | PASS (`test_acceptance_h`) | Regex pattern matcher | None | Maintain updated pattern list |
| **Source Control: Git Status** | IMPLEMENTED & VERIFIED | `GET /coding/git/status` | PASS (`test_acceptance_i`) | Host `git` CLI (v2.43) | None | Ready for production |
| **Source Control: Unified Diff** | IMPLEMENTED & VERIFIED | `GET /coding/git/diff` | PASS (`test_acceptance_i`) | Host `git diff` | None | Ready for production |
| **Source Control: Commit Creation** | IMPLEMENTED & VERIFIED | `POST /coding/git/commit` | PASS (`test_ide_e2e_acceptance.py`) | Host `git commit` | None | Ready for production |
| **Test Runner: Pytest / NPM** | IMPLEMENTED & VERIFIED | `POST /coding/tests/run` | PASS (`test_acceptance_a`, `test_acceptance_d`) | Installed runtimes | Compiler-dependent | Detect runner automatically |
| **Web Dev Live Preview** | IMPLEMENTED & VERIFIED | Sandboxed `iframe` + viewport switcher | PASS (Vitest & DOM preview) | Browser sandboxing | Live hot-reload sync | Connect Vite HMR socket |
| **AI Coding Agent: Planning** | IMPLEMENTED & VERIFIED | `POST /coding/agent/assist` | PASS (`test_acceptance_b`) | `AgentPlanner`, LLM router | None | Ready for production |
| **AI Coding Agent: Diffs** | IMPLEMENTED & VERIFIED | Unified diff synthesis | PASS (`test_acceptance_c`, `test_acceptance_d`) | Python `difflib` | None | Ready for production |
| **Multilingual Prompts (Urdu)** | IMPLEMENTED & VERIFIED | Roman Urdu intent detection | PASS (`test_acceptance_g`) | Linguistic parser | None | Ready for production |
| **Central Tool Registry Exposure** | IMPLEMENTED & VERIFIED | `GET /coding/tools` (11 tools) | PASS (`test_acceptance_j`) | `ToolRegistry.get_instance()` | None | Ready for production |
| **Permission Supervision Gate** | IMPLEMENTED & VERIFIED | `requires_approval` flag in agent assist | PASS (`test_acceptance_c`) | Roxy Permission Engine | None | Ready for production |
| **Python Language Support** | IMPLEMENTED & VERIFIED | Editing, Execution, Testing | PASS (`test_acceptance_f`) | Python 3.14.0 active | None | Full support verified |
| **TypeScript / Node.js Support** | IMPLEMENTED & VERIFIED | Editing, Execution, Compilation | PASS (`test_acceptance_f`, `tsc`) | Node.js v24.19, tsc | None | Full support verified |
| **Go Language Support** | PARTIALLY IMPLEMENTED | Syntax editing supported | BLOCKED for execution | `go` compiler absent on host | Runtime not installed | Document prerequisite |
| **Rust Language Support** | PARTIALLY IMPLEMENTED | Syntax editing supported | BLOCKED for execution | `rustc` compiler absent on host | Runtime not installed | Document prerequisite |
| **C / C++ Language Support** | PARTIALLY IMPLEMENTED | Syntax editing supported | BLOCKED for execution | `gcc`/`clang` absent on host | Runtime not installed | Document prerequisite |
| **Java Language Support** | PARTIALLY IMPLEMENTED | Syntax editing supported | BLOCKED for execution | `javac` absent on host | Runtime not installed | Document prerequisite |
| **Voice Microphone Input** | PARTIALLY IMPLEMENTED | Web Speech API UI + Multilingual routing | BLOCKED in headless environment | Physical microphone hardware | Physical mic in CI / headless test | Manual browser hardware verification |

---

## 2. Language Capability Matrix Summary

| Language | Syntax Highlighting | Language Detection | Agent Code Gen | Execution Support | Test Integration | Host Toolchain Verified |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Python** | YES | YES (`.py`) | YES | YES | YES (`pytest`) | Python 3.14.0 |
| **JavaScript** | YES | YES (`.js`, `.jsx`) | YES | YES | YES (`npm test`) | Node.js v24.19.0 |
| **TypeScript** | YES | YES (`.ts`, `.tsx`) | YES | YES | YES (`tsc`, `vitest`)| `tsc` 5.3.3, Node.js |
| **HTML / CSS** | YES | YES (`.html`, `.css`) | YES | YES (Live Preview) | YES | Browser DOM runtime |
| **JSON / YAML** | YES | YES (`.json`, `.yaml`)| YES | N/A (Config) | N/A | Python `json`/`yaml` |
| **Markdown** | YES | YES (`.md`) | YES | N/A (Documentation)| N/A | Built-in renderer |
| **SQL** | YES | YES (`.sql`) | YES | VIA DB CONNECTOR | VIA TEST SUITE | SQLite / Postgres |
| **Rust** | YES | YES (`.rs`) | YES | BLOCKED (No `rustc`) | BLOCKED | Not installed on host |
| **Go** | YES | YES (`.go`) | YES | BLOCKED (No `go`) | BLOCKED | Not installed on host |
| **C / C++** | YES | YES (`.c`, `.cpp`) | YES | BLOCKED (No `gcc`) | BLOCKED | Not installed on host |
| **Java** | YES | YES (`.java`) | YES | BLOCKED (No `javac`)| BLOCKED | Not installed on host |
| **PHP** | YES | YES (`.php`) | YES | BLOCKED (No `php`) | BLOCKED | Not installed on host |
| **C# / .NET** | YES | YES (`.cs`) | YES | BLOCKED (No `dotnet`)| BLOCKED | Not installed on host |
