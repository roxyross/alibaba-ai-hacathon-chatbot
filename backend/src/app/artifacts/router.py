"""FastAPI router for Cowork Workspace and Multi-Artifact Canvas."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.artifacts.schemas import (
    Artifact,
    CreateArtifactRequest,
    DiffReviewResponse,
    RefineArtifactRequest,
    RenderDiagramRequest,
    RevertVersionRequest,
    UpdateArtifactRequest,
)
from app.artifacts.service import CoworkService
from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/workspace/artifacts", tags=["workspace-artifacts"])
_service = CoworkService.get_instance()
_repo = _service.repo


@router.post("", response_model=Artifact, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    req: CreateArtifactRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new live artifact in Cowork Task Workspace."""
    art = await _service.create_artifact(
        user_id=user.id,
        title=req.title,
        content=req.content,
        artifact_type=req.artifact_type,
        language=req.language,
        task_id=req.task_id,
        session_id=req.session_id,
        metadata=req.metadata,
    )
    return art


@router.get("", response_model=list[dict[str, Any]])
async def list_artifacts(
    task_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    artifact_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List artifacts belonging to the authenticated user."""
    return await _service.list_artifacts(
        user_id=user.id,
        task_id=task_id,
        session_id=session_id,
        artifact_type=artifact_type,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{artifact_id}", response_model=Artifact)
async def get_artifact(
    artifact_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve full artifact record including all historical revisions and diffs."""
    art = await _service.get_artifact(user_id=user.id, artifact_id=artifact_id)
    if not art:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return art


@router.patch("/{artifact_id}", response_model=Artifact)
async def update_artifact(
    artifact_id: str,
    req: UpdateArtifactRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update artifact content or title, capturing revision snapshot and unified diff."""
    updated = await _service.update_artifact(
        user_id=user.id,
        artifact_id=artifact_id,
        title=req.title,
        content=req.content,
        change_summary=req.change_summary,
        created_by="user",
        metadata=req.metadata,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return updated


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Permanently delete an artifact and all associated version snapshots."""
    deleted = await _service.delete_artifact(user_id=user.id, artifact_id=artifact_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return {"deleted": True, "artifact_id": artifact_id}


@router.post("/{artifact_id}/refine", response_model=Artifact)
async def refine_artifact(
    artifact_id: str,
    req: RefineArtifactRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Human-in-the-loop iterative AI refinement of an artifact based on user feedback."""
    refined = await _service.refine_artifact_with_ai(
        user_id=user.id,
        artifact_id=artifact_id,
        instruction=req.instruction,
        target_aspect=req.target_aspect,
    )
    if not refined:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return refined


@router.post("/{artifact_id}/revert", response_model=Artifact)
async def revert_artifact_version(
    artifact_id: str,
    req: RevertVersionRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Revert artifact to an earlier version number."""
    reverted = await _repo.revert_version(
        user_id=user.id,
        artifact_id=artifact_id,
        version_number=req.version_number,
    )
    if not reverted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {req.version_number} of artifact '{artifact_id}' not found",
        )
    return reverted


@router.get("/{artifact_id}/diff", response_model=DiffReviewResponse)
async def get_version_diff(
    artifact_id: str,
    from_version: int = Query(..., ge=1),
    to_version: int = Query(..., ge=1),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Compute unified diff between two historical revisions."""
    diff_res = await _repo.get_version_diff(
        user_id=user.id,
        artifact_id=artifact_id,
        from_v=from_version,
        to_v=to_version,
    )
    if not diff_res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diff between v{from_version} and v{to_version} could not be computed",
        )
    return diff_res


@router.post("/diagram", response_model=Artifact, status_code=status.HTTP_201_CREATED)
async def render_diagram_endpoint(
    req: RenderDiagramRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate and store visual diagram artifact (Mermaid or SVG)."""
    return await _service.render_diagram(
        user_id=user.id,
        diagram_type=req.diagram_type,
        specification=req.specification,
        title=req.title,
        description=req.description,
        nodes=req.nodes,
        relationships=req.relationships,
    )
