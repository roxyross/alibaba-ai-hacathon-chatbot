"""Multi-format document parser using pypdf, python-docx, python-pptx, and unstructured.

Supports: PDF, DOCX, PPTX, TXT, MD, CSV, HTML, and any format unstructured supports.

Usage:
    result = await parse_document(file_bytes, filename, mime_type)
    # result.text        — full extracted text
    # result.chunks      — pre-chunked text segments
    # result.doc_type    — detected document type
    # result.metadata     — extraction metadata
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

import structlog

from runtime.config import settings

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ParseResult:
    """Output of a successful document parse."""
    text: str  # Full extracted text
    doc_type: str  # e.g. "pdf", "docx", "image", "video"
    file_name: str
    metadata: dict[str, str | int | float] = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)  # Pre-chunked segments


class ParseError(Exception):
    """Raised when document parsing fails."""


# Alias for backward compatibility with upload.py
DocumentParseError = ParseError


def parse(file_bytes: bytes, mime_type: str, filename: str) -> str:
    """Synchronous parse wrapper — calls parse_document in a sync context.

    This is the API expected by the upload endpoint.
    Returns only the extracted text string.
    """
    import asyncio
    import concurrent.futures

    def _run_in_thread() -> str:
        # Create a fresh event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_parse_sync(file_bytes, mime_type, filename))
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run_in_thread).result()


async def _parse_sync(file_bytes: bytes, mime_type: str, filename: str) -> str:
    """Async implementation — returns just the text."""
    result = await parse_document(file_bytes, filename, mime_type)
    return result.text


# ---------------------------------------------------------------------------
# Core dispatcher
# ---------------------------------------------------------------------------

SUPPORTED_TYPES: dict[str, str] = {
    # mime_type -> parser_key
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/plain": "text",
    "text/markdown": "text",
    "text/csv": "text",
    "text/html": "text",
    "application/vnd.ms-excel": "csv",
    "application/octet-stream": "auto",  # use extension
}


async def parse_document(
    file_bytes: bytes,
    file_name: str,
    mime_type: str | None = None,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> ParseResult:
    """Parse a document from bytes, auto-detecting format.

    Args:
        file_bytes: Raw file content.
        file_name: Original filename (used for extension detection).
        mime_type: Optional MIME type hint.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between chunks.

    Returns:
        ParseResult with extracted text and metadata.

    Raises:
        ParseError: When no suitable parser is found or parsing fails.
    """
    # Detect mime type
    detected = mime_type or _detect_mime(file_name, file_bytes)
    parser_key = SUPPORTED_TYPES.get(detected, "auto")
    if parser_key == "auto":
        parser_key = _extension_parser(file_name)

    log.info(
        "document_parser.parse",
        file_name=file_name,
        mime_type=detected,
        parser=parser_key,
        size=len(file_bytes),
    )

    # Route to parser
    try:
        if parser_key == "pdf":
            text = await _parse_pdf(file_bytes)
        elif parser_key == "docx":
            text = await _parse_docx(file_bytes)
        elif parser_key == "pptx":
            text = await _parse_pptx(file_bytes)
        elif parser_key == "csv":
            text = await _parse_csv(file_bytes)
        elif parser_key == "unstructured":
            text = await _parse_unstructured(file_bytes, file_name, detected)
        else:
            text = await _parse_text(file_bytes, file_name)

        if not text or not text.strip():
            raise ParseError(f"Empty text extracted from {file_name}")

        # Chunk the text
        chunks = _chunk_text(text, chunk_size, chunk_overlap)

        return ParseResult(
            text=text,
            doc_type=parser_key,
            file_name=file_name,
            metadata={
                "size_bytes": len(file_bytes),
                "char_count": len(text),
                "chunk_count": len(chunks),
                "mime_type": detected,
            },
            chunks=chunks,
        )
    except ParseError:
        raise
    except Exception as exc:
        log.error("document_parser.parse_error", file_name=file_name, error=str(exc))
        raise ParseError(f"Failed to parse {file_name}: {exc}") from exc


# ---------------------------------------------------------------------------
# Per-format parsers
# ---------------------------------------------------------------------------

async def _parse_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        parts: list[str] = []

        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                parts.append(f"[Page {i + 1}]\n{text}")

        return "\n\n".join(parts)
    except Exception as exc:
        raise ParseError(f"PDF parsing failed: {exc}") from exc


async def _parse_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX using python-docx."""
    try:
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        parts: list[str] = []

        # Extract paragraphs with section markers
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                parts.append(text)

        # Extract tables
        for i, table in enumerate(doc.tables):
            table_parts = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    table_parts.append(" | ".join(cells))
            if table_parts:
                parts.append(f"[Table {i + 1}]\n" + "\n".join(table_parts))

        return "\n\n".join(parts)
    except Exception as exc:
        raise ParseError(f"DOCX parsing failed: {exc}") from exc


