"""Knowledge Vault Document and Chunk ORM models.

Maps to `documents` and `document_chunks` tables for Phase 5 Knowledge Vault
and Vector Memory subsystem.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DocumentRecord(Base):
    """Document metadata and indexing record for Knowledge Vault."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    folder: Mapped[str] = mapped_column(String(128), default="Default", nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(128), default="application/octet-stream", nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_documents_user_folder", "user_id", "folder"),
        Index("idx_documents_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        tag_list: list[str] = []
        if self.tags:
            tag_list = [t.strip() for t in self.tags.split(",") if t.strip()]

        created_str: str | None = None
        if self.created_at is not None:
            created_str = self.created_at.isoformat()

        updated_str: str | None = None
        if self.updated_at is not None:
            updated_str = self.updated_at.isoformat()

        return {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "folder": self.folder,
            "file_size_bytes": self.file_size_bytes,
            "mime_type": self.mime_type,
            "chunk_count": self.chunk_count,
            "summary": self.summary,
            "status": self.status,
            "tags": tag_list,
            "file_path": self.file_path,
            "created_at": created_str,
            "updated_at": updated_str,
        }


class DocumentChunkRecord(Base):
    """Vector chunk and dense embedding record for document search."""

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    document_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    __table_args__ = (
        Index("idx_doc_chunks_user_doc", "user_id", "document_id"),
        Index("idx_doc_chunks_doc_index", "document_id", "chunk_index"),
    )

    def get_embedding(self) -> list[float]:
        """Deserialize embedding vector from JSON text."""
        if not self.embedding_json:
            empty_emb: list[float] = []
            return empty_emb
        try:
            val = json.loads(self.embedding_json)
            if isinstance(val, list):
                return [float(x) for x in val]
        except Exception:
            pass
        fallback_emb: list[float] = []
        return fallback_emb

    def set_embedding(self, emb: list[float]) -> None:
        """Serialize embedding vector to JSON text."""
        self.embedding_json = json.dumps(emb)

    def to_dict(self) -> dict[str, Any]:
        created_str: str | None = None
        if self.created_at is not None:
            created_str = self.created_at.isoformat()

        return {
            "id": self.id,
            "document_id": self.document_id,
            "user_id": self.user_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "token_count": self.token_count,
            "page_number": self.page_number,
            "section": self.section,
            "has_embedding": bool(self.embedding_json),
            "created_at": created_str,
        }
