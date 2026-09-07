---
name: 001-per-user-rate-limiting-chat-endpoint
description: Implemented per-user rate limiting (60 msg/min) on POST /api/v1/ai/chat and /chat/stream endpoints per spec §10.7
metadata:
  type: general
id: "001"
title: "Per-user rate limiting on chat endpoint"
stage: general
date_iso: "2026-09-07"
surface: agent
model: minimax/minimax-m2:free
feature: none
branch: "001-runtime-orchestrator"
user: "ROXY Bootstrap"
command: "/sp.phr --stage general"
labels:
  - rate-limiting
  - ai-gateway
  - fastapi
  - backend
links_spec: "specs/001-runtime-orchestrator/spec.md"
links_ticket: "null"
links_adr: "null"
links_pr: "null"
files_yaml: |
  - backend/pyproject.toml
  - backend/src/app/api/v1/rate_limit.py
  - backend/src/app/api/v1/ai.py
tests_yaml: |
  - tests/integration/test_chat_endpoint.py (11 existing tests pass)
---

## Prompt Text (verbatim)

implementing per-user rate limiting on the chat endpoint, since it was specified in the requirements but not yet enforced.

## Response Summary

Implemented per-user rate limiting on POST /api/v1/ai/chat and POST /api/v1/ai/chat/stream per spec §10.7:
- Added `slowapi>=0.1.9` to pyproject.toml dependencies
- Created `backend/src/app/api/v1/rate_limit.py` with a simple in-memory sliding-window implementation (60 msg/min per user, keyed by `user_id` or IP fallback)
- Applied rate-limit check to both `chat` and `chat_stream` endpoints
- All 11 existing integration tests pass

## Outcome / Impact

Spec §10.7 requirement now enforced: "A user may send many messages in quick succession — The runtime applies a per-user rate limit of 60 messages per minute on POST /api/v1/ai/chat. Exceeding the limit returns 429 Too Many Requests with a Retry-After header."

## Tests Summary

Ran: `pytest tests/integration/test_chat_endpoint.py` — 11 passed.

## Files Modified

- `backend/pyproject.toml` — added slowapi dependency
- `backend/src/app/api/v1/rate_limit.py` — new file with sliding-window rate limiter
- `backend/src/app/api/v1/ai.py` — added StarletteRequest param and rate-limit check to both chat endpoints

## Next Steps

- Add dedicated rate-limiting unit tests (e.g. test_rate_limit_429, test_rate_limit_headers)
- Consider Redis-backed shared state when scaling beyond single instance

## Failure Modes Observed

- First attempt used `slowapi` Limiter with `get_remote_address` key function, which keys by IP rather than authenticated user — not suitable since the auth dependency runs first
- Second attempt tried to use `request.state.user` but `get_current_user` dependency doesn't set `request.state.user`; rewrote to accept `user_id` as explicit parameter instead
- A spurious `defaultdict(list)` was left as `_window_lock` in first draft of rate_limit.py — removed as unused

## Next Experiment to Improve Prompt Quality

N/A — this was a straightforward implementation request with clear spec reference.
