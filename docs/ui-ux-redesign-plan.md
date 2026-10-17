# ROXY JARVIS — Comprehensive UI/UX Redesign Plan & Blueprint

**Repository**: `roxyross/alibaba-ai-hacathon-chatbot`  
**Feature Branch**: `design/roxy-ui-ux-redesign`  
**Target Delivery**: Polished, Premium, Cohesive AI Operating Workspace  
**Date**: October 18, 2026  
**Architect**: Antigravity AI  

---

## 1. Vision & Core Design Principles

ROXY JARVIS is an autonomous personal AI operating system. The redesigned interface should feel like a state-of-the-art AI command deck: **intentional, calm, modern, polished, responsive, and deeply capable.**

### Core Tenets:
1. **Zero Functionality Regression**: Every API contract, session flow, agent router, tool execution, security gate, and persistence mechanism must remain 100% operational.
2. **Visual Hierarchy & Calm Clarity**: Eliminate competing buttons and redundant entry points. Give every workspace a distinct identity while sharing a common design grammar.
3. **Harmonious Palette & Craftsmanship**:
   - Refined brand accent: Curated emerald/teal (`#0d9488` in light mode, `#14b8a6` in dark mode).
   - Light mode: Crisp, soft ceramic surfaces (`#f8faf9` base, `#ffffff` card surfaces, subtle borders `#e2e8e6`).
   - Dark mode: Deep obsidian slate (`#0d1313` base, `#141d1d` surface, fine borders `#222f2f`).
   - Eliminate harsh saturated buttons and emoji icons in favor of crisp SVG iconography from `lucide-react`.
4. **Predictable Layout & Scrolling**:
   - Distinct non-scrolling chrome (Header, Activity Bar, Footer).
   - Dedicated internal scroll regions with customized, elegant scrollbars.
   - Zero horizontal document overflow across all 11 standardized viewports (320px to 1920px).

---

## 2. Information Architecture & Navigation Blueprint

### 2.1 Navigation & Sidebar Architecture (`SessionSidebar.tsx`)

#### Consolidation of Redundancies:
- **Consolidate New Actions**: Replace the duplicate trio (Header buttons + Mode switcher + Primary Nav links) with a single, elegant **Primary Command Section**:
  - `New Chat` (Primary brand action)
  - `New Task` (Goal-oriented task console)
- **Categorized Accordion Navigation**:
  Group the 26 views into four clear, logical sections:
  1. **Core Workspaces**:
     - `Chat` (Conversational assistant with model-driven attribution)
     - `Code Studio (IDE)` (Full workspace editor, terminal, sandboxing)
     - `Cowork Copilot` (Side-by-side collaborative execution)
  2. **Autonomous Tool Studios**:
     - `Browser Studio` (Web automation, inspection, DOM extraction)
     - `Device Hub` (Universal App Control & multi-device fleet)
     - `Deep Research` (Autonomous web synthesis & report generation)
     - `Image Studio` & `Video Studio` (Generative media creators)
  3. **Knowledge & Productivity**:
     - `Knowledge Vault` & `Memory Studio` (Semantic long-term memory & documents)
     - `Calendar` & `Scheduled Jobs` (AI agenda & cron automations)
     - `Email Dispatch` & `Voice Session` (Communications & hands-free mode)
     - `Study Studio` & `Calculator` (Focused learning & numerical tools)
  4. **System, Security & Finance**:
     - `Control Center` (Diagnostics, system health, provider status)
     - `Trust & Safety` (Production gates, adversarial matrix, DLP policies)
     - `Audit Studio` (Immutable cryptographic security ledger)
     - `Connectors Hub` (MCP servers, custom skills & external integrations)
     - `Billing, Usage & Pricing` (Subscription plans, credits, payment methods)
- **Session History Preservation**:
  - Pinned conversations section with distinct pin icons and unpin actions.
  - Chronological grouped conversations (Today, Yesterday, Previous 7 Days, Older).
  - Search bar with instant keyboard shortcut trigger (`Ctrl+K` / `⌘K`).
  - Context menu actions (Rename, Pin, Archive, Share, Delete) preserved with confirmation protection.
- **Collapsed Desktop Rail Mode**:
  - Compact 60px icon rail for maximum editor/chat screen real estate.
  - Hover tooltips and active state indicators for each primary action.
- **Mobile Responsive Drawer**:
  - Smooth slide-out navigation with backdrop blur and touch targets (>= 44px).
  - Automatically collapses on selection or outside tap.

---

