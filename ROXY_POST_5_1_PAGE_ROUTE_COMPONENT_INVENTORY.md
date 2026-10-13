# ROXY-AI — POST-PHASE 5.1: PAGE, ROUTE & COMPONENT INVENTORY
*(Workstream A Deliverable)*

## 1. Overview & Architectural Discovery

The Roxy-AI client is structured as a rich, single-page reactive dashboard with deep-linked views, modal overlays, and omnibar command capabilities.

- **Primary Client:** [frontend/src/App.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/App.tsx)
- **Deep-Linked URL Routes:**
  - `/`: Main dashboard (Chat, Cowork, or active secondary view).
  - `/code-studio`: Direct route to Code Studio IDE (synchronized with browser `popstate` and pushState).
- **Navigation Model:** [SessionSidebar.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/session/SessionSidebar.tsx) drives `AppView` state transitions across 25 distinct interactive surfaces.

---

## 2. Complete Inventory of Discovered Views & Components

| View Identifier (`AppView`) | Component & File Location | Route / Entry Point | Purpose | Backend Endpoints Required | Auth Required | Interactive Controls |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `chat` | [ChatWindow.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/chat/ChatWindow.tsx) | `/` (default) | Conversational AI, tool execution display, real-time message stream | `POST /api/v1/ai/chat/stream`, `POST /api/v1/sessions` | Optional (Guest trial enabled) | Text input, voice trigger, model picker, file attach, pin message, retry |
| `coding` | [CodeStudioIDE.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/CodingStudio/CodeStudioIDE.tsx) | `/code-studio` or `Ctrl+Alt+I` | Full-featured IDE, file tree, syntax highlighting, workspace sync | `POST /api/v1/coding/execute`, `GET /api/v1/projects` | Yes | File explorer, editor, terminal run button, new file, branch pill |
| `control_center` | [ControlCenter.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/ControlCenter/ControlCenter.tsx) | Sidebar → Control Center | System health overview, quick actions, telemetry | `GET /api/v1/system-health`, `GET /api/v1/observability` | Yes | Telemetry cards, service refresh, navigation jump links |
| `trust_center` | [TrustCenter.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/TrustCenter/TrustCenter.tsx) | Sidebar → Trust & Safety | Security audits, exit gates, adversarial tests | `GET /api/v1/trust/events`, `GET /api/v1/testing-matrix` | Yes | Exit gate panel, security scanner trigger, audit log export |
| `device_hub` | [DeviceHub.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/DeviceHub/DeviceHub.tsx) | Sidebar → Device Hub | Enrolled devices, desktop automation, app discovery | `GET /api/v1/device/enrolled`, `POST /api/v1/device/commands` | Yes | Enroll device modal, app launcher, send command, disconnect |
| `connectors` | [ConnectorsHub.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Connectors/ConnectorsHub.tsx) | Sidebar → Connectors & MCP | MCP servers, 3rd party tool integrations | `GET /api/v1/connectors`, `POST /api/v1/mcp/servers` | Yes | Add server, toggle connector, test connection, revoke |
| `knowledge_vault` | [KnowledgeVault.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/KnowledgeVault/KnowledgeVault.tsx) | Sidebar → Knowledge Vault | Document ingestion, RAG vector index, semantic search | `GET /api/v1/vault/documents`, `POST /api/v1/vault/upload` | Yes | File dropzone, re-index button, delete document, search |
| `memory` | [MemoryStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/MemoryStudio/MemoryStudio.tsx) | Sidebar → Memory Studio | Long-term semantic memories, user facts, preferences | `GET /api/v1/memory/facts`, `DELETE /api/v1/memory/facts/{id}` | Yes | Edit memory, delete fact, search memories, toggle extraction |
| `image_studio` | [ImageStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/ImageStudio/ImageStudio.tsx) | Sidebar → Image Studio | Generative image studio (Imagen 3, Flux), prompt editor | `POST /api/v1/images/generate`, `GET /api/v1/images/gallery` | Yes | Prompt input, aspect ratio picker, style selector, download |
| `video_studio` | [VideoStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/VideoStudio/VideoStudio.tsx) | Sidebar → Video Studio | Veo 3.1 video generator, canvas inpainting, camera motion | `POST /api/v1/media/jobs/video`, `GET /api/v1/media/jobs` | Yes | Motion sliders, resolution, duration picker, preview player |
| `workspace_hub` | [WorkspaceHub.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/WorkspaceHub/WorkspaceHub.tsx) | Sidebar → Workspace Hub | Projects, multi-agent workspaces, file repos | `GET /api/v1/projects`, `POST /api/v1/projects` | Yes | Create workspace, switch active workspace, archive project |
| `jobs` | [ScheduledJobsView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/ScheduledJobs/ScheduledJobsView.tsx) | Sidebar → Scheduled Jobs | APScheduler tasks, recurring prompts, cron jobs | `GET /api/v1/jobs`, `POST /api/v1/jobs` | Yes | New job modal, pause job, resume job, trigger now, delete |
| `finance` | [FinanceView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Finance/FinanceView.tsx) | Sidebar → Finance Dashboard | Accounts, expense tracking, Raast payment links | `GET /api/v1/finance/accounts`, `POST /api/v1/raast/initiate` | Yes | Add account, spending alerts, export report, transfer |
| `usage` | [UsageView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Usage/UsageView.tsx) | Sidebar → Usage & Credits | Token consumption, model cost breakdown, quotas | `GET /api/v1/usage/summary`, `GET /api/v1/usage/logs` | Yes | Date range picker, export CSV, navigate to billing |
| `billing` | [BillingView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Billing/BillingView.tsx) | Sidebar → Billing & Plans | Subscription tier, invoices, top-up credits | `GET /api/v1/billing/subscription`, `POST /api/v1/billing/checkout` | Yes | Upgrade tier, cancel subscription, add credits, view invoices |
| `payment_methods`| [PaymentMethodView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/PaymentMethods/PaymentMethodView.tsx)| Sidebar → Payment Methods | Saved cards, Stripe/Safepay wallets | `GET /api/v1/billing/payment-methods` | Yes | Add payment method, set default, remove card |
| `email` | [EmailSendPanel.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Email/EmailSendPanel.tsx) | Sidebar → Email Studio | SMTP email composer, target confirmation | `POST /api/v1/emails/send` | Yes | To, Subject, Body editor, send button, confirmation dialog |
| `voice` | [VoiceSession.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Voice/VoiceSession.tsx) | Sidebar → Voice Mode | Full-screen interactive voice conversation | `POST /api/v1/voice/transcribe`, `POST /api/v1/voice/synthesize` | Yes | Push-to-talk, live waveform, speech speed, stop speech |
| `documents` | [DocumentUpload.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Documents/DocumentUpload.tsx) | Sidebar → Document Upload | Quick PDF/text analyzer and parser | `POST /api/v1/documents/upload` | Yes | Upload dropzone, file parser, summarize in chat |
| `calculator` | [Calculator.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Calculator/Calculator.tsx) | Sidebar → Calculator | Built-in financial and scientific calculator | Client-side math engine + `/api/v1/tools` | Optional | Keypad, memory buttons, copy result, send to chat |
| `calendar` | [CalendarView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Calendar/CalendarView.tsx) | Sidebar → Calendar | Interactive month/week agenda, AI schedule planner | `GET /api/v1/calendar/events`, `POST /api/v1/calendar/events` | Yes | Add event, date navigation, schedule with AI prompt |
| `research` | [ResearchHub.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Research/ResearchHub.tsx) | Sidebar → Deep Research | Multi-step research engine, citations, synthesis | `POST /api/v1/research/start`, `GET /api/v1/research/{id}` | Yes | Query input, depth selector, download PDF report, cancel |
| `browser` | [BrowserStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/BrowserStudio/BrowserStudio.tsx) | Sidebar → Browser Studio | Headless web navigation, screenshot extraction | `POST /api/v1/browser/tasks`, `GET /api/v1/browser/tasks/{id}` | Yes | URL input, execute task, inspect live screenshots |
| `study` | [StudyStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/StudyStudio/StudyStudio.tsx) | Sidebar → Study Studio | Flashcards, quiz generator, Zia tutor | `GET /api/v1/study/decks`, `POST /api/v1/study/decks` | Yes | Flip card, quiz answers, generate deck from topic |
| `audit` | [AuditStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/AuditStudio/AuditStudio.tsx) | Sidebar → Audit Logs | Security audit trail, user actions, data export | `GET /api/v1/audit/logs`, `POST /api/v1/trust/export` | Yes | Filter by event type, date range, export JSON/CSV |
| `pricing` | [PricingPlans.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/PricingPlans/PricingPlans.tsx) | Sidebar → Pricing Plans | Tiers overview (Free, Pro, Team, Enterprise) | Static config + `POST /api/v1/billing/checkout` | No | Tier selection, switch billing frequency, checkout |

