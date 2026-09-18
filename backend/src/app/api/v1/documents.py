"""Document API — Native RAG ingestion, listing, deleting, and querying.

POST /api/v1/documents/upload  — upload a file (PDF, DOCX, PPTX, TXT, CSV, MD, image, video)
GET  /api/v1/documents          — list authenticated user's uploaded documents
DELETE /api/v1/documents/{id}   — delete document and remove vector chunks
POST /api/v1/documents/query    — semantic RAG search over user documents

Enforces strict multi-tenant isolation: User B can never view, query, or delete User A's files.
Persists document records to PostgreSQL NeonDB with transparent in-memory fallback.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from pydantic import Field as PydanticField

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.documents.repository import DocumentRepository
from app.skills.document_ingest import (
    DocumentIngestRequest,
    DocumentIngestSkill,
    _document_meta,
    delete_user_document,
)
from app.skills.document_parser import parse_document
from app.skills.document_rag_query import DocumentRAGSkill
from app.skills.schemas import DocumentRagQueryRequest

log = structlog.get_logger()

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------------------------

class DocumentUploadResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_stored: int
    chunk_ids: list[str]
    doc_type: str
    metadata: dict[str, Any] = {}


class DocumentListItem(BaseModel):
    document_id: str
    document_name: str
    chunk_count: int
    last_ingested: str | None


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]


class DocumentDeleteResponse(BaseModel):
    document_id: str
    chunks_deleted: int


class DocumentQueryRequest(BaseModel):
    query: str = PydanticField(..., min_length=1, max_length=1000)
    document_ids: list[str] | None = None
    top_k: Annotated[int, PydanticField(ge=1, le=50)] = 8
    min_score: Annotated[float, PydanticField(ge=0.0, le=1.0)] = 0.0


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
    answer: str | None = None
    sources: list[str] = []


# ---------------------------------------------------------------------------
# POST /api/v1/documents/upload
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    responses={
        413: {"description": "File too large"},
        422: {"description": "Could not parse file"},
    },
)
async def upload_document(
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(description="File to upload: PDF, DOCX, PPTX, TXT, CSV, MD, JPG, PNG, MP4, ..."),
    document_name: str | None = Form(default=None, description="Display name override; defaults to filename"),
    replace_existing: bool = Form(default=False, description="Replace existing chunks for this document"),
) -> DocumentUploadResponse:
    """Upload a file, parse, chunk, embed, and persist into the Knowledge Vault."""
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE // 1024 // 1024} MB limit",
        )

    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to read file: {exc}",
        ) from exc

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE // 1024 // 1024} MB limit",
        )

    filename = file.filename or "unnamed"
    doc_name = (document_name or filename).strip() or "unnamed"
    user_id_str = str(current_user.id)

    log.info(
        "documents.upload.start",
        user_id=user_id_str,
        filename=filename,
        size=len(file_bytes),
    )

    # 1. Parse document text
    try:
        parse_result = parse_document(
            file_bytes=file_bytes,
            content_type=file.content_type or "",
            filename=filename,
        )
    except Exception as exc:
        log.warning("documents.upload.parse_error", user_id=user_id_str, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse document: {exc}",
        ) from exc

    if parse_result.is_empty():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parsed document text is empty",
        )

    doc_id = str(uuid.uuid4())

    # 2. Ingest into vector store
    ingest_skill = DocumentIngestSkill()
    ingest_req = DocumentIngestRequest(
        document_id=doc_id,
        document_name=doc_name,
        file_bytes=file_bytes,
        content_type=file.content_type or "",
        filename=filename,
        replace_existing=replace_existing,
        user_id=user_id_str,
    )
    ingest_res = await ingest_skill.execute(ingest_req)

    # 3. Persist metadata into PostgreSQL / NeonDB DocumentRecord
    repo = DocumentRepository()
    await repo.create(
        user_id=user_id_str,
        filename=doc_name,
        document_id=doc_id,
        folder="General",
        file_size_bytes=len(file_bytes),
        mime_type=file.content_type or "application/octet-stream",
        extracted_text=parse_result.content,
    )

    log.info(
        "documents.upload.success",
        user_id=user_id_str,
        document_id=doc_id,
        chunks=ingest_res.chunks_stored,
    )

    return DocumentUploadResponse(
        document_id=doc_id,
        document_name=doc_name,
        chunks_stored=ingest_res.chunks_stored,
        chunk_ids=ingest_res.chunk_ids,
        doc_type=ingest_res.doc_type,
        metadata={
            **ingest_res.metadata,
            "filename": filename,
            "size_bytes": len(file_bytes),
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/documents
# ---------------------------------------------------------------------------

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    """List all documents ingested by the authenticated user."""
    user_id_str = str(current_user.id)
    repo = DocumentRepository()
    records = await repo.list_for_user(user_id_str)

    user_chunks_map = _document_meta.get(user_id_str, {})
    items: list[DocumentListItem] = []

    for rec in records:
        chunk_count = len(user_chunks_map.get(rec.id, {}).get("chunk_ids", []))
        if chunk_count == 0 and rec.extracted_text:
            chunk_count = max(1, len(rec.extracted_text) // 1800)

        created_iso = None
        if getattr(rec, "created_at", None):
            created_iso = rec.created_at.isoformat() if hasattr(rec.created_at, "isoformat") else str(rec.created_at)

        items.append(
            DocumentListItem(
                document_id=rec.id,
                document_name=rec.filename,
                chunk_count=chunk_count,
                last_ingested=created_iso,
            )
        )

    return DocumentListResponse(documents=items)


# ---------------------------------------------------------------------------
# DELETE /api/v1/documents/{document_id}
# ---------------------------------------------------------------------------

@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
) -> DocumentDeleteResponse:
    """Delete a document and all its chunks from the RAG store with tenant guard."""
    user_id_str = str(current_user.id)

    log.info(
        "documents.delete",
        user_id=user_id_str,
        document_id=document_id,
    )

    repo = DocumentRepository()
    deleted = await repo.delete(document_id, user_id_str)
    chunks_deleted = delete_user_document(document_id, user_id_str)

    if not deleted and chunks_deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    return DocumentDeleteResponse(
        document_id=document_id,
        chunks_deleted=chunks_deleted,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/documents/query  — Semantic RAG query over user's documents
# ---------------------------------------------------------------------------

@router.post("/query", response_model=DocumentQueryResponse)
async def query_documents(
    body: DocumentQueryRequest,
    current_user: User = Depends(get_current_user),
) -> DocumentQueryResponse:
    """RAG query over the authenticated user's uploaded documents."""
    user_id_str = str(current_user.id)

    log.info(
        "documents.query",
        user_id=user_id_str,
        query=body.query[:80],
        top_k=body.top_k,
    )

    rag_skill = DocumentRAGSkill()
    req = DocumentRagQueryRequest(
        query=body.query,
        user_id=user_id_str,
        document_ids=body.document_ids,
        top_k=body.top_k,
        min_score=body.min_score,
    )
    result = await rag_skill.execute(req)

    chunks: list[DocumentQueryChunk] = [
        DocumentQueryChunk(
            document_id=c.document_id,
            document_name=c.document_name,
            location=f"chunk_{c.chunk_id[:8]}",
            text=c.content,
            score=c.relevance_score,
        )
        for c in result.chunks
    ]

    # Synthesize grounded answer
    if chunks:
        consulted_docs = ", ".join(result.documents_consulted)
        top_chunk_snippet = chunks[0].text[:400].strip()
        answer = f"Grounded in **{consulted_docs}**: {top_chunk_snippet}"
    else:
        answer = "No matching information found in your Knowledge Vault documents for this query."

    return DocumentQueryResponse(
        query=body.query,
        chunks=chunks,
        total_candidates=result.total_chunks,
        answer=answer,
        sources=result.documents_consulted,
    )
