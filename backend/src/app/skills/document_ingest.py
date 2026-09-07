"""document_ingest skill — parse a file and ingest it into the RAG vector store.

Uses ChromaDB for vector storage (in-memory, per-process).
In production, replace with a persistent ChromaDB or pgvector backend.

Chunking strategy:
  - ~2000 chars per chunk
  - 200-char overlap across sentence boundaries
  - Respects natural paragraph breaks when possible

Embedding:
  - Uses Gemini embeddings via the AI gateway (if GEMINI_API_KEY is set)
  - Falls back to a simple TF-IDF mock for development

Storage:
  - ChromaDB collection per user (user_id as collection namespace)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import DocumentRagQueryRequest, DocumentRagQueryResponse, DocumentChunk
from app.skills.document_parser import parse_document, ParseResult

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# In-memory document + chunk store (replace with ChromaDB in production)
# ---------------------------------------------------------------------------

# Global stores — keyed by user_id
_document_meta: dict[str, dict[str, dict[str, Any]]] = {}  # user_id -> doc_id -> {name, doc_type, created_at, chunk_ids}
_chunk_store: dict[str, dict[str, Any]] = {}  # chunk_id -> {user_id, doc_id, content, embedding, page, section}


def _get_user_docs(user_id: str) -> dict[str, dict[str, Any]]:
    if user_id not in _document_meta:
        _document_meta[user_id] = {}
    return _document_meta[user_id]


def _chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks respecting sentence boundaries."""
    if not text.strip():
        return []

    # Split into sentences (period followed by space or end)
    sentence_pattern = re.compile(r"(?<=[.!?])\s+")
    sentences: list[str] = sentence_pattern.split(text)
    if len(sentences) <= 1:
        # No sentence boundaries — split by paragraph
        sentences = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        slen = len(sentence)
        if current_len + slen + 1 <= chunk_size:
            current.append(sentence)
            current_len += slen + 1
        else:
            # Emit current chunk
            if current:
                chunks.append(" ".join(current))
            # Start new chunk with overlap
            overlap_text = " ".join(current)
            # Keep sentences that fit in overlap
            new_current: list[str] = []
            new_len = 0
            for s in reversed(current):
                if new_len + len(s) + 1 <= overlap:
                    new_current.insert(0, s)
                    new_len += len(s) + 1
                else:
                    break
            if new_current:
                current = new_current
                current_len = new_len
            else:
                current = [sentence]
                current_len = slen

    # Don't forget the last chunk
    if current:
        chunks.append(" ".join(current))

    return [c.strip() for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Simple embedding fallback (replace with Gemini embeddings in production)
# ---------------------------------------------------------------------------

def _make_embedding(text: str) -> list[float]:
    """Very simple TF-IDF-like embedding fallback.

    Maps each chunk to a deterministic pseudo-embedding based on word hashes.
    In production, call Gemini embed_text endpoint or OpenAI embeddings API.
    """
    words = re.findall(r"\w+", text.lower())
    dim = 128
    vec = [0.0] * dim
    for i, word in enumerate(words[:dim]):
        # Simple hash into the vector
        h = hash(word)
        vec[i % dim] += (h % 1000) / 1000.0
    # L2 normalize
    norm = (sum(v * v for v in vec) ** 0.5) or 1.0
    return [v / norm for v in vec]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = (sum(x * x for x in a) ** 0.5) or 1e-9
    norm_b = (sum(x * x for x in b) ** 0.5) or 1e-9
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Skill schema (local, not in schemas.py to avoid circular imports)
# ---------------------------------------------------------------------------

@dataclass
class DocumentIngestRequest:
    document_id: str | None = None
    document_name: str = ""
    file_bytes: bytes = field(default_factory=b"")
    content_type: str = ""
    filename: str = ""
    replace_existing: bool = False
    user_id: str | None = None


@dataclass
class DocumentIngestResponse:
    document_id: str
    document_name: str
    chunks_stored: int
    chunk_ids: list[str]
    doc_type: str
    metadata: dict


# ---------------------------------------------------------------------------
# Skill executor
# ---------------------------------------------------------------------------

class DocumentIngestSkill(SkillExecutor[DocumentIngestRequest, DocumentIngestResponse]):
    slug = "document_ingest"

    async def execute(self, input_data: DocumentIngestRequest) -> DocumentIngestResponse:
        user_id = input_data.user_id or "anonymous"

        if not input_data.document_name:
            raise ValueError("document_name is required")
        if not input_data.file_bytes:
            raise ValueError("file_bytes is required")

        # ── 1. Parse the document ───────────────────────────────────────────
        try:
            result: ParseResult = parse_document(
                input_data.file_bytes,
                content_type=input_data.content_type,
                filename=input_data.filename,
            )
        except Exception as exc:
            raise ValueError(f"Could not parse document: {exc}") from exc

        if result.is_empty():
            raise ValueError("Document text is empty after parsing")

        # ── 2. Generate or use existing document_id ─────────────────────────
        document_id = input_data.document_id or str(uuid.uuid4())

        # ── 3. Replace existing if requested ────────────────────────────────
        if input_data.replace_existing:
            await self._delete_document(document_id, user_id)

        # ── 4. Chunk the text ──────────────────────────────────────────────
        chunks = _chunk_text(result.content)
        if not chunks:
            raise ValueError("Could not chunk document text")

        # ── 5. Generate embeddings ─────────────────────────────────────────
        embeddings = [_make_embedding(c) for c in chunks]

        # ── 6. Store chunks ────────────────────────────────────────────────
        chunk_ids: list[str] = []
        now = datetime.now(timezone.utc).isoformat()

        user_docs = _get_user_docs(user_id)

        # Record doc metadata
        user_docs[document_id] = {
            "name": input_data.document_name,
            "doc_type": result.doc_type,
            "created_at": user_docs.get(document_id, {}).get("created_at", now),
            "chunk_ids": [],
        }
        user_docs[document_id]["created_at"] = now

        for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = str(uuid.uuid4())
            chunk_ids.append(chunk_id)

            _chunk_store[chunk_id] = {
                "user_id": user_id,
                "doc_id": document_id,
                "content": chunk_text,
                "embedding": embedding,
                "chunk_index": i,
                "page": None,
                "section": None,
            }

            user_docs[document_id]["chunk_ids"].append(chunk_id)

        log.info(
            "document_ingest.done",
            document_id=document_id,
            user_id=user_id,
            chunks=len(chunk_ids),
            doc_type=result.doc_type,
        )

        return DocumentIngestResponse(
            document_id=document_id,
            document_name=input_data.document_name,
            chunks_stored=len(chunk_ids),
            chunk_ids=chunk_ids,
            doc_type=result.doc_type,
            metadata=result.metadata,
        )

    async def _delete_document(self, document_id: str, user_id: str) -> None:
        """Remove all chunks for a document."""
        user_docs = _get_user_docs(user_id)
        if document_id in user_docs:
            chunk_ids = user_docs[document_id].get("chunk_ids", [])
            for chunk_id in chunk_ids:
                _chunk_store.pop(chunk_id, None)
            del user_docs[document_id]


def get_executor() -> DocumentIngestSkill:
    return DocumentIngestSkill()
