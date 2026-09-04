# ROXY JARVIS AI Gateway

**Multi-provider AI abstraction layer** — routes requests across DeepSeek, Grok (xAI), OpenAI, and Gemini with automatic failover, per-response attribution, token-usage logging, and circuit-breaker protection.

---

## Quick Start

```bash
cd backend

# Install dependencies
pip install -e ".[dev]"

# Copy and fill in API keys
cp .env.example .env
# Edit .env — set at least one of DEEPSEEK_API_KEY, XAI_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY

# Run the server
python -m app.main
# API available at http://localhost:8000/api/v1/ai
# Docs at http://localhost:8000/docs
```

## Multi-Provider Setup

All providers are disabled by default until their feature-flag env vars are set:

| Provider | Feature Flag | API Key Env Var | Base URL |
|---|---|---|---|
| DeepSeek | `PROVIDER_DEEPSEEK_ENABLED=true` | `DEEPSEEK_API_KEY` | `https://api.deepseek.com` |
| Grok | `PROVIDER_GROK_ENABLED=true` | `XAI_API_KEY` | `https://api.x.ai/v1` |
| OpenAI | `PROVIDER_OPENAI_ENABLED=true` | `OPENAI_API_KEY` | `https://api.openai.com/v1` |
| Gemini | `PROVIDER_GEMINI_ENABLED=true` | `GEMINI_API_KEY` | `https://generativelanguage.googleapis.com/v1beta` |

Enable a provider by setting its flag to `true` (no restart required).

## Provider Override

Three-tier override hierarchy — highest specificity wins:

1. **Operator disable** — `PROVIDER_<NAME>_ENABLED=false` (absolute)
2. **Request-level override** — `provider` field in request body or `X-Provider-Preference` header
3. **User preference** — stored in DB `UserPreference` table (post-hackathon)

Default routing priority: **DeepSeek → Grok → OpenAI → Gemini**

## Streaming SSE

Streaming is enabled per-request with `stream: true`:

```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role":"user","content":"Hello"}], "stream": true}'
```

Response format:
```
: provider=deepseek model=deepseek-chat-v3

data: {"delta": "Hello", "provider": "deepseek", "model": "deepseek-chat-v3", "done": false}
data: {"delta": " world", "provider": "deepseek", "model": "deepseek-chat-v3", "done": false}
event: attribution
data: {"done": true, "provider": "deepseek", "model": "deepseek-chat-v3"}
```

## Failover Testing

Simulate a provider outage to verify automatic failover:

```bash
# Disable DeepSeek — next request should route to Grok
curl -X PATCH http://localhost:8000/api/v1/ai/providers/deepseek

# Or set the env var directly (requires restart):
# PROVIDER_DEEPSEEK_ENABLED=false
```

All circuit-breaker and failover logic is in `src/app/ai_gateway/services/router.py`.

## Circuit Breaker

| Parameter | Default | Env Var |
|---|---|---|
| Failures before open | 5 | `CIRCUIT_BREAKER_FAILURES` |
| Reset timeout (seconds) | 30 | `CIRCUIT_BREAKER_RESET_SECONDS` |
| Successes to close | 2 | — |

## Token Usage Logging

Every AI request is logged (no prompt contents stored):

```bash
curl http://localhost:8000/api/v1/ai/usage?limit=10
```

Logs include: `request_id`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`.

**Note:** Persistence is in-memory by default. To use Neon PostgreSQL:

```bash
# Set DATABASE_URL in .env
# prisma generate
# prisma migrate dev --name add_ai_provider_models
# python -m app.seeds.providers
```

## Project Structure

```
backend/
├── prisma/schema.prisma          # DB schema (Provider, Model, TokenUsageLog, UserPreference)
├── src/app/
│   ├── ai_gateway/
│   │   ├── adapters/             # Provider adapters (deepseek, grok, openai, gemini)
│   │   ├── models/               # Pydantic schemas + provider config
│   │   └── services/
│   │       ├── router.py         # AIRouter — failover + routing
│   │       ├── sanitizer.py     # Prompt injection blocklist + wrapping
│   │       └── token_logger.py   # Per-request token usage logging
│   ├── api/v1/ai.py              # FastAPI router + SSE streaming endpoint
│   ├── db.py                     # SQLAlchemy async engine + sessionmaker singleton (T027)
│   ├── repositories/             # Data access (TokenUsageRepository)
│   └── seeds/providers.py        # Seed script: python -m app.seeds.providers
└── tests/
    ├── unit/                     # Adapter, router, sanitizer unit tests
    └── integration/              # Endpoint + failover integration tests
