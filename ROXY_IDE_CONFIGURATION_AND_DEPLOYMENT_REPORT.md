# ROXY-AI — Code Studio Configuration & Deployment Report
**Date:** October 12, 2026  
**Auditor:** DevSecOps Lead & Production Reliability Engineer  
**Classification:** Production Configuration Specification (Zero Secrets Disclosed)

---

## 1. Environment Variable & Configuration Matrix

This matrix documents all configuration variables governing Roxy-AI Code Studio, AI model routing, terminal sandboxing, and multilingual pipelines.

| Variable Name | Purpose | Required / Optional | Default / Fallback | Safe Setup Location | Restart Required |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ROXY_WORKSPACE_ROOT` | Base directory root for sandboxed file operations | Optional | Current repository root | `.env` / System Env | Yes |
| `ROXY_TERMINAL_TIMEOUT_SEC` | Maximum execution duration before killing subprocesses | Optional | `30` | `.env` / System Env | No |
| `ROXY_AI_PROVIDER` | Active LLM provider (`gemini`, `openai`, `anthropic`, `local`) | Optional | `gemini` | `.env` | Yes |
| `GEMINI_API_KEY` | Authentication key for Google Gemini model inference | Required for cloud LLM | None (Prompt fallback) | `.env` (Never commit) | Yes |
| `OPENAI_API_KEY` | Optional alternate model provider key | Optional | None | `.env` (Never commit) | Yes |
| `ANTHROPIC_API_KEY` | Optional alternate model provider key | Optional | None | `.env` (Never commit) | Yes |
| `JWT_SECRET` | Signing key for session authorization tokens | Required | Random fallback in dev | `.env` (High entropy) | Yes |
| `JWT_ALGORITHM` | Symmetric hashing algorithm for auth tokens | Optional | `HS256` | `.env` | Yes |
| `DATABASE_URL` | Persistence store for snippets, executions, and audit | Optional | `sqlite+aiosqlite:///./data/roxy.db` | `.env` | Yes |
| `ROXY_LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | Optional | `INFO` | `.env` | No |
| `ROXY_SANDBOX_STRICT` | If `true`, restricts file access strictly to project root | Optional | `true` | `.env` | Yes |
| `VITE_API_BASE` | Frontend API base endpoint prefix | Optional | `/api/v1` | `frontend/.env` | Rebuild required |

---

## 2. Local vs. Deployed Environment Separation

### 2.1 Local Desktop Environment (Windows / macOS / Linux)
- **Filesystem Access:** Direct sandboxed access to local workspace folders via standard Python `pathlib`.
- **Terminal Execution:** Native local subprocesses executing in the workspace directory under the host user's local security context.
- **Compilers:** Leverages local system compilers (`python.exe`, `node.exe`, `tsc`, `git`). Missing compilers must be installed locally on PATH by the developer.
- **Voice Input:** Web Speech API in Chrome / Edge / Firefox capturing local microphone audio.

### 2.2 Cloud Container / Production Deployed Environment (Docker / GCP Cloud Run / Render)
- **Filesystem Access:** Bounded within container volume mounts (e.g. `/workspace`).
- **Terminal Execution:** Confined to container PID namespace with non-root user (`appuser` / `roxy`).
- **Compilers:** Pre-installed inside the container image via Dockerfile multi-stage builds (`python:3.11-slim`, `node:20-slim`).
- **Security Isolation:** Kernel cgroups and namespaces enforce memory limits (e.g. 2GB) and CPU quotas (e.g. 2 vCPUs), preventing denial-of-service from user scripts.
- **Secrets Management:** Cloud Secret Manager (GCP) or environment secret injections at runtime. Zero secrets baked into container images or frontend bundles.

---

## 3. Production Deployment Checklist

1. [x] **Sanitize Secrets:** Ensure `.env` is listed in `.gitignore` and `.dockerignore`.
2. [x] **Compile Assets:** Run `npm run build` in `frontend/` to produce production dist bundle.
3. [x] **Container Health Checks:** Configure `GET /api/v1/health` with 200 OK liveness/readiness probe.
4. [x] **Subprocess Resource Quotas:** Ensure timeout defaults (30s) are active in production environments.
5. [x] **Tool Registry Validation:** Verify `GET /api/v1/coding/tools` returns all 11 core workspace tools on container startup.
