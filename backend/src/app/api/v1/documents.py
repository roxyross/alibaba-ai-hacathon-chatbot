"""Document Upload API — proxy file uploads to the runtime for parsing + RAG ingestion.

POST /api/v1/documents/upload  — upload a file (PDF, DOCX, PPTX, TXT, image, video) and ingest into RAG
GET  /api/v1/documents          — list user's uploaded documents
DELETE /api/v1/documents/{document_id}  — delete a document

The backend authenticates the user and proxies to the runtime's
``POST /api/v1/runtime/upload`` endpoint, which handles parsing and storage.
"""

from __future__ import annotations

import os
import time
from typing import Annotated

import httpx
import jwt
import structlog
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.models import User

log = structlog.get_logger()

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Runtime base URL
# ---------------------------------------------------------------------------

_RUNTIME_BASE = os.environ.get("RUNTIME_BASE_URL", "http://localhost:8001")
_JWT_SECRET = os.environ.get("JWT_SECRET", os.environ.get("SECRET_KEY", "dev-secret-change-in-production"))


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class DocumentUploadResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_stored: int
    chunk_ids: list[str]
    doc_type: str
    metadata: dict[str, str | int | float]


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


class DocumentParseError(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _runtime_post(
    path: str,
    files: dict | None = None,
    data: dict | None = None,
    token: str | None = None,
) -> dict:
    """Proxy a multipart request to the runtime service."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{_RUNTIME_BASE}{path}",
            files=files,
            data=data,
            headers=headers,
        )

    if not resp.is_success:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return resp.json()


async def _runtime_get(
    path: str,
    token: str | None = None,
    params: dict | None = None,
) -> dict:
    """Proxy a GET request to the runtime service."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_RUNTIME_BASE}{path}",
            headers=headers,
            params=params,
        )

    if not resp.is_success:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return resp.json()


