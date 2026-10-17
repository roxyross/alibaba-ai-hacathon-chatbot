# Roxy-AI — Phase 5 IDE, Workspace & Sandbox Security Audit

**Audited Services:**  
- Coding Studio & Autonomous Engineering: `backend/src/app/api/v1/coding.py`  
- Filesystem & Sandbox Boundary: `backend/src/app/files/service.py` & `sandbox.py`  
- Study Studio: `backend/src/app/api/v1/study.py`  
- Frontend IDE Component: `frontend/src/components/CodingStudio/CodeStudioIDE.tsx`  
**Date:** October 13, 2026  

---

## 1. Executive Summary

The Developer Studio and Coding Agent provide rich in-browser IDE capabilities, including Monaco code editing, recursive file trees, multi-file diff previews, terminal execution, and Git source control status.

However, forensic audit of `FileSecuritySandbox` and `FileSystemService` identified a **major architectural limitation regarding multi-tenant workspace boundaries and host command execution**.

---

## 2. Workspace & Sandbox Boundary Audit

### A. Root Boundary Containment
- **Implementation:** `backend/src/app/files/sandbox.py` (lines 45–52):
  ```python
  workspace_root = Path(__file__).resolve().parents[4]  # roxy-personal-ai repository root
  self.allowed_roots = [workspace_root]
  ```
- **Finding:** The sandbox roots itself at the top-level repository directory (`roxy-personal-ai`). While directory traversal attempts seeking to escape above this root (`../../../../etc/passwd` or `C:\Windows`) are successfully intercepted and blocked (**VERIFIED** in `FileSecuritySandbox.validate_path`), the sandbox does **not** confine different users to isolated subdirectories. Every authenticated user who accesses `/api/v1/coding/workspace/tree` views the application's source code files (`backend/`, `frontend/`, `tests/`).
- **Classification:** **FAILED / P1 ARCHITECTURAL LIMITATION**

### B. Sensitive Secret File Masking
- **Implementation:** `_SENSITIVE_PATTERNS` explicitly blocks `.env`, `.env.local`, `.env.production`, `.git/config`, `id_rsa`, `credentials.json`, and `.pem`/`.key` files.
- **Verification:** Any attempt to read or modify protected secrets yields `PermissionError: '... is a protected secret file'` and logs a security warning (**VERIFIED** via unit tests).

### C. Terminal Execution & Host Subprocess Isolation
- **Implementation:** `backend/src/app/files/service.py` lines 446–505 (`run_terminal_command`):
  ```python
  proc = await asyncio.create_subprocess_shell(
      command,
      cwd=str(canon_cwd),
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
  )
  ```
- **Finding:** Terminal commands are executed directly in the host OS process environment using `asyncio.create_subprocess_shell`. While an in-memory blocklist rejects 8 specific destructive string patterns (`rm -rf /`, `format c:`, etc.), commands are **not executed inside a dedicated Docker container, gVisor sandbox, or Linux cgroup jail**.
- **Impact:** Any authenticated user with terminal execution access runs processes under the permissions of the user account executing the backend server.
- **Classification:** **FAILED / P1 SECURITY CONCERN**

---

## 3. IDE Editor, Tabs & State Synchronization Matrix

| Feature / Control | Frontend Component | Backend API | Behavior Under Test | Audit Status |
| :--- | :--- | :--- | :--- | :--- |
| **Open / Close IDE** | `CodingStudio.tsx` | N/A (Client state) | Clean transitions between chat and full-screen IDE | **VERIFIED** |
| **File Tree Sync** | `FileTree.tsx` | `GET /api/v1/coding/workspace/tree` | Hierarchical folder expand/collapse with dotfile toggle | **VERIFIED** |
| **File Open & Tabs** | `CodeEditor.tsx` | `GET /api/v1/coding/workspace/file` | Multi-tab switching, dirty state indicators on unsaved edits | **VERIFIED** |
| **File Save & Reload** | `CodeEditor.tsx` | `POST /api/v1/coding/workspace/file` | Ctrl+S writes file content; reloads on external change | **VERIFIED** |
| **Go To Line Control** | `MonacoWrapper.tsx` | Client Monaco API | Ctrl+G navigation scrolls cursor to target line number | **VERIFIED** |
| **Terminal Output** | `TerminalPanel.tsx` | `POST /api/v1/coding/terminal/exec` | Real stdout/stderr streaming with exit code display | **VERIFIED** |
| **AI Agent Assist** | `AgentAssistModal.tsx` | `POST /api/v1/coding/agent/assist` | Proposes unified diffs with accept/reject review controls | **VERIFIED** |
| **Git Source Control** | `GitPanel.tsx` | `GET/POST /api/v1/coding/git/*` | Displays branch, unstaged/staged diffs, commit dialog | **VERIFIED** |

---

## 4. Multi-Tenant Workspace Recommendations (Post-Release Roadmap)

1. **Per-Tenant Directory Scoping:** Refactor `FileSecuritySandbox` to construct isolated roots per user: `allowed_roots = [workspace_root / "workspaces" / user_id]`.
2. **Containerized Terminal Execution:** Replace `asyncio.create_subprocess_shell` with ephemeral Docker container execution (`docker run --rm -v /user_workspace:...`) with disabled network access and memory caps.
