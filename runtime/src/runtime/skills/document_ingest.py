"""Real `document_ingest` skill — chunk, embed, and store a document in pgvector.

Used by the Files Agent when a user uploads a new document. The frontend
passes the raw extracted text (already parsed from PDF/DOCX/etc.) to this
skill, which:
  1. Chunks the text (recursive character splitting, ~2000 chars, 200 char overlap)
  2. Generates embeddings via the Gemini embedding API
  3. Stores chunks + embeddings in pgvector

The document is then queryable via `document_rag_query`.
"""

from __future__ import annotations

import uuid

import structlog

from runtime.infrastructure.embedding import EmbeddingError
from runtime.infrastructure.vector_store import VectorStoreError, chunk_text
from runtime.rag import rag_ingest
from runtime.skills.executor import SkillResult

log = structlog.get_logger()


async def document_ingest(
    document_id: str | None,
    document_name: str,
    text: str,
    replace_existing: bool = False,
    *,
    user_id: str,
) -> SkillResult:
    """Ingest a document into the vector store.

    Args:
        document_id: Stable ID for the document (e.g. UUID from the upload system).
                     If None, a new ID is generated. Use the same ID to re-ingest
                     (e.g. after the source file is re-uploaded).
        document_name: Human-readable name shown in citations.
        text: Full raw text of the document (extracted from the uploaded file).
        replace_existing: If True, delete any existing chunks for this document_id
                         before ingesting (useful for re-ingesting updated files).
        user_id: The user who owns this document.

    Returns:
        SkillResult with the stored chunk IDs and document metadata.
    """
    if not document_name:
        return SkillResult(ok=False, data=None, error="document_name is required")
    if not text or not text.strip():
        return SkillResult(ok=False, data=None, error="document text is empty")

    doc_id = document_id or str(uuid.uuid4())
    log.info(
        "document_ingest.invoked",
        user_id=user_id,
        document_id=doc_id,
        document_name=document_name,
        text_length=len(text),
        replace_existing=replace_existing,
    )

    try:
        chunk_ids = await rag_ingest(
            document_id=doc_id,
            document_name=document_name,
            text=text,
            user_id=user_id,
        )
    except VectorStoreError as exc:
        log.error(
            "document_ingest.vector_store_error",
            user_id=user_id,
            document_id=doc_id,
            error=str(exc),
        )
        return SkillResult(
            ok=False,
            data=None,
            error=f"Database error: {exc}",
        )
    except EmbeddingError as exc:
        log.error(
            "document_ingest.embedding_error",
            user_id=user_id,
            document_id=doc_id,
            error=str(exc),
        )
        return SkillResult(
            ok=False,
            data=None,
            error=f"Embedding error: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "document_ingest.unexpected_error",
            user_id=user_id,
            document_id=doc_id,
            error=str(exc),
            exc_info=True,
        )
        return SkillResult(
            ok=False,
            data=None,
            error=f"Unexpected error during ingestion: {exc}",
        )

    log.info(
        "document_ingest.done",
        user_id=user_id,
        document_id=doc_id,
        chunks_stored=len(chunk_ids),
    )
    return SkillResult(
        ok=True,
        data={
            "document_id": doc_id,
            "document_name": document_name,
            "chunks_stored": len(chunk_ids),
            "chunk_ids": chunk_ids,
        },
    )
