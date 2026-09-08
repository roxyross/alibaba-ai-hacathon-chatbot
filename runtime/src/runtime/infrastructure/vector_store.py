"""pgvector-backed document chunk store for RAG.

Provides synchronous and async primitives for:
  - Storing document chunks with their embedding vectors
  - Similarity search using cosine distance (operator <=>)

Schema (run once per database):
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    document_id     TEXT NOT NULL,
    document_name   TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(768) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_chunks_user ON document_chunks(user_id);
  CREATE INDEX IF NOT EXISTS idx_chunks_doc  ON document_chunks(document_id);
  -- IVFFlat index for approximate nearest-neighbor search
  CREATE INDEX IF NOT EXISTS idx_chunks_emb
    ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

Chunking strategy: recursive character splitting at 512 tokens (~2000 chars),
with 50-token overlap to preserve cross-chunk context.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import asyncpg
import structlog

from runtime.config import settings

log = structlog.get_logger()


class VectorStoreError(Exception):
    """Raised when the vector store (pgvector) operation fails."""


# Default embedding dimension for `embedding-001`
_EMBEDDING_DIM = 768

# Chunking constants (approximate token → char ratio of 4)
_CHUNK_SIZE_CHARS = 2000
_CHUNK_OVERLAP_CHARS = 200


@dataclass
class Chunk:
    """A single text chunk with its embedding vector."""
    chunk_id: str
    document_id: str
    document_name: str
    chunk_index: int
    chunk_text: str
    score: float  # cosine similarity (1 = identical)


@dataclass
class SearchResult:
    """Result of a similarity search."""
    chunks: list[Chunk]
    total_candidates: int


# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    """Get or create the asyncpg connection pool."""
    global _pool
    if _pool is None:
        url = settings.database_url
        if not url:
            raise VectorStoreError("DATABASE_URL is not configured for vector store")
        _pool = await asyncpg.create_pool(
            url,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        log.info("vector_store.pool.created")
    return _pool


async def close_pool() -> None:
    """Close the connection pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("vector_store.pool.closed")


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    document_id     TEXT NOT NULL,
    document_name   TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(%s) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON document_chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc  ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_emb
    ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""


async def ensure_schema() -> None:
    """Create the document_chunks table and indexes if they don't exist."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL, _EMBEDDING_DIM)
    log.info("vector_store.schema.ready")


# ---------------------------------------------------------------------------
# Chunking utilities
# ---------------------------------------------------------------------------

def chunk_text(text: str, size: int = _CHUNK_SIZE_CHARS, overlap: int = _CHUNK_OVERLAP_CHARS) -> list[str]:
    """Split text into overlapping chunks of approximately `size` chars.

    Uses recursive character splitting — respects sentence/paragraph boundaries
    when possible to keep chunks semantically coherent.
    """
    if not text or len(text) <= size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        # Try to break at a sentence or paragraph boundary
        if end < text_len:
            for punct in (". ", ".\n", "!\n", "?\n", "\n\n"):
                last_punct = text.rfind(punct, start, end + 20)
                if last_punct > start:
                    end = last_punct + len(punct)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if start <= chunks[-1].find(chunks[-1][:20]) if chunks else 0:
            start = end

    return chunks


# ---------------------------------------------------------------------------
# Store operations
# ---------------------------------------------------------------------------

async def store_chunks(
    user_id: str,
    document_id: str,
    document_name: str,
    text: str,
    embeddings: list[list[float]],
) -> list[str]:
    """Chunk `text`, associate with `embeddings`, and store in pgvector.

    Args:
        user_id: Owner of the document (for per-user isolation).
        document_id: Stable identifier for the document (e.g. UUID from upload).
        document_name: Human-readable document name.
        text: Full raw text of the document.
        embeddings: One embedding vector per chunk (from `embed_texts`).

    Returns:
        List of chunk IDs (UUIDs) stored.
    """
    chunks = chunk_text(text)
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"got {len(embeddings)} embeddings for {len(chunks)} chunks — "
            "these must match 1:1"
        )

    pool = await _get_pool()
    chunk_ids: list[str] = []

    async with pool.acquire() as conn:
        for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO document_chunks
                    (id, user_id, document_id, document_name, chunk_index, chunk_text, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO NOTHING
                """,
                chunk_id,
                user_id,
                document_id,
                document_name,
                i,
                chunk_text,
                embedding,
            )
            chunk_ids.append(chunk_id)

    log.info(
        "vector_store.chunks.stored",
        user_id=user_id,
        document_id=document_id,
        chunk_count=len(chunk_ids),
    )
    return chunk_ids


