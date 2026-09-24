"""Media API router — registry, async generation jobs, real file uploads, and asset library."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.auth.dependencies import get_current_user, get_optional_current_user
from app.auth.models import User
from app.media.schemas import (
    MediaAssetListResponse,
    MediaGenerateRequest,
    MediaJobListResponse,
    MediaJobResponse,
    MediaModelListResponse,
)
from app.media.service import MediaService
from app.settings.repository import SettingsRepository

router = APIRouter(prefix="/media", tags=["media"])
_service = MediaService()
_settings_repo = SettingsRepository()


@router.get("/models", response_model=MediaModelListResponse)
async def list_media_models(
    user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> MediaModelListResponse:
    """Return available image & video models with truthfully evaluated capabilities and availability."""
    user_byok: dict[str, str] = {}
    if user:
        settings_row = await _settings_repo.get_for_user(user.id)
        if settings_row and settings_row.extra_settings:
            user_byok = {
                k: str(v)
                for k, v in settings_row.extra_settings.items()
                if k.startswith("byok_") and v
            }

    return _service.get_models(user_byok=user_byok)


@router.post("/generate", response_model=MediaJobResponse)
async def generate_media(
    req: MediaGenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> MediaJobResponse:
    """Initiate an asynchronous generation job for image or video synthesis."""
    user_byok: dict[str, str] = {}
    settings_row = await _settings_repo.get_for_user(current_user.id)
    if settings_row and settings_row.extra_settings:
        user_byok = {
            k: str(v)
            for k, v in settings_row.extra_settings.items()
            if k.startswith("byok_") and v
        }

    try:
        return await _service.create_job(
            user_id=str(current_user.id),
            req=req,
            user_byok=user_byok,
        )
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation failed to start: {exc}") from exc


@router.get("/jobs/{job_id}", response_model=MediaJobResponse)
async def get_generation_job(
    job_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> MediaJobResponse:
    """Poll live state and progress of an asynchronous generation job."""
    job = await _service.get_job(user_id=str(current_user.id), job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs", response_model=MediaJobListResponse)
async def list_generation_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> MediaJobListResponse:
    """List recent generation jobs for the authenticated user."""
    if not current_user:
        return MediaJobListResponse(jobs=[])
    return await _service.list_jobs(user_id=str(current_user.id), limit=limit)


@router.post("/upload")
async def upload_media_file(
    file: UploadFile = File(...),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> dict[str, Any]:
    """Store actual uploaded user media asset with SHA-256 deduplication and persist to library."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required to upload media")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "uploaded_media.png"
    content_type = file.content_type or "application/octet-stream"

    return await _service.upload_file(
        user_id=str(current_user.id),
        filename=filename,
        file_bytes=content,
        content_type=content_type,
    )


@router.get("/assets", response_model=MediaAssetListResponse)
async def list_media_assets(
    media_type: str | None = Query(default=None),
    favorite: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> MediaAssetListResponse:
    """List assets from the centralized Media Asset Library."""
    if not current_user:
        return MediaAssetListResponse(assets=[])
    return await _service.list_assets(
        user_id=str(current_user.id),
        media_type=media_type,
        favorite_only=favorite,
        limit=limit,
    )


@router.post("/assets/{asset_id}/favorite")
async def toggle_asset_favorite(
    asset_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Toggle favorite bookmark on a media asset."""
    fav = await _service.toggle_favorite(user_id=str(current_user.id), asset_id=asset_id)
    return {"asset_id": asset_id, "is_favorite": fav}
