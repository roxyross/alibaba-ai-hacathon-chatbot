---
name: document_rag_query
description: Retrieve relevant chunks from the user's uploaded documents given a natural-language query. Used by the Files Agent as its primary read path.
---

# document_rag_query

## Purpose

Embed the user's question, retrieve the most relevant chunks from their document store, optionally re-rank, and return them with citations.

## Inputs

- `query` (string, required) — the question or topic.
- `document_ids` (list of string, optional) — restrict the search to specific uploaded documents. If empty, search the whole library.
- `top_k` (int, optional, default 8) — number of chunks to return.
- `min_score` (float, optional, default 0.0) — drop chunks below this similarity score.

## Outputs

- `chunks`: list of `{document_id, document_name, location (page/section), text, score}`.
- `total_candidates`: how many chunks were considered before filtering.

## Steps

1. Validate the query (non-empty).
2. Embed the query using the runtime's configured embedding model.
3. Vector-search the user's document store (only docs the user has granted access to in this session).
4. Optional re-rank with a cross-encoder if configured.
5. Filter by `min_score`, take top `top_k`.
6. Return with citations back to the source document.

## Failure modes

- No matching chunks → return empty list; the Files Agent should tell the user "the documents don't appear to contain this".
- Document is scanned without OCR → surface to the user; the doc needs OCR before it can be searched.
- Embedding model rate-limited → retry with backoff; fail soft if persistent.
- The user revoked a document mid-session → drop its chunks from results and surface the revocation.