---

## 3. Global Modal Overlays & Omnibar Controls

1. **Roxy Command Omnibar (`Ctrl+K`):**
   - [RoxyCommandBar.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/CommandBar/RoxyCommandBar.tsx)
   - Dispatches fuzzy search across all 25 views, active sessions, models, and actions.
   - Tested in `RoxyCommandBar.test.tsx` (3 tests passed).

2. **New Task Autonomous Modal (`Ctrl+N`):**
   - [NewTaskModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/NewTaskModal/NewTaskModal.tsx)
   - Allows users to specify task objective, model override (default: `gemini-3.8-flash`), execution mode (Autonomous vs Guided), and repository context.
   - Tested in `NewTaskModal.test.tsx` (2 tests passed).

3. **Global Settings Modal (15 Sections):**
   - [SettingsModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/SettingsModal/SettingsModal.tsx)
   - Implements Profile, Appearance, AI Persona, Models & Providers, Image, Video, Voice, Notifications, Privacy, Security, Accounts, Billing, BYOK, Memory, Danger Zone.
   - Tested in `test_phase34_settings_all_15_sections.py` (passed).

4. **Authentication & Session Modal:**
   - [AuthModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/AuthModal/AuthModal.tsx)
   - Magic link sign-in, password authentication, and Google OAuth redirect trigger.

5. **Target-Scoped Confirmation Dialog:**
   - [ConfirmationModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/ConfirmationModal/ConfirmationModal.tsx)
   - Intercepts dangerous actions (file deletions, financial transfers, external email dispatch) with signed token validation.

---

## 4. Disconnected Prototypes & Experimental Boundaries

- **`nextjs-frontend/`:** Standalone Next.js 14 prototype. Does not participate in the Vite build or Docker production containers. Documented as unlinked prototype.
- **`runtime/`:** Standalone agent runner codebase. Currently integrated directly into FastAPI gateway in `backend/src/app/agent_runtime/`.
- **`android/` and `ios/`:** Native project shells containing capacitor/react-native bindings. Documented as device shells pending physical hardware deployment.
