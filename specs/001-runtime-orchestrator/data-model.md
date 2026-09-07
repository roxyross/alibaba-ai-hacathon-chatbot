# Data Model: Runtime Storage (PR 3+)

**PR:** 3 | **Status:** Design (not implemented in PR 2)
**Storage:** Neon PostgreSQL (same DB as `backend/`)

> PR 2 does not require a database — the vertical slice uses the existing magic-link JWT auth and the backend AI gateway. The tables below are introduced in PR 3 alongside the memory, scheduler, and audit features.

---

## Overview

```
memory_entries    — user long-term memory (PR 3)
scheduled_jobs    — recurring/one-shot scheduled jobs (PR 3)
audit_log         — every agent action, for accountability (PR 2+)
```

All three tables are **user-scoped**: every row has a `user_id` foreign key; rows are visible only to the owning user.

---

## `memory_entries`

Stores user-provided facts, preferences, and context. Backed by Neon PostgreSQL with the `store_memory` and `retrieve_memory` skills.

```sql
CREATE TABLE memory_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,              -- from JWT sub claim
    content         TEXT NOT NULL,             -- the remembered text
    importance      TEXT NOT NULL DEFAULT 'normal'
                    CHECK (importance IN ('forever', 'normal', 'low')),
    source          TEXT,                      -- 'user', 'agent', 'curator'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retrieved_at    TIMESTAMPTZ,
    retrieved_count  INT NOT NULL DEFAULT 0,
    soft_deleted_at TIMESTAMPTZ,               -- NULL = active; non-NULL = soft-deleted
    importance_locked BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = cannot be deleted by curator

    INDEX idx_memory_user_active (user_id) WHERE soft_deleted_at IS NULL,
    INDEX idx_memory_retrieved (user_id, retrieved_at DESC)
);
```

### Importance levels

| Level | Meaning | Retention policy |
|-------|---------|-----------------|
| `forever` | User explicitly said "always remember this" | Never pruned by curator |
| `normal` | Default | Summarized if >30 days old and retrieved_count < 3 |
| `low` | Low-value entries | Soft-deleted after 90 days of no retrieval |

---

## `scheduled_jobs`

Stores recurring and one-shot jobs created by the Automation Agent.

```sql
CREATE TABLE scheduled_jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT NOT NULL,
    agent_slug       TEXT NOT NULL,               -- which agent runs the job
    action_chain     JSONB NOT NULL,              -- list of {skill, inputs} steps
    cron_expression  TEXT,                        -- e.g. '0 8 * * 1-5' (weekdays 8am local)
    next_fire_at     TIMESTAMPTZ,                -- NULL = disabled
    last_fire_at     TIMESTAMPTZ,
    last_fire_result TEXT,                        -- 'success' | 'failure' | 'no_confirmation'
    confirm_on_fire  BOOLEAN NOT NULL DEFAULT FALSE,
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'paused', 'cancelled')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    INDEX idx_jobs_user (user_id),
    INDEX idx_jobs_next_fire (next_fire_at) WHERE status = 'active'
);
```

### `action_chain` JSONB shape

```json
[
  {"skill": "web_search", "inputs": {"query": "top 3 AI news today"}},
  {"skill": "store_memory", "inputs": {"content": "Daily AI briefing for {{date}}"}}
]
```

### `confirm_on_fire` constraint

A job with a `sensitive: true` skill in its `action_chain` MUST have `confirm_on_fire: TRUE`. The `schedule_job` skill enforces this at creation time (per spec §3.4).

---

## `audit_log`

Every agent action is written to the audit log. Used for debugging, compliance, and incident response.

```sql
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    trace_id        TEXT,                        -- from X-Trace-ID header or generated UUID
    agent_slug      TEXT NOT NULL,
    action          TEXT NOT NULL,               -- e.g. 'routed', 'skill_invoked', 'timeout', 'error'
    skill_slug      TEXT,                       -- NULL for non-skill actions
    request_query   TEXT,                       -- user's original query (may be NULL for internal)
    response_summary TEXT,                       -- first 500 chars of agent reply
    decision        TEXT,                       -- e.g. 'routed_to_research', 'blocked', 'uncertain'
    latency_ms      INT,                        -- wall-clock ms for the agent call
    status_code     TEXT,                        -- 'ok' | 'timeout' | 'error' | 'blocked'
    metadata        JSONB,                      -- flexible extra context
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    INDEX idx_audit_user (user_id DESC, created_at DESC),
    INDEX idx_audit_trace (trace_id)
);
```

### Retention policy

- `audit_log` is retained for **1 year** (per spec §10.12)
- Operators may shorten; they may not lengthen without a Constitution amendment (§4)

---

## Migrations

Migrations are managed with `alembic` (deferred to PR 3). The runtime creates the tables if they don't exist on startup (idempotent, safe for dev). Production migrations run via `alembic upgrade head` in the deployment pipeline.

---

## DB Connection

The runtime reads the connection string from `DATABASE_URL` env var. In development, it uses the same Neon DB as `backend/`. In production, it's a separate DB user with access only to the runtime tables.

```python
# runtime/src/runtime/infrastructure/db.py
from sqlalchemy.ext.asyncio import create_async_engine
engine = create_async_engine(settings.database_url, echo=False)
```
