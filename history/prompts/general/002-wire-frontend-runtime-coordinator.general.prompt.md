---
name: wire-frontend-runtime-coordinator
description: Wire frontend useChat to Runtime Coordinator + upgrade Coding skills
metadata:
  type: general
---

# PHR — Wire Frontend to Runtime Coordinator + Upgrade Coding Skills

**ID:** 002
**Stage:** implement
**Surface:** agent
**Feature:** none
**Branch:** 001-runtime-orchestrator
**User:** (local user)
**Date (ISO):** 2026-09-06
**Model:** minimax/minimax-m2.2:free

## Command

User prompt: "upgrade the Coding skills to real implementations (with actual file/tools access), and then wire the frontend to Runtime Frontend → Runtime Plan. The frontend currently calls /api/v1/ai/chat/stream (AI gateway). Needs to call /api/v1/runtime/chat (Coordinator) instead. Key changes: 1. useChat.ts — swap SSE parsing for Coordinator's JSON response format 2. Add VITE_RUNTIME_URL — point to port 8001 3. AuthContext — already passes accessToken as Bearer token (same JWT), so auth will work"

## Labels

["frontend", "runtime", "coordinator", "useChat", "coding-skills"]

## Links

- SPEC: `specs/001-runtime-orchestrator/spec.md`
- Runtime Chat API: `runtime/src/runtime/api/chat.py`

## Files (YAML)

```yaml
- frontend/src/hooks/useChat.ts        # SSE → JSON, new Attribution/ChatState shapes
- frontend/.env                        # added VITE_RUNTIME_URL
- frontend/.env.example                # added VITE_RUNTIME_URL
- frontend/src/App.tsx                 # read VITE_RUNTIME_URL, runtime vs API routing
- frontend/src/model_provider/ModelPicker.tsx  # added Runtime Coordinator option
- .claude/skills/code_generate/SKILL.md       # explicit Read/Bash/Write tool calls
- .claude/skills/code_explain/SKILL.md        # explicit Read/Grep tool calls
- .claude/skills/code_debug/SKILL.md          # explicit Bash/Read/Edit tool calls
```

## Prompt Text (verbatim)

upgrade the Coding skills to real implementations (with actual file/tools access), and then wire the frontend to Runtime Frontend → Runtime Plan

The frontend currently calls /api/v1/ai/chat/stream (AI gateway). Needs to call /api/v1/runtime/chat (Coordinator) instead. Key changes:

1. useChat.ts — swap SSE parsing for Coordinator's JSON response format
2. Add VITE_RUNTIME_URL — point to port 8001
3. AuthContext — already passes accessToken as Bearer token (same JWT), so auth will work

## Response Text (concise)

Completed all tasks:

1. **useChat.ts** — Replaced SSE `ReadableStream` loop with a single `fetch` + `await response.json()`. Changed `Attribution` from `{provider, model}` to `{agentSlug}`. Added `needsClarification` and `nextActions` to `ChatState`. Request body now `{ message, session_id }` (Coordinator format).

2. **VITE_RUNTIME_URL** — Added to both `.env` and `.env.example` as `http://localhost:8001`.

3. **App.tsx** — Reads `VITE_RUNTIME_URL` env var. Routes to `runtimeUrl` when `provider === 'runtime'`, otherwise uses `apiBase`.

4. **ModelPicker.tsx** — Added static "Runtime Coordinator" option (`provider='runtime'`, empty model) in a Runtime optgroup above the AI providers. Removed the `rest.length === 0` guard that prevented empty model selection.

5. **Coding skills** — Added explicit tool names to Steps sections:
   - `code_generate`: **Read** (context), **Bash** (lint/typecheck), **Bash** (sandbox verify), **Write** (output file)
   - `code_explain`: **Read** (file), **Grep** (locate lines), **Read** (call graph)
   - `code_debug`: **Bash** (repro), **Read** (trace), **Edit** (fix), **Bash** (verify)
