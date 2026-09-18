"""REST API endpoints for Autonomous Coding Agent & Developer Studio (Phase 17).

Mounted at /api/v1/coding.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.coding.repository import CodeRepository
from app.coding.schemas import (
    CodeDebugRequest,
    CodeDebugResponse,
    CodeExecuteRequest,
    CodeExecuteResponse,
    CodeExecutionListResponse,
    CodeExplainRequest,
    CodeExplainResponse,
    CodeGenerateRequest,
    CodeGenerateResponse,
    CodeSnippetCreate,
    CodeSnippetListResponse,
    CodeSnippetResponse,
    CodeSnippetUpdate,
    CodeStatsResponse,
)
from app.coding.service import CodingService
from app.db import get_db

router = APIRouter(prefix="/coding", tags=["coding"])


def get_coding_service(
    db: Annotated[AsyncSession | None, Depends(get_db)] = None,
) -> CodingService:
    """Dependency provider for CodingService."""
    repo = CodeRepository(session=db)
    return CodingService(repo=repo)


# ---------------------------------------------------------------------------
# Snippets CRUD
# ---------------------------------------------------------------------------

@router.get("/snippets", response_model=CodeSnippetListResponse)
async def list_snippets(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
    language: str | None = Query(None, description="Filter by language"),
    is_favorite: bool | None = Query(None, description="Filter by favorite"),
    search: str | None = Query(None, description="Search term across title/code/tags"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> CodeSnippetListResponse:
    """List code snippets owned by current user."""
    items, total = await service.repo.list_snippets(
        user_id=current_user.id,
        language=language,
        is_favorite=is_favorite,
        search=search,
        limit=limit,
        offset=offset,
    )
    return CodeSnippetListResponse(
        snippets=[CodeSnippetResponse(**item) for item in items],
        total=total,
    )


@router.post(
    "/snippets",
    response_model=CodeSnippetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_snippet(
    payload: CodeSnippetCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeSnippetResponse:
    """Create a new code snippet."""
    item = await service.repo.create_snippet(
        user_id=current_user.id,
        title=payload.title,
        language=payload.language,
        code=payload.code,
        description=payload.description,
        tags=payload.tags,
        is_favorite=payload.is_favorite,
    )
    return CodeSnippetResponse(**item)


@router.get("/snippets/{snippet_id}", response_model=CodeSnippetResponse)
async def get_snippet(
    snippet_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeSnippetResponse:
    """Retrieve single snippet with strict 404 security isolation."""
    item = await service.repo.get_snippet(current_user.id, snippet_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code snippet not found",
        )
    return CodeSnippetResponse(**item)


@router.patch("/snippets/{snippet_id}", response_model=CodeSnippetResponse)
async def update_snippet(
    snippet_id: str,
    payload: CodeSnippetUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeSnippetResponse:
    """Update existing snippet (returns 404 for unowned)."""
    item = await service.repo.update_snippet(
        user_id=current_user.id,
        snippet_id=snippet_id,
        title=payload.title,
        language=payload.language,
        code=payload.code,
        description=payload.description,
        tags=payload.tags,
        is_favorite=payload.is_favorite,
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code snippet not found",
        )
    return CodeSnippetResponse(**item)


@router.delete("/snippets/{snippet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snippet(
    snippet_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> None:
    """Delete snippet permanently (returns 404 for unowned)."""
    deleted = await service.repo.delete_snippet(current_user.id, snippet_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Code snippet not found",
        )


# ---------------------------------------------------------------------------
# AI Assistance
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=CodeGenerateResponse)
async def generate_code(
    payload: CodeGenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeGenerateResponse:
    """Generate production-grade code adhering to task and constraints."""
    return await service.generate_code(user_id=current_user.id, request=payload)


@router.post("/explain", response_model=CodeExplainResponse)
async def explain_code(
    payload: CodeExplainRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeExplainResponse:
    """Explain code snippet with line-by-line notes and key concepts."""
    return await service.explain_code(user_id=current_user.id, request=payload)


@router.post("/debug", response_model=CodeDebugResponse)
async def debug_code(
    payload: CodeDebugRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeDebugResponse:
    """Diagnose bug, form hypothesis, and generate minimal fix diff."""
    return await service.debug_code(user_id=current_user.id, request=payload)


# ---------------------------------------------------------------------------
# Code Execution & Sandbox
# ---------------------------------------------------------------------------

@router.post("/execute", response_model=CodeExecuteResponse)
async def execute_code(
    payload: CodeExecuteRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeExecuteResponse:
    """Execute code in a sandboxed subprocess and record execution history."""
    return await service.execute_code(user_id=current_user.id, request=payload)


@router.get("/executions", response_model=CodeExecutionListResponse)
async def list_executions(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
    snippet_id: str | None = Query(None, description="Filter by snippet"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CodeExecutionListResponse:
    """List execution history logs."""
    items, total = await service.repo.list_executions(
        user_id=current_user.id,
        snippet_id=snippet_id,
        limit=limit,
        offset=offset,
    )
    return CodeExecutionListResponse(
        executions=[CodeExecuteResponse(**item) for item in items],
        total=total,
    )


@router.get("/executions/{execution_id}", response_model=CodeExecuteResponse)
async def get_execution(
    execution_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeExecuteResponse:
    """Get single execution run log (404 on unowned)."""
    item = await service.repo.get_execution(current_user.id, execution_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution record not found",
        )
    return CodeExecuteResponse(**item)


# ---------------------------------------------------------------------------
# Stats / Analytics
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=CodeStatsResponse)
async def get_code_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CodingService, Depends(get_coding_service)],
) -> CodeStatsResponse:
    """Aggregate developer studio metrics."""
    stats = await service.repo.get_user_stats(current_user.id)
    return CodeStatsResponse(**stats)
