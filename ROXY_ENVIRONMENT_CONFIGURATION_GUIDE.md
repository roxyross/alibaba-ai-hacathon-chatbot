# ROXY-AI Environment Configuration Guide

**Document Purpose:** Complete Configuration & Environment Setup Manual  
**Applies To:** Roxy-AI Backend (FastAPI), Frontend (Vite/React), Database (PostgreSQL/pgvector), Redis, and Multi-Platform Clients  
**Audience:** DevOps Engineers, Full-Stack Developers, Release Managers

---

## 1. Quick Start Local Setup

1. **Clone & Initialize Submodules:**
   ```bash
   git clone https://github.com/<org>/roxy-personal-ai.git
   cd roxy-personal-ai
   git submodule update --init --recursive
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   ```
   Generate random JWT secrets:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Paste the generated value into `JWT_SECRET` and `JWT_SERVICE_SECRET`.

3. **Run Database Migrations:**
   ```bash
   cd backend
   alembic upgrade head
   python scripts/validate_migrations.py
   ```

4. **Launch Development Servers:**
   - **Backend API:**
     ```bash
     cd backend
     uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
     ```
   - **Frontend App:**
     ```bash
     cd frontend
     npm install
     npm run dev
     # Access application at http://localhost:5173
     ```

---

## 2. Master Environment Variables Matrix

### 2.1 Core Application & Server

| Variable Name | Default Value | Production Example | Description |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | `development` | `production` | Runtime mode: `development`, `test`, `staging`, `production`. |
| `ROXY_VERSION` | `2.0.0` | `2.0.0` | Current release semver tag. |
| `COMMIT_SHA` | `local` | `6becde7` | Git commit SHA populated by CI/CD pipeline. |
| `HOST` | `0.0.0.0` | `0.0.0.0` | Network binding interface. |
| `PORT` | `8000` | `8000` | Internal HTTP listening port for FastAPI. |
| `APP_BASE_URL` | `http://localhost:5173` | `https://roxy.ai` | Canonical web application origin URL. |
| `LOG_LEVEL` | `INFO` | `INFO` | Logging severity threshold: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

### 2.2 Database & Migrations (PostgreSQL 16 + pgvector)

| Variable Name | Default Value | Production Example | Description |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@db:5432/roxy_dev` | `postgresql+asyncpg://user:pass@10.0.0.3:5432/roxy_prod` | Asynchronous SQLAlchemy connection URI. |
| `STRICT_MIGRATIONS` | `false` | `true` | When `true`, startup aborts immediately if migrations are pending. |

### 2.3 Cache & Token Bucket Rate Limiting (Redis 7)

| Variable Name | Default Value | Production Example | Description |
| :--- | :--- | :--- | :--- |
| `REDIS_URL` | `redis://redis:6379/0` | `rediss://:pass@redis-cluster:6380/0` | Redis instance connection URI. |
| `RATE_LIMIT_TOKENS_PER_MINUTE` | `10000` | `60000` | Global token limit for API gateway rate limiting. |

### 2.4 Authentication & Secrets (Strictly Server-Side)

| Variable Name | Security Level | Description |
| :--- | :--- | :--- |
| `JWT_SECRET` | **CRITICAL SECRET** | 32-byte hexadecimal secret key used for signing client JWTs. |
| `JWT_SERVICE_SECRET` | **CRITICAL SECRET** | Secret key for internal microservice and background worker tokens. |
| `JWT_EXPIRY_HOURS` | Standard Config | Access token validity window (default: `168` hours = 7 days). |
| `MAGIC_LINK_TTL_MINUTES` | Standard Config | Expiration for passwordless sign-in magic links (default: `15`). |
| `CORS_ALLOWED_ORIGINS` | Network Security | Comma-delimited list of permitted CORS web origins. |

### 2.5 Multi-Provider AI Credentials

| Variable Name | Provider | Supported Capabilities |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini | Flash 2.0, Pro 1.5, Multimodal Vision, Grounding Search |
| `GROK_API_KEY` | xAI Grok | Grok 2, Fast reasoning, Real-time query synthesis |
| `OPENAI_API_KEY` | OpenAI | GPT-4o, GPT-4o-mini, Embeddings (text-embedding-3) |
| `DEEPSEEK_API_KEY` | DeepSeek | DeepSeek V3, DeepSeek R1 Reasoning |

### 2.6 Frontend Public Client Variables (Vite)

| Variable Name | Default Value | Description |
| :--- | :--- | :--- |
| `VITE_API_BASE` | `/api/v1` | Relative API path proxy or absolute gateway URL. |
| `VITE_RUNTIME_URL` | `http://localhost:8000` | Direct backend runtime URL for local tooling. |

---

## 3. Configuration Validation & Health Check

Run the following checks to verify configuration health:

1. **Verify Database Connectivity:**
   ```bash
   python -c "import asyncio, asyncpg, os; asyncio.run(asyncpg.connect(os.environ.get('DATABASE_URL').replace('+asyncpg', '')))"
   ```
2. **Verify Migration Status:**
   ```bash
   alembic current
   python scripts/validate_migrations.py
   ```
3. **Verify Frontend Environment Build:**
   ```bash
   cd frontend
   npm run typecheck
   npm run build
   ```
