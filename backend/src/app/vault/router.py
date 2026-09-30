"""REST API router for Knowledge Vault and Vector Memory (Phase 5).

Endpoints under `/api/v1/vault` for document ingestion, quick notes,
hybrid semantic search, chunk inspection, and statistical telemetry.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.skills.document_parser import parse_document
from app.vault.schemas import (
    VaultDocumentCreateRequest,
    VaultDocumentListResponse,
    VaultDocumentResponse,
    VaultNoteCreateRequest,
    VaultSearchRequest,
    VaultSearchResponse,
    VaultStatsResponse,
)
from app.vault.service import VaultService

log = structlog.get_logger()

router = APIRouter(prefix="/vault", tags=["vault"])
_service = VaultService.get_instance()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Document Ingestion & Upload
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=VaultDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and vectorize a document",
)
@router.post(
    "/documents/upload",
    response_model=VaultDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and vectorize a document (alias)",
)
async def upload_document(
    file: UploadFile = File(description="File to index: PDF, DOCX, TXT, CSV, MD, Code..."),
    document_name: str | None = Form(None, description="Custom document title override"),
    folder: str = Form("General", description="Vault category/folder name"),
    current_user: User = Depends(get_current_user),
) -> VaultDocumentResponse:
    """Upload a file, parse text, chunk hierarchically, embed, and store in vault."""
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
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    filename = file.filename or "uploaded_document.txt"
    title = (document_name or filename).strip() or filename
    content_type = file.content_type or "application/octet-stream"

    # Extract text content
    extracted_text = ""
    try:
        parse_res = parse_document(file_bytes=file_bytes, content_type=content_type, filename=filename)
        extracted_text = parse_res.content
    except Exception:
        # Fallback to UTF-8 decode
        try:
            extracted_text = file_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not extract readable text from '{filename}': {exc}",
            ) from exc

    if not extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Extracted document content for '{filename}' is empty.",
        )

    doc_resp = await _service.ingest_document(
        user_id=current_user.id,
        filename=title,
        content=extracted_text,
        folder=folder.strip() or "General",
        mime_type=content_type,
    )
    return doc_resp


@router.post(
    "/documents",
    response_model=VaultDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a document from raw text or markdown",
)
async def create_document(
    body: VaultDocumentCreateRequest,
    current_user: User = Depends(get_current_user),
) -> VaultDocumentResponse:
    """Index a new document directly from provided text content."""
    return await _service.ingest_document(
        user_id=current_user.id,
        filename=body.filename,
        content=body.content,
        folder=body.folder,
        mime_type=body.mime_type,
        tags=body.tags,
    )


@router.post(
    "/notes",
    response_model=VaultDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a knowledge note",
)
async def create_note(
    body: VaultNoteCreateRequest,
    current_user: User = Depends(get_current_user),
) -> VaultDocumentResponse:
    """Save a quick markdown note directly into the Knowledge Vault."""
    return await _service.create_note(
        user_id=current_user.id,
        title=body.title,
        content=body.content,
        folder=body.folder,
        tags=body.tags,
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.post(
    "/search",
    response_model=VaultSearchResponse,
    summary="Hybrid semantic vector & keyword search",
)
async def search_vault(
    body: VaultSearchRequest,
    current_user: User = Depends(get_current_user),
) -> VaultSearchResponse:
    """Perform hybrid search over user's vectorized knowledge chunks."""
    return await _service.search(
        user_id=current_user.id,
        query=body.query,
        folder=body.folder,
        document_ids=body.document_ids,
        top_k=body.top_k,
        min_score=body.min_score,
        hybrid=body.hybrid,
    )


# ---------------------------------------------------------------------------
# Document Listing & Retrieval
# ---------------------------------------------------------------------------

@router.get(
    "/documents",
    response_model=VaultDocumentListResponse,
    summary="List user documents in the Knowledge Vault",
)
async def list_documents(
    folder: str | None = Query(None, description="Filter by folder name"),
    query: str | None = Query(None, description="Filter by document name"),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_user: User = Depends(get_current_user),
) -> VaultDocumentListResponse:
    """List documents belonging to the authenticated user."""
    return await _service.list_documents(
        user_id=current_user.id,
        folder=folder,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{document_id}",
    response_model=VaultDocumentResponse,
    summary="Get document details and all vector chunks",
)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
) -> VaultDocumentResponse:
    """Retrieve full document metadata and constituent chunks."""
    doc = await _service.get_document(user_id=current_user.id, document_id=document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found in user vault.",
        )
    return doc


@router.delete(
    "/documents/{document_id}",
    summary="Delete a document and all associated chunks",
)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Permanently delete a document and its vector embeddings."""
    success = await _service.delete_document(user_id=current_user.id, document_id=document_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found or already deleted.",
        )
    return {"deleted": True, "document_id": document_id}


# ---------------------------------------------------------------------------
# Telemetry & Statistics
# ---------------------------------------------------------------------------

@router.get(
    "/stats",
    response_model=VaultStatsResponse,
    summary="Retrieve vault metrics and folder counts",
)
async def get_vault_stats(
    current_user: User = Depends(get_current_user),
) -> VaultStatsResponse:
    """Return statistical summary of user's private Knowledge Vault."""
    return await _service.get_stats(user_id=current_user.id)
