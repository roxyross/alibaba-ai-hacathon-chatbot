# Quickstart: Running the Runtime Locally

**PR:** 2 | **Runtime:** `http://localhost:8001`

This guide gets the multi-agent runtime running on your machine without Docker.

---

## Prerequisites

- **Python** 3.12+
- **uv** — run `pip install uv` or follow [docs.uv.dev](https://docs.uv.dev)
- **Backend** running at `http://localhost:8000` (for the AI gateway — the runtime calls it)

---

## 1. Install dependencies

```bash
cd runtime
uv sync
```

This installs all dependencies from `pyproject.toml` including the dev tools (pytest, ruff, mypy).

---

## 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set:

| Variable | Required | Notes |
|----------|----------|-------|
| `JWT_SECRET` | ✅ | Must match `backend/.env` — the runtime validates the same magic-link JWTs |
| `BACKEND_BASE_URL` | ✅ | Default: `http://localhost:8000` — change if backend is elsewhere |
| `HOST` | | Default: `0.0.0.0` |
| `PORT` | | Default: `8001` |
| `LOG_LEVEL` | | Default: `INFO` — set to `DEBUG` for verbose output |

---

## 3. Run the runtime

```bash
uv run python -m runtime.main
```

Expected output:
```
runtime.startup agents=20 routable=19 skills=32 backend=http://localhost:8000
```

The service binds to `http://localhost:8001`.

---

## 4. Verify it's up

```bash
# Process is up
curl http://localhost:8001/health/live
# → {"status": "ok", "service": "runtime"}

# Registries populated (may show "degraded" if backend is unreachable)
curl http://localhost:8001/health/ready
# → {"status": "ok", "agents_loaded": 20, "skills_loaded": 32, ...}
```

---

## 5. Try a chat request

You'll need a valid JWT from the backend's magic-link flow. In development, you can generate a test token:

```python
import jwt, time
payload = {"sub": "test-user-id", "email": "test@example.com", "exp": int(time.time()) + 3600}
token = jwt.encode(payload, "YOUR_JWT_SECRET", algorithm="HS256")
print(token)
```

Then:

```bash
curl -X POST http://localhost:8001/api/v1/runtime/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "search the web for latest AI research news"}'
```

Expected response:
```json
{
  "needs_clarification": false,
  "agent_slug": "research",
  "response": "According to my research, ...",
  "citations": [],
  "status": "ok",
  "next_actions": []
}
```

---

## 6. List loaded agents and skills

```bash
# List all agents
curl http://localhost:8001/api/v1/runtime/agents \
  -H "Authorization: Bearer YOUR_TOKEN"

# List all skills (web_search should show registered=true)
curl http://localhost:8001/api/v1/runtime/skills \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 7. Run the test suite

```bash
uv run python -m pytest                            # full suite
uv run python -m pytest tests/unit/                # unit tests only
uv run python -m pytest tests/integration/        # integration tests
uv run python -m pytest tests/contract/           # API contract tests
uv run ruff check src/runtime/                    # lint
uv run mypy src/runtime/                          # type check
```

---

## 8. OpenAPI docs

Interactive docs at: **http://localhost:8001/docs**

---

## Common Issues

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` | Check `JWT_SECRET` matches the backend's |
| `gateway 5xx` | Backend at `BACKEND_BASE_URL` is not running |
| `agents_loaded: 0` | `AGENTS_DIR` / `SKILLS_DIR` paths wrong; check logs |
| `skill.load.failed` | One of the `.claude/skills/*/SKILL.md` files has bad YAML frontmatter; fix or remove the file |
