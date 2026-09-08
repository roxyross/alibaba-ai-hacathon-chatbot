# ROXY JARVIS Runtime

The multi-agent runtime: loads `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` at startup, classifies user queries, and dispatches them to the right specialist.

**Status:** PR 2 — vertical slice. Coordinator + Research Agent + `web_search` stub. See `specs/001-runtime-orchestrator/spec.md` for the full plan.

## Quick start

```bash
# Install dependencies (uses uv, per Constitution §14.1)
uv sync

# Copy and fill in env
cp .env.example .env

# Run the runtime
uv run python -m runtime.main
# Service binds to http://localhost:8001
# Docs at http://localhost:8001/docs
# Health at http://localhost:8001/health/live
```

## Architecture

The runtime is a thin orchestration layer that sits alongside the existing AI gateway in `backend/`:

```
frontend (Vite SPA, :5173)
  ├─ /api/v1/auth/*    ─►  backend  (AI gateway, :8000)
  ├─ /api/v1/ai/*      ─►  backend
  └─ /api/v1/runtime/* ─►  runtime (this package, :8001)
                                  │
                                  └─ /api/v1/ai/chat  ─►  backend
```

The runtime **does not import** from `backend/src/app/**`. It calls the backend over HTTP.

## Project layout

```
runtime/
├── pyproject.toml
├── .env.example
├── src/
│   └── runtime/
│       ├── main.py            # FastAPI app factory; binds :8001
│       ├── config.py          # Pydantic Settings; reads .env
│       ├── logging.py         # structlog config (mirrors backend/src/app/logging.py)
│       ├── domain/            # Cross-feature domain types
│       ├── agents/            # Loader, registry, executor
│       ├── skills/            # Loader, registry, executor
│       ├── coordinator/       # Classifier, router, timeout
│       ├── api/               # FastAPI endpoints
│       └── infrastructure/    # DB, gateway client, auth
└── tests/
    ├── unit/
    ├── integration/
    └── contract/
```

## Tests

```bash
uv run pytest                            # full suite
uv run pytest tests/unit/                # unit only
uv run pytest tests/integration/         # integration
```

## Phase status

| Phase | Status | What's in it |
|---|---|---|
| PR 2 (this PR) | in progress | Coordinator + Research + `web_search` stub |
| PR 3 | not started | Real skills (search, calendar, code, memory), more agents |
| PR 4 | not started | Scheduler, Memory Curator, sensitive-skill gate, voice, browser |
