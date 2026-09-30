"""Knowledge Vault & Vector Memory Service implementation (Phase 5).

Provides complete document lifecycle management, hierarchical chunking,
dense vector embeddings, hybrid RRF search, and central ToolRegistry integration.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, func, select

from app.db import get_session_factory
from app.models.document_vault import DocumentChunkRecord, DocumentRecord
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource
from app.vault.chunker import RecursiveChunker
from app.vault.embeddings import EmbeddingEngine
from app.vault.schemas import (
    VaultChunkItem,
    VaultDocumentListResponse,
    VaultDocumentResponse,
    VaultSearchResponse,
    VaultSearchResultItem,
    VaultStatsResponse,
)

log = structlog.get_logger()


class VaultService:
    """Enterprise Knowledge Vault and Vector Memory service with hybrid search."""

    _instance: VaultService | None = None

    def __init__(self) -> None:
        self._tool_registry = ToolRegistry.get_instance()
        self._chunker = RecursiveChunker(chunk_size=1200, chunk_overlap=150)
        self._embedding_engine = EmbeddingEngine

        # In-memory stores for resilience and isolated test runs
        self._mem_documents: dict[str, dict[str, Any]] = {}  # doc_id -> doc_dict
        self._mem_chunks: dict[str, list[dict[str, Any]]] = {}  # doc_id -> list of chunk_dicts

        self.register_vault_tools()

    @classmethod
    def get_instance(cls) -> VaultService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -------------------------------------------------------------------------
    # Ingestion & Note Creation
    # -------------------------------------------------------------------------

    async def ingest_document(
        self,
        user_id: str,
        filename: str,
        content: str,
        folder: str = "General",
        mime_type: str = "text/plain",
        file_path: str | None = None,
        tags: list[str] | None = None,
    ) -> VaultDocumentResponse:
        """Parse, chunk, embed, and persist a document into the Knowledge Vault."""
        doc_id = str(uuid.uuid4())
        clean_content = content.strip()
        tags_list = tags or []
        tags_str = ",".join(tags_list) if tags_list else None
        now_dt = datetime.now(UTC)
        now_str = now_dt.isoformat()
        size_bytes = len(clean_content.encode("utf-8"))

        # 1. Generate structural chunks
        chunks = self._chunker.split_text(clean_content, default_section=filename)
        chunk_items: list[VaultChunkItem] = []
        chunk_dicts: list[dict[str, Any]] = []

        for ch in chunks:
            chunk_id = str(uuid.uuid4())
            emb = self._embedding_engine.get_embedding(ch.content)
            ch_dict: dict[str, Any] = {
                "id": chunk_id,
                "document_id": doc_id,
                "user_id": user_id,
                "chunk_index": ch.index,
                "content": ch.content,
                "embedding": emb,
                "token_count": ch.token_count,
                "page_number": ch.page_number,
                "section": ch.section,
                "created_at": now_str,
            }
            chunk_dicts.append(ch_dict)

            chunk_items.append(
                VaultChunkItem(
                    id=chunk_id,
                    document_id=doc_id,
                    chunk_index=ch.index,
                    content=ch.content,
                    token_count=ch.token_count,
                    page_number=ch.page_number,
                    section=ch.section,
                    has_embedding=True,
                    created_at=now_str,
                )
            )

        # 2. Extract brief summary
        summary = (clean_content[:280] + "...") if len(clean_content) > 280 else clean_content

        # 3. Store in in-memory cache
        doc_dict: dict[str, Any] = {
            "id": doc_id,
            "user_id": user_id,
            "filename": filename,
            "folder": folder,
            "file_size_bytes": size_bytes,
            "mime_type": mime_type,
            "chunk_count": len(chunks),
            "summary": summary,
            "status": "ready",
            "tags": tags_list,
            "file_path": file_path,
            "created_at": now_str,
            "updated_at": now_str,
        }
        self._mem_documents[doc_id] = doc_dict
        self._mem_chunks[doc_id] = chunk_dicts

        # 4. Persist to database if available
        session_factory = get_session_factory()
        if session_factory is not None:
            try:
                async with session_factory() as session:
                    db_doc = DocumentRecord(
                        id=doc_id,
                        user_id=user_id,
                        filename=filename,
                        folder=folder,
                        file_size_bytes=size_bytes,
                        mime_type=mime_type,
                        file_path=file_path,
                        extracted_text=clean_content,
                        chunk_count=len(chunks),
                        summary=summary,
                        status="ready",
                        tags=tags_str,
                        created_at=now_dt,
                        updated_at=now_dt,
                    )
                    session.add(db_doc)

                    for ch_data in chunk_dicts:
                        db_chunk = DocumentChunkRecord(
                            id=ch_data["id"],
                            document_id=doc_id,
                            user_id=user_id,
                            chunk_index=ch_data["chunk_index"],
                            content=ch_data["content"],
                            token_count=ch_data["token_count"],
                            page_number=ch_data["page_number"],
                            section=ch_data["section"],
                            created_at=now_dt,
                        )
                        db_chunk.set_embedding(ch_data["embedding"])
                        session.add(db_chunk)

                    await session.commit()
            except Exception as exc:
                log.warning("vault_service.db_ingest_failed", error=str(exc))

        return VaultDocumentResponse(
            id=doc_id,
            user_id=user_id,
            filename=filename,
            folder=folder,
            file_size_bytes=size_bytes,
            mime_type=mime_type,
            chunk_count=len(chunks),
            summary=summary,
            status="ready",
            tags=tags_list,
            file_path=file_path,
            created_at=now_str,
            updated_at=now_str,
            chunks=chunk_items,
        )

    async def create_note(
        self,
        user_id: str,
        title: str,
        content: str,
        folder: str = "Notes",
        tags: list[str] | None = None,
    ) -> VaultDocumentResponse:
        """Create a markdown knowledge note directly in the vault."""
        filename = f"{title.strip()}.md"
        return await self.ingest_document(
            user_id=user_id,
            filename=filename,
            content=content,
            folder=folder,
            mime_type="text/markdown",
            tags=tags or ["note", "personal"],
        )

    # -------------------------------------------------------------------------
    # Hybrid Vector & Lexical Search
    # -------------------------------------------------------------------------

    async def search(
        self,
        user_id: str,
        query: str,
        folder: str | None = None,
        document_ids: list[str] | None = None,
        top_k: int = 5,
        min_score: float = 0.0,
        hybrid: bool = True,
    ) -> VaultSearchResponse:
        """Execute high-precision hybrid semantic vector and keyword search."""
        start_time = time.perf_counter()
        clean_query = query.strip()
        query_vec = self._embedding_engine.get_embedding(clean_query)

        # 1. Gather candidate chunks for this user
        candidate_chunks: list[dict[str, Any]] = []

        # From in-memory cache
        for doc_id, doc in self._mem_documents.items():
            if doc.get("user_id") != user_id:
                continue
            if folder and doc.get("folder", "").lower() != folder.lower():
                continue
            if document_ids and doc_id not in document_ids:
                continue

            for ch in self._mem_chunks.get(doc_id, []):
                chunk_entry: dict[str, Any] = dict(ch)
                chunk_entry["document_name"] = doc.get("filename", "Untitled")
                chunk_entry["folder"] = doc.get("folder", "General")
                candidate_chunks.append(chunk_entry)

        # Merge with database chunks if available and not in memory
        session_factory = get_session_factory()
        if session_factory is not None:
            try:
                async with session_factory() as session:
                    stmt = (
                        select(DocumentChunkRecord, DocumentRecord.filename, DocumentRecord.folder)
                        .join(DocumentRecord, DocumentChunkRecord.document_id == DocumentRecord.id)
                        .where(DocumentChunkRecord.user_id == user_id)
                    )
                    if folder:
                        stmt = stmt.where(DocumentRecord.folder == folder)
                    if document_ids:
                        stmt = stmt.where(DocumentChunkRecord.document_id.in_(document_ids))

                    res = await session.execute(stmt)
                    rows = res.all()
                    existing_chunk_ids = {c["id"] for c in candidate_chunks}

                    for chunk_row, doc_fname, doc_folder in rows:
                        if chunk_row.id not in existing_chunk_ids:
                            candidate_chunks.append({
                                "id": chunk_row.id,
                                "document_id": chunk_row.document_id,
                                "document_name": doc_fname,
                                "folder": doc_folder,
                                "chunk_index": chunk_row.chunk_index,
                                "content": chunk_row.content,
                                "embedding": chunk_row.get_embedding(),
                                "token_count": chunk_row.token_count,
                                "page_number": chunk_row.page_number,
                                "section": chunk_row.section,
                            })
            except Exception as exc:
                log.warning("vault_service.db_search_fetch_failed", error=str(exc))

        if not candidate_chunks:
            empty_results: list[VaultSearchResultItem] = []
            return VaultSearchResponse(
                query=clean_query,
                results=empty_results,
                total_matches=0,
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        # 2. Score candidate chunks
        scored_candidates: list[tuple[float, float, float, dict[str, Any]]] = []
        for ch in candidate_chunks:
            c_text = ch.get("content", "")
            c_vec = ch.get("embedding", [])
            comb_score, d_score, l_score = self._embedding_engine.hybrid_score(
                clean_query, c_text, query_vec, c_vec, hybrid=hybrid
            )
            if comb_score >= min_score:
                scored_candidates.append((comb_score, d_score, l_score, ch))

        # 3. Sort by highest score first
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[:top_k]

        results: list[VaultSearchResultItem] = [
            VaultSearchResultItem(
                chunk_id=ch["id"],
                document_id=ch["document_id"],
                document_name=ch.get("document_name", "Untitled"),
                folder=ch.get("folder", "General"),
                chunk_index=ch.get("chunk_index", 0),
                content=ch.get("content", ""),
                score=round(c_score, 4),
                dense_score=round(d_score, 4),
                lexical_score=round(l_score, 4),
                section=ch.get("section"),
                page_number=ch.get("page_number"),
            )
            for c_score, d_score, l_score, ch in top_candidates
        ]

        duration = round((time.perf_counter() - start_time) * 1000, 2)
        return VaultSearchResponse(
            query=clean_query,
            results=results,
            total_matches=len(scored_candidates),
            execution_time_ms=duration,
        )

    # -------------------------------------------------------------------------
    # Document Retrieval & Listing
    # -------------------------------------------------------------------------

    async def get_document(self, user_id: str, document_id: str) -> VaultDocumentResponse | None:
        """Fetch complete document metadata and all constituent chunks."""
        # Check in-memory first
        doc_data = self._mem_documents.get(document_id)
        if doc_data and doc_data.get("user_id") == user_id:
            chunks = self._mem_chunks.get(document_id, [])
            chunk_items = [
                VaultChunkItem(
                    id=c["id"],
                    document_id=document_id,
                    chunk_index=c.get("chunk_index", 0),
                    content=c.get("content", ""),
                    token_count=c.get("token_count", 0),
                    page_number=c.get("page_number"),
                    section=c.get("section"),
                    has_embedding=bool(c.get("embedding")),
                    created_at=c.get("created_at"),
                )
                for c in chunks
            ]
            return VaultDocumentResponse(
                id=doc_data["id"],
                user_id=user_id,
                filename=doc_data.get("filename", "Untitled"),
                folder=doc_data.get("folder", "General"),
                file_size_bytes=doc_data.get("file_size_bytes", 0),
                mime_type=doc_data.get("mime_type", "text/plain"),
                chunk_count=doc_data.get("chunk_count", len(chunk_items)),
                summary=doc_data.get("summary"),
                status=doc_data.get("status", "ready"),
                tags=doc_data.get("tags", []),
                file_path=doc_data.get("file_path"),
                created_at=doc_data.get("created_at"),
                updated_at=doc_data.get("updated_at"),
                chunks=chunk_items,
            )

        # Database lookup
        session_factory = get_session_factory()
        if session_factory is not None:
            try:
                async with session_factory() as session:
                    stmt = select(DocumentRecord).where(
                        DocumentRecord.id == document_id,
                        DocumentRecord.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    db_doc = res.scalars().first()
                    if db_doc:
                        ch_stmt = (
                            select(DocumentChunkRecord)
                            .where(DocumentChunkRecord.document_id == document_id)
                            .order_by(DocumentChunkRecord.chunk_index.asc())
                        )
                        ch_res = await session.execute(ch_stmt)
                        db_chunks = ch_res.scalars().all()
                        chunk_items = [
                            VaultChunkItem(
                                id=c.id,
                                document_id=c.document_id,
                                chunk_index=c.chunk_index,
                                content=c.content,
                                token_count=c.token_count,
                                page_number=c.page_number,
                                section=c.section,
                                has_embedding=bool(c.embedding_json),
                                created_at=c.created_at.isoformat() if c.created_at else None,
                            )
                            for c in db_chunks
                        ]
                        doc_dict = db_doc.to_dict()
                        return VaultDocumentResponse(
                            id=doc_dict["id"],
                            user_id=user_id,
                            filename=doc_dict["filename"],
                            folder=doc_dict["folder"],
                            file_size_bytes=doc_dict["file_size_bytes"],
                            mime_type=doc_dict["mime_type"],
                            chunk_count=doc_dict["chunk_count"],
                            summary=doc_dict["summary"],
                            status=doc_dict["status"],
                            tags=doc_dict["tags"],
                            file_path=doc_dict["file_path"],
                            created_at=doc_dict["created_at"],
                            updated_at=doc_dict["updated_at"],
                            chunks=chunk_items,
                        )
            except Exception as exc:
                log.warning("vault_service.db_get_doc_failed", error=str(exc))

        return None

    async def list_documents(
        self,
        user_id: str,
        folder: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> VaultDocumentListResponse:
        """List documents owned by user with optional folder and text filtering."""
        docs_map: dict[str, dict[str, Any]] = {}

        # 1. From database
        session_factory = get_session_factory()
        if session_factory is not None:
            try:
                async with session_factory() as session:
                    stmt = select(DocumentRecord).where(DocumentRecord.user_id == user_id)
                    if folder and folder.lower() != "all":
                        stmt = stmt.where(DocumentRecord.folder.ilike(folder))
                    if query:
                        stmt = stmt.where(DocumentRecord.filename.ilike(f"%{query}%"))
                    stmt = stmt.order_by(DocumentRecord.created_at.desc())

                    res = await session.execute(stmt)
                    for r in res.scalars().all():
                        docs_map[r.id] = r.to_dict()
            except Exception as exc:
                log.warning("vault_service.db_list_docs_failed", error=str(exc))

        # 2. Merge with in-memory fallback
        for doc_id, doc in self._mem_documents.items():
            if doc.get("user_id") != user_id:
                continue
            if folder and folder.lower() != "all" and doc.get("folder", "").lower() != folder.lower():
                continue
            if query and query.lower() not in doc.get("filename", "").lower():
                continue
            if doc_id not in docs_map:
                docs_map[doc_id] = dict(doc)

        sorted_docs = sorted(
            docs_map.values(),
            key=lambda x: x.get("created_at") or "",
            reverse=True,
        )

        total = len(sorted_docs)
        paged = sorted_docs[offset : offset + limit]

        doc_items: list[VaultDocumentResponse] = [
            VaultDocumentResponse(
                id=d["id"],
                user_id=d["user_id"],
                filename=d.get("filename", "Untitled"),
                folder=d.get("folder", "General"),
                file_size_bytes=d.get("file_size_bytes", 0),
                mime_type=d.get("mime_type", "text/plain"),
                chunk_count=d.get("chunk_count", 0),
                summary=d.get("summary"),
                status=d.get("status", "ready"),
                tags=d.get("tags", []),
                file_path=d.get("file_path"),
                created_at=d.get("created_at"),
                updated_at=d.get("updated_at"),
            )
            for d in paged
        ]

        return VaultDocumentListResponse(documents=doc_items, total=total)

    # -------------------------------------------------------------------------
    # Deletion & Stats
    # -------------------------------------------------------------------------

    async def delete_document(self, user_id: str, document_id: str) -> bool:
        """Permanently delete a document and all its constituent vector chunks."""
        deleted = False

        # In-memory purge
        if document_id in self._mem_documents and self._mem_documents[document_id].get("user_id") == user_id:
            del self._mem_documents[document_id]
            self._mem_chunks.pop(document_id, None)
            deleted = True

        # Database purge
        session_factory = get_session_factory()
        if session_factory is not None:
            try:
                async with session_factory() as session:
                    # Chunks first
                    ch_del = delete(DocumentChunkRecord).where(
                        DocumentChunkRecord.document_id == document_id,
                        DocumentChunkRecord.user_id == user_id,
                    )
                    await session.execute(ch_del)

                    # Document
                    doc_del = delete(DocumentRecord).where(
                        DocumentRecord.id == document_id,
                        DocumentRecord.user_id == user_id,
                    )
                    res = await session.execute(doc_del)
                    await session.commit()
                    rowcount = getattr(res, "rowcount", None) or 0
                    if rowcount > 0:
                        deleted = True
            except Exception as exc:
                log.warning("vault_service.db_delete_failed", error=str(exc))

        return deleted

    async def get_stats(self, user_id: str) -> VaultStatsResponse:
        """Aggregate statistical metrics for the user's private Knowledge Vault."""
        total_docs = 0
        total_chunks = 0
        total_bytes = 0
        folders: dict[str, int] = {}

        # Scan in-memory
        for _doc_id, doc in self._mem_documents.items():
            if doc.get("user_id") == user_id:
                total_docs += 1
                total_chunks += doc.get("chunk_count", 0)
                total_bytes += doc.get("file_size_bytes", 0)
                f = doc.get("folder", "General")
                folders[f] = folders.get(f, 0) + 1

        # Check DB
        session_factory = get_session_factory()
        if session_factory is not None:
            try:
                async with session_factory() as session:
                    stmt = select(
                        func.count(DocumentRecord.id),
                        func.sum(DocumentRecord.chunk_count),
                        func.sum(DocumentRecord.file_size_bytes),
                    ).where(DocumentRecord.user_id == user_id)
                    res = await session.execute(stmt)
                    db_cnt, db_chunks, db_bytes = res.first() or (0, 0, 0)
                    total_docs = max(total_docs, db_cnt or 0)
                    total_chunks = max(total_chunks, db_chunks or 0)
                    total_bytes = max(total_bytes, db_bytes or 0)
            except Exception as exc:
                log.warning("vault_service.db_stats_failed", error=str(exc))

        # Format bytes
        if total_bytes < 1024:
            size_fmt = f"{total_bytes} B"
        elif total_bytes < 1024 * 1024:
            size_fmt = f"{round(total_bytes / 1024, 1)} KB"
        else:
            size_fmt = f"{round(total_bytes / (1024 * 1024), 2)} MB"

        return VaultStatsResponse(
            total_documents=total_docs,
            total_chunks=total_chunks,
            total_bytes=total_bytes,
            folders=folders,
            storage_formatted=size_fmt,
        )

    # -------------------------------------------------------------------------
    # Tool Registry Integration
    # -------------------------------------------------------------------------

    def register_vault_tools(self) -> None:
        """Register Knowledge Vault actions into the Central Tool Registry."""

        async def _tool_vault_search(
            query: str,
            top_k: int = 5,
            folder: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            resp = await self.search(user_id=uid, query=query, folder=folder, top_k=top_k)
            return {
                "query": query,
                "matches_count": len(resp.results),
                "results": [r.model_dump() for r in resp.results],
            }

        async def _tool_vault_read_document(
            document_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            doc = await self.get_document(user_id=uid, document_id=document_id)
            if not doc:
                return {"error": f"Document '{document_id}' not found in user vault.", "found": False}
            return {
                "document_id": doc.id,
                "filename": doc.filename,
                "folder": doc.folder,
                "total_chunks": doc.chunk_count,
                "chunks": [c.model_dump() for c in doc.chunks],
                "found": True,
            }

        async def _tool_vault_list_documents(
            folder: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            resp = await self.list_documents(user_id=uid, folder=folder)
            return {
                "total": resp.total,
                "documents": [d.model_dump() for d in resp.documents],
            }

        async def _tool_vault_store_knowledge(
            title: str,
            content: str,
            folder: str = "Notes",
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            doc = await self.create_note(user_id=uid, title=title, content=content, folder=folder)
            return {
                "document_id": doc.id,
                "filename": doc.filename,
                "folder": doc.folder,
                "chunks_created": doc.chunk_count,
                "status": "stored",
            }

        async def _tool_vault_delete_document(
            document_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            success = await self.delete_document(user_id=uid, document_id=document_id)
            return {"document_id": document_id, "deleted": success}

        # 1. vault_search
        self._tool_registry.register(
            AgentTool(
                id="vault_search",
                name="vault_search",
                description="Search private Knowledge Vault documents and notes using hybrid semantic vector and keyword search.",
                source=ToolSource.SYSTEM,
                capabilities=["vault", "search", "rag"],
                permissions=["vault:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query to match against vault chunks"},
                        "top_k": {"type": "integer", "default": 5, "description": "Max results to return"},
                        "folder": {"type": "string", "description": "Optional folder name filter"},
                    },
                    "required": ["query"],
                },
            ),
            _tool_vault_search,
        )

        # 2. vault_read_document
        self._tool_registry.register(
            AgentTool(
                id="vault_read_document",
                name="vault_read_document",
                description="Retrieve full text and structural chunks of a specific document in the Knowledge Vault.",
                source=ToolSource.SYSTEM,
                capabilities=["vault", "document", "read"],
                permissions=["vault:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string", "description": "Unique identifier of the vault document"},
                    },
                    "required": ["document_id"],
                },
            ),
            _tool_vault_read_document,
        )

        # 3. vault_list_documents
        self._tool_registry.register(
            AgentTool(
                id="vault_list_documents",
                name="vault_list_documents",
                description="List all indexed documents, folders, and notes in the user's Knowledge Vault.",
                source=ToolSource.SYSTEM,
                capabilities=["vault", "documents", "list"],
                permissions=["vault:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "folder": {"type": "string", "description": "Optional folder filter"},
                    },
                },
            ),
            _tool_vault_list_documents,
        )

        # 4. vault_store_knowledge
        self._tool_registry.register(
            AgentTool(
                id="vault_store_knowledge",
                name="vault_store_knowledge",
                description="Directly save a knowledge note or factual markdown record into the Knowledge Vault for long-term retrieval.",
                source=ToolSource.SYSTEM,
                capabilities=["vault", "knowledge", "write"],
                permissions=["vault:write"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title or filename of the note"},
                        "content": {"type": "string", "description": "Text or markdown content"},
                        "folder": {"type": "string", "default": "Notes", "description": "Vault folder category"},
                    },
                    "required": ["title", "content"],
                },
            ),
            _tool_vault_store_knowledge,
        )

        # 5. vault_delete_document
        self._tool_registry.register(
            AgentTool(
                id="vault_delete_document",
                name="vault_delete_document",
                description="Permanently delete a document and its associated vector chunks from the Knowledge Vault.",
                source=ToolSource.SYSTEM,
                capabilities=["vault", "document", "delete", "destructive"],
                permissions=["vault:write"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string", "description": "ID of document to delete"},
                    },
                    "required": ["document_id"],
                },
            ),
            _tool_vault_delete_document,
        )
