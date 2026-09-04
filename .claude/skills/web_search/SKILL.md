---
name: web_search
description: Issue a web search and return the top results with URLs, snippets, and dates. Used by the Research Agent as its primary primitive.
---

# web_search

## Purpose

Run a web search query and return ranked results with metadata.

## Inputs

- `query` (string, required) — the search query.
- `num_results` (int, optional, default 10) — how many results to return.
- `recency` (enum, optional) — `day`, `week`, `month`, `year`, or `any` (default).
- `site` (string, optional) — restrict to a specific domain (e.g. `arxiv.org`).

## Outputs

- `results`: list of `{title, url, snippet, published_date}`.
- `total_estimated`: rough count of total matching pages.

## Steps

1. Validate the query (non-empty, length ≤ 500 chars).
2. Issue the search via the runtime's web-search provider.
3. Deduplicate by URL.
4. Filter out known low-quality domains (configurable blocklist).
5. Return the top N results, sorted by relevance.

## Failure modes

- Provider rate-limited → retry up to 3× with exponential backoff; surface the error to the caller after.
- Zero results → return empty list; let the caller reformulate.
- Provider down → surface a clear error so the caller can fall back to `retrieve_memory` or another agent.
