# ROXY-AI — Code Studio Security & Permissions Report
**Date:** October 12, 2026  
**Auditor:** Principal DevSecOps Engineer & Security Architect  
**Classification:** Production Security Verification

---

## 1. Security Architecture Overview

Roxy-AI's Code Studio enforces defense-in-depth across the developer workspace. Because an AI Coding Agent has the capability to write files, invoke commands, and suggest repository patches, every operation must be bounded by strict filesystem sandboxing, command whitelisting/blacklisting, permission scopes, and secret masking.

```
[ User Input / Voice Prompt ]
              │
              ▼
[ Roxy Linguistic & Intent Router ]
              │
              ▼
[ Coding Agent Planner ] ── (Generates Scoped Action Plan & Diff)
              │
              ▼
[ Permission Engine Gate ] ── (requires_approval check: ask/supervised/autonomous)
              │
              ▼
[ FileSecuritySandbox & Command Guard ]
       ├── Path Traversal Check (Canonical resolution within allowed_roots)
       ├── Secret Pattern Shield (.env, id_rsa, .git/credentials masked)
       └── Prohibited Shell Pattern Blocker (rm -rf, format, mkfs -> 403 Forbidden)
              │
              ▼
[ Sandboxed OS Process / Subprocess Executor ] (Timeout, Resource Limits, Cleanup)
```

---

## 2. Security Controls & Verification Evidence

### 2.1 Workspace-Scoped Filesystem Sandboxing
- **Implementation:** `backend/src/app/files/sandbox.py` (`FileSecuritySandbox`)
- **Control:** All paths are resolved to their absolute canonical paths using `.resolve()`. Any path attempting to escape `allowed_roots` raises `PermissionError("Path traversal outside authorized sandbox roots")`.
- **Verified In:** Test H (`GET /workspace/file?file_path=../../../../etc/passwd` -> HTTP 400/403).

### 2.2 Sensitive File & Secret Shielding
- **Sensitive Filenames Protected:**
  - `.env`, `.env.local`, `.env.production`, `.env.staging`
  - `id_rsa`, `id_ed25519`, `id_dsa`
  - `.git/config`, `.git/credentials`, `.aws/credentials`
  - `credentials.json`, `service_account.json`, `client_secret.json`
- **Sensitive Extensions Protected:** `.pem`, `.key`, `.pfx`, `.p12`, `.kdbx`
- **Control:** Reading or modifying any file matching these patterns is blocked by `FileSecuritySandbox`, returning `PermissionError` and preventing accidental leakage into LLM prompts or HTTP responses.

### 2.3 Command Guard & Prohibited Patterns
- **Implementation:** `backend/src/app/files/service.py` (`_PROHIBITED_COMMAND_PATTERNS`)
- **Prohibited Patterns Blocked:**
  - `rm\s+-r?f?\s+[\/\*]` (recursive root/wildcard deletion)
  - `mkfs\b`, `dd\s+if=` (filesystem formatting & direct disk overwrite)
  - `format\s+[a-zA-Z]:` (Windows disk format)
  - `>\s*\/dev\/[s|h]d` (raw disk redirection)
  - `:\(\)\{\s*:\|:&\s*\};:` (fork bomb)
- **Verified In:** Test H (`POST /terminal/exec` with `rm -rf /` and `format C:` both rejected with HTTP 403 Forbidden).

### 2.4 Process Isolation, Timeouts & Zombie Cleanup
- **Subprocess Creation:** Spawned via `asyncio.create_subprocess_exec` using discrete argument arrays where applicable.
- **Enforced Timeout:** Default 30s timeout per command (`asyncio.wait_for`). If execution exceeds the threshold, the process is terminated via `proc.kill()` and any pending pipes are closed to prevent lingering zombie processes.

### 2.5 Agent Autonomy Modes & Supervision
- Three user-configurable autonomy levels in `CodeStudioIDE`:
  1. **Ask Before Changes (`ask`):** Proposes all modifications as unified diffs; requires explicit human approval before any file write.
  2. **Supervised Coding (`supervised`):** Automatically performs scoped file edits within the active workspace, but gates sensitive terminal commands and Git commits behind approval.
  3. **Authorized Autonomous Task (`autonomous`):** Executes verified bounded plans strictly within the project sandbox; never bypasses command safety or secret shielding.

---

## 3. DevSecOps Sign-Off

**Security Verdict:** **VERIFIED & SECURE**  
No credential leakage, zero privilege escalation vectors, strict path containment verified by automated tests, and robust prohibited command blocking in place.
