# ROXY — Autonomous Personal AI Assistant & Multi-Agent Operating System

**ROXY** is a production-hardened, multi-agent AI personal operating system powered by a high-performance **FastAPI** backend, a modern **React 18 / Vite SPA**, and a **Next.js 16 (Turbopack)** companion application. It coordinates 22+ specialist agents through an intent-classifying Coordinator, a multi-provider AI gateway with automatic failover, and 18 dedicated productivity studios.

---

## 🌟 Key Highlights & Architecture

- **Multi-Agent Runtime & Coordinator**: Intelligent keyword and semantic classification routing requests across 22+ specialist agents (Coding, Memory, Audit, Research, Browser, Voice, Finance, Study, etc.).
- **Multi-Provider AI Gateway with Failover**: Hierarchical fault-tolerant failover: **Gemini → Grok → DeepSeek → OpenAI**, ensuring zero downtime with provider attribution and token logging.
- **18 Specialized Studios**: Full-featured, production-ready interfaces with optimistic UI mutations, resilient retryable error banners, non-intrusive guest authentication guidance, and zero mock demo data.
- **Dual Frontend Architecture**:
  - **React 18 / Vite SPA (`frontend/`)**: Ultra-responsive single-page application with dark mode styling (`#162020` card surfaces, `#273636` borders, `#0d9488` teal / `#10b981` emerald accents).
  - **Next.js 16 (Turbopack) Companion (`nextjs-frontend/`)**: Static pre-rendered companion suite compiling 22/22 routes for global CDN edge deployment.
- **Enterprise Security & Compliance**:
  - **§10.12 Immutable Audit Ledger**: Append-only 1-year compliance retention with strict prohibition of record modification or deletion.
  - **Pre-Execution Risk Gate (Security Agent)**: Automated T1 (Safe Read), T2 (Caution External Action), and T3 (Destructive / Exfiltration Block) verification.
  - **GDPR / CCPA "Right to be Forgotten"**: Instant portable JSON data exports and verified permanent erasure across all data vaults.

---

## 🛠️ The 18 Specialized Studios

| Studio | Features & Capabilities |
|---|---|
| 💬 **Chat & Multi-Agent Runtime** | SSE streaming, Critic pre-flight review (>200 chars), multi-agent chat grounding, and session history persistence. |
| 💻 **Coding & Execution Studio** | Multi-language runner (`python`, `js`, `ts`, `bash`, `sql`), stdin drawer, live stdout/stderr execution terminal, AI copilot (Generate, Explain, Debug), and snippets library. |
| 🧠 **Semantic Memory & Curator** | Cross-session facts vault, Forever importance pinning, soft-delete archive, autonomous clustering & pruning curator, scored hybrid retrieval, and GDPR export/purge. |
| 🛡️ **Audit, Security & Activity** | Immutable 1-year audit ledger, Pre-Execution Risk Gate simulator (T1/T2/T3 verdicts, blast radius analysis), and compliance archive export. |
| 🎓 **Study & Learning Studio** | Leitner 5-box spaced repetition deck reviewer, AI flashcard synthesis from topic or lecture notes, and interactive 4-choice practice quizzes. |
| 🌐 **Browser Automation Studio** | Live URL inspector, heading hierarchy (H1-H6), hyperlinks directory, forms & inputs detector, visual snapshot capture, and autonomous multi-step execution flows. |
| 🔬 **Deep Research Hub** | Multi-source academic & web synthesis, deep topic breakdown, live citations, and markdown research report exports. |
| 🎙️ **Voice Session Studio** | Push-to-talk voice recording, Whisper speech-to-text (STT), runtime coordination, and ElevenLabs / OpenAI TTS playback with real-time waveform. |
| 📅 **Calendar & Scheduling** | Schedule management, conflict detection, recurring agenda tracking, and ICS calendar exports. |
| 📧 **Email Hub** | Gmail OAuth2 integration, SMTP fallback engine, rich email composer, recipient validation, and inbox telemetry. |
| 🎨 **Image Studio** | Multi-model generative image synthesis, aspect ratio controls, prompt enhancement, and gallery management. |
| 📚 **Knowledge Vault** | Multi-format document ingestion (PDF, DOCX, TXT), semantic vector chunking, and similarity search grounding. |
| 📁 **Workspace Hub** | Multi-project organization, sandboxed artifacts storage, contextual notes, and multi-tenant isolation. |
| ⏰ **Scheduled Jobs Studio** | APScheduler-powered recurring tasks (Cron, Interval, One-shot ISO), job pause/resume/cancel controls, and execution history. |
| 💳 **Finance Dashboard** | Plaid sandbox banking OAuth, real-time balance inquiries, spending category analysis, and budget tracking. |
| 📊 **Usage Telemetry** | Real-time token consumption metrics, cost breakdown by provider and agent, and quota status. |
| 📑 **Billing & Subscriptions** | Subscription plan upgrades/downgrades (Free, Pro, Enterprise), payment history, and downloadable PDF invoices. |
| 💳 **Payment Methods** | Safepay & Stripe card management, default payment selector, and PCI-compliant tokenization. |

