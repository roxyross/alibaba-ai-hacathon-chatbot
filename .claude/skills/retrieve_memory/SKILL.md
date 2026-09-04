---
name: retrieve_memory
description: Read entries from the user's long-term memory store by semantic query or by tag. Used by user-facing agents when a question depends on prior context.
---

# retrieve_memory

## Purpose

Fetch relevant memory entries by semantic query, by tag, or by ID.

## Inputs

- `query` (string, optional) — semantic search query. At least one of `query`, `tags`, or `ids` is required.
- `tags` (list of string, optional) — restrict to entries with any of these tags.
- `ids` (list of string, optional) — fetch specific entries by ID.
- `top_k` (int, optional, default 10) — max entries to return.
- `min_score` (float, optional, default 0.0) — drop entries below similarity.

## Outputs

- `entries`: list of `{entry_id, content, tags, importance, source, stored_at, score}`.
- `total_candidates`: how many were considered.

## Steps

1. Validate that at least one of `query` / `tags` / `ids` is provided.
2. If `ids`: fetch directly.
3. Else: embed the query, vector-search, filter by tags if provided, return top `top_k`.
4. Sort by score (semantic) or by `stored_at` desc (ID-based).

## Failure modes

- Empty store → return empty list; the agent should treat it as "the user has no prior context".
- Query is too broad → many low-score results; the agent should re-query with a tighter focus.
- Stale or contradicted entries → surface as-is; the agent should note the conflict, not silently pick a side.
- Entry marked soft-deleted by the Memory Curator → exclude from results (but the entry ID is still recoverable within the soft-delete window).
