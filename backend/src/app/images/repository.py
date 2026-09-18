"""ImageStudioRepository — SQLAlchemy async persistence with in-memory fallback for image studio."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session_factory
from app.models.generated_image import GeneratedImage, UploadedMedia

logger = logging.getLogger(__name__)

# Thread-safe in-memory stores for dev and test environments without DB connection
_MEM_IMAGES: dict[str, list[dict[str, Any]]] = {}   # user_id -> list of image dicts
_MEM_UPLOADS: dict[str, list[dict[str, Any]]] = {}  # user_id -> list of upload dicts


def clear_in_memory_stores() -> None:
    """Reset in-memory storage for test isolation."""
    _MEM_IMAGES.clear()
    _MEM_UPLOADS.clear()


class ImageStudioRepository:
    """Repository handling multi-tenant image studio generations, favorites, and uploads."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    def _get_factory(self) -> async_sessionmaker[AsyncSession] | None:
        if not os.environ.get("DATABASE_URL"):
            return None
        return get_session_factory()

    # -------------------------------------------------------------------------
    # Generations
    # -------------------------------------------------------------------------

    async def list_generations(
        self,
        user_id: str,
        favorite_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List media generations for authenticated user."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    query = select(GeneratedImage).where(GeneratedImage.user_id == user_id)
                    if favorite_only:
                        query = query.where(GeneratedImage.is_favorite.is_(True))
                    query = query.order_by(GeneratedImage.created_at.desc()).limit(limit)

                    res = await db.execute(query)
                    orms = res.scalars().all()
                    return [
                        {
                            "id": img.id,
                            "user_id": img.user_id,
                            "prompt": img.prompt,
                            "revised_prompt": img.revised_prompt,
                            "media_url": img.media_url,
                            "media_type": img.media_type,
                            "style_preset": img.style_preset,
                            "speed": img.speed,
                            "quality": img.quality,
                            "aspect_ratio": img.aspect_ratio,
                            "width": img.width,
                            "height": img.height,
                            "model": img.model,
                            "seed": img.seed,
                            "is_favorite": img.is_favorite,
                            "vault_document_id": img.vault_document_id,
                            "created_at": img.created_at.isoformat() if img.created_at else None,
                        }
                        for img in orms
                    ]
            except Exception as exc:
                logger.warning(f"DB list_generations failed: {exc}")

        # In-memory fallback
        user_images = _MEM_IMAGES.get(user_id, [])
        filtered = [
            mem_img for mem_img in user_images
            if not favorite_only or mem_img.get("is_favorite")
        ]
        return filtered[:limit]

    async def get_generation(
        self,
        user_id: str,
        image_id: str,
    ) -> dict[str, Any] | None:
        """Get single generation with multi-tenant verification."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(GeneratedImage).where(
                        GeneratedImage.id == image_id,
                        GeneratedImage.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    img = res.scalars().first()
                    if img:
                        return {
                            "id": img.id,
                            "user_id": img.user_id,
                            "prompt": img.prompt,
                            "revised_prompt": img.revised_prompt,
                            "media_url": img.media_url,
                            "media_type": img.media_type,
                            "style_preset": img.style_preset,
                            "speed": img.speed,
                            "quality": img.quality,
                            "aspect_ratio": img.aspect_ratio,
                            "width": img.width,
                            "height": img.height,
                            "model": img.model,
                            "seed": img.seed,
                            "is_favorite": img.is_favorite,
                            "vault_document_id": img.vault_document_id,
                            "created_at": img.created_at.isoformat() if img.created_at else None,
                        }
            except Exception as exc:
                logger.warning(f"DB get_generation failed: {exc}")

        # In-memory fallback
        user_images = _MEM_IMAGES.get(user_id, [])
        return next((mem_img for mem_img in user_images if mem_img["id"] == image_id), None)

    async def create_generation(
        self,
        user_id: str,
        prompt: str,
        media_url: str,
        revised_prompt: str | None = None,
        style_preset: str = "photorealistic",
        media_type: str = "image",
        speed: str = "Fast",
        quality: str = "Quality 2.0",
        aspect_ratio: str = "1:1",
        width: int = 1024,
        height: int = 1024,
        model: str = "flux",
        seed: int | None = None,
        vault_document_id: str | None = None,
    ) -> dict[str, Any]:
        """Record newly generated image for user."""
        image_id = f"gen-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        data = {
            "id": image_id,
            "user_id": user_id,
            "prompt": prompt,
            "revised_prompt": revised_prompt,
            "media_url": media_url,
            "media_type": media_type,
            "style_preset": style_preset,
            "speed": speed,
            "quality": quality,
            "aspect_ratio": aspect_ratio,
            "width": width,
            "height": height,
            "model": model,
            "seed": seed,
            "is_favorite": False,
            "vault_document_id": vault_document_id,
            "created_at": now.isoformat(),
        }

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    orm_img = GeneratedImage(
                        id=image_id,
                        user_id=user_id,
                        prompt=prompt,
                        revised_prompt=revised_prompt,
                        media_url=media_url,
                        media_type=media_type,
                        style_preset=style_preset,
                        speed=speed,
                        quality=quality,
                        aspect_ratio=aspect_ratio,
                        width=width,
                        height=height,
                        model=model,
                        seed=seed,
                        is_favorite=False,
                        vault_document_id=vault_document_id,
                        created_at=now,
                    )
                    db.add(orm_img)
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB create_generation failed: {exc}")

        if user_id not in _MEM_IMAGES:
            _MEM_IMAGES[user_id] = []
        _MEM_IMAGES[user_id].insert(0, data)
        return data

    async def toggle_favorite(
        self,
        user_id: str,
        image_id: str,
    ) -> dict[str, Any] | None:
        """Toggle favorite state of a generation."""
        img = await self.get_generation(user_id, image_id)
        if not img:
            return None

        new_fav = not img.get("is_favorite", False)

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(GeneratedImage).where(
                        GeneratedImage.id == image_id,
                        GeneratedImage.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    orm_img = res.scalars().first()
                    if orm_img:
                        orm_img.is_favorite = new_fav
                        await db.commit()
            except Exception as exc:
                logger.warning(f"DB toggle_favorite failed: {exc}")

        user_images = _MEM_IMAGES.get(user_id, [])
        for mem_img in user_images:
            if mem_img["id"] == image_id:
                mem_img["is_favorite"] = new_fav
                return mem_img

        img["is_favorite"] = new_fav
        return img

    async def attach_vault_document(
        self,
        user_id: str,
        image_id: str,
        vault_document_id: str,
    ) -> dict[str, Any] | None:
        """Attach a Knowledge Vault document ID to a generation."""
        img = await self.get_generation(user_id, image_id)
        if not img:
            return None

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(GeneratedImage).where(
                        GeneratedImage.id == image_id,
                        GeneratedImage.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    orm_img = res.scalars().first()
                    if orm_img:
                        orm_img.vault_document_id = vault_document_id
                        await db.commit()
            except Exception as exc:
                logger.warning(f"DB attach_vault_document failed: {exc}")

        user_images = _MEM_IMAGES.get(user_id, [])
        for mem_img in user_images:
            if mem_img["id"] == image_id:
                mem_img["vault_document_id"] = vault_document_id
                return mem_img

        img["vault_document_id"] = vault_document_id
        return img

    async def delete_generation(
        self,
        user_id: str,
        image_id: str,
    ) -> bool:
        """Delete generation from user gallery."""
        img = await self.get_generation(user_id, image_id)
        if not img:
            return False

        deleted = False
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = delete(GeneratedImage).where(
                        GeneratedImage.id == image_id,
                        GeneratedImage.user_id == user_id,
                    )
                    await db.execute(stmt)
                    await db.commit()
                    deleted = True
            except Exception as exc:
                logger.warning(f"DB delete_generation failed: {exc}")

        user_images = _MEM_IMAGES.get(user_id, [])
        before = len(user_images)
        _MEM_IMAGES[user_id] = [m for m in user_images if m["id"] != image_id]
        if len(_MEM_IMAGES[user_id]) < before:
            deleted = True

        return deleted

    # -------------------------------------------------------------------------
    # Uploads
    # -------------------------------------------------------------------------

    async def list_uploads(
        self,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """List uploaded reference assets for user."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(UploadedMedia).where(
                        UploadedMedia.user_id == user_id
                    ).order_by(UploadedMedia.created_at.desc())
                    res = await db.execute(stmt)
                    return [
                        {
                            "id": u.id,
                            "user_id": u.user_id,
                            "filename": u.filename,
                            "media_url": u.media_url,
                            "media_type": u.media_type,
                            "created_at": u.created_at.isoformat() if u.created_at else None,
                        }
                        for u in res.scalars().all()
                    ]
            except Exception as exc:
                logger.warning(f"DB list_uploads failed: {exc}")

        return _MEM_UPLOADS.get(user_id, [])

    async def create_upload(
        self,
        user_id: str,
        filename: str,
        media_url: str,
        media_type: str = "image",
    ) -> dict[str, Any]:
        """Record newly uploaded media asset."""
        upload_id = f"upl-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)

        data = {
            "id": upload_id,
            "user_id": user_id,
            "filename": filename,
            "media_url": media_url,
            "media_type": media_type,
            "created_at": now.isoformat(),
        }

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    orm_upl = UploadedMedia(
                        id=upload_id,
                        user_id=user_id,
                        filename=filename,
                        media_url=media_url,
                        media_type=media_type,
                        created_at=now,
                    )
                    db.add(orm_upl)
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB create_upload failed: {exc}")

        if user_id not in _MEM_UPLOADS:
            _MEM_UPLOADS[user_id] = []
        _MEM_UPLOADS[user_id].insert(0, data)
        return data

    async def delete_upload(
        self,
        user_id: str,
        upload_id: str,
    ) -> bool:
        """Delete uploaded reference asset."""
        user_uploads = _MEM_UPLOADS.get(user_id, [])
        match = next((u for u in user_uploads if u["id"] == upload_id), None)

        deleted = False
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = delete(UploadedMedia).where(
                        UploadedMedia.id == upload_id,
                        UploadedMedia.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    await db.commit()
                    if getattr(res, "rowcount", 0) > 0:
                        deleted = True
            except Exception as exc:
                logger.warning(f"DB delete_upload failed: {exc}")

        if match:
            _MEM_UPLOADS[user_id] = [u for u in user_uploads if u["id"] != upload_id]
            deleted = True

        return deleted
