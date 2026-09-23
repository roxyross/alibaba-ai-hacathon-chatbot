"""Autonomous Web Research & Real-Time Information Retrieval API router (Phase 14).

Provides multi-tenant endpoints for autonomous deep research investigations,
query decomposition, multi-engine live search, web page extraction, and report persistence.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.research.repository import ResearchRepository
from app.research.schemas import (
    DeepResearchRequest,
    DeepResearchResponse,
    LiveSearchRequest,
    LiveSearchResponse,
    ResearchReportCreate,
    ResearchReportListResponse,
    ResearchReportResponse,
    ResearchReportUpdate,
    WebFetchRequest,
    WebFetchResponse,
)
from app.research.service import ResearchService

log = structlog.get_logger()

router = APIRouter(prefix="/research", tags=["Research Engine"])


@router.get("", response_model=ResearchReportListResponse)
@router.get("/", response_model=ResearchReportListResponse)
@router.get("/reports", response_model=ResearchReportListResponse)
async def list_research_reports(
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> ResearchReportListResponse:
    """List authenticated user's saved research reports with search and tag filters."""
    user_id = str(current_user.id)
    repo = ResearchRepository()
    items = await repo.list_reports(user_id=user_id, limit=limit, search=search, tag=tag)
    return ResearchReportListResponse(reports=items, total=len(items))


@router.post("", response_model=ResearchReportResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ResearchReportResponse, status_code=status.HTTP_201_CREATED)
@router.post("/reports", response_model=ResearchReportResponse, status_code=status.HTTP_201_CREATED)
async def create_research_report(
    payload: ResearchReportCreate,
    current_user: User = Depends(get_current_user),
) -> ResearchReportResponse:
    """Manually persist a new research report for the authenticated user."""
    user_id = str(current_user.id)
    repo = ResearchRepository()
    created = await repo.create_report(
        user_id=user_id,
        data={
            "query": payload.query,
            "title": payload.title or payload.query[:60],
            "summary": payload.summary,
            "findings": payload.findings,
            "sources": payload.sources,
            "confidence": payload.confidence,
            "depth": payload.depth,
            "tags": payload.tags,
        },
    )
    return ResearchReportResponse(report=created)


@router.get("/{report_id}", response_model=ResearchReportResponse)
async def get_research_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
) -> ResearchReportResponse:
    """Retrieve a single research report, enforcing strict tenant isolation."""
    user_id = str(current_user.id)
    repo = ResearchRepository()
    report = await repo.get_report(user_id=user_id, report_id=report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research report '{report_id}' not found.",
        )
    return ResearchReportResponse(report=report)


@router.patch("/{report_id}", response_model=ResearchReportResponse)
async def update_research_report(
    report_id: str,
    payload: ResearchReportUpdate,
    current_user: User = Depends(get_current_user),
) -> ResearchReportResponse:
    """Update metadata, findings, or tags of an existing research report."""
    user_id = str(current_user.id)
    repo = ResearchRepository()
    data: dict[str, Any] = {}
    if payload.title is not None:
        data["title"] = payload.title
    if payload.summary is not None:
        data["summary"] = payload.summary
    if payload.findings is not None:
        data["findings"] = payload.findings
    if payload.sources is not None:
        data["sources"] = payload.sources
    if payload.confidence is not None:
        data["confidence"] = payload.confidence
    if payload.depth is not None:
        data["depth"] = payload.depth
    if payload.tags is not None:
        data["tags"] = payload.tags

    updated = await repo.update_report(user_id=user_id, report_id=report_id, data=data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research report '{report_id}' not found.",
        )
    return ResearchReportResponse(report=updated)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_research_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a research report, enforcing strict tenant isolation."""
    user_id = str(current_user.id)
    repo = ResearchRepository()
    deleted = await repo.delete_report(user_id=user_id, report_id=report_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research report '{report_id}' not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search", response_model=LiveSearchResponse)
async def live_search_endpoint(
    payload: LiveSearchRequest,
    current_user: User = Depends(get_current_user),
) -> LiveSearchResponse:
    """Execute live multi-engine web search with normalized schema."""
    service = ResearchService()
    results = await service.search_web(
        query=payload.query,
        num_results=payload.num_results,
        source=payload.source,
    )
    return LiveSearchResponse(
        query=payload.query,
        results=results,
        total_results=len(results),
    )


@router.post("/deep-research", response_model=DeepResearchResponse)
async def deep_research_endpoint(
    payload: DeepResearchRequest,
    current_user: User = Depends(get_current_user),
) -> DeepResearchResponse:
    """Execute autonomous deep research pipeline and optionally persist the report."""
    user_id = str(current_user.id)
    service = ResearchService()
    res = await service.synthesize_research(
        topic=payload.query,
        depth=payload.depth,
        save_report=payload.save_report,
        user_id=user_id,
        title=payload.title,
        tags=payload.tags,
    )
    return DeepResearchResponse(
        topic=res["topic"],
        title=res["title"],
        summary=res["summary"],
        findings=res["findings"],
        sources=res["sources"],
        citations=res["citations"],
        confidence=res["confidence"],
        depth=res["depth"],
        sub_queries=res["sub_queries"],
        next_actions=res["next_actions"],
        report_id=res.get("report_id"),
    )


@router.post("/fetch-url", response_model=WebFetchResponse)
async def fetch_url_endpoint(
    payload: WebFetchRequest,
    current_user: User = Depends(get_current_user),
) -> WebFetchResponse:
    """Extract primary text content, clean HTML, and title from a web URL."""
    service = ResearchService()
    res = await service.fetch_url(url=payload.url, max_chars=payload.max_chars)
    return WebFetchResponse(
        url=res["url"],
        title=res["title"],
        content=res["content"],
        domain=res["domain"],
        status=res.get("status", "success"),
    )
