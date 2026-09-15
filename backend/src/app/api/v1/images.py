"""Image Studio API router — media generation, speed/quality/aspect ratio, and media uploads."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(prefix="/images", tags=["images"])

# In-memory generation showcase
_GENERATIONS: list[dict[str, Any]] = [
    {
        "id": "gen_1",
        "prompt": "Futuristic minimalist workspace with soft teal lighting, frosted glass desk, ambient neon accents, high resolution",
        "media_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=800&q=80",
        "media_type": "image",
        "speed": "Fast",
        "quality": "Quality 2.0",
        "aspect_ratio": "16:9",
        "model": "imagen-3.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "gen_2",
        "prompt": "Autonomous robot assistant organizing complex holographic charts in a sleek data center",
        "media_url": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=800&q=80",
        "media_type": "image",
        "speed": "Quality",
        "quality": "Quality 2.0",
        "aspect_ratio": "2:3",
        "model": "imagen-3.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
]

_UPLOADS: list[dict[str, Any]] = [
    {
        "id": "upl_1",
        "filename": "reference_architecture.png",
        "media_url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=800&q=80",
        "media_type": "image",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
]


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=2)
    media_type: str = Field(default="image")  # image or video
    speed: str = Field(default="Fast")  # Fast, Quality, Cinematic
    quality: str = Field(default="Quality 2.0")  # Quality 1.0, Quality 2.0, Ultra HD
    aspect_ratio: str = Field(default="1:1")  # 1:1, 16:9, 9:16, 2:3, 3:2
    model: str = Field(default="imagen-3.0")


@router.get("/generations")
async def list_generations(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get recent Image Studio media generations."""
    return {"generations": _GENERATIONS}


@router.get("/uploads")
async def list_uploads(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Get uploaded media assets."""
    return {"uploads": _UPLOADS}


@router.post("/generate")
async def generate_media(
    req: GenerateImageRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate image or video using the specified parameters."""
    # Placeholders curated for professional tech visualization
    sample_images = [
        "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=800&q=80",
    ]
    chosen_url = sample_images[len(_GENERATIONS) % len(sample_images)]

    new_gen = {
        "id": f"gen_{uuid.uuid4().hex[:8]}",
        "prompt": req.prompt,
        "media_url": chosen_url,
        "media_type": req.media_type,
        "speed": req.speed,
        "quality": req.quality,
        "aspect_ratio": req.aspect_ratio,
        "model": req.model,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _GENERATIONS.insert(0, new_gen)
    return {"generation": new_gen, "message": "Media generated successfully."}


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload user media for image/video references."""
    new_upl = {
        "id": f"upl_{uuid.uuid4().hex[:8]}",
        "filename": file.filename or "media_upload.png",
        "media_url": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=800&q=80",
        "media_type": "image" if not (file.filename or "").endswith((".mp4", ".mov")) else "video",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _UPLOADS.insert(0, new_upl)
    return {"upload": new_upl, "message": "Media uploaded successfully."}
