# ROXY — Personal AI Assistant

ROXY is a multi-agent AI assistant with a FastAPI backend and a React/TypeScript frontend. It routes every user request to the right specialist agent — research, coding, finance, automation, voice, and more — using a keyword-classification Coordinator and a multi-provider AI gateway with automatic failover.

---

## Tech Stack

**Backend** — Python 3.11+ · FastAPI · Pydantic · APScheduler · httpx · structlog

**Frontend** — TypeScript · React 18 · Vite · CSS custom properties (Catppuccin Mocha theme)

**AI Providers** (in priority order, with automatic failover):
- **Gemini** — primary model
- **Grok** — fallback when Gemini is unavailable
- **DeepSeek** — fallback #2
- **OpenAI** — fallback #3

**Voice** — Whisper (STT) · OpenAI TTS / ElevenLabs (TTS)

**Banking** — Plaid OAuth (sandbox)

**Email** — Gmail API (OAuth2) · SMTP fallback

---

## Project Structure

```
roxy-personal-ai/
├── backend/src/app/
│   ├── main.py                  # FastAPI entry point, CORS, route registration
│   ├── api/v1/                  # REST endpoints
│   │   ├── runtime/            # Coordinator router (keyword → agent dispatch)
│   │   ├── ai/                 # Direct AI chat
│   │   ├── session/            # Chat sessions
│   │   ├── chat_history/       # Per-session message history
│   │   ├── bank/               # Plaid OAuth + account/transactions API
│   │   └── finance/            # Budget + spending insights
│   ├── skills/                 # 17 skill executors (store_memory, web_search, …)
│   ├── ai_gateway/             # Multi-provider AI abstraction layer
│   │   ├── adapters/           # Gemini, Grok, DeepSeek, OpenAI adapters
│   │   └── services/router.py  # Failover routing, token logging
│   └── job_scheduler.py         # APScheduler integration for scheduled jobs
├── frontend/src/
│   ├── App.tsx                 # Root component, view switcher
│   ├── components/
│   │   ├── ChatWindow/         # Streaming message list
│   │   ├── ChatInput/          # Text input with model picker
│   │   ├── VoiceSession/       # Push-to-talk voice UI
│   │   ├── FinanceDashboard/    # Bank accounts, budgets, spending
│   │   ├── ScheduledJobsPanel/ # Create/list/pause/cancel jobs
│   │   ├── EmailSendPanel/     # Compose and send emails
│   │   └── SensitiveActionConfirm/ # Confirmation modal for sensitive ops
│   └── hooks/
│       └── useChat.ts          # SSE streaming + one-shot chat hook
├── .claude/agents/             # 22 agent system prompts (markdown)
└── .claude/skills/             # Skill definitions (markdown + SKILL.md)
```

---

## Features

| Feature | Description |
|---|---|
| **Multi-Agent Orchestration** | Keyword-classification Coordinator routes to 10+ specialist agents |
| **AI Failover** | Automatic switch to next provider when one is unavailable |
| **Streaming Chat** | SSE-based token streaming with per-provider attribution |
| **Skill System** | 17 standalone skills — memory, search, email, banking, calendar, voice |
| **Scheduled Jobs** | APScheduler-powered recurring jobs with cron/ISO scheduling |
| **Voice** | Push-to-talk recording → Whisper STT → Runtime → TTS playback |
| **Banking** | Plaid OAuth connect, account balances, transaction history |
| **Email** | Gmail OAuth2 compose & send, SMTP fallback |
| **Sensitive Action Gate** | Confirmation modal before email send, bank connect, job creation |
| **Critic Pre-flight** | Silent review of all responses > 200 chars before delivery |
| **Session History** | Persistent chat sessions with full turn history |

---

## Getting Started

### Backend

```bash
cd backend
cp .env.example .env   # fill in API keys
pip install -e .
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and calls the backend at `http://localhost:8000`.

---

## API Keys Required

| Service | Environment Variable |
|---|---|
| Gemini | `GEMINI_API_KEY` |
| Grok | `GROK_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Gmail (send) | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI` |
| SMTP | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` |
| Plaid | `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENVIRONMENT` |
