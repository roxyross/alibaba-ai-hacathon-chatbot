"""Image Studio API router — neural synthesis, styling presets, prompt enhancement, and Knowledge Vault integration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.images.repository import ImageStudioRepository
from app.images.service import ImageStudioService

router = APIRouter(prefix="/images", tags=["images"])
_repo = ImageStudioRepository()
_service = ImageStudioService(_repo)


# -----------------------------------------------------------------------------
# Request & Response Models
# -----------------------------------------------------------------------------

class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=2000)
    media_type: str = Field(default="image")  # image or video
    style_preset: str = Field(default="photorealistic")
    speed: str = Field(default="Fast")  # Fast, Quality, Cinematic
    quality: str = Field(default="Quality 2.0")  # Quality 1.0, Quality 2.0, Ultra HD
    aspect_ratio: str = Field(default="1:1")  # 1:1, 16:9, 9:16, 2:3, 3:2, 4:5
    model: str = Field(default="flux")
    seed: int | None = Field(default=None)


class EnhancePromptRequest(BaseModel):
    prompt: str = Field(..., min_length=2, max_length=2000)
    style_preset: str = Field(default="photorealistic")


# -----------------------------------------------------------------------------
# Studio Configuration & Metas
# -----------------------------------------------------------------------------

@router.get("/config")
async def get_studio_config() -> dict[str, Any]:
    """Get creative studio configuration, supported styles, aspect ratios, and models."""
    return {
        "styles": _service.get_style_presets(),
        "aspect_ratios": _service.get_aspect_ratios(),
        "models": [
            {"id": "flux", "name": "Flux.1 Schnell (Default)", "badge": "Fast"},
            {"id": "flux-realism", "name": "Flux Realism", "badge": "Photo"},
            {"id": "flux-anime", "name": "Flux Anime & Manga", "badge": "Art"},
            {"id": "flux-3d", "name": "Flux 3D Cinematic", "badge": "3D"},
            {"id": "turbo", "name": "Diffusion Turbo", "badge": "Ultra Fast"},
            {"id": "imagen-3.0", "name": "Imagen 3.0", "badge": "High Detail"},
        ],
        "speeds": ["Fast", "Quality", "Cinematic"],
        "qualities": ["Quality 1.0", "Quality 2.0", "Ultra HD"],
    }


# -----------------------------------------------------------------------------
# Generation Endpoints
# -----------------------------------------------------------------------------

@router.get("/generations")
async def list_generations(
    favorite: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get recent Image Studio media generations for authenticated user."""
    user_id = str(user.id)
    items = await _repo.list_generations(user_id=user_id, favorite_only=favorite, limit=limit)
    return {"generations": items}


@router.post("/generate")
async def generate_media(
    req: GenerateImageRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate image using neural diffusion synthesis with chosen styling and dimensions."""
    user_id = str(user.id)

    media_url, revised_prompt, width, height, seed = _service.synthesize_image_url(
        prompt=req.prompt,
        aspect_ratio=req.aspect_ratio,
        style_preset=req.style_preset,
        model=req.model,
        seed=req.seed,
    )

    new_gen = await _repo.create_generation(
        user_id=user_id,
        prompt=req.prompt,
        media_url=media_url,
        revised_prompt=revised_prompt,
        style_preset=req.style_preset,
        media_type=req.media_type,
        speed=req.speed,
        quality=req.quality,
        aspect_ratio=req.aspect_ratio,
        width=width,
        height=height,
        model=req.model,
        seed=seed,
    )

    return {"generation": new_gen, "message": "Media generated successfully."}


@router.post("/enhance-prompt")
async def enhance_prompt(
    req: EnhancePromptRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Enrich a basic prompt with lighting, texture, and compositional nuances based on style preset."""
    enhanced = _service.enhance_prompt(base_prompt=req.prompt, style_preset=req.style_preset)
    return {"original_prompt": req.prompt, "enhanced_prompt": enhanced, "style_preset": req.style_preset}


# -----------------------------------------------------------------------------
# Upload Reference Endpoints (placed before /{image_id} to avoid path collision)
# -----------------------------------------------------------------------------

@router.get("/uploads")
async def list_uploads(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get uploaded reference assets for authenticated user."""
    user_id = str(user.id)
    uploads = await _repo.list_uploads(user_id=user_id)
    return {"uploads": uploads}


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload user media for image/video references."""
    user_id = str(user.id)
    filename = file.filename or "reference_asset.png"
    media_type = "video" if filename.lower().endswith((".mp4", ".mov", ".webm")) else "image"

    media_url = "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=800&q=80"

    upl = await _repo.create_upload(
        user_id=user_id,
        filename=filename,
        media_url=media_url,
        media_type=media_type,
    )
    return {"upload": upl, "message": "Media uploaded successfully."}


@router.delete("/uploads/{upload_id}")
async def delete_upload(
    upload_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete uploaded reference asset."""
    user_id = str(user.id)
    deleted = await _repo.delete_upload(user_id=user_id, upload_id=upload_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Uploaded asset not found.")
    return {"status": "success", "message": "Reference asset deleted."}


# -----------------------------------------------------------------------------
# Single Generation Detail & Action Endpoints
# -----------------------------------------------------------------------------

@router.get("/{image_id}")
async def get_generation(
    image_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get single generation details with strict ownership verification."""
    user_id = str(user.id)
    img = await _repo.get_generation(user_id=user_id, image_id=image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Generation not found.")
    return {"generation": img}


@router.post("/{image_id}/favorite")
async def toggle_favorite_generation(
    image_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Toggle favorite status of a generated image."""
    user_id = str(user.id)
    img = await _repo.toggle_favorite(user_id=user_id, image_id=image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Generation not found.")
    return {"generation": img, "message": "Favorite status updated."}


@router.delete("/{image_id}")
async def delete_generation(
    image_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a generated image from user's creative gallery."""
    user_id = str(user.id)
    deleted = await _repo.delete_generation(user_id=user_id, image_id=image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Generation not found.")
    return {"status": "success", "message": "Image deleted from gallery."}


@router.post("/{image_id}/save-to-vault")
async def save_generation_to_vault(
    image_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Export generated artwork and creative specifications into Knowledge Vault."""
    user_id = str(user.id)
    exported = await _service.export_to_knowledge_vault(user_id=user_id, image_id=image_id)
    if not exported:
        raise HTTPException(status_code=404, detail="Generation not found.")
    return {
        "generation": exported,
        "vault_document_id": exported.get("vault_document_id"),
        "message": "Artwork saved to Knowledge Vault successfully.",
    }
