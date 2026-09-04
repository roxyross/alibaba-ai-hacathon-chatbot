# Frontend — ROXY Personal AI

> Multi-provider AI chat frontend. Communicates with the backend via the
> `/api/v1/ai` router.

## Prerequisites

- Node.js ≥ 20
- Backend running at `http://localhost:8000` (or set `VITE_API_BASE`)

## Setup

```bash
npm install
cp .env.example .env.local
# fill in VITE_API_BASE if not using the default
```

## Development

```bash
npm run dev      # Vite dev server on :5173
npm run build    # production build
npm run preview  # preview production build
```

## Testing

```bash
npm test               # Vitest unit tests
npx playwright test    # E2E tests (requires running backend)
npx playwright install  # install browsers first
```

## Multi-Provider Setup

The frontend supports provider routing via the `provider` query / option:

- **User override**: pass `provider=grok` to `/api/v1/ai/chat/stream`
- **Attribution badge**: after a streaming response completes, a
  `{provider} · {model}` badge appears below the assistant message with an
  `aria-label` for accessibility.
- **Failover**: when the primary provider is unavailable the router automatically
  falls back to the next available provider; the badge reflects the actual
  provider that served the response.

## Architecture

```
src/
  components/
    ChatMessage.tsx    # message bubble + optional attribution badge
  hooks/
    useChat.ts         # SSE streaming hook
  App.tsx
tests/
  e2e/
    ai-chat.spec.ts    # Playwright E2E tests (T033)
```
