"""Document parser — extracts raw text from PDFs, DOCX, PPTX, images, and videos.

Each ``parse_*`` function returns a ``ParseResult``:
    content: str        — raw text
    doc_type: str       — "pdf" | "docx" | "pptx" | "txt" | "image" | "video"
    metadata: dict      — arbitrary key/value (page count, dimensions, etc.)

For images and videos, ``content`` already includes OCR / transcription text.
"""

from __future__ import annotations

import io
import logging
import re
import tempfile
import os
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    content: str
    doc_type: str
    metadata: dict = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.content.strip()


# ---------------------------------------------------------------------------
# PDF — pdfplumber (primary), PyPDF2 (fallback)
# ---------------------------------------------------------------------------

def _parse_pdf_plumber(file_bytes: bytes) -> ParseResult:
    import pdfplumber

    metadata: dict = {}
    pages: list[str] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        metadata["page_count"] = len(pdf.pages)
        if pdf.metadata:
            metadata["title"] = pdf.metadata.get("Title", "")
            metadata["author"] = pdf.metadata.get("Author", "")

        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[Page {i + 1}]\n{text}")

    return ParseResult(
        content="\n\n".join(pages),
        doc_type="pdf",
        metadata=metadata,
    )


def _parse_pdf_llamaparse(file_bytes: bytes) -> ParseResult:
    """Parse PDF using LlamaParse (premium parsing — better layout/table extraction)."""
    import os

    from llama_parse import LlamaParse

    api_key = os.getenv("LLAMAPARSE_API_KEY")
    if not api_key:
        raise ValueError("LLAMAPARSE_API_KEY is not set")

    parser = LlamaParse(api_key=api_key, result_type="text")
    # llamaparse accepts file bytes or a file path; pass bytes via a temporary file
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        docs = parser.load_data(tmp_path)
        pages: list[str] = []
        for i, doc in enumerate(docs):
            text = doc.text.strip()
            if text:
                pages.append(f"[Page {i + 1}]\n{text}")
        return ParseResult(
            content="\n\n".join(pages),
            doc_type="pdf",
            metadata={"parser": "llamaparse", "page_count": len(docs)},
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _parse_pdf_pypdf(file_bytes: bytes) -> ParseResult:
    from PyPDF2 import PdfReader

    metadata: dict = {}
    pages: list[str] = []

    reader = PdfReader(io.BytesIO(file_bytes))
    metadata["page_count"] = len(reader.pages)
    if reader.metadata:
        metadata["title"] = str(reader.metadata.get("/Title", ""))
        metadata["author"] = str(reader.metadata.get("/Author", ""))

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {i + 1}]\n{text}")

    return ParseResult(
        content="\n\n".join(pages),
        doc_type="pdf",
        metadata=metadata,
    )


def parse_pdf(file_bytes: bytes) -> ParseResult:
    """Parse a PDF using a three-tier strategy:
    1. pdfplumber  — fast, good for plain-text PDFs
    2. PyPDF2      — fallback for encrypted or image-only PDFs
    3. LlamaParse  — premium parser with superior layout/table extraction
                       (requires LLAMAPARSE_API_KEY env var)
    """
    try:
        return _parse_pdf_plumber(file_bytes)
    except Exception as exc:
        log.warning("pdf.plumber_failed", error=str(exc))
        try:
            return _parse_pdf_pypdf(file_bytes)
        except Exception as exc2:
            log.warning("pdf.pypdf_also_failed", error=str(exc2))
            try:
                return _parse_pdf_llamaparse(file_bytes)
            except Exception as exc3:
                log.error("pdf.llamaparse_also_failed", error=str(exc3))
                raise ValueError(f"Could not parse PDF: {exc3}") from exc2


# ---------------------------------------------------------------------------
# DOCX — python-docx
# ---------------------------------------------------------------------------

def parse_docx(file_bytes: bytes) -> ParseResult:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs: list[str] = []

    # Extract paragraphs (skip empty)
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)

    # Extract tables
    tables_text: list[str] = []
    for i, table in enumerate(doc.tables):
        rows_text: list[str] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                rows_text.append(" | ".join(cells))
        if rows_text:
            tables_text.append(f"[Table {i + 1}]\n" + "\n".join(rows_text))

    content_parts = paragraphs + tables_text
    content = "\n\n".join(content_parts)

    core_props = doc.core_properties
    metadata = {
        "paragraph_count": len([p for p in doc.paragraphs if p.text.strip()]),
        "table_count": len(doc.tables),
        "title": str(core_props.title) if core_props.title else "",
        "author": str(core_props.author) if core_props.author else "",
    }

    return ParseResult(content=content, doc_type="docx", metadata=metadata)


# ---------------------------------------------------------------------------
# PPTX — python-pptx
# ---------------------------------------------------------------------------