### 2.2 Top Header & Command Experience (`App.tsx`, `App.css`)

- **Left Section**:
  - Brand badge ("ROXY JARVIS").
  - Current Workspace / Session Breadcrumb.
  - Model indicator pill (showing active provider, e.g. `Gemini 4 Argon`).
- **Center Section**:
  - Universal Command Omnibar (`Ctrl+K`): Clean search trigger with keyboard shortcut pill and search icon.
- **Right Section**:
  - Cowork Mode toggle button with active badge.
  - Pinned Items quick drawer.
  - Notifications / Alarm indicator.
  - Theme toggle (Clean Lucide `Sun` / `Moon` SVG icons).
  - User Account Menu:
    - User email avatar.
    - Quick links to Settings, Billing, Usage.
    - Sign out action.

---

### 2.3 Key Workspaces Redesign Plans

#### A. New Task Modal (`NewTaskModal.tsx`)
- Transform from a generic dialog into a **Goal-First Autonomous Task Launcher**:
  - **Task Objective & Prompt**: Prominent auto-expanding text area with clear placeholder examples.
  - **Category Cards**: Development, Security Audit, Research, System Automation.
  - **Execution Mode Switcher**:
    - *Autonomous*: Full agent self-direction with automatic step sequencing.
    - *Guided*: Step-by-step confirmation challenges with human-in-the-loop approval.
  - **Target Device & Application**: Device chip selector showing live workstation connectivity.
  - **Quick Start Templates**: Visual one-click cards for popular workflows.
  - **Validation & Safe Launch**: Prevents empty submission; preserves exact `NewTaskConfig` contract.

#### B. Cowork Workspace (`CoworkWorkspace.tsx`)
- Transform into a **State-of-the-Art Pair Copilot Experience**:
  - Remove deprecated milestone labels (`(Phase 16)`, `(Phase 19)`).
  - Clean surface navigation bar:
    - `Code Workspace` (`<CodingStudio />`)
    - `Browser Workspace` (`<BrowserStudio />`)
    - `Device Control` (`<DeviceHub />`)
    - `Task Plan` (`<TaskWorkspacePanel />`)
  - Layout controls:
    - `Split View` (50/50 copilot split with drag divider or clean columns)
    - `Maximize Surface` (Focus on code/browser/device)
    - `Maximize Chat` (Focus on conversation/planning)
  - Real-time synchronization pulse indicator.

#### C. Code Studio & Full IDE (`CodingStudio.tsx`, `CodeStudioIDE.tsx`)
- Professional IDE polish:
  - Activity Bar on the left: Explorer (`FolderTree`), Search, Git, Problems, Preview.
  - Project Selector dropdown: ROXY Workspace (Current), Frontend React + Vite, Backend FastAPI, AI Hub.
  - Tab bar with dirty state indicator (`•`), language badge, and close button.
  - Editor surface with clean monospace typography (`Fira Code`, `JetBrains Mono`, `Consolas`), line numbers, and syntax highlighting.
  - Collapsible bottom panel with tabbed navigation:
    - `Terminal` (interactive command log with execution duration)
    - `Problems` (linter and compiler diagnostics)
    - `Git Status` (staged, modified, commit input)
    - `Output` (execution stdout/stderr)
  - AI Assistant side drawer with diff comparison and code application buttons.

#### D. Browser Studio (`BrowserStudio.tsx`)
- Refined browser inspection shell:
  - Clean URL address bar with SSL lock indicator, reload button, and action controls.
  - Live viewport preview / interactive screenshot viewer.
  - Extracted data tab (Headings, Tables, Forms, Links) with copy-to-clipboard and export actions.

#### E. Universal App Control & Device Hub (`DeviceHub.tsx`)
- Multi-device fleet manager:
  - Registered device cards with OS badges (Windows, macOS, Linux, Android, iOS), IP, and connection health.
  - Target-scoped permission matrix with clear security risk tiers (Low, Medium, High).
  - Screen surface session viewer with interactive controls.

#### F. Trust Center & Control Center (`TrustCenter.tsx`, `ControlCenter.tsx`)
- Executive security dashboard:
  - Production readiness exit gate checklist (Migrations, Encryption, Token Persistence, Billing Idempotency).
  - Adversarial security testing matrix.
  - System health grid for AI providers, database, and background services.

---

## 3. Shared Design System & Visual Grammar

### 3.1 Design Tokens (CSS Variables)

