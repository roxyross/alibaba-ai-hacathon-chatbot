"""RAG (Retrieval-Augmented Generation) module.

Provides the core RAG pipeline:
  - `query_chunks`: embed a query and search pgvector for relevant chunks
  - `ingest_document`: chunk text, embed, and store in pgvector

Exposes:
  - `rag_query(query, user_id, document_ids?, top_k?, min_score?) -> SearchResult`
  - `rag_ingest(document_id, document_name, text, user_id) -> chunk_ids`
"""

from __future__ import annotations

from runtime.infrastructure.embedding import embed_text, embed_texts
from runtime.infrastructure.vector_store import (
    SearchResult as RAGSearchResult,
    chunk_text,
    delete_document,
    list_user_documents,
    search_chunks,
    store_chunks,
)

__all__ = [
    "embed_text",
    "embed_texts",
    "rag_query",
    "rag_ingest",
    "list_user_documents",
    "delete_document",
    "RAGSearchResult",
]


async def rag_query(
    query: str,
    user_id: str,
    document_ids: list[str] | None = None,
    top_k: int = 8,
    min_score: float = 0.0,
) -> RAGSearchResult:
    """Embed `query` and search the vector store for relevant chunks.

    Args:
        query: Natural-language question or topic.
        user_id: Restrict search to this user's documents.
        document_ids: Optional filter to specific document IDs.
        top_k: Maximum chunks to return.
        min_score: Minimum cosine similarity (0.0–1.0).

    Returns:
        RAGSearchResult with matched chunks and citation metadata.
    """
    embedding = await embed_text(query)
    return await search_chunks(
        user_id=user_id,
        query_embedding=embedding,
        top_k=top_k,
        min_score=min_score,
        document_ids=document_ids,
    )


async def rag_ingest(
    document_id: str,
    document_name: str,
    text: str,
    user_id: str,
) -> list[str]:
    """Chunk `text`, generate embeddings, and store in the vector store.

    Args:
        document_id: Stable identifier (e.g. UUID from the upload system).
        document_name: Human-readable name for citation.
        text: Full raw text of the document.
        user_id: Owner for per-user isolation.

    Returns:
        List of stored chunk IDs.
    """
    chunks = chunk_text(text)
    embeddings = await embed_texts(chunks)
    return await store_chunks(
        user_id=user_id,
        document_id=document_id,
        document_name=document_name,
        text=text,
        embeddings=embeddings,
    )
