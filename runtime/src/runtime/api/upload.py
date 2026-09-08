"""POST /api/v1/runtime/upload — ingest an uploaded file into the RAG pipeline.

Accepts a multipart form upload, parses the file to plain text (document, image, or video),
and passes it to the `document_ingest` skill for chunking, embedding, and storage in pgvector.

Supported document types: PDF, DOCX, PPTX, Markdown, plain text, CSV.
Supported image types: JPEG, PNG, GIF, BMP, WEBP, TIFF (OCR + AI captioning).
Supported video types: MP4, MOV, AVI, MKV, WEBM (transcription + frame captions).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from runtime.infrastructure.auth import AuthError, UserContext, decode_bearer
from runtime.infrastructure.document_parser import (
    DocumentParseError,
    ParseError,
    parse_document as _parse_document_async,
)
from runtime.infrastructure.media_parser import MediaParseError, parse_media

router = APIRouter(prefix="/api/v1/runtime", tags=["upload"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_stored: int
    chunk_ids: list[str]
    doc_type: str  # "pdf" | "docx" | "pptx" | "image" | "video" | ...
    metadata: dict[str, str | int | float] = {}


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def _user_dep(
    authorization: Annotated[str | None, Header()] = None,
) -> UserContext:
    try:
        return decode_bearer(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


def _skill_executor_dep(request: Request):
    """Pull the SkillExecutor off app state (set by create_app)."""
    se = getattr(request.app.state, "skill_executor", None)
    if se is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime is not initialized yet",
        )
    return se


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# Detect image or video by MIME type or extension
IMAGE_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/bmp",
    "image/webp", "image/tiff",
}
VIDEO_MIME_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/mpeg",
}


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    request: Request,
    user: Annotated[UserContext, _user_dep],
    skill_executor: Annotated[object, _skill_executor_dep],
    file: Annotated[
        UploadFile,
        File(description="File to ingest (PDF, DOCX, PPTX, MD, TXT, JPG, PNG, MP4, ...)")
    ],
    document_name: Annotated[
        str | None,
        Form(description="Display name; defaults to filename")
    ] = None,
    replace_existing: Annotated[
        bool,
        Form(description="Replace existing chunks for this document")
    ] = False,
) -> UploadResponse:
    """Parse and ingest a document, image, or video into the RAG vector store.

    The file is:
      - Documents (PDF/DOCX/PPTX/TXT): parsed to plain text via pypdf/python-docx/python-pptx
      - Images (JPEG/PNG/etc.): OCR via pytesseract + AI captioning via Gemini
      - Videos (MP4/MOV/etc.): audio transcription + key-frame captioning

    The parsed text is then handed to ``document_ingest`` for chunking,
    embedding via Gemini, and storage in pgvector.

    The authenticated user (``Authorization: Bearer <jwt>``) owns the document.
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
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    # Re-check size after reading
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE // 1024 // 1024} MB limit",
        )

    # ── Determine document_name ──────────────────────────────────────────────
    filename = file.filename or "unnamed"
    doc_name = (document_name or filename).strip() or "unnamed"

    # ── Detect media type ───────────────────────────────────────────────────
    mime_type = file.content_type or "application/octet-stream"

    # ── Parse file ─────────────────────────────────────────────────────────
    parsed_text = ""
    doc_type = "unknown"
    extra_metadata: dict[str, str | int | float] = {}

    try:
        if mime_type in IMAGE_MIME_TYPES or _is_image_by_extension(filename):
            # Image: OCR + AI caption
            media_result = await parse_media(file_bytes, filename, mime_type)
            parsed_text = media_result.text
            doc_type = "image"
            extra_metadata = {
                "ocr_text": media_result.ocr_text,
                "description": media_result.description,
                "width": media_result.metadata.get("width", 0),
                "height": media_result.metadata.get("height", 0),
            }

        elif mime_type in VIDEO_MIME_TYPES or _is_video_by_extension(filename):
            # Video: transcription + frame captions
            media_result = await parse_media(file_bytes, filename, mime_type)
            parsed_text = media_result.text
            doc_type = "video"
            extra_metadata = {
                "duration_sec": media_result.metadata.get("duration_sec", 0),
                "transcription": media_result.transcription[:500] if media_result.transcription else "",
            }

        else:
            # Document: PDF, DOCX, PPTX, TXT, etc.
            parsed_result = await _parse_document_async(file_bytes, filename, mime_type)
            parsed_text = parsed_result.text
            doc_type = _doc_type_from_mime(mime_type)
            extra_metadata = {}

    except MediaParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Media parsing failed: {exc}",
        ) from exc
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parsing failed: {exc}",
        ) from exc

    if not parsed_text or not parsed_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text could be extracted from the file",
        )

    # ── Generate stable document_id ────────────────────────────────────────
    document_id = str(uuid.uuid4())

    # ── Invoke document_ingest skill ───────────────────────────────────────
    invoke: callable = skill_executor.invoke  # type: ignore[attr-defined]
    result = await invoke(
        "document_ingest",
        inputs={
            "document_id": document_id,
            "document_name": doc_name,
            "text": parsed_text,
            "replace_existing": replace_existing,
        },
        user_id=user.user_id,
    )

    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document ingestion failed: {result.error}",
        )

    data: dict = result.data  # type: ignore[assignment]
    return UploadResponse(
        document_id=data["document_id"],
        document_name=data["document_name"],
        chunks_stored=data["chunks_stored"],
        chunk_ids=data["chunk_ids"],
        doc_type=doc_type,
        metadata={
            "char_count": len(parsed_text),
            "chunk_count": data["chunks_stored"],
            **extra_metadata,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_image_by_extension(filename: str) -> bool:
    exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
    return filename.lower().rsplit(".", 1)[-1:] in exts


def _is_video_by_extension(filename: str) -> bool:
    exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}
    return filename.lower().rsplit(".", 1)[-1:] in exts


def _doc_type_from_mime(mime_type: str) -> str:
    mapping = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "text/plain": "text",
        "text/markdown": "markdown",
        "text/csv": "csv",
        "text/html": "html",
    }
    return mapping.get(mime_type, "document")
