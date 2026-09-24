"""MediaService orchestrating truthful generation, jobs queue, and asset management."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import desc, select

from app.db import get_session_factory
from app.media.google_engine import GoogleGenAIMediaEngine
from app.media.registry import CapabilityRegistry
from app.media.schemas import (
    MediaAssetListResponse,
    MediaAssetResponse,
    MediaGenerateRequest,
    MediaJobListResponse,
    MediaJobResponse,
    MediaModelListResponse,
)
from app.models.generated_image import GeneratedImage, UploadedMedia
from app.models.media_job import MediaAsset, MediaGenerationJob
from app.models.subscription import CreditWallet, UsageLog

logger = logging.getLogger(__name__)

MEDIA_STORAGE_DIR = os.path.join(os.getcwd(), "static", "media")
GENERATED_DIR = os.path.join(MEDIA_STORAGE_DIR, "generated")
UPLOADS_DIR = os.path.join(MEDIA_STORAGE_DIR, "uploads")

os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# In-memory storage fallback for test and local dev environments without DB connection
_MEM_JOBS: dict[str, dict[str, Any]] = {}
_MEM_ASSETS: dict[str, list[dict[str, Any]]] = {}


def clear_media_in_memory_stores() -> None:
    """Reset in-memory storage for test isolation."""
    _MEM_JOBS.clear()
    _MEM_ASSETS.clear()


class MediaService:
    """Production service for creative media synthesis, background jobs, and asset library."""

    def __init__(self) -> None:
        self.registry = CapabilityRegistry()
        self.google_engine = GoogleGenAIMediaEngine()

    def get_models(self, user_byok: dict[str, str] | None = None) -> MediaModelListResponse:
        """Return registered models with dynamically verified availability."""
        models = self.registry.list_models(user_byok=user_byok)
        return MediaModelListResponse(models=models)

    async def create_job(
        self,
        user_id: str,
        req: MediaGenerateRequest,
        user_byok: dict[str, str] | None = None,
    ) -> MediaJobResponse:
        """Submit and queue a generation job."""
        byok = user_byok or {}
        factory = get_session_factory()
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()

        if factory is not None:
            try:
                async with factory() as session:
                    wallet = (
                        await session.execute(
                            select(CreditWallet).where(CreditWallet.user_id == user_id)
                        )
                    ).scalars().first()

                    model_cap = self.registry.get_model(req.model)
                    cost = model_cap.credit_cost if model_cap else 1

                    if wallet:
                        if wallet.remaining_credits < cost:
                            raise ValueError(
                                f"Insufficient credits. This job requires {cost} credits, remaining balance is {wallet.remaining_credits}."
                            )
                        wallet.remaining_credits -= float(cost)
                        wallet.used_this_month = (wallet.used_this_month or 0.0) + float(cost)
                        log_entry = UsageLog(
                            user_id=user_id,
                            feature=f"media_{req.media_type}",
                            model=req.model,
                            tokens_input=0,
                            tokens_output=int(cost),
                        )
                        session.add(log_entry)

                    job = MediaGenerationJob(
                        id=job_id,
                        user_id=user_id,
                        media_type=req.media_type,
                        provider=req.provider,
                        model=req.model,
                        prompt=req.prompt,
                        negative_prompt=req.negative_prompt,
                        status="processing",
                        progress=15,
                        parameters=req.model_dump(),
                    )
                    session.add(job)
                    await session.commit()
            except ValueError:
                raise
            except Exception as exc:
                logger.warning(f"DB job record creation failed, using memory fallback: {exc}")

        # Always track in-memory state
        _MEM_JOBS[job_id] = {
            "id": job_id,
            "user_id": user_id,
            "media_type": req.media_type,
            "provider": req.provider,
            "model": req.model,
            "prompt": req.prompt,
            "status": "processing",
            "progress": 15,
            "media_url": None,
            "thumbnail_url": None,
            "error_message": None,
            "parameters": req.model_dump(),
            "created_at": now_str,
            "completed_at": None,
        }

        # Fire asynchronous background synthesis worker
        asyncio.create_task(
            self._process_generation_job(job_id=job_id, user_id=user_id, req=req, user_byok=byok)
        )

        return MediaJobResponse(
            id=job_id,
            user_id=user_id,
            media_type=req.media_type,
            provider=req.provider,
            model=req.model,
            prompt=req.prompt,
            status="processing",
            progress=15,
            parameters=req.model_dump(),
            created_at=now_str,
        )

    async def _resolve_media_bytes(self, url: str | None) -> bytes | None:
        """Resolve raw file bytes from data URL, local static path, or remote URL."""
        if not url:
            return None
        try:
            if url.startswith("data:"):
                payload = url.split(",", 1)[1] if "," in url else url
                return base64.b64decode(payload)
            if url.startswith("/static/"):
                rel_path = url.lstrip("/")
                disk_path = os.path.join(os.getcwd(), rel_path)
                if os.path.exists(disk_path):
                    with open(disk_path, "rb") as f:
                        return f.read()
            if url.startswith("http://") or url.startswith("https://"):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return r.content
            if os.path.exists(url):
                with open(url, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.warning(f"Failed to resolve media bytes from '{url[:60]}': {e}")
        return None

    async def _process_generation_job(
        self,
        job_id: str,
        user_id: str,
        req: MediaGenerateRequest,
        user_byok: dict[str, str],
    ) -> None:
        """Background worker that executes the actual media synthesis and saves assets."""
        try:
            media_url: str = ""
            width: int = 1024
            height: int = 1024
            duration_sec: float | None = None

            if req.aspect_ratio == "16:9":
                width, height = 1344, 768
            elif req.aspect_ratio == "9:16":
                width, height = 768, 1344
            elif req.aspect_ratio == "4:3":
                width, height = 1152, 896
            elif req.aspect_ratio == "3:4":
                width, height = 896, 1152

            if req.media_type == "image":
                images: list[bytes] = []
                if req.provider == "google":
                    google_key = (
                        user_byok.get("byok_gemini")
                        or os.getenv("GEMINI_API_KEY")
                        or os.getenv("GOOGLE_API_KEY")
                    )
                    if google_key:
                        try:
                            images = await self.google_engine.generate_image(
                                prompt=req.prompt,
                                model=req.model,
                                aspect_ratio=req.aspect_ratio,
                                number_of_images=1,
                                negative_prompt=req.negative_prompt,
                                seed=req.seed,
                                override_key=google_key,
                            )
                        except Exception as g_err:
                            logger.warning(f"Google engine image synthesis failed ({g_err}), falling back to FLUX")

                if images:
                    filename = f"gen_{job_id}.png"
                    filepath = os.path.join(GENERATED_DIR, filename)
                    with open(filepath, "wb") as f:
                        f.write(images[0])
                    media_url = f"/static/media/generated/{filename}"
                else:
                    # Pollinations / FLUX fallback synthesis
                    encoded = urllib.parse.quote(req.prompt)
                    poll_model = "flux" if "flux" in req.model else "turbo"
                    seed = req.seed or 42
                    poll_url = (
                        f"https://image.pollinations.ai/prompt/{encoded}"
                        f"?width={width}&height={height}&model={poll_model}&seed={seed}&nologo=true"
                    )
                    try:
                        async with httpx.AsyncClient(timeout=15.0) as client:
                            resp = await client.get(poll_url)
                            if resp.status_code == 200 and resp.content:
                                filename = f"gen_{job_id}.jpg"
                                filepath = os.path.join(GENERATED_DIR, filename)
                                with open(filepath, "wb") as f:
                                    f.write(resp.content)
                                media_url = f"/static/media/generated/{filename}"
                            else:
                                media_url = poll_url
                    except Exception:
                        media_url = poll_url

            elif req.media_type == "video":
                google_key = (
                    user_byok.get("byok_gemini")
                    or os.getenv("GEMINI_API_KEY")
                    or os.getenv("GOOGLE_API_KEY")
                )
                if not google_key:
                    raise ValueError(
                        f"Video generation with {req.model} requires a valid Google GenAI API key in Settings (BYOK)."
                    )

                duration_sec = float(req.duration)
                first_frame_bytes = await self._resolve_media_bytes(req.first_frame_url)
                last_frame_bytes = await self._resolve_media_bytes(req.last_frame_url)

                operation = await self.google_engine.generate_video_operation(
                    prompt=req.prompt,
                    model=req.model,
                    duration_seconds=int(req.duration),
                    first_frame_bytes=first_frame_bytes,
                    last_frame_bytes=last_frame_bytes,
                    aspect_ratio=req.aspect_ratio or "16:9",
                    resolution=req.resolution or "720p",
                    fps=req.fps or 24,
                    audio=req.audio,
                    negative_prompt=req.negative_prompt,
                    seed=req.seed,
                    override_key=google_key,
                )

                attempts = 0
                while not getattr(operation, "done", False) and attempts < 60:
                    await asyncio.sleep(5)
                    operation = await self.google_engine.poll_video_operation(
                        operation=operation, override_key=google_key
                    )
                    attempts += 1

                if hasattr(operation, "error") and operation.error:
                    err_msg = getattr(operation.error, "message", None) or str(operation.error)
                    raise RuntimeError(f"Veo video generation failed: {err_msg}")

                if hasattr(operation, "response") and operation.response:
                    gen_vids = getattr(operation.response, "generated_videos", [])
                    if gen_vids and hasattr(gen_vids[0], "video"):
                        vid_bytes = getattr(gen_vids[0].video, "video_bytes", None)
                        if vid_bytes:
                            filename = f"gen_{job_id}.mp4"
                            filepath = os.path.join(GENERATED_DIR, filename)
                            with open(filepath, "wb") as f:
                                f.write(vid_bytes)
                            media_url = f"/static/media/generated/{filename}"
                        elif getattr(gen_vids[0].video, "uri", None):
                            media_url = gen_vids[0].video.uri

                if not media_url:
                    raise RuntimeError("Veo video generation operation completed without returning video content.")

            now_iso = datetime.now(timezone.utc).isoformat()

            # Update memory store
            if job_id in _MEM_JOBS:
                _MEM_JOBS[job_id]["status"] = "completed"
                _MEM_JOBS[job_id]["progress"] = 100
                _MEM_JOBS[job_id]["media_url"] = media_url
                _MEM_JOBS[job_id]["completed_at"] = now_iso

            # Update asset in memory store
            asset_dict = {
                "id": f"asset_{job_id}",
                "user_id": user_id,
                "title": req.prompt[:60],
                "media_type": req.media_type,
                "source_type": "generated",
                "url": media_url,
                "thumbnail_url": None,
                "prompt": req.prompt,
                "model": req.model,
                "provider": req.provider,
                "width": width,
                "height": height,
                "duration_seconds": duration_sec,
                "file_size_bytes": None,
                "is_favorite": False,
                "tags": [],
                "created_at": now_iso,
            }
            _MEM_ASSETS.setdefault(user_id, []).insert(0, asset_dict)

            # Persist to DB if available
            factory = get_session_factory()
            if factory is not None:
                try:
                    async with factory() as session:
                        job = (
                            await session.execute(
                                select(MediaGenerationJob).where(MediaGenerationJob.id == job_id)
                            )
                        ).scalars().first()
                        if job:
                            job.status = "completed"
                            job.progress = 100
                            job.media_url = media_url
                            job.completed_at = datetime.now(timezone.utc)
                            session.add(job)

                        asset = MediaAsset(
                            id=asset_dict["id"],
                            user_id=user_id,
                            title=asset_dict["title"],
                            media_type=req.media_type,
                            source_type="generated",
                            url=media_url,
                            prompt=req.prompt,
                            model=req.model,
                            provider=req.provider,
                            width=width,
                            height=height,
                            duration_seconds=duration_sec,
                        )
                        session.add(asset)

                        if req.media_type == "image":
                            gen_img = GeneratedImage(
                                id=job_id,
                                user_id=user_id,
                                prompt=req.prompt,
                                media_url=media_url,
                                media_type="image",
                                style_preset=req.style_preset,
                                aspect_ratio=req.aspect_ratio,
                                width=width,
                                height=height,
                                model=req.model,
                                seed=req.seed,
                            )
                            session.add(gen_img)

                        await session.commit()
                except Exception as db_err:
                    logger.warning(f"Async DB update for job {job_id} failed: {db_err}")

        except Exception as exc:
            logger.error(f"Generation job {job_id} failed: {exc}")
            now_iso = datetime.now(timezone.utc).isoformat()
            if job_id in _MEM_JOBS:
                _MEM_JOBS[job_id]["status"] = "failed"
                _MEM_JOBS[job_id]["error_message"] = str(exc)
                _MEM_JOBS[job_id]["completed_at"] = now_iso

            factory = get_session_factory()
            if factory is not None:
                try:
                    async with factory() as session:
                        job = (
                            await session.execute(
                                select(MediaGenerationJob).where(MediaGenerationJob.id == job_id)
                            )
                        ).scalars().first()
                        if job:
                            job.status = "failed"
                            job.error_message = str(exc)
                            job.completed_at = datetime.now(timezone.utc)
                            session.add(job)
                            await session.commit()
                except Exception:
                    pass

    async def get_job(self, user_id: str, job_id: str) -> MediaJobResponse | None:
        """Retrieve live state of a generation job."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    job = (
                        await session.execute(
                            select(MediaGenerationJob).where(
                                MediaGenerationJob.id == job_id,
                                MediaGenerationJob.user_id == user_id,
                            )
                        )
                    ).scalars().first()
                    if job:
                        return MediaJobResponse(
                            id=job.id,
                            user_id=job.user_id,
                            media_type=job.media_type,
                            provider=job.provider,
                            model=job.model,
                            prompt=job.prompt,
                            status=job.status,
                            progress=job.progress,
                            media_url=job.media_url,
                            thumbnail_url=job.thumbnail_url,
                            error_message=job.error_message,
                            parameters=job.parameters or {},
                            created_at=job.created_at.isoformat(),
                            completed_at=job.completed_at.isoformat() if job.completed_at else None,
                        )
            except Exception:
                pass

        # In-memory lookup
        mem = _MEM_JOBS.get(job_id)
        if mem and mem["user_id"] == user_id:
            return MediaJobResponse(**mem)
        return None

    async def list_jobs(self, user_id: str, limit: int = 50) -> MediaJobListResponse:
        """List recent generation jobs for a user."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    rows = (
                        await session.execute(
                            select(MediaGenerationJob)
                            .where(MediaGenerationJob.user_id == user_id)
                            .order_by(desc(MediaGenerationJob.created_at))
                            .limit(limit)
                        )
                    ).scalars().all()

                    jobs = [
                        MediaJobResponse(
                            id=j.id,
                            user_id=j.user_id,
                            media_type=j.media_type,
                            provider=j.provider,
                            model=j.model,
                            prompt=j.prompt,
                            status=j.status,
                            progress=j.progress,
                            media_url=j.media_url,
                            thumbnail_url=j.thumbnail_url,
                            error_message=j.error_message,
                            parameters=j.parameters or {},
                            created_at=j.created_at.isoformat(),
                            completed_at=j.completed_at.isoformat() if j.completed_at else None,
                        )
                        for j in rows
                    ]
                    if jobs:
                        return MediaJobListResponse(jobs=jobs)
            except Exception:
                pass

        # In-memory lookup
        user_jobs = [
            MediaJobResponse(**j)
            for j in _MEM_JOBS.values()
            if j["user_id"] == user_id
        ]
        return MediaJobListResponse(jobs=user_jobs[:limit])

    async def upload_file(
        self,
        user_id: str,
        filename: str,
        file_bytes: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        """Store actual uploaded user file with SHA-256 deduplication and persist to library."""
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        dest_filename = f"{sha256_hash[:12]}_{safe_name}"
        dest_path = os.path.join(UPLOADS_DIR, dest_filename)

        with open(dest_path, "wb") as f:
            f.write(file_bytes)

        media_url = f"/static/media/uploads/{dest_filename}"
        media_type = "video" if filename.lower().endswith((".mp4", ".mov", ".webm")) else "image"
        now_iso = datetime.now(timezone.utc).isoformat()
        asset_id = f"upl_{uuid.uuid4().hex[:12]}"

        # Always save to in-memory asset library
        asset_dict = {
            "id": asset_id,
            "user_id": user_id,
            "title": filename,
            "media_type": media_type,
            "source_type": "uploaded",
            "url": media_url,
            "thumbnail_url": None,
            "prompt": None,
            "model": None,
            "provider": None,
            "width": None,
            "height": None,
            "duration_seconds": None,
            "file_size_bytes": len(file_bytes),
            "is_favorite": False,
            "tags": ["upload"],
            "created_at": now_iso,
        }
        _MEM_ASSETS.setdefault(user_id, []).insert(0, asset_dict)

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    upl = UploadedMedia(
                        id=asset_id,
                        user_id=user_id,
                        filename=filename,
                        media_url=media_url,
                        media_type=media_type,
                    )
                    session.add(upl)

                    asset = MediaAsset(
                        id=asset_id,
                        user_id=user_id,
                        title=filename,
                        media_type=media_type,
                        source_type="uploaded",
                        url=media_url,
                        file_size_bytes=len(file_bytes),
                        mime_type=content_type,
                    )
                    session.add(asset)
                    await session.commit()
            except Exception as exc:
                logger.warning(f"DB upload persistence failed, memory fallback active: {exc}")

        return {
            "id": asset_id,
            "filename": filename,
            "media_url": media_url,
            "media_type": media_type,
            "file_size_bytes": len(file_bytes),
            "created_at": now_iso,
        }

    async def list_assets(
        self,
        user_id: str,
        media_type: str | None = None,
        favorite_only: bool = False,
        limit: int = 100,
    ) -> MediaAssetListResponse:
        """Retrieve user's central media asset library."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(MediaAsset).where(MediaAsset.user_id == user_id)
                    if media_type:
                        stmt = stmt.where(MediaAsset.media_type == media_type)
                    if favorite_only:
                        stmt = stmt.where(MediaAsset.is_favorite == True)  # noqa: E712
                    stmt = stmt.order_by(desc(MediaAsset.created_at)).limit(limit)

                    rows = (await session.execute(stmt)).scalars().all()
                    if rows:
                        assets = [
                            MediaAssetResponse(
                                id=a.id,
                                title=a.title,
                                media_type=a.media_type,
                                source_type=a.source_type,
                                url=a.url,
                                thumbnail_url=a.thumbnail_url,
                                prompt=a.prompt,
                                model=a.model,
                                provider=a.provider,
                                width=a.width,
                                height=a.height,
                                duration_seconds=a.duration_seconds,
                                file_size_bytes=a.file_size_bytes,
                                is_favorite=a.is_favorite,
                                tags=a.tags or [],
                                created_at=a.created_at.isoformat(),
                            )
                            for a in rows
                        ]
                        return MediaAssetListResponse(assets=assets)
            except Exception:
                pass

        # In-memory lookup
        items = _MEM_ASSETS.get(user_id, [])
        filtered = [
            MediaAssetResponse(**a)
            for a in items
            if (not media_type or a["media_type"] == media_type)
            and (not favorite_only or a["is_favorite"])
        ]
        return MediaAssetListResponse(assets=filtered[:limit])

    async def toggle_favorite(self, user_id: str, asset_id: str) -> bool:
        """Toggle favorite state on a media asset."""
        # Update in-memory
        for a in _MEM_ASSETS.get(user_id, []):
            if a["id"] == asset_id:
                a["is_favorite"] = not a["is_favorite"]
                return a["is_favorite"]

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    asset = (
                        await session.execute(
                            select(MediaAsset).where(
                                MediaAsset.id == asset_id,
                                MediaAsset.user_id == user_id,
                            )
                        )
                    ).scalars().first()
                    if asset:
                        asset.is_favorite = not asset.is_favorite
                        session.add(asset)
                        await session.commit()
                        return asset.is_favorite
            except Exception:
                pass

        return False