def parse_pptx(file_bytes: bytes) -> ParseResult:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation(io.BytesIO(file_bytes))
    slides: list[str] = []

    for i, slide in enumerate(prs.slides):
        parts: list[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                parts.append(shape.text.strip())
        if parts:
            slides.append(f"[Slide {i + 1}]\n" + "\n".join(parts))

    metadata = {
        "slide_count": len(prs.slides),
    }

    return ParseResult(
        content="\n\n".join(slides),
        doc_type="pptx",
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# TXT / MD / CSV — built-in
# ---------------------------------------------------------------------------

def parse_txt(file_bytes: bytes, filename: str = "") -> ParseResult:
    # Try UTF-8 first, then latin-1
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    # Strip HTML tags if it looks like HTML
    if "<html" in text.lower() or "<body" in text.lower():
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

    ext = Path(filename).suffix.lower()
    doc_type = "txt"
    if ext == ".md":
        doc_type = "markdown"
    elif ext == ".csv":
        doc_type = "csv"

    return ParseResult(content=text.strip(), doc_type=doc_type, metadata={"filename": filename})


# ---------------------------------------------------------------------------
# Image — Pillow + pytesseract (OCR)
# ---------------------------------------------------------------------------

def parse_image(file_bytes: bytes, filename: str = "") -> ParseResult:
    from PIL import Image

    metadata: dict = {}
    text_parts: list[str] = []

    try:
        img = Image.open(io.BytesIO(file_bytes))
        metadata["width"] = img.width
        metadata["height"] = img.height
        metadata["format"] = img.format

        # OCR the image
        import pytesseract

        ocr_text = pytesseract.image_to_string(img)
        if ocr_text.strip():
            text_parts.append("[OCR]\n" + ocr_text.strip())

        # Also get available data
        try:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            # Get confident text only
            confidences = [int(x) for x in data["conf"] if x != "-"]
            if confidences:
                metadata["ocr_avg_confidence"] = round(sum(confidences) / len(confidences), 1)
        except Exception:
            pass

    except Exception as exc:
        log.warning("image.ocr_failed", error=str(exc))
        text_parts.append(f"[Image: could not perform OCR — {filename}]")

    content = "\n\n".join(text_parts) if text_parts else ""
    return ParseResult(content=content, doc_type="image", metadata=metadata)


# ---------------------------------------------------------------------------
# Video — moviepy for audio extraction + transcription placeholder
# ---------------------------------------------------------------------------

def parse_video(file_bytes: bytes, filename: str = "") -> ParseResult:
    """Extract audio from video and return transcript.

    For now, audio is extracted and a placeholder transcript is generated.
    In production, integrate with Whisper API or Deepgram for actual transcription.
    """
    import pytesseract
    from PIL import Image
    from moviepy.editor import VideoFileClip

    metadata: dict = {}
    text_parts: list[str] = []

    # Write to a temp file (moviepy needs a real path)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        clip = VideoFileClip(tmp_path)
        duration = clip.duration
        fps = clip.fps
        metadata["duration_seconds"] = round(duration, 2)
        metadata["fps"] = round(fps, 1)
        metadata["width"] = clip.size[0]
        metadata["height"] = clip.size[1]

        # Extract a frame every 30 seconds for visual description
        num_frames = max(1, int(duration // 30))
        frame_interval = duration / num_frames if num_frames > 0 else 0

        for i in range(num_frames):
            t = i * frame_interval
            try:
                frame = clip.get_frame(t)
                img = Image.fromarray(frame)
                # Quick OCR of frame
                frame_text = pytesseract.image_to_string(img)
                if frame_text.strip():
                    text_parts.append(f"[Video frame at {int(t)}s]\n{frame_text.strip()}")
            except Exception as exc:
                log.debug("video.frame_extract_failed", t=t, error=str(exc))

        clip.close()

        # Audio transcription note — real implementation would use Whisper/Deepgram here
        if duration > 0:
            text_parts.append(
                f"[Video: {int(duration)}s] Audio transcription not yet implemented. "
                "Video frames have been OCR'd above. "
                "To enable full transcription, configure a Speech-to-Text provider."
            )

    except Exception as exc:
        log.warning("video.processing_failed", error=str(exc))
        text_parts.append(f"[Video: could not process — {filename}]")

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    content = "\n\n".join(text_parts)
    return ParseResult(content=content, doc_type="video", metadata=metadata)


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

CONTENT_TYPE_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/plain": "txt",
    "text/markdown": "markdown",
    "text/csv": "csv",
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/bmp": "image",
    "image/webp": "image",
    "image/tiff": "image",
    "video/mp4": "video",
    "video/quicktime": "video",
    "video/x-msvideo": "video",
    "video/x-matroska": "video",
    "video/webm": "video",
    "video/mpeg": "video",
}

EXTENSION_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".txt": "txt",
    ".md": "markdown",
    ".csv": "csv",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".bmp": "image",
    ".webp": "image",
    ".tiff": "image",
    ".tif": "image",
    ".mp4": "video",
    ".mov": "video",
    ".avi": "video",
    ".mkv": "video",
    ".webm": "video",
    ".mpeg": "video",
}


def parse_document(file_bytes: bytes, content_type: str = "", filename: str = "") -> ParseResult:
    """Dispatch to the right parser based on MIME type or file extension."""
    # Determine doc type
    ext = Path(filename).suffix.lower()
    doc_type = EXTENSION_MAP.get(ext, "")

    if not doc_type:
        doc_type = CONTENT_TYPE_MAP.get(content_type, "")

    log.info("document.parse.start", doc_type=doc_type, filename=filename, size=len(file_bytes))

    try:
        if doc_type == "pdf":
            result = parse_pdf(file_bytes)
        elif doc_type == "docx":
            result = parse_docx(file_bytes)
        elif doc_type == "pptx":
            result = parse_pptx(file_bytes)
        elif doc_type in ("txt", "markdown", "csv"):
            result = parse_txt(file_bytes, filename)
        elif doc_type == "image":
            result = parse_image(file_bytes, filename)
        elif doc_type == "video":
            result = parse_video(file_bytes, filename)
        else:
            # Fallback: try to read as text
            result = parse_txt(file_bytes, filename)
            log.warning("document.parse.unknown_type", content_type=content_type, ext=ext)

        log.info(
            "document.parse.done",
            doc_type=result.doc_type,
            content_chars=len(result.content),
            metadata=result.metadata,
        )
        return result

    except Exception as exc:
        log.error("document.parse.error", doc_type=doc_type, filename=filename, error=str(exc))
        raise ValueError(f"Failed to parse document: {exc}") from exc
