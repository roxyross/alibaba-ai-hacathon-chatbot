# ROXY-AI — Debugger Capability Matrix by Language (Phase 5)

**Document Version:** 2.0.0-verified  
**Audit & Remediation Date:** October 12, 2026  
**Status:** IMPLEMENTED AND VERIFIED FOR PYTHON; HONESTLY RESTRICTED FOR NON-INSTALLED TOOLCHAINS

---

## 1. Architectural Overview

ROXY-AI Code Studio distinguishes between **Editing**, **Executing**, **Testing**, and **Interactive Debugging**. A language whose files can be edited or syntax-highlighted is NOT automatically marked as having debugger support.

In Phase 5, we implemented `PythonDebuggerManager` (`backend/src/app/coding/debugger.py`) using Python's standard-library `bdb.Bdb` engine to provide a stateful, sandboxed interactive debugger.

---

## 2. Comprehensive Language Debugger Matrix

| Language | Editing Support | Run Support | Test Support | Debug Adapter / Engine | Breakpoint Support | Variable Inspection | Call-Stack Inspection | Cleanup & Isolation | Verified Status |
|---|---|---|---|---|---|---|---|---|---|
| **Python** | YES | YES | YES | Standard Library `bdb.Bdb` (`PythonDebuggerManager`) | YES (Line & Function) | YES (`f_locals` string repr) | YES (`f_back` chain unwinding) | YES (Sandboxed thread join) | **IMPLEMENTED_AND_VERIFIED** |
| **JavaScript** | YES | YES | YES | V8 Inspector (`node --inspect`) | STAGED (CLI worker required) | STAGED | STAGED | STAGED | **PARTIALLY_IMPLEMENTED** |
| **TypeScript** | YES | YES | YES | ts-node / source-map inspector | STAGED (ts-node required) | STAGED | STAGED | STAGED | **PARTIALLY_IMPLEMENTED** |
| **HTML / CSS** | YES | N/A | N/A | Browser DevTools MCP | N/A | N/A | N/A | N/A | **NOT_APPLICABLE** |
| **SQL** | YES | N/A | N/A | EXPLAIN / Query Plan | N/A | N/A | N/A | N/A | **NOT_APPLICABLE** |
| **Go** | YES | NO (Host PATH) | NO | Delve (`dlv`) | NO (Compiler missing) | NO | NO | NO | **BLOCKED_BY_ENVIRONMENT** |
| **Rust** | YES | NO (Host PATH) | NO | LLDB / GDB / rust-gdb | NO (Compiler missing) | NO | NO | NO | **BLOCKED_BY_ENVIRONMENT** |
| **C / C++** | YES | NO (Host PATH) | NO | GDB / LLDB | NO (Compiler missing) | NO | NO | NO | **BLOCKED_BY_ENVIRONMENT** |
| **Java** | YES | NO (Host PATH) | NO | JDWP / java-debug | NO (JDK missing) | NO | NO | NO | **BLOCKED_BY_ENVIRONMENT** |
| **PHP** | YES | NO (Host PATH) | NO | Xdebug | NO (Runtime missing) | NO | NO | NO | **BLOCKED_BY_ENVIRONMENT** |
| **C# / .NET** | YES | NO (Host PATH) | NO | NetCoreDbg | NO (SDK missing) | NO | NO | NO | **BLOCKED_BY_ENVIRONMENT** |
| **Bash** | YES | NO (on Windows) | NO | bashdb | NO (Posix only) | NO | NO | NO | **BLOCKED_BY_ENVIRONMENT** |
| **PowerShell** | YES | YES | NO | PS Debugger | NO (Not wired to API) | NO | NO | NO | **NOT_IMPLEMENTED** |

---

## 3. Python Debugger Capabilities Breakdown

| Capability | Supported? | Implementation Mechanism | Safety & Sandboxing |
|---|---|---|---|
| **Launch Session** | **YES** | `POST /debug/session/start` | Path validated by `FileSecuritySandbox` |
| **Set Breakpoints** | **YES** | `POST /debug/session/{id}/breakpoint` | Stored in `session.breakpoints`; lines verified |
| **Remove Breakpoints** | **YES** | `DELETE /debug/session/{id}/breakpoint/{line}` | Removed dynamically during execution |
| **Pause at Breakpoint** | **YES** | `SandboxedBdb.user_line` event wait | Thread pauses on `resume_event.wait()` |
| **Continue Execution** | **YES** | `action: "continue"` | Calls `set_continue()` |
| **Step Over** | **YES** | `action: "step_over"` | Calls `set_next(frame)` |
| **Step Into** | **YES** | `action: "step_into"` | Calls `set_step()` |
| **Step Out** | **YES** | `action: "step_out"` | Calls `set_return(frame)` |
| **Local Variables** | **YES** | `frame.f_locals` sanitized dict | Keys without `__`; string representations |
| **Call Stack** | **YES** | Traversal of `frame.f_back` | Function name, filename, lineno, locals |
| **Stop Session** | **YES** | `DELETE /debug/session/{id}` | Calls `set_quit()`, joins thread, cleans up |
| **Runtime Exceptions** | **YES** | `user_exception` capture | Captured in `session.exception_info` |
| **Tenant Isolation** | **YES** | `session.user_id` validation | User B forbidden (`403`) from accessing User A |