```css
:root {
  /* Core brand palette */
  --roxy-primary: #0d9488;
  --roxy-primary-hover: #0f766e;
  --roxy-primary-light: rgba(13, 148, 136, 0.1);
  --roxy-accent: #14b8a6;
  
  /* Status tokens */
  --roxy-success: #10b981;
  --roxy-warning: #f59e0b;
  --roxy-error: #ef4444;
  --roxy-info: #0284c7;

  /* Typography */
  --roxy-font-sans: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --roxy-font-mono: 'JetBrains Mono', 'Fira Code', Consolas, monospace;

  /* Elevations */
  --roxy-shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --roxy-shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
  --roxy-shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.03);
  --roxy-shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05);

  /* Radii */
  --roxy-radius-sm: 6px;
  --roxy-radius-md: 8px;
  --roxy-radius-lg: 12px;
  --roxy-radius-full: 9999px;

  /* Transitions */
  --roxy-transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --roxy-transition-normal: 250ms cubic-bezier(0.4, 0, 0.2, 1);
}

[data-theme="light"] {
  --color-bg: #f8faf9;
  --color-surface: #ffffff;
  --color-surface-hover: #f1f5f4;
  --color-surface-active: #e2e8e6;
  --color-border: #e2e8e6;
  --color-border-subtle: #edf2f0;
  --color-text: #131d1d;
  --color-text-secondary: #475569;
  --color-text-muted: #64748b;
  --color-input-bg: #ffffff;
}

[data-theme="dark"] {
  --color-bg: #0d1313;
  --color-surface: #141d1d;
  --color-surface-hover: #1c2626;
  --color-surface-active: #243232;
  --color-border: #222f2f;
  --color-border-subtle: #192323;
  --color-text: #f1f5f4;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;
  --color-input-bg: #111818;
}
```

---

## 4. File-by-File Implementation Strategy

| File | Scope of Changes | Functionality Preserved |
|---|---|---|
| `frontend/src/App.css` | Comprehensive design system tokens, typography, header layout, responsive cards, buttons, animations, and dark/light polish | All theme variables, RTL layout support, responsive media queries |
| `frontend/src/session/SessionSidebar.tsx` | Redesign navigation hierarchy, group 26 views into 4 clean accordions, consolidate New Chat & New Task, refine session search and context menu | All session operations (create, select, rename, pin, archive, delete, share), language switching, collapse/expand |
| `frontend/src/session/SessionSidebar.css` | Sleek modern styling, elegant scrollbar, active indicators, category headers, smooth accordion animations | Mobile drawer responsive rules, rail mode layout |
| `frontend/src/App.tsx` | Header consolidation: replace emoji buttons with crisp Lucide icons, unified command bar trigger, clean user menu | All route switching, session hydration, platform deep links, sensitive confirm hooks |
| `frontend/src/components/NewTaskModal/NewTaskModal.tsx` | Elevate task creation UI: visual category cards, autonomous vs. guided chips, device status badge | Exact `NewTaskConfig` structure, validation, submission handler, template selection |
| `frontend/src/components/NewTaskModal/NewTaskModal.css` | Modern modal backdrop, cards, responsive inputs, focus rings | Accessibility focus trap and escape handling |
| `frontend/src/components/CoworkWorkspace/CoworkWorkspace.tsx` | Remove dev milestone strings `(Phase 16)`, `(Phase 19)`, add clean surface tabs with Lucide icons | All 4 surfaces (Code, Browser, Device, Plan), layout modes (split, maximize), chat synchronization |
| `frontend/src/components/CoworkWorkspace/CoworkWorkspace.css` | Refine split-screen copilot styling, header status pill, tab active styles | Responsive flex layouts and transition animations |
| `frontend/src/components/CodingStudio/CodeStudioIDE.tsx` & `.css` | Visual polish of activity bar, file tree, tab indicators, terminal status pills | All workspace file tree APIs, saving, code execution, git integration, coding agent |

---

## 5. Strict Regression & Safety Boundaries

1. **No Backend API Changes**: No modifications to endpoints, payloads, response models, or schemas in `backend/`.
2. **No Auth or Security Gate Bypasses**: `useAuth`, `useSensitiveConfirm`, JWT tokens, and permission challenge dialogs remain strictly enforced.
3. **No Mock Data Replacement**: Real persistence in PostgreSQL and Redis is preserved.
4. **Sandbox Enforcement**: All runtime verification and external integrations must remain strictly in sandbox/test mode.
5. **Branch Isolation**: All commits belong exclusively to `design/roxy-ui-ux-redesign`. `master` remains untouched.
