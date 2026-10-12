# ROXY-AI — Language Runtime Strategy & Capability Matrix
**Audit Date:** October 12, 2026  
**Auditor:** Principal IDE Architect & Senior Developer Tools Engineer  
**Host Environment:** Windows x64, Python 3.14.0, Node.js v24.19.0, npm 11.17.0, Git 2.43.0  
**Docker Daemon Status:** CLI installed (v29.7.2); Docker Desktop daemon inactive on named pipe

---

## 1. Full Multi-Language Capability Matrix

| Language | File Extensions | Editing & Highlighting | AST Understanding | Linting & Diagnostics | Compilation | Execution | Automated Testing | Verified Host Toolchain |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Python** | `.py`, `.pyi` | YES | YES | YES | N/A (Interpreted) | YES | YES (`pytest`) | Python 3.14.0 |
| **JavaScript** | `.js`, `.mjs`, `.cjs` | YES | YES | YES | N/A (JIT) | YES | YES (`vitest`, `npm test`) | Node.js v24.19.0 |
| **TypeScript** | `.ts`, `.tsx` | YES | YES | YES | YES (`tsc`) | YES (via Node/ts-node) | YES (`vitest`) | `tsc` 5.3.3, Node.js v24.19 |
| **HTML / CSS** | `.html`, `.css`, `.scss`| YES | YES | YES (DOM validator)| N/A | YES (Browser Preview) | YES | Browser DOM runtime |
| **SQL** | `.sql` | YES | YES | N/A | N/A | YES (via DB connector)| YES (Query tests) | SQLite 3 / aiosqlite |
| **Shell / Bash** | `.sh`, `.bash` | YES | YES | YES | N/A | YES (via bash/WSL if configured) | YES | Subprocess executor |
| **PowerShell** | `.ps1` | YES | YES | YES | N/A | YES | YES | PowerShell 7 / Windows PS |
| **JSON / YAML** | `.json`, `.yaml`, `.yml`| YES | YES | N/A | N/A | N/A (Config) | N/A | Python `json` / `yaml` |
| **Markdown** | `.md` | YES | YES | N/A | N/A | N/A (Docs) | N/A | Built-in renderer |
| **Go** | `.go` | YES | YES | YES | BLOCKED (No `go`) | BLOCKED | BLOCKED | `go` not on host PATH |
| **Rust** | `.rs` | YES | YES | YES | BLOCKED (No `rustc`) | BLOCKED | BLOCKED | `rustc` not on host PATH |
| **C / C++** | `.c`, `.cpp`, `.h` | YES | YES | YES | BLOCKED (No `gcc`/`clang`)| BLOCKED | BLOCKED | `gcc`/`clang` not on host PATH |
| **Java** | `.java` | YES | YES | YES | BLOCKED (No `javac`)| BLOCKED | BLOCKED | `javac` not on host PATH |
| **PHP** | `.php` | YES | YES | YES | BLOCKED (No `php`)| BLOCKED | BLOCKED | `php` not on host PATH |
| **C# / .NET** | `.cs` | YES | YES | YES | BLOCKED (No `dotnet`)| BLOCKED | BLOCKED | `dotnet` not on host PATH |
| **Ruby** | `.rb` | YES | YES | YES | N/A | BLOCKED (No `ruby`)| BLOCKED | `ruby` not on host PATH |
| **Kotlin** | `.kt`, `.kts` | YES | YES | YES | BLOCKED (No `kotlinc`)| BLOCKED | BLOCKED | `kotlinc` not on host PATH |
| **Swift** | `.swift` | YES | YES | YES | BLOCKED (No `swiftc`)| BLOCKED | BLOCKED | `swiftc` not on host PATH |
| **Dart** | `.dart` | YES | YES | YES | BLOCKED (No `dart`) | BLOCKED | BLOCKED | `dart` not on host PATH |

---

## 2. Verified Host Runtimes & Execution Evidence

### 2.1 Python 3.14.0 Execution Evidence
```powershell
Command: python -c "import sys; print('PYTHON_VERIFIED', sys.version)"
Stdout:  PYTHON_VERIFIED 3.14.0 (tags/v3.14.0:eb13e43, Oct  7 2026, 12:00:00) [MSC v.1944 64 bit (AMD64)]
Exit:    0
Duration: 85ms
```

### 2.2 Node.js v24.19.0 Execution Evidence
```powershell
Command: node -e "console.log('NODE_VERIFIED', process.version)"
Stdout:  NODE_VERIFIED v24.19.0
Exit:    0
Duration: 110ms
```

### 2.3 TypeScript Compiler Evidence
```powershell
Command: npx tsc --version
Stdout:  Version 5.3.3
Exit:    0
Duration: 620ms
```

---

## 3. Environment & Deployment Strategy (Section 2.2 Decision)

### Deployment Decision: Option D (Restricted Existing Runtime) with Staged Containerization Profile
1. **Host Environment Analysis:**
   - Docker CLI is installed (`Docker version 29.7.2`), but the local Docker Desktop daemon is not running (`cannot connect to docker API at npipe:////./pipe/dockerDesktopLinuxEngine`).
   - Per Section 2.2 rule: *"If no additional runtime can safely be deployed now, retain currently verified execution support and report unsupported languages honestly. Do not force a cloud architecture change solely to satisfy a language checklist."*
2. **Runtime Policy:**
   - For Python, Node.js/TypeScript, Shell, and PowerShell, code executes locally within `FileSecuritySandbox` and `asyncio.subprocess` boundaries.
   - For Go, Rust, C/C++, Java, PHP, and .NET, the IDE presents clear truthful notices:
     `"Editing & syntax analysis supported. Native compiler not detected on host PATH. To execute, configure compiler or run in container worker."`
3. **Container Worker Profile (For Docker / Cloud Run Production):**
   - In production Docker deployments, `backend/Dockerfile` provides a Debian base with `build-essential` (`gcc`, `g++`, `make`), enabling C/C++ compilation.
   - A multi-toolchain Dockerfile profile is specified in Section 4 below to support Go and Rust in cloud worker environments.

---

## 4. Multi-Toolchain Execution Worker Dockerfile Profile

```dockerfile
# Roxy Multi-Language Execution Worker Image Profile
FROM debian:bookworm-slim AS roxy-toolchain-worker

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    nodejs npm \
    build-essential gcc g++ make \
    golang-go \
    rustc cargo \
    openjdk-17-jdk-headless \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# Restricted non-root execution user
RUN useradd -m -u 1001 roxyworker
USER roxyworker
WORKDIR /workspace

CMD ["/bin/bash"]
```

---

## 5. Security & Isolation Safeguards

For every user-code execution path:
- **Workspace Containment:** Enforced by `FileSecuritySandbox` ensuring paths never escape the target workspace root.
- **Process Timeout:** Enforced 30-second default timeout via `asyncio.wait_for`.
- **Prohibited Command Blocker:** Destructive commands (`rm -rf /`, `format C:`, `dd if=/dev`, fork bombs) rejected with HTTP 403 Forbidden.
- **Secret Isolation:** Environment files (`.env*`), private keys (`id_rsa`, `*.pem`, `*.key`), and cloud credentials (`credentials.json`, `.aws/credentials`) are strictly masked and inaccessible to user code.
