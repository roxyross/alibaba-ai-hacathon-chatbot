"""Document management API — list, delete, and query user documents.

GET  /api/v1/runtime/documents       — list all documents for a user
DELETE /api/v1/runtime/documents/{document_id}  — delete a document and its chunks
POST /api/v1/runtime/documents/query  — RAG query over user's documents

These are thin wrappers around the infrastructure/vector_store functions.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from runtime.infrastructure.auth import AuthError, UserContext, decode_bearer
from runtime.infrastructure.vector_store import VectorStoreError, delete_document, list_user_documents

router = APIRouter(prefix="/api/v1/runtime", tags=["documents"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def _user_dep(
    authorization: Annotated[str | None, str | None] = None,  # noqa: ARG001
) -> UserContext:
    try:
        return decode_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# GET /api/v1/runtime/documents
# ---------------------------------------------------------------------------

class DocumentListItem(BaseModel):
    document_id: str
    document_name: str
    chunk_count: int
    last_ingested: str | None


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    authorization: Annotated[str | None, str | None] = None,
) -> DocumentListResponse:
    """List all documents ingested by the authenticated user.

    Returns document_id, name, chunk_count, and last_ingested timestamp.
    """
    try:
        user_ctx = decode_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    try:
        docs = await list_user_documents(user_ctx.user_id)
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vector store unavailable: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return DocumentListResponse(
        documents=[
            DocumentListItem(
                document_id=d["document_id"],
                document_name=d["document_name"],
                chunk_count=d["chunk_count"],
                last_ingested=d.get("last_ingested"),
            )
            for d in docs
        ]
    )


# ---------------------------------------------------------------------------
# DELETE /api/v1/runtime/documents/{document_id}
# ---------------------------------------------------------------------------

class DocumentDeleteResponse(BaseModel):
    document_id: str
    chunks_deleted: int


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_doc(
    request: Request,
    document_id: str,
    authorization: Annotated[str | None, str | None] = None,
) -> DocumentDeleteResponse:
    """Delete a document and all its chunks from the RAG store."""
    try:
        user_ctx = decode_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    log = structlog.get_logger()
    log.info("documents.delete", user_id=user_ctx.user_id, document_id=document_id)

    try:
        count = await delete_document(user_ctx.user_id, document_id)
    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vector store unavailable: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return DocumentDeleteResponse(document_id=document_id, chunks_deleted=count)


# ---------------------------------------------------------------------------
# POST /api/v1/runtime/documents/query
# ---------------------------------------------------------------------------

class DocumentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    document_ids: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentQueryChunk(BaseModel):
    document_id: str
    document_name: str
    location: str
    text: str
    score: float


class DocumentQueryResponse(BaseModel):
    query: str
    chunks: list[DocumentQueryChunk]
    total_candidates: int


@router.post("/documents/query", response_model=DocumentQueryResponse)
async def query_documents(
    request: Request,
    body: DocumentQueryRequest,
    authorization: Annotated[str | None, str | None] = None,
) -> DocumentQueryResponse:
    """RAG query over the authenticated user's uploaded documents.

    Embeds ``query`` via Gemini, searches pgvector for the top-k most
    similar chunks, and returns them with similarity scores and citations.
    """
    try:
        user_ctx = decode_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    log = structlog.get_logger()
    log.info(
        "documents.query",
        user_id=user_ctx.user_id,
        query=body.query[:80],
        top_k=body.top_k,
    )

    try:
        from runtime.rag import rag_query

        result = await rag_query(
            query=body.query,
            user_id=user_ctx.user_id,
            document_ids=body.document_ids,
            top_k=body.top_k,
            min_score=body.min_score,
        )

        chunks = [
            DocumentQueryChunk(
                document_id=c.document_id,
                document_name=c.document_name,
                location=f"§{c.chunk_index + 1}",
                text=c.chunk_text,
                score=round(c.score, 4),
            )
            for c in result.chunks
        ]

        return DocumentQueryResponse(
            query=body.query,
            chunks=chunks,
            total_candidates=result.total_candidates,
        )

    except VectorStoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vector store unavailable: {exc}",
        ) from exc
    except Exception as exc:
        log.error("documents.query_failed", user_id=user_ctx.user_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
