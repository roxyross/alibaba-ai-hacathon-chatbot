"""Media parser for images and videos — OCR, captioning, frame extraction, and transcription.

Supports:
  - Images (JPEG, PNG, GIF, BMP, WEBP): OCR via pytesseract, captioning via Gemini
  - Videos (MP4, MOV, AVI, MKV, WEBM): audio extraction + transcription, key-frame extraction

Usage:
    # Image
    result = await parse_image(file_bytes, filename)
    # result.text         — OCR + caption text
    # result.description  — AI-generated caption
    # result.ocr_text     — raw OCR output

    # Video
    result = await parse_video(file_bytes, filename)
    # result.text           — transcription
    # result.frame_captions — per-frame descriptions
    # result.duration_sec   — video duration
"""

from __future__ import annotations

import base64
import io
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import structlog

from runtime.config import settings

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class MediaParseResult:
    """Output of a successful media parse."""
    text: str  # Full extracted text (OCR + transcription)
    doc_type: str  # "image" or "video"
    file_name: str
    description: str = ""  # AI-generated caption/summary
    ocr_text: str = ""  # Raw OCR output
    transcription: str = ""  # Raw video/audio transcription
    metadata: dict[str, str | int | float] = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)


class MediaParseError(Exception):
    """Raised when media parsing fails."""


# ---------------------------------------------------------------------------
# Image parsing
# ---------------------------------------------------------------------------


SUPPORTED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/webp",
    "image/tiff",
}

SUPPORTED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
    "video/mpeg",
}


async def parse_image(
    file_bytes: bytes,
    file_name: str,
    mime_type: str | None = None,
    include_caption: bool = True,
    ocr_lang: str = "eng",
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> MediaParseResult:
    """Parse an image — extract text via OCR and optionally generate a caption.

    Args:
        file_bytes: Raw image content.
        file_name: Original filename.
        mime_type: Optional MIME type hint.
        include_caption: Whether to generate an AI caption via Gemini.
        ocr_lang: Tesseract language code(s), e.g. "eng", "eng+spa", "chi_sim".
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between chunks.

    Returns:
        MediaParseResult with OCR text, optional caption, and metadata.
    """
    import imghdr

    detected_type = mime_type or _detect_image_type(file_bytes) or "application/octet-stream"
    if detected_type not in SUPPORTED_IMAGE_TYPES:
        raise MediaParseError(f"Unsupported image type: {detected_type}")

    log.info(
        "media_parser.image",
        file_name=file_name,
        type=detected_type,
        size=len(file_bytes),
    )

    try:
        from PIL import Image

        image = Image.open(io.BytesIO(file_bytes))
        width, height = image.size
        mode = image.mode

        # ── OCR ────────────────────────────────────────────────────────────
        ocr_text = await _ocr_image(image, lang=ocr_lang)

        # ── AI Caption ───────────────────────────────────────────────────
        description = ""
        if include_caption:
            description = await _caption_image(image, file_name)

        # Combine OCR and caption
        parts = []
        if description:
            parts.append(f"[Image Description]\n{description}")
        if ocr_text:
            parts.append(f"[Extracted Text (OCR)]\n{ocr_text}")

        text = "\n\n".join(parts) if parts else ocr_text or description

        # Chunk
        chunks = _chunk_text(text, chunk_size, chunk_overlap)

        return MediaParseResult(
            text=text,
            doc_type="image",
            file_name=file_name,
            description=description,
            ocr_text=ocr_text,
            metadata={
                "width": width,
                "height": height,
                "mode": mode,
                "size_bytes": len(file_bytes),
                "char_count": len(text),
                "chunk_count": len(chunks),
            },
            chunks=chunks,
        )

    except ImportError as exc:
        raise MediaParseError(f"Missing dependency for image parsing: {exc}") from exc
    except Exception as exc:
        log.error("media_parser.image_error", file_name=file_name, error=str(exc))
        raise MediaParseError(f"Image parsing failed: {exc}") from exc


async def _ocr_image(image: "Image.Image", lang: str = "eng") -> str:
    """Run Tesseract OCR on a PIL Image."""
    try:
        import pytesseract

        try:
            # Try with specified language
            text = pytesseract.image_to_string(image, lang=lang)
        except Exception:
            # Fallback to English only
            text = pytesseract.image_to_string(image, lang="eng")

        return text.strip()
    except ImportError:
        log.warning("media_parser.pytesseract_not_available")
        return ""
    except Exception as exc:
        log.warning("media_parser.ocr_failed", error=str(exc))
        return ""


async def _caption_image(image: "Image.Image", file_name: str) -> str:
    """Generate a caption for an image using the Gemini API."""
    try:
        import google.genai as genai

        if not settings.google_api_key:
            log.warning("media_parser.no_api_key_for_caption")
            return ""

        client = genai.Client(api_key=settings.google_api_key)

        # Resize large images to save API quota (max 1024px)
        max_dim = 1024
        if max(image.size) > max_dim:
            image = image.copy()
            image.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Convert to JPEG bytes for API
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=85)
        image_b64 = base64.b64encode(buf.getvalue()).decode()

        prompt = (
            "Describe this image in detail. Include:\n"
            "- What is shown (objects, people, scene)\n"
            "- Text visible in the image (if any)\n"
            "- Any notable colors, style, or composition\n"
            "- Context or setting\n"
            "Be specific and thorough."
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_b64,
                            }
                        },
                    ],
                }
            ],
        )

        caption = ""
        for part in response.parts:
            if part.text:
                caption += part.text

        return caption.strip()
    except Exception as exc:
        log.warning("media_parser.caption_failed", error=str(exc))
        return ""


