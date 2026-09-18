"""REST API endpoints for Semantic Memory and Memory Curator (Phase 18).

Provides multi-tenant long-term semantic memory management, semantic retrieval,
autonomous curator execution, policy configuration, and GDPR data export/erasure.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_db
from app.memory.repository import MemoryRepository
from app.memory.schemas import (
    CuratorPolicyConfig,
    CuratorRunResponse,
    DataExportResponse,
    MemoryCreateRequest,
    MemoryResponse,
    MemoryRetrieveItem,
    MemoryRetrieveRequest,
    MemoryRetrieveResponse,
    MemoryStatsResponse,
    MemoryUpdateRequest,
)
from app.memory.service import MemoryService

log = structlog.get_logger()

router = APIRouter(prefix="/memory", tags=["memory"])


def get_service(
    db: Annotated[AsyncSession | None, Depends(get_db)] = None,
) -> MemoryService:
    """Dependency provider for MemoryService."""
    repo = MemoryRepository(session=db)
    return MemoryService(repository=repo)


# ---------------------------------------------------------------------------
# Semantic Memory Entries
# ---------------------------------------------------------------------------

@router.get("/entries", response_model=dict[str, Any])
async def list_memories(
    query: str | None = Query(None, description="Search query in content"),
    tag: str | None = Query(None, description="Filter by tag"),
    importance: str | None = Query(None, description="Filter by importance"),
    include_soft_deleted: bool = Query(False, description="Include soft-deleted memories"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> dict[str, Any]:
    """List semantic memory entries for the authenticated user."""
    items, total = await service.repo.list_memories(
        user_id=current_user.id,
        query=query,
        tag=tag,
        importance=importance,
        include_soft_deleted=include_soft_deleted,
        limit=limit,
        offset=offset,
    )
    return {"entries": items, "total": total}


@router.post("/entries", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def store_memory(
    body: MemoryCreateRequest,
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> MemoryResponse:
    """Store a new long-term semantic memory entry."""
    try:
        data = await service.store_memory(
            user_id=current_user.id,
            content=body.content,
            importance=body.importance,
            source=body.source,
            tags=body.tags,
        )
        return MemoryResponse(**data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/entries/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    include_soft_deleted: bool = Query(False),
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> MemoryResponse:
    """Retrieve a single semantic memory by ID (enforces 404 on unowned)."""
    mem = await service.repo.get_memory(
        user_id=current_user.id,
        memory_id=memory_id,
        include_soft_deleted=include_soft_deleted,
    )
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found or access denied.",
        )
    return MemoryResponse(**mem)


@router.patch("/entries/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    body: MemoryUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> MemoryResponse:
    """Update an existing semantic memory entry (enforces 404 on unowned)."""
    updated = await service.repo.update_memory(
        user_id=current_user.id,
        memory_id=memory_id,
        content=body.content,
        importance=body.importance,
        tags=body.tags,
        is_soft_deleted=body.is_soft_deleted,
        soft_delete_reason=body.soft_delete_reason,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found or access denied.",
        )
    return MemoryResponse(**updated)


@router.delete("/entries/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    permanent: bool = Query(False, description="Whether to permanently purge"),
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> None:
    """Delete a semantic memory. Default is soft-delete; permanent=true purges."""
    deleted = await service.repo.delete_memory(
        user_id=current_user.id,
        memory_id=memory_id,
        permanent=permanent,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found or access denied.",
        )


@router.post("/entries/{memory_id}/restore", response_model=MemoryResponse)
async def restore_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> MemoryResponse:
    """Restore a soft-deleted memory within the grace period."""
    restored = await service.repo.restore_memory(
        user_id=current_user.id,
        memory_id=memory_id,
    )
    if not restored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found or access denied.",
        )
    return MemoryResponse(**restored)


# ---------------------------------------------------------------------------
# Retrieval & Context Grounding
# ---------------------------------------------------------------------------

@router.post("/retrieve", response_model=MemoryRetrieveResponse)
async def retrieve_memories(
    body: MemoryRetrieveRequest,
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> MemoryRetrieveResponse:
    """Retrieve scored semantic memories matching query or tags."""
    entries, total = await service.retrieve_memory(
        user_id=current_user.id,
        query=body.query,
        tags=body.tags,
        importance=body.importance,
        top_k=body.top_k,
        min_score=body.min_score,
    )
    items = [MemoryRetrieveItem(**e) for e in entries]
    return MemoryRetrieveResponse(entries=items, total_candidates=total)


# ---------------------------------------------------------------------------
# Memory Curator Operations
# ---------------------------------------------------------------------------

@router.post("/curator/run", response_model=CuratorRunResponse)
async def trigger_curator_pass(
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> CuratorRunResponse:
    """Trigger an on-demand Memory Curator pass to cluster, summarize, and prune."""
    report = await service.run_curator_pass(user_id=current_user.id)
    return CuratorRunResponse(**report)


@router.get("/curator/reports", response_model=list[CuratorRunResponse])
async def list_curator_reports(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> list[CuratorRunResponse]:
    """List execution reports and diff summaries from past curator passes."""
    reports = await service.repo.list_curator_reports(
        user_id=current_user.id, limit=limit
    )
    return [CuratorRunResponse(**r) for r in reports]


@router.get("/curator/policy", response_model=CuratorPolicyConfig)
async def get_curator_policy(
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> CuratorPolicyConfig:
    """Get the active curator pruning policy thresholds."""
    policy = await service.repo.get_policy(user_id=current_user.id)
    return CuratorPolicyConfig(**policy)


@router.put("/curator/policy", response_model=CuratorPolicyConfig)
async def update_curator_policy(
    body: CuratorPolicyConfig,
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> CuratorPolicyConfig:
    """Update custom curator pruning policy thresholds."""
    saved = await service.repo.save_policy(
        user_id=current_user.id, policy=body.model_dump()
    )
    return CuratorPolicyConfig(**saved)


# ---------------------------------------------------------------------------
# Stats, Export & GDPR Erasure
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> MemoryStatsResponse:
    """Get real-time telemetry on stored memories, favorites, and curator passes."""
    stats = await service.repo.get_stats(user_id=current_user.id)
    return MemoryStatsResponse(**stats)


@router.get("/export", response_model=DataExportResponse)
async def export_memory_data(
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> DataExportResponse:
    """Export complete user memory vault in a portable JSON format."""
    bundle = await service.export_user_data(user_id=current_user.id)
    return DataExportResponse(**bundle)


@router.delete("/purge-all", status_code=status.HTTP_200_OK)
async def purge_all_memories(
    current_user: User = Depends(get_current_user),
    service: MemoryService = Depends(get_service),
) -> dict[str, Any]:
    """Permanently delete all memories for the authenticated user."""
    purged_count = await service.purge_all(user_id=current_user.id)
    return {
        "status": "success",
        "purged_count": purged_count,
        "message": f"Successfully purged {purged_count} memories permanently.",
    }
