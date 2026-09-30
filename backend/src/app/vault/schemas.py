"""Knowledge Vault and Vector Memory schemas.

Pydantic models for Document ingestion, Chunking, Hybrid Search, and RAG.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField


class VaultDocumentCreateRequest(BaseModel):
    """Request schema for creating a document from raw text/markdown."""

    model_config = ConfigDict(extra="ignore")

    filename: str = PydanticField(..., min_length=1, max_length=255)
    content: str = PydanticField(..., min_length=1)
    folder: str = PydanticField(default="General", max_length=128)
    mime_type: str = PydanticField(default="text/markdown", max_length=128)
    tags: list[str] = PydanticField(default_factory=list)


class VaultNoteCreateRequest(BaseModel):
    """Request schema for creating a quick knowledge note directly into the vault."""

    model_config = ConfigDict(extra="ignore")

    title: str = PydanticField(..., min_length=1, max_length=255)
    content: str = PydanticField(..., min_length=1)
    folder: str = PydanticField(default="Notes", max_length=128)
    tags: list[str] = PydanticField(default_factory=list)


class VaultChunkItem(BaseModel):
    """Single vector chunk belonging to a document."""

    model_config = ConfigDict(extra="ignore")

    id: str
    document_id: str
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None = None
    section: str | None = None
    has_embedding: bool = False
    created_at: str | None = None


class VaultDocumentResponse(BaseModel):
    """Detailed response for an indexed Knowledge Vault document."""

    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: str
    filename: str
    folder: str
    file_size_bytes: int
    mime_type: str
    chunk_count: int
    summary: str | None = None
    status: str = "ready"
    tags: list[str] = PydanticField(default_factory=list)
    file_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    chunks: list[VaultChunkItem] = PydanticField(default_factory=list)


class VaultDocumentListResponse(BaseModel):
    """Paginated or complete list of user vault documents."""

    model_config = ConfigDict(extra="ignore")

    documents: list[VaultDocumentResponse] = PydanticField(default_factory=list)
    total: int = 0


class VaultSearchRequest(BaseModel):
    """Semantic and hybrid search query parameters."""

    model_config = ConfigDict(extra="ignore")

    query: str = PydanticField(..., min_length=1, max_length=1000)
    folder: str | None = None
    document_ids: list[str] | None = None
    top_k: Annotated[int, PydanticField(ge=1, le=50)] = 5
    min_score: Annotated[float, PydanticField(ge=0.0, le=1.0)] = 0.0
    hybrid: bool = True


class VaultSearchResultItem(BaseModel):
    """Scored chunk returned from hybrid vector and lexical search."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    document_id: str
    document_name: str
    folder: str
    chunk_index: int
    content: str
    score: float
    dense_score: float
    lexical_score: float
    section: str | None = None
    page_number: int | None = None


class VaultSearchResponse(BaseModel):
    """Response containing ranked search results and metadata."""

    model_config = ConfigDict(extra="ignore")

    query: str
    results: list[VaultSearchResultItem] = PydanticField(default_factory=list)
    total_matches: int = 0
    execution_time_ms: float = 0.0


class VaultStatsResponse(BaseModel):
    """Statistical overview of the user's Knowledge Vault."""

    model_config = ConfigDict(extra="ignore")

    total_documents: int = 0
    total_chunks: int = 0
    total_bytes: int = 0
    folders: dict[str, int] = PydanticField(default_factory=dict)
    storage_formatted: str = "0 KB"
