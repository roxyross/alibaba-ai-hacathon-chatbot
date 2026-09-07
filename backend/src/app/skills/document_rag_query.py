"""document_rag_query skill — RAG over user-uploaded documents.

Uses a simple TF-IDF / keyword fallback retriever.
Replace with a real embedding model (OpenAI embeddings, etc.) in production.
"""

from __future__ import annotations

import math
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    DocumentChunk,
    DocumentRagQueryRequest,
    DocumentRagQueryResponse,
)


log = structlog.get_logger()

# In-memory document store: user_id -> doc_id -> {name, chunks: list[dict]}
_document_store: dict[str, dict[str, dict[str, Any]]] = {}


def _get_store() -> dict[str, dict[str, dict[str, Any]]]:
    global _document_store
    return _document_store


class DocumentRAGSkill(SkillExecutor[DocumentRagQueryRequest, DocumentRagQueryResponse]):
    slug = "document_rag_query"

    async def execute(self, input_data: DocumentRagQueryRequest) -> DocumentRagQueryResponse:
        user_id = input_data.user_id or "anonymous"
        store = _get_store()
        user_docs = store.get(user_id, {})

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

        # Score each chunk against the query using simple TF-IDF
        scored: list[tuple[float, DocumentChunk]] = []
        query_terms = set(re.findall(r"\w+", query))

        for doc_id, doc in user_docs.items():
            doc_name = doc.get("name", doc_id)
            for chunk in doc.get("chunks", []):
                content = chunk.get("content", "")
                content_lower = content.lower()
                content_terms = set(re.findall(r"\w+", content_lower))

                # Jaccard similarity as a quick proxy
                if not query_terms:
                    score = 0.0
                else:
                    intersection = len(query_terms & content_terms)
                    union = len(query_terms | content_terms)
                    score = intersection / union if union > 0 else 0.0

                # Boost exact phrase matches
                if query.lower() in content_lower:
                    score += 0.5

                scored.append((
                    score,
                    DocumentChunk(
                        chunk_id=chunk.get("chunk_id", str(uuid.uuid4())),
                        document_id=doc_id,
                        document_name=doc_name,
                        content=content,
                        page=chunk.get("page"),
                        section=chunk.get("section"),
                        relevance_score=round(score, 4),
                    )
                ))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [chunk for _, chunk in scored[:top_k]]
        docs_consulted = list(dict.fromkeys(c.document_name for c in top_chunks))

        return DocumentRagQueryResponse(
            query=input_data.query,
            chunks=top_chunks,
            total_chunks=len(top_chunks),
            documents_consulted=docs_consulted,
        )


def get_executor() -> DocumentRAGSkill:
    return DocumentRAGSkill()