async def delete_document(user_id: str, document_id: str) -> int:
    """Delete all chunks for a document. Returns the number of chunks deleted."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM document_chunks WHERE user_id = $1 AND document_id = $2",
            user_id,
            document_id,
        )
    # Result is like "DELETE 12"
    count = int(result.split()[-1]) if result else 0
    log.info(
        "vector_store.document.deleted",
        user_id=user_id,
        document_id=document_id,
        chunks_deleted=count,
    )
    return count


# ---------------------------------------------------------------------------
# Retrieval / similarity search
# ---------------------------------------------------------------------------

async def search_chunks(
    user_id: str,
    query_embedding: list[float],
    top_k: int = 8,
    min_score: float = 0.0,
    document_ids: list[str] | None = None,
) -> SearchResult:
    """Find the most similar chunks to `query_embedding` for `user_id`.

    Uses cosine distance (`<=>`) via pgvector's IVFFlat index for
    approximate nearest-neighbor search.

    Args:
        user_id: Restrict search to this user's documents.
        query_embedding: Unit-normalized embedding from the user's query.
        top_k: Maximum number of chunks to return.
        min_score: Drop chunks with cosine similarity below this threshold.
        document_ids: If set, restrict search to these document IDs only.

    Returns:
        SearchResult with chunks sorted by descending similarity score.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if document_ids:
            rows = await conn.fetch(
                f"""
                SELECT id, document_id, document_name, chunk_index, chunk_text,
                       1 - (embedding <=> $1::vector) AS score
                FROM document_chunks
                WHERE user_id = $2
                  AND document_id = ANY($3)
                  AND (1 - (embedding <=> $1::vector)) >= $4
                ORDER BY embedding <=> $1::vector
                LIMIT $5
                """,
                query_embedding,
                user_id,
                document_ids,
                min_score,
                top_k,
            )
            total = await conn.fetchval(
                """
                SELECT COUNT(*) FROM document_chunks
                WHERE user_id = $1 AND document_id = ANY($2)
                """,
                user_id,
                document_ids,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, document_id, document_name, chunk_index, chunk_text,
                       1 - (embedding <=> $1::vector) AS score
                FROM document_chunks
                WHERE user_id = $2
                  AND (1 - (embedding <=> $1::vector)) >= $3
                ORDER BY embedding <=> $1::vector
                LIMIT $4
                """,
                query_embedding,
                user_id,
                min_score,
                top_k,
            )
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks WHERE user_id = $1",
                user_id,
            )

    chunks = [
        Chunk(
            chunk_id=str(row["id"]),
            document_id=str(row["document_id"]),
            document_name=str(row["document_name"]),
            chunk_index=int(row["chunk_index"]),
            chunk_text=str(row["chunk_text"]),
            score=float(row["score"]),
        )
        for row in rows
    ]

    log.debug(
        "vector_store.search.done",
        user_id=user_id,
        top_k=top_k,
        total_candidates=total,
        returned=len(chunks),
    )
    return SearchResult(chunks=chunks, total_candidates=total or 0)


async def list_user_documents(user_id: str) -> list[dict]:
    """List all documents stored for a user, with chunk counts."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT document_id, document_name, COUNT(*) AS chunk_count, MAX(created_at) AS last_ingested
            FROM document_chunks
            WHERE user_id = $1
            GROUP BY document_id, document_name
            ORDER BY MAX(created_at) DESC
            """,
            user_id,
        )
    return [
        {
            "document_id": str(r["document_id"]),
            "document_name": str(r["document_name"]),
            "chunk_count": int(r["chunk_count"]),
            "last_ingested": r["last_ingested"].isoformat() if r["last_ingested"] else None,
        }
        for r in rows
    ]
