"""Real `document_rag_query` skill using pgvector + Google embedding API.

Per the spec, the Files Agent uses this as its primary read primitive.
Embeds the user's query, searches pgvector for the most relevant chunks,
and returns them with citations.
"""

from __future__ import annotations

import structlog

from runtime.infrastructure.vector_store import VectorStoreError
from runtime.rag import rag_query
from runtime.skills.executor import SkillResult

log = structlog.get_logger()


class RAGError(Exception):
    """Raised when the RAG pipeline fails."""


async def document_rag_query(
    query: str,
    document_ids: list[str] | None = None,
    top_k: int = 8,
    min_score: float = 0.0,
    *,
    user_id: str,
) -> SkillResult:
    """Retrieve relevant chunks from the user's document store.

    Args:
        query: The question or topic to search for.
        document_ids: If set, restrict search to these specific documents.
        top_k: Maximum number of chunks to return (default 8).
        min_score: Minimum cosine similarity threshold (0.0–1.0, default 0.0).
        user_id: The user making the request (for per-user isolation).

    Returns:
        SkillResult with chunks and citation metadata, or an error.
    """
    if not query or not query.strip():
        return SkillResult(
            ok=False,
            data=None,
            error="query cannot be empty",
        )

    log.info(
        "document_rag_query.invoked",
        user_id=user_id,
        query=query[:80],
        document_ids=document_ids,
        top_k=top_k,
    )

    try:
        result = await rag_query(
            query=query,
            user_id=user_id,
            document_ids=document_ids,
            top_k=top_k,
            min_score=min_score,
        )
    except VectorStoreError as exc:
        log.error("document_rag_query.vector_store_error", user_id=user_id, error=str(exc))
        return SkillResult(
            ok=False,
            data=None,
            error=f"Document store unavailable: {exc}",
        )
    except RAGError as exc:
        log.error("document_rag_query.embedding_error", user_id=user_id, error=str(exc))
        return SkillResult(
            ok=False,
            data=None,
            error=f"Embedding service error: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "document_rag_query.unexpected_error",
            user_id=user_id,
            error=str(exc),
            exc_info=True,
        )
        return SkillResult(
            ok=False,
            data=None,
            error=f"Unexpected error during document search: {exc}",
        )

    chunks_data = [
        {
            "document_id": c.document_id,
            "document_name": c.document_name,
            "location": f"§{c.chunk_index + 1}",  # Sections are 1-indexed
            "text": c.chunk_text,
            "score": round(c.score, 4),
        }
        for c in result.chunks
    ]

    log.info(
        "document_rag_query.done",
        user_id=user_id,
        returned=len(chunks_data),
        total_candidates=result.total_candidates,
    )

    return SkillResult(
        ok=True,
        data={
            "chunks": chunks_data,
            "total_candidates": result.total_candidates,
        },
    )
