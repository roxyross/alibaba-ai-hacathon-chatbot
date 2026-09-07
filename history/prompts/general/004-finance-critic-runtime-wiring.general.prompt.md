---
name: finance-critic-runtime-wiring
description: Build Runtime Router, Finance API, Critic pre-flight, and Finance Dashboard UI
metadata:
  type: general
---

# PHR — Finance + Critic Agent Full-Stack Wiring

**ID:** 004
**Stage:** implement
**Surface:** agent
**Feature:** none
**Branch:** 001-runtime-orchestrator
**User:** (local user)
**Date (ISO):** 2026-09-07
**Model:** minimax/minimax-m2.2:free

## Command

User asked to complete and fully wire: Finance agent (bank connection, transaction categorization, budget summaries, spending alerts) and Critic/Evaluator agent (silent pre-flight review of all specialist responses). Both backend and frontend. Skills: bank_connect, critic_review.

## Labels

["finance-agent", "critic-agent", "runtime-router", "finance-api", "finance-dashboard", "critic-preflight", "backend", "frontend"]

## Links

- Backend Runtime Router: `backend/src/app/api/v1/runtime.py`
- Backend Finance API: `backend/src/app/api/v1/finance.py`
- Finance Dashboard UI: `frontend/src/components/FinanceDashboard/FinanceDashboard.tsx`
- Finance Dashboard CSS: `frontend/src/components/FinanceDashboard/FinanceDashboard.css`
- Finance Hook: `frontend/src/hooks/useFinance.ts`
- Budget Model: `backend/src/app/models/budget.py`
- SpendingAlert Model: `backend/src/app/models/spending_alert.py`

## Files Created/Modified

- `backend/src/app/api/v1/runtime.py` — NEW: Runtime Router with Coordinator pattern, intent classification, Critic pre-flight
- `backend/src/app/api/v1/finance.py` — NEW: Finance API (budgets CRUD, alerts CRUD, summary, transactions)
- `backend/src/app/models/budget.py` — NEW: Budget ORM model
- `backend/src/app/models/spending_alert.py` — NEW: SpendingAlert ORM model
- `backend/src/app/models/__init__.py` — MODIFIED: Export Budget and SpendingAlert
- `backend/src/app/main.py` — MODIFIED: Register runtime_router and finance_router
- `frontend/src/components/FinanceDashboard/FinanceDashboard.tsx` — NEW: Finance Dashboard with all cards
- `frontend/src/components/FinanceDashboard/FinanceDashboard.css` — NEW: Dark theme CSS
- `frontend/src/hooks/useFinance.ts` — NEW: Finance data hook
- `frontend/src/App.tsx` — MODIFIED: Finance Dashboard toggle, runtime URL fix (8001→8000)
- `frontend/src/components/ChatMessage/ChatMessage.tsx` — MODIFIED: Fix Attribution.provider/model → agentSlug

## What Was Built

### Backend — Runtime Router (`runtime.py`)
- `POST /api/v1/runtime/chat` — Coordinator routing with keyword-based intent classification
- Routes to: finance | critic | automation | research | coding | study | browser | general
- Loads agent system prompts from `.claude/agents/<slug>.md` at startup
- Calls AI gateway with agent-specific system prompt
- **Critic pre-flight**: responses > 200 chars run through `critic_review` skill before returning
- `POST /api/v1/runtime/chat/stream` — SSE streaming with Critic pre-flight on final chunk

### Backend — Finance API (`finance.py`)
- `GET /finance/summary` — Full financial snapshot (accounts, balances, budgets, alerts, month spending)
- `GET /finance/transactions` — Transactions proxied via `bank_connect` skill
- `GET|POST /finance/budgets` — Budget list and create
- `PUT|DELETE /finance/budgets/{id}` — Budget update and delete
- `GET|POST /finance/alerts` — Alert list and create
- `DELETE /finance/alerts/{id}` — Delete alert
- `GET /finance/accounts` — Connected accounts via `bank_connect` skill

### Backend — Finance Models
- `Budget` ORM model: category, monthly_limit, alert_threshold, current_spent
- `SpendingAlert` ORM model: name, alert_type, threshold_amount, category, institution, enabled

### Frontend — Finance Dashboard (`FinanceDashboard.tsx`)
- `BankConnectionCard` — Shows connected accounts, total balance, "Connect Bank" button
- `TransactionListCard` — Recent transactions with debit/credit coloring
- `BudgetOverviewCard` — Budget bars with color coding (green/yellow/red), add/delete budgets
- `SpendingAlertsCard` — Alert list with add/delete, type icons
- `MonthSpendingCard` — This month's total spending vs combined budget
- Responsive grid layout (auto-fit, minmax 280px)
- All mobile responsive

### Frontend — Finance Hook (`useFinance.ts`)
- `useFinance({ accessToken })` hook with: fetchSummary, fetchTransactions, createBudget, deleteBudget, createAlert, deleteAlert
- All calls include Bearer auth when token present

### Frontend — App.tsx wiring
- "💰 Finance" toggle button in header (accent-colored when active)
- Conditional render: FinanceDashboard ↔ ChatWindow
- Runtime URL fixed: `localhost:8001` → `localhost:8000`

### Frontend — ChatMessage fix
- Attribution display now uses `agentSlug` instead of non-existent `provider`/`model` fields

## Outcome

Finance Agent and Critic/Evaluator Agent are now fully implemented end-to-end in both backend and frontend. The Runtime Router routes Finance queries to the Finance agent, and all specialist responses automatically run through Critic pre-flight before returning to the user. The Finance Dashboard provides a full UI for bank connections, transactions, budgets, and spending alerts.