async def _runtime_delete(
    path: str,
    token: str | None = None,
) -> dict:
    """Proxy a DELETE request to the runtime service."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(
            f"{_RUNTIME_BASE}{path}",
            headers=headers,
        )

    if not resp.is_success:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/v1/documents/upload
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


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
    file: UploadFile = File(description="File to upload: PDF, DOCX, PPTX, TXT, CSV, MD, JPG, PNG, MP4, MOV, ..."),
    document_name: str | None = Form(default=None, description="Display name override; defaults to filename"),
    replace_existing: bool = Form(default=False, description="Replace existing chunks for this document"),
) -> DocumentUploadResponse:
    """Upload a file and ingest it into the RAG vector store.

    Supports:
      - Documents: PDF, DOCX, PPTX, TXT, CSV, Markdown (via pypdf, python-docx, python-pptx)
      - Images: JPEG, PNG, GIF, BMP, WEBP (OCR + AI captioning via Gemini)
      - Videos: MP4, MOV, AVI, MKV, WEBM (transcription + frame captioning)

    The file is parsed server-side, then chunked, embedded via Gemini,
    and stored in pgvector. The user can then query it via
    ``POST /api/v1/documents/query``.
    """
    # ── File size guard ─────────────────────────────────────────────────────
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE // 1024 // 1024} MB limit",
        )

    # ── Read file bytes ─────────────────────────────────────────────────────
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

    # ── Get user JWT for runtime auth ───────────────────────────────────────
    token = _get_runtime_token(current_user)

    # ── Proxy to runtime ─────────────────────────────────────────────────────
    filename = file.filename or "unnamed"
    doc_name = (document_name or filename).strip() or "unnamed"

    log.info(
        "documents.upload",
        user_id=str(current_user.id),
        filename=filename,
        size=len(file_bytes),
    )

    try:
        result = await _runtime_post(
            "/api/v1/runtime/upload",
            files={
                "file": (filename, file_bytes, file.content_type or "application/octet-stream"),
            },
            data={
                "document_name": doc_name,
                "replace_existing": str(replace_existing),
            },
            token=token,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("documents.upload_failed", user_id=str(current_user.id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Runtime error: {exc}",
        ) from exc

    return DocumentUploadResponse(**result)


# ---------------------------------------------------------------------------
# GET /api/v1/documents
# ---------------------------------------------------------------------------

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    """List all documents ingested by the authenticated user."""
    token = _get_runtime_token(current_user)

    try:
        result = await _runtime_get(
            "/api/v1/runtime/documents",
            token=token,
        )
    except HTTPException:
        # Runtime might not implement this endpoint yet — return empty list
        return DocumentListResponse(documents=[])
    except Exception as exc:
        log.error("documents.list_failed", user_id=str(current_user.id), error=str(exc))
        return DocumentListResponse(documents=[])

    return DocumentListResponse(documents=[
        DocumentListItem(
            document_id=d["document_id"],
            document_name=d["document_name"],
            chunk_count=d.get("chunk_count", 0),
            last_ingested=d.get("last_ingested"),
        )
        for d in result.get("documents", [])
    ])


# ---------------------------------------------------------------------------
# DELETE /api/v1/documents/{document_id}
# ---------------------------------------------------------------------------

@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
) -> DocumentDeleteResponse:
    """Delete a document and all its chunks from the RAG store."""
    token = _get_runtime_token(current_user)

    log.info(
        "documents.delete",
        user_id=str(current_user.id),
        document_id=document_id,
    )

    try:
        result = await _runtime_delete(
            f"/api/v1/runtime/documents/{document_id}",
            token=token,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found",
            )
        raise
    except Exception as exc:
        log.error("documents.delete_failed", user_id=str(current_user.id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Runtime error: {exc}",
        ) from exc

    return DocumentDeleteResponse(
        document_id=document_id,
        chunks_deleted=result.get("chunks_deleted", 0),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/documents/query  — RAG query over user's documents
# ---------------------------------------------------------------------------

from pydantic import Field as PydanticField


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


@router.post("/query", response_model=DocumentQueryResponse)
async def query_documents(
    body: DocumentQueryRequest,
    current_user: User = Depends(get_current_user),
) -> DocumentQueryResponse:
    """RAG query over the authenticated user's uploaded documents.

    Searches for chunks relevant to ``query`` using semantic similarity
    (Gemini embeddings + pgvector). Returns top-k chunks with scores.
    """
    token = _get_runtime_token(current_user)

    log.info(
        "documents.query",
        user_id=str(current_user.id),
        query=body.query[:80],
        top_k=body.top_k,
    )

    try:
        result = await _runtime_post(
            "/api/v1/runtime/documents/query",
            data={
                "query": body.query,
                "top_k": body.top_k,
                "min_score": body.min_score,
                "document_ids": body.document_ids or [],
            },
            token=token,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("documents.query_failed", user_id=str(current_user.id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Runtime error: {exc}",
        ) from exc

    return DocumentQueryResponse(
        query=result.get("query", body.query),
        chunks=[
            DocumentQueryChunk(
                document_id=c["document_id"],
                document_name=c["document_name"],
                location=c.get("location", ""),
                text=c["text"],
                score=c["score"],
            )
            for c in result.get("chunks", [])
        ],
        total_candidates=result.get("total_candidates", 0),
    )


# ---------------------------------------------------------------------------
# Runtime token helper
# ---------------------------------------------------------------------------

def _get_runtime_token(user: User) -> str:
    """Generate a runtime JWT for the user (delegation token).

    The runtime validates this token using the shared JWT secret.
    For now, we re-sign the user's existing JWT with the runtime secret.
    """
    import time

    import jwt

    payload = {
        "sub": str(user.id),
        "email": getattr(user, "email", ""),
        "exp": int(time.time()) + 3600,  # 1 hour
        "iat": int(time.time()),
        "iss": "backend",
    }
    secret = _JWT_SECRET
    return jwt.encode(payload, secret, algorithm="HS256")
