# Quickstart: Multi-Provider AI Abstraction

**Feature:** multi-provider-ai | **Date:** 2026-09-02

---

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- API keys for at least one provider (DeepSeek, Grok, OpenAI, or Gemini)

---

## Environment Setup

```bash
# Clone the repo
git clone https://github.com/<org>/roxy-personal-ai.git
cd roxy-personal-ai

# Copy environment template
cp .env.example .env

# Fill in at least one provider key
# DeepSeek
DEEPSEEK_API_KEY=sk-your-deepseek-key

# Grok (xAI)
XAI_API_KEY=sk-your-xai-key

# OpenAI (fallback)
OPENAI_API_KEY=sk-your-openai-key

# Gemini
GEMINI_API_KEY=your-gemini-key

# Provider enable/disable flags (all enabled by default)
PROVIDER_DEEPSEEK_ENABLED=true
PROVIDER_GROK_ENABLED=true
PROVIDER_OPENAI_ENABLED=true
PROVIDER_GEMINI_ENABLED=true
```

---

## Run Backend

```bash
cd backend

# Install dependencies (uses uv)
uv sync

# Run database migrations
uv run alembic upgrade head

# Seed provider configuration
uv run python -m app.seeds.providers

# Start FastAPI dev server
uv run uvicorn app.main:app --reload --port 8000
```

---

## Run Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

---

## Verify Health

```bash
# Check provider health status
curl http://localhost:8000/api/v1/ai/providers/health

# Expected response:
# {
#   "providers": [
#     { "name": "deepseek", "status": "healthy", "circuit_state": "closed" },
#     { "name": "grok",     "status": "healthy", "circuit_state": "closed" },
#     { "name": "openai",   "status": "healthy", "circuit_state": "closed" },
#     { "name": "gemini",   "status": "healthy", "circuit_state": "closed" }
#   ]
# }
```

---

## Test a Chat Request

```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello, which provider are you using?"}],
    "stream": false
  }'
```

Response will include `provider`, `model`, `input_tokens`, `cost_usd`, and `latency_ms`.

---

## Test Streaming

```bash
curl -N -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Write a short poem."}],
    "stream": true
  }'
```

Attribution is emitted as SSE comments. The final event contains full attribution metadata.

---

## Test Failover

```bash
# Disable DeepSeek (simulates outage)
curl -X PATCH http://localhost:8000/api/v1/ai/providers/deepseek \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Now send a request — it should route to Grok automatically
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## View Token Usage Logs

```bash
curl http://localhost:8000/api/v1/ai/usage?limit=10
```

---

## Adding a New Provider (Operator)

1. Add the API key to `.env`
2. Add the provider record to the database:
   ```bash
   uv run python -m app.seeds.providers --add anthropic
   ```
3. Set `PROVIDER_ANTHROPIC_ENABLED=true` in `.env`
4. No code changes needed. Agents automatically route to the new provider based on priority order.