---

## 🏗️ Project Structure

```
roxy-personal-ai/
├── backend/                         # FastAPI Python Backend
│   ├── src/app/
│   │   ├── api/v1/                  # REST API routers (coding, memory, audit, study, browser, etc.)
│   │   ├── ai_gateway/              # Multi-provider AI gateway (Gemini, Grok, DeepSeek, OpenAI)
│   │   ├── auth/                    # OAuth2 (Google, GitHub), Magic Link, JWT session auth
│   │   ├── memory/                  # Semantic vector memory repository & autonomous curator
│   │   ├── audit/                   # §10.12 Immutable audit ledger & risk gate verification
│   │   ├── skills/                  # Standalone skill executors
│   │   └── main.py                  # App entry point, CORS, and lifecycle handlers
│   ├── tests/integration/           # 24 Master integration test suites (100% passing)
│   ├── alembic/                     # Database migrations (PostgreSQL / SQLite)
│   └── vercel.json                  # Vercel serverless function deployment config
├── frontend/                        # React 18 / Vite SPA
│   ├── src/
│   │   ├── components/              # 18 Studio UI components & common design system
│   │   ├── session/                 # SessionSidebar, session management
│   │   ├── auth/                    # AuthGate & authentication modal
│   │   └── App.tsx                  # Root switcher & global state
│   └── vite.config.ts               # Vite bundler configuration
├── nextjs-frontend/                 # Next.js 16 Companion App (Turbopack)
│   ├── src/app/                     # 22 Static routes (/coding, /memory, /audit, /study, etc.)
│   ├── src/components/              # Navigation header, shared cards, and layout wrappers
│   └── next.config.ts               # Next.js Turbopack configuration
└── specs/                           # Engineering specifications and phase blueprints
```

---

## 🚀 Getting Started

### 1. Backend Setup

```bash
cd backend
cp .env.example .env   # Configure your API keys (Gemini, OpenAI, Database URL, etc.)
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. React Vite SPA Setup

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```
The React SPA runs at `http://localhost:5173` and proxies requests to `http://localhost:8000`.

### 3. Next.js Companion App Setup

```bash
cd nextjs-frontend
cp .env.example .env.local
npm install
npm run dev
```
The Next.js companion runs at `http://localhost:3000`.

---

## 🧪 Testing & Verification

The system includes comprehensive automated test coverage across all architectural phases:

```bash
# Run all integration test suites
cd backend
pytest tests/integration/ -v

# Run frontend typecheck and build
cd ../frontend
npm run typecheck
npm run build

# Run Next.js companion Turbopack build
cd ../nextjs-frontend
npm run build
```

---

## 🛡️ License & Attributions

Developed for the **Alibaba AI Hackathon**. Built with FastAPI, React, Next.js, and multi-agent AI orchestration.
