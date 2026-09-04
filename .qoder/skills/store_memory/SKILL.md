---
name: store_memory
description: Write an entry to the user's long-term memory store. Used by user-facing agents when the user asks the runtime to remember something, and by the Automation / Memory Curator Agents.
---

# store_memory

## Purpose

Persist a fact, preference, or context entry to the user's long-term memory for retrieval in future sessions.

## Inputs

- `content` (string, required) — the thing to remember. Plain text or structured.
- `tags` (list of string, optional) — for retrieval clustering.
- `importance` (enum, optional) — `low`, `normal` (default), `high`, `forever`. `forever` entries are exempt from the Memory Curator's pruning.
- `source` (string, optional) — what produced this entry (e.g. `user:explicit`, `agent:files-agent`, `job:nightly-curator`).

## Outputs

- `entry_id`: the new memory entry's ID.
- `stored_at`: timestamp.

## Steps

1. Validate content (non-empty, length ≤ 4000 chars; longer content is split into multiple entries).
2. Embed the content for retrieval.
3. Check for near-duplicates. If a high-similarity entry exists, surface to the caller; the caller decides whether to update or skip.
4. Persist with metadata: source, importance, tags, timestamp.
5. Return the entry ID.

## Failure modes

- Storage quota exceeded → surface to the caller; the user may need to delete old entries.
- Duplicate detected → return the existing entry ID with a `duplicate: true` flag; the caller decides.
- Persistence error → return a clear error; do not lose the original content silently (caller should retry or store locally as a fallback).