```

## Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

See [`specs/feature/multi-provider-ai.md`](specs/feature/multi-provider-ai.md) for the full feature specification and [`specs/feature/multi-provider-ai/tasks.md`](specs/feature/multi-provider-ai/tasks.md) for the task breakdown.

---

## Authentication

ROXY supports three sign-in methods on the same `/auth` namespace:

- **Magic link** — `POST /api/v1/auth/request-link` then `POST /api/v1/auth/verify`. Already wired in dev (link is printed to the server log when no SMTP is configured).
- **Google OAuth** — see below.
- **GitHub OAuth** — see below.

### Google OAuth setup

1. **Create an OAuth client** at <https://console.cloud.google.com/apis/credentials>:
   - Application type: **Web application**
   - Authorized redirect URI: `<OAUTH_REDIRECT_BASE_URL>/api/v1/auth/oauth/google/callback`
     For local dev with the default backend on `:8000`, that's
     `http://localhost:8000/api/v1/auth/oauth/google/callback`.
2. **Add the keys to `backend/.env`:**

   ```bash
   GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=...
   OAUTH_REDIRECT_BASE_URL=http://localhost:8000
   # Optional: comma-separated allowlist for the hackathon demo.
   # GOOGLE_ALLOWED_EMAILS=alice@example.com,bob@example.com
   ```

3. **Restart the backend.** With `GOOGLE_CLIENT_ID` set, the "Sign in with Google" button on the auth gate will start working. Without it, the start endpoint returns `503 Google OAuth is not configured` — this is intentional, not a silent fallback.

### How the OAuth flow works

```
Browser → GET /api/v1/auth/oauth/google/start
            ← 302 to https://accounts.google.com/o/oauth2/v2/auth?...&state=...
              (also sets an HttpOnly `roxy.oauth_state` cookie for CSRF)

User approves on Google.

Google → GET /api/v1/auth/oauth/google/callback?code=...&state=...
            Backend validates state cookie == state param (single-use).
            Exchanges code for tokens, verifies the id_token against Google's JWKS.
            Requires `email_verified: true` on the id_token.
            Upserts the user by email and mints a session JWT.
            ← 302 to ${APP_BASE_URL}/auth/callback#access_token=...&expires_in=...
              (token in URL hash, never sent in Referer)

Frontend /auth/callback reads the hash, calls /auth/me, stores the JWT.
```

The `state` cookie is `HttpOnly`, `SameSite=Lax`, and single-use. JWKS responses are cached in-process for 5 minutes; a `kid` miss forces a refetch.

### GitHub OAuth setup

1. **Create an OAuth App** at <https://github.com/settings/developers> → **New OAuth App**:
   - Homepage URL: `http://localhost:5173`
   - Authorization callback URL: `http://localhost:8000/api/v1/auth/oauth/github/callback`
2. **Generate a client secret** (GitHub shows it once on creation; you can also rotate it under the app's settings). Add to `backend/.env`:

   ```bash
   GITHUB_CLIENT_ID=...
   GITHUB_CLIENT_SECRET=...
   # OAUTH_REDIRECT_BASE_URL is shared with Google and defaults to http://localhost:8000.
   # GITHUB_ALLOWED_EMAILS=alice@example.com,bob@example.com   # optional allowlist
   ```

3. **Restart the backend.** With `GITHUB_CLIENT_ID` set, the "Continue with GitHub" button on the auth gate will start working. Without it, the start endpoint returns `503 GitHub OAuth is not configured` — same fail-closed rule as Google.

### How the GitHub OAuth flow differs from Google

- GitHub returns an **opaque `access_token`** (not a signed `id_token`). We exchange the code, then call `GET /user` (identity) and `GET /user/emails` (verified primary email) with it.
- There is **no `email_verified` claim**. We enforce it ourselves: the user must have an email where `primary == true && verified == true`. If they don't, the backend redirects back to the frontend with `#error=email_unverified`.
- We request the `read:user` and `user:email` scopes. Without `user:email` the `/user/emails` endpoint returns 404.
- GitHub's API requires `Accept: application/vnd.github+json` and a pinned `X-GitHub-Api-Version: 2022-11-28`. We send both.
- Rate limit: 5000 req/hr with auth — three calls per login is well under.

Everything else (state cookie, URL-hash handoff, session JWT, account linking by email) is identical to Google.
