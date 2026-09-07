"""document_rag_query skill — RAG over user-uploaded documents.

Uses the shared in-memory chunk store from document_ingest
and cosine-similarity search over pseudo-embeddings.

In production, replace with Gemini embeddings + ChromaDB / pgvector.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    DocumentChunk,
    DocumentRagQueryRequest,
    DocumentRagQueryResponse,
)

log = structlog.get_logger()

# Import the shared stores from document_ingest
# We re-import here to avoid circular imports at module level
# by using lazy access inside functions


class DocumentRAGSkill(SkillExecutor[DocumentRagQueryRequest, DocumentRagQueryResponse]):
    slug = "document_rag_query"

    async def execute(self, input_data: DocumentRagQueryRequest) -> DocumentRagQueryResponse:
        user_id = input_data.user_id or "anonymous"

        # Lazy import to avoid circular import at module load time
        from app.skills.document_ingest import _document_meta, _chunk_store

        user_docs = _document_meta.get(user_id, {})

        query = input_data.query.lower()
        top_k = input_data.top_k

        # Filter to specific documents if requested
        if input_data.document_ids:
            user_docs = {k: v for k, v in user_docs.items() if k in input_data.document_ids}

        if not user_docs:
            return DocumentRagQueryResponse(
                query=input_data.query,
                chunks=[],
                total_chunks=0,
                documents_consulted=[],
            )

        # Collect all chunks for this user's scoped docs
        all_chunks: list[dict[str, Any]] = []
        for doc_id, doc_meta in user_docs.items():
            doc_name = doc_meta.get("name", doc_id)
            for chunk_id in doc_meta.get("chunk_ids", []):
                chunk_data = _chunk_store.get(chunk_id)
                if chunk_data:
                    all_chunks.append({
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "doc_name": doc_name,
                        "content": chunk_data.get("content", ""),
                        "embedding": chunk_data.get("embedding", []),
                        "page": chunk_data.get("page"),
                        "section": chunk_data.get("section"),
                    })

        if not all_chunks:
            return DocumentRagQueryResponse(
                query=input_data.query,
                chunks=[],
                total_chunks=0,
                documents_consulted=[],
            )

        # Score each chunk against the query
        from app.skills.document_ingest import _make_embedding, _cosine_sim

        query_embedding = _make_embedding(query)

        scored: list[tuple[float, dict[str, Any]]] = []
        query_terms = set(re.findall(r"\w+", query))

        for chunk in all_chunks:
            content = chunk["content"]
            content_lower = content.lower()

            # Cosine similarity over embeddings
            emb = chunk.get("embedding", [])
            if emb:
                score = _cosine_sim(query_embedding, emb)
            else:
                # Fallback: Jaccard on terms
                content_terms = set(re.findall(r"\w+", content_lower))
                intersection = len(query_terms & content_terms)
                union = len(query_terms | content_terms)
                score = intersection / union if union > 0 else 0.0

            # Boost exact phrase matches
            if query.lower() in content_lower:
                score += 0.5

            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = scored[:top_k]

        chunks_out: list[DocumentChunk] = [
            DocumentChunk(
                chunk_id=chunk["chunk_id"],
                document_id=chunk["doc_id"],
                document_name=chunk["doc_name"],
                content=chunk["content"],
                page=chunk.get("page"),
                section=chunk.get("section"),
                relevance_score=round(score, 4),
            )
            for score, chunk in top_chunks
        ]

        docs_consulted = list(dict.fromkeys(c.document_name for c in chunks_out))

        return DocumentRagQueryResponse(
            query=input_data.query,
            chunks=chunks_out,
            total_chunks=len(chunks_out),
            documents_consulted=docs_consulted,
        )


def get_executor() -> DocumentRAGSkill:
    return DocumentRAGSkill()
