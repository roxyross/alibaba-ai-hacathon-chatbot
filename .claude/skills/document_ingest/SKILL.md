---
name: document_ingest
description: Ingest a document, image, or video into the RAG vector store for semantic search. Used by the Files Agent after parsing.
---

# document_ingest

## Purpose

Chunk extracted text from a document (PDF, DOCX, PPTX), image (OCR + caption), or video (transcription + frame captions), embed each chunk via Gemini, and store in pgvector for later retrieval.

## Inputs

- `document_id` (string, optional) — Stable ID for the document. If None, a new UUID is generated. Use the same ID to re-ingest after re-upload.
- `document_name` (string, required) — Human-readable name shown in citations.
- `text` (string, required) — Full raw text extracted from the file (parsed content).
- `replace_existing` (bool, optional, default false) — If True, delete existing chunks for this document_id before ingesting.
- `user_id` (string, required) — The authenticated user's ID (injected by the router).

## Outputs

- `document_id`: The stored document's ID.
- `document_name`: The name used for citations.
- `chunks_stored`: Number of chunks created.
- `chunk_ids`: List of stored chunk UUIDs.

## Steps

1. Validate inputs (document_name non-empty, text non-empty).
2. Chunk the text into ~2000-char segments with 200-char overlap, respecting sentence boundaries.
3. Generate Gemini embeddings for each chunk (batch with 5 concurrent calls).
4. Store chunks + embeddings in pgvector with user_id isolation.
5. Return the list of stored chunk IDs.

## Supported file types

| Type | Parser | Extracted content |
|------|--------|-------------------|
| PDF | pypdf | Page-by-page text extraction |
| DOCX | python-docx | Paragraphs + tables |
| PPTX | python-pptx | Slide-by-slide text |
| TXT/MD/CSV | built-in | Plain text with HTML stripping |
| Image | pytesseract + Gemini | OCR text + AI caption |
| Video | moviepy + Gemini | Audio transcription + frame captions |

## Failure modes

- Empty text → return error (nothing stored).
- Database error → return error with "Database error" prefix.
- Embedding API error → return error with "Embedding error" prefix.
- Chunk/embedding count mismatch → raise ValueError (programming error).

## Notes

- The `document_id` is intentionally decoupled from the storage ID — the caller (e.g. upload endpoint) generates the document_id so the same ID can be used to replace an existing document.
- For images and videos, the parsed `text` already includes OCR/caption/transcription content from the media_parser.