async def _parse_pptx(file_bytes: bytes) -> str:
    """Extract text from a PPTX using python-pptx."""
    try:
        from pptx import Presentation

        prs = Presentation(io.BytesIO(file_bytes))
        parts: list[str] = []

        for i, slide in enumerate(prs.slides):
            slide_parts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_parts.append(shape.text.strip())
            if slide_parts:
                parts.append(f"[Slide {i + 1}]\n" + "\n".join(slide_parts))

        return "\n\n".join(parts)
    except Exception as exc:
        raise ParseError(f"PPTX parsing failed: {exc}") from exc


async def _parse_csv(file_bytes: bytes) -> str:
    """Extract text from a CSV."""
    try:
        import csv

        text = file_bytes.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            return ""

        # Header row
        header = rows[0]
        parts = ["Columns: " + ", ".join(header)]

        # First few rows as sample
        for i, row in enumerate(rows[1:21], start=1):
            cells = [f"{header[j] if j < len(header) else 'col'}: {v}" for j, v in enumerate(row) if v.strip()]
            if cells:
                parts.append(f"Row {i}: " + " | ".join(cells))

        if len(rows) > 21:
            parts.append(f"... ({len(rows) - 21} more rows)")

        return "\n".join(parts)
    except Exception as exc:
        raise ParseError(f"CSV parsing failed: {exc}") from exc


async def _parse_text(file_bytes: bytes, file_name: str) -> str:
    """Extract text from plain text / markdown / HTML."""
    try:
        # Try UTF-8 first, fallback to latin-1
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")

        # Strip HTML tags if present
        if "<" in text and ">" in text:
            text = _strip_html(text)

        return text.strip()
    except Exception as exc:
        raise ParseError(f"Text parsing failed: {exc}") from exc


async def _parse_unstructured(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
) -> str:
    """Use unstructured library for complex document parsing.

    Falls back gracefully if unstructured is not installed.
    """
    try:
        from unstructured.partition.auto import partition

        # Determine file type hint
        file_type = None
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if ext:
            file_type = ext

        with io.BytesIO(file_bytes) as f:
            elements = partition(
                file=f,
                filename=file_name,
                content_type=mime_type,
                file_type=file_type,
            )

        # Join all element texts
        texts = [str(el) for el in elements if str(el).strip()]
        return "\n\n".join(texts)
    except ImportError:
        log.warning("document_parser.unstructured_not_available", falling_back=True)
        # Fallback: try raw text parsing
        return await _parse_text(file_bytes, file_name)
    except Exception as exc:
        # Don't fail hard — try fallback
        log.warning("document_parser.unstructured_failed", error=str(exc), falling_back=True)
        try:
            return await _parse_text(file_bytes, file_name)
        except Exception:
            raise ParseError(f"Unstructured parsing failed and fallback also failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _detect_mime(file_name: str, file_bytes: bytes) -> str:
    """Detect MIME type from file magic bytes and extension."""
    # Magic bytes
    magic: dict[bytes, str] = {
        b"%PDF": "application/pdf",
        b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"\xd0\xcf\x11\xe0": "application/vnd.ms-excel",
    }
    for magic_bytes, mime in magic.items():
        if file_bytes[: len(magic_bytes)] == magic_bytes:
            return mime

    # Extension fallback
    ext_map: dict[str, str] = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".html": "text/html",
        ".htm": "text/html",
        ".xlsx": "application/vnd.ms-excel",
    }
    for ext, mime in ext_map.items():
        if file_name.lower().endswith(ext):
            return mime

    return "application/octet-stream"


def _extension_parser(file_name: str) -> str:
    """Map file extension to parser key."""
    ext_map: dict[str, str] = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".pptx": "pptx",
        ".txt": "text",
        ".md": "text",
        ".csv": "csv",
        ".html": "text",
        ".htm": "text",
        ".xlsx": "csv",
    }
    ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return ext_map.get(ext, "text")


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities."""
    # Remove script and style blocks
    text = re.sub(r"(?s)<script.*?</script>", "", text)
    text = re.sub(r"(?s)<style.*?</style>", "", text)
    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    text = text.replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _chunk_text(
    text: str,
    size: int = 2000,
    overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks, respecting sentence boundaries."""
    if not text or len(text) <= size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        if end < text_len:
            # Try to break at sentence boundary
            for punct in (". ", ".\n", "!\n", "?\n", "\n\n", ".\r\n"):
                last_punct = text.rfind(punct, start, end + 40)
                if last_punct > start:
                    end = last_punct + len(punct)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if chunks and start <= len(chunks[-1]):
            start = end

    return chunks