# ---------------------------------------------------------------------------
# Video parsing
# ---------------------------------------------------------------------------


async def parse_video(
    file_bytes: bytes,
    file_name: str,
    mime_type: str | None = None,
    max_frames: int = 8,
    include_transcription: bool = True,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> MediaParseResult:
    """Parse a video — extract audio, transcribe, and optionally extract key frames.

    Args:
        file_bytes: Raw video content.
        file_name: Original filename.
        mime_type: Optional MIME type hint.
        max_frames: Maximum number of key frames to caption.
        include_transcription: Whether to transcribe the audio track.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between chunks.

    Returns:
        MediaParseResult with transcription, frame captions, and metadata.
    """
    detected_type = mime_type or "video/mp4"
    if detected_type not in SUPPORTED_VIDEO_TYPES:
        raise MediaParseError(f"Unsupported video type: {detected_type}")

    log.info(
        "media_parser.video",
        file_name=file_name,
        type=detected_type,
        size=len(file_bytes),
    )

    try:
        # Write video to temp file (moviepy requires a file path)
        suffix = _video_extension(file_name)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            # ── Extract metadata ──────────────────────────────────────────
            duration, fps = await _get_video_info(tmp_path)

            # ── Extract and transcribe audio ─────────────────────────────
            transcription = ""
            if include_transcription:
                transcription = await _transcribe_video(tmp_path, file_name)

            # ── Extract key frames ───────────────────────────────────────
            frame_captions = await _extract_frame_captions(tmp_path, max_frames)

            # ── Assemble text ───────────────────────────────────────────
            parts = []
            if duration:
                parts.append(f"[Video Info]\nDuration: {duration:.1f}s | FPS: {fps:.2f}")

            if transcription:
                parts.append(f"[Audio Transcription]\n{transcription}")

            if frame_captions:
                frame_text = "\n".join(
                    f"  Frame {i + 1} ({t:.1f}s): {cap}"
                    for i, (cap, t) in enumerate(frame_captions)
                )
                parts.append(f"[Key Frames]\n{frame_text}")

            text = "\n\n".join(parts)

            # Chunk
            chunks = _chunk_text(text, chunk_size, chunk_overlap)

            return MediaParseResult(
                text=text,
                doc_type="video",
                file_name=file_name,
                transcription=transcription,
                metadata={
                    "duration_sec": duration or 0,
                    "fps": fps or 0,
                    "size_bytes": len(file_bytes),
                    "max_frames": max_frames,
                    "char_count": len(text),
                    "chunk_count": len(chunks),
                },
                chunks=chunks,
            )

        finally:
            # Clean up temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    except MediaParseError:
        raise
    except ImportError as exc:
        raise MediaParseError(f"Missing dependency for video parsing: {exc}") from exc
    except Exception as exc:
        log.error("media_parser.video_error", file_name=file_name, error=str(exc))
        raise MediaParseError(f"Video parsing failed: {exc}") from exc


async def _get_video_info(video_path: Path) -> tuple[float, float]:
    """Get video duration and FPS using moviepy."""
    try:
        from moviepy.editor import VideoFileClip

        clip = VideoFileClip(str(video_path))
        duration = clip.duration
        fps = clip.fps if hasattr(clip, "fps") and clip.fps else 0
        clip.close()
        return duration, fps
    except Exception as exc:
        log.warning("media_parser.video_info_failed", error=str(exc))
        return 0.0, 0.0


async def _transcribe_video(video_path: Path, file_name: str) -> str:
    """Extract audio from video and transcribe using Google Cloud Speech-to-Text."""
    try:
        import os as _os
        from moviepy.editor import AudioFileClip

        # Extract audio to a temp WAV file
        audio_suffix = ".wav"
        with tempfile.NamedTemporaryFile(suffix=audio_suffix, delete=False) as tmp:
            audio_path = Path(tmp.name)

        try:
            clip = AudioFileClip(str(video_path))
            clip.write_audiofile(str(audio_path), fps=16000, codec="pcm_s16le", verbose=False, logger=None)
            clip.close()

            # Read audio bytes
            audio_bytes = audio_path.read_bytes()

            # Transcribe using Google Cloud Speech-to-Text
            transcription = await _speech_to_text(audio_bytes, "audio/wav")
            return transcription

        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

    except ImportError:
        log.warning("media_parser.moviepy_not_available")
        return "[Audio transcription unavailable — moviepy not installed]"
    except Exception as exc:
        log.warning("media_parser.transcription_failed", error=str(exc))
        return f"[Transcription failed: {exc}]"


async def _speech_to_text(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """Transcribe audio bytes using Google Cloud Speech-to-Text API."""
    try:
        from google.cloud import speech

        if not settings.google_api_key:
            # Fall back to Gemini for transcription if no GCP key
            return await _transcribe_with_gemini(audio_bytes, mime_type)

        client = speech.SpeechClient(
            client_options={"api_key": settings.google_api_key}
        )

        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="video",
        )

        response = client.recognize(config=config, audio=audio)

        transcripts = []
        for result in response.results:
            if result.alternatives:
                transcripts.append(result.alternatives[0].transcript)

        return "\n".join(transcripts)

    except Exception as exc:
        log.warning("media_parser.speech_to_text_failed", error=str(exc))
        return await _transcribe_with_gemini(audio_bytes, mime_type)


async def _transcribe_with_gemini(audio_bytes: bytes, mime_type: str) -> str:
    """Fallback: transcribe audio using Gemini's native audio support (if available)."""
    try:
        import google.genai as genai

        if not settings.google_api_key:
            return "[Transcription unavailable — no API key configured]"

        client = genai.Client(api_key=settings.google_api_key)

        # Gemini 2.0 flash supports audio input in some versions
        # We'll use the audio as a base64-encoded inline data with a prompt
        import base64

        prompt = (
            "Transcribe the following audio content verbatim. "
            "Include all spoken words. If there are multiple speakers, "
            "indicate speaker changes if possible. If you cannot hear audio clearly, "
            "say '[Audio unclear or not available]'."
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(audio_bytes).decode()}},
                    ],
                }
            ],
        )

        transcript = ""
        for part in response.parts:
            if part.text:
                transcript += part.text

        return transcript.strip() or "[No transcription returned]"

    except Exception as exc:
        log.warning("media_parser.gemini_transcription_failed", error=str(exc))
        return "[Transcription failed — audio could not be processed]"


