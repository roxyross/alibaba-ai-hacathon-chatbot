# ROXY-AI — POST-PHASE 5.1: BUILT-IN TOOLS & DEEP RESEARCH AUDIT
*(Workstream F Deliverable)*

## 1. Tool Registry Acceptance Matrix

Roxy-AI exposes a suite of built-in productivity and analytical tools accessible both directly via dedicated UI views and programmatically by the Agent Coordinator:

| Tool Name | Frontend View | Backend Handler | Credentials Required | Confirmation Policy | Result Format | Test Status | Live Status |
| :--- | :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| **Calculator** | [Calculator.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Calculator/Calculator.tsx) | Client Engine + `app.tools` | None | None (Safe) | Numeric / Formula JSON | **PASS** | **PASS** |
| **Calendar** | [CalendarView.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Calendar/CalendarView.tsx) | `app.calendar.router` | None (Local DB) | None (Safe) | Event Object List | **PASS** | **PASS** |
| **Documents Vault** | [DocumentUpload.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Documents/DocumentUpload.tsx) | `app.documents.router` | None (Local OCR/Text) | None (Safe) | Extracted Text & Chunks | **PASS** | **PASS** |
| **Email Sender** | [EmailSendPanel.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Email/EmailSendPanel.tsx) | `app.emails.router` | `SMTP_HOST`, `SMTP_USER` | **Target Confirmation Token** | Message ID / Status | **PASS (Mock)** | **BLOCKED (No SMTP)** |
| **Web Browser Agent** | [BrowserStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/BrowserStudio/BrowserStudio.tsx) | `app.browser.router` | Optional Proxy | Confirmation for POST forms | HTML / Screenshots / Text | **PASS (Mock)** | **PARTIAL** |
| **Deep Research** | [ResearchHub.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/Research/ResearchHub.tsx) | `app.research.router` | Search API / Scraper | None (Read-only) | Markdown Synthesis & Citations | **PASS** | **PARTIAL (Mocked Search)** |
| **Code Runner** | [CodeStudioIDE.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/CodingStudio/CodeStudioIDE.tsx) | `app.coding.router` | Container Environment | Confirmation on destructive bash | Stdout / Stderr / Return code | **PASS** | **PASS (Sandboxed)** |

---

## 2. Deep Research Engine Workflow

The Deep Research service ([backend/src/app/research/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/research/)) implements an autonomous multi-stage research lifecycle:

1. **Request Intake & Query Expansion:** User specifies research topic and search depth (Standard: 3 queries, Deep: 10 queries).
2. **Concurrent Web Retrieval:** Dispatches search queries, crawls top search results, and filters boilerplate HTML.
3. **Evidence Extraction & Deduplication:** Extracts key empirical findings, claims, and author citations.
4. **Cross-Checking & Contradiction Detection:** Evaluates contradictory claims across diverse sources.
5. **Synthesis & Citation Numbering:** Compiles comprehensive markdown report with inline superscript citations (`[^1]`, `[^2]`) and verified bibliography.
6. **Persistence:** Saves final structured report in PostgreSQL table `research_reports` with downloadable PDF/Markdown export.

---

## 3. Tool Security & Action Confirmation

Dangerous and consequential external actions enforce **Target-Scoped Permission Tokens** (Alembic migration `007_target_scoped_permissions`):
- Attempting to send an external email, transfer funds, or execute destructive shell commands returns `HTTP 403 Forbidden` with a `confirmation_required` payload containing:
  - `confirmation_token` (cryptographically signed, 5-minute expiry).
  - `target_action` (e.g. `send_email`).
  - `target_recipient` (e.g. `client@external.com`).
- The frontend intercepts this response and presents [ConfirmationModal.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/ConfirmationModal/ConfirmationModal.tsx). Once the user approves, the signed token is re-submitted to complete execution.

---

## 4. Test Verification Evidence

- `tests/integration/test_phase6_deep_research.py`: Deep research request lifecycle, query planning, report synthesis (**PASS**).
- `tests/integration/test_phase11_calendar.py`: Event scheduling, conflict detection, recurrence (**PASS**).
- `tests/integration/test_phase12_email.py`: Email drafting, confirmation interception, mock send (**PASS**).
- `tests/integration/test_phase15_browser.py`: Browser task queuing and screenshot capture (**PASS**).
