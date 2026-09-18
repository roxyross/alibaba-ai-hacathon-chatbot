"""DocumentRepository — SQLAlchemy async with in-memory fallback for Knowledge Vault."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, func, select

from app.db import get_session_factory
from app.models.document_vault import DocumentRecord

log = structlog.get_logger()


@dataclass
class _MemDocument:
    id: str
    user_id: str
    filename: str
    folder: str
    file_size_bytes: int
    mime_type: str
    file_path: str | None
    extracted_text: str | None
    created_at: datetime


# Module-level in-memory fallback store keyed by user_id
_MEM_DOCUMENTS: dict[str, list[_MemDocument]] = {}


class DocumentRepository:
    """Persist, list, and delete documents for the Knowledge Vault.

    Interacts with PostgreSQL `documents` table via SQLAlchemy async session,
    with transparent in-memory fallback if the database is unreachable.
    """

    _mem: dict[str, list[_MemDocument]] = _MEM_DOCUMENTS

    def __init__(self) -> None:
        self._mem = _MEM_DOCUMENTS

    async def create(
        self,
        user_id: str,
        filename: str,
        document_id: str | None = None,
        folder: str = "Default",
        file_size_bytes: int = 0,
        mime_type: str = "application/octet-stream",
        file_path: str | None = None,
        extracted_text: str | None = None,
    ) -> DocumentRecord | _MemDocument:
        """Create a new document record scoped to user_id."""
        doc_id = document_id or str(uuid.uuid4())
        factory = get_session_factory()
        if factory is None:
            mem_doc = _MemDocument(
                id=doc_id,
                user_id=user_id,
                filename=filename,
                folder=folder,
                file_size_bytes=file_size_bytes,
                mime_type=mime_type,
                file_path=file_path,
                extracted_text=extracted_text,
                created_at=datetime.now(UTC),
            )
            self._mem.setdefault(user_id, []).insert(0, mem_doc)
            return mem_doc

        try:
            async with factory() as session:
                record = DocumentRecord(
                    id=doc_id,
                    user_id=user_id,
                    filename=filename,
                    folder=folder,
                    file_size_bytes=file_size_bytes,
                    mime_type=mime_type,
                    file_path=file_path,
                    extracted_text=extracted_text,
                )
                session.add(record)
                await session.commit()
                await session.refresh(record)
                return record
        except Exception as exc:
            log.warning("document_repo.db_create_failed_fallback", user_id=user_id, error=str(exc))
            mem_doc = _MemDocument(
                id=doc_id,
                user_id=user_id,
                filename=filename,
                folder=folder,
                file_size_bytes=file_size_bytes,
                mime_type=mime_type,
                file_path=file_path,
                extracted_text=extracted_text,
                created_at=datetime.now(UTC),
            )
            self._mem.setdefault(user_id, []).insert(0, mem_doc)
            return mem_doc

    async def list_for_user(self, user_id: str) -> list[DocumentRecord | _MemDocument]:
        """List all documents belonging to user_id, ordered by creation descending."""
        factory = get_session_factory()
        if factory is None:
            return list(self._mem.get(user_id, []))

        try:
            async with factory() as session:
                stmt = (
                    select(DocumentRecord)
                    .where(DocumentRecord.user_id == user_id)
                    .order_by(DocumentRecord.created_at.desc())
                )
                res = await session.execute(stmt)
                rows: list[DocumentRecord | _MemDocument] = list(res.scalars().all())
                # Merge in-memory if DB returned empty but mem has items
                if not rows and user_id in self._mem:
                    return list(self._mem.get(user_id, []))
                return rows
        except Exception as exc:
            log.warning("document_repo.db_list_failed_fallback", user_id=user_id, error=str(exc))
            return list(self._mem.get(user_id, []))

    async def get_by_id(self, document_id: str, user_id: str) -> DocumentRecord | _MemDocument | None:
        """Fetch a document by ID with strict tenant check."""
        factory = get_session_factory()
        if factory is None:
            for doc in self._mem.get(user_id, []):
                if doc.id == document_id:
                    return doc
            return None

        try:
            async with factory() as session:
                stmt = select(DocumentRecord).where(
                    DocumentRecord.id == document_id,
                    DocumentRecord.user_id == user_id,
                )
                res = await session.execute(stmt)
                db_doc: DocumentRecord | None = res.scalar_one_or_none()
                if db_doc is not None:
                    return db_doc
                # Fallback to mem
                for mdoc in self._mem.get(user_id, []):
                    if mdoc.id == document_id:
                        return mdoc
                return None
        except Exception as exc:
            log.warning("document_repo.db_get_failed_fallback", document_id=document_id, user_id=user_id, error=str(exc))
            for mdoc in self._mem.get(user_id, []):
                if mdoc.id == document_id:
                    return mdoc
            return None

    async def delete(self, document_id: str, user_id: str) -> bool:
        """Delete a document by ID with strict tenant ownership check."""
        deleted = False
        # Remove from in-memory fallback
        if user_id in self._mem:
            initial_len = len(self._mem[user_id])
            self._mem[user_id] = [d for d in self._mem[user_id] if d.id != document_id]
            if len(self._mem[user_id]) < initial_len:
                deleted = True

        factory = get_session_factory()
        if factory is None:
            return deleted

        try:
            async with factory() as session:
                stmt = delete(DocumentRecord).where(
                    DocumentRecord.id == document_id,
                    DocumentRecord.user_id == user_id,
                )
                res = await session.execute(stmt)
                await session.commit()
                rowcount = getattr(res, "rowcount", None) or 0
                if rowcount > 0:
                    deleted = True
                return deleted
        except Exception as exc:
            log.warning("document_repo.db_delete_failed", document_id=document_id, user_id=user_id, error=str(exc))
            return deleted

    async def count_for_user(self, user_id: str) -> int:
        """Return the total number of documents owned by user_id."""
        factory = get_session_factory()
        if factory is None:
            return len(self._mem.get(user_id, []))

        try:
            async with factory() as session:
                stmt = select(func.count(DocumentRecord.id)).where(DocumentRecord.user_id == user_id)
                res = await session.execute(stmt)
                count = res.scalar() or 0
                return max(count, len(self._mem.get(user_id, [])))
        except Exception as exc:
            log.warning("document_repo.db_count_failed", user_id=user_id, error=str(exc))
            return len(self._mem.get(user_id, []))