async def _extract_frame_captions(video_path: Path, max_frames: int = 8) -> list[tuple[str, float]]:
    """Extract key frames from video and generate captions using Gemini vision."""
    try:
        from moviepy.editor import VideoFileClip
        from PIL import Image

        clip = VideoFileClip(str(video_path))
        duration = clip.duration

        if duration <= 0:
            clip.close()
            return []

        # Sample frames evenly across the video
        timestamps = [duration * i / max_frames for i in range(max_frames)]

        captions: list[tuple[str, float]] = []

        for ts in timestamps:
            try:
                frame = clip.get_frame(ts)
                image = Image.fromarray(frame)

                # Resize for API efficiency
                max_dim = 512
                if max(image.size) > max_dim:
                    image.thumbnail((max_dim, max_dim), Image.LANCZOS)

                caption = await _caption_image(image, f"frame at {ts:.1f}s")
                if caption:
                    captions.append((caption, ts))

            except Exception as exc:
                log.warning("media_parser.frame_caption_failed", timestamp=ts, error=str(exc))

        clip.close()
        return captions

    except ImportError:
        log.warning("media_parser.moviepy_not_available_for_frames")
        return []
    except Exception as exc:
        log.warning("media_parser.frame_extraction_failed", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------


async def parse_media(
    file_bytes: bytes,
    file_name: str,
    mime_type: str | None = None,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> MediaParseResult:
    """Auto-detect and parse image or video file.

    Args:
        file_bytes: Raw file content.
        file_name: Original filename.
        mime_type: Optional MIME type hint.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between chunks.

    Returns:
        MediaParseResult for the detected media type.
    """
    detected = mime_type or "application/octet-stream"

    # Try to detect from magic bytes
    if detected == "application/octet-stream":
        detected = _detect_media_type(file_bytes, file_name)

    if detected in SUPPORTED_IMAGE_TYPES:
        return await parse_image(file_bytes, file_name, detected, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    elif detected in SUPPORTED_VIDEO_TYPES:
        return await parse_video(file_bytes, file_name, detected, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    else:
        raise MediaParseError(f"Unsupported media type: {detected}")


def _detect_image_type(file_bytes: bytes) -> str | None:
    """Detect image type from magic bytes."""
    import imghdr

    # Try imghdr
    detected = imghdr.what(None, h=file_bytes[:32])
    if detected:
        return f"image/{detected}"

    # Magic bytes
    magic: list[tuple[bytes, str]] = [
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG", "image/png"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"BM", "image/bmp"),
        (b"RIFF", "image/webp"),  # WEBP starts with RIFF....WEBP
        (b"\x49\x49\x2a\x00", "image/tiff"),
        (b"\x4d\x4d\x00\x2a", "image/tiff"),
    ]
    for magic_bytes, mime in magic:
        if file_bytes[: len(magic_bytes)] == magic_bytes:
            # WEBP needs extra check
            if mime == "image/webp" and file_bytes[8:12] != b"WEBP":
                continue
            return mime

    return None


def _detect_media_type(file_bytes: bytes, file_name: str) -> str:
    """Detect if file is image or video from magic bytes."""
    # Check image first
    img_type = _detect_image_type(file_bytes)
    if img_type:
        return img_type

    # Check video magic bytes
    video_magic: list[tuple[bytes, str]] = [
        (b"\x00\x00\x00", "video/quicktime"),  # QT/MOV
        (b"RIFF", "video/webm"),  # WEBM/AVI starts with RIFF
        (b"\x1aE\xdf\xa3", "video/x-matroska"),  # MKV
    ]
    for magic_bytes, mime in video_magic:
        if file_bytes[: len(magic_bytes)] == magic_bytes:
            return mime

    # Extension fallback
    ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    video_exts = {".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo", ".mkv": "video/x-matroska", ".webm": "video/webm"}
    if ext in video_exts:
        return video_exts[ext]

    image_exts = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp", ".tiff": "image/tiff"}
    if ext in image_exts:
        return image_exts[ext]

    return "application/octet-stream"


def _video_extension(file_name: str) -> str:
    """Get video file extension."""
    ext_map = {
        ".mp4": ".mp4",
        ".mov": ".mov",
        ".avi": ".avi",
        ".mkv": ".mkv",
        ".webm": ".webm",
        ".mpeg": ".mpeg",
    }
    ext = "." + file_name.rsplit(".", 1)[-1].lower()
    return ext_map.get(ext, ".mp4")


# ---------------------------------------------------------------------------
# Chunking utility (duplicated from document_parser — kept here for self-containment)
# ---------------------------------------------------------------------------

def _chunk_text(text: str, size: int = 2000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks, respecting sentence boundaries."""
    import re

    if not text or len(text) <= size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        if end < text_len:
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
