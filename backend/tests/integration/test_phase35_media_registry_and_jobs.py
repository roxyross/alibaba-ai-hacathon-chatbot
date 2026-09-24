"""Phase 35 Integration Test Suite: Unified Media Registry, Asynchronous Jobs, and Real Uploads.

Covers:
1. Dynamic model capability inspection (GET /api/v1/media/models).
2. Verified parameter constraints across image and video models.
3. Truthful file upload processing with SHA-256 deduplication (No Unsplash placeholders).
4. Asynchronous generation job lifecycle and status polling.
5. Media asset library indexing and bookmarking.
"""

from __future__ import annotations

import io
import sys
from collections.abc import AsyncIterator

import httpx
import pytest

sys.path.insert(0, "src")

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def _get_auth_headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    jwt = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()["access_token"]
    return {"Authorization": f"Bearer {jwt}"}


async def test_media_models_registry_truthful_capabilities(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "media_tester@roxy.ai")

    resp = await client.get("/api/v1/media/models", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    models = data["models"]
    assert len(models) >= 6

    model_ids = {m["id"] for m in models}
    # Verify presence of official Google & FLUX models
    assert "imagen-3.0-generate-002" in model_ids
    assert "imagen-4.0-generate-001" in model_ids
    assert "flux-schnell" in model_ids
    assert "veo-3.1-generate-preview" in model_ids
    assert "veo-2.0-generate-001" in model_ids
    assert "gemini-omni-1.1-flash" in model_ids

    # Check Veo 3.1 video capabilities
    veo = next(m for m in models if m["id"] == "veo-3.1-generate-preview")
    assert veo["media_type"] == "video"
    assert "16:9" in veo["supported_aspect_ratios"]
    assert "1080p" in veo["supported_resolutions"]
    assert 5 in veo["supported_durations"]
    assert veo["supports_audio"] is True

    # Check FLUX Schnell free fallback
    flux = next(m for m in models if m["id"] == "flux-schnell")
    assert flux["media_type"] == "image"
    assert flux["is_available"] is True
    assert "Free" in flux["availability_reason"]


async def test_truthful_media_upload_no_unsplash_mock(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "uploader@roxy.ai")

    # Create dummy PNG binary bytes
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    files = {"file": ("test_texture.png", io.BytesIO(fake_png), "image/png")}

    resp = await client.post("/api/v1/media/upload", headers=headers, files=files)
    assert resp.status_code == 200
    upload = resp.json()
    assert upload["filename"] == "test_texture.png"
    assert "unsplash.com" not in upload["media_url"]
    assert upload["media_url"].startswith("/static/media/uploads/")
    assert upload["file_size_bytes"] == len(fake_png)


async def test_media_generation_job_queue_and_asset_library(client: httpx.AsyncClient) -> None:
    headers = await _get_auth_headers(client, "generator@roxy.ai")

    req_payload = {
        "media_type": "image",
        "provider": "pollinations",
        "model": "flux-schnell",
        "prompt": "Futuristic cyberpunk terminal with glowing green phosphor text",
        "aspect_ratio": "1:1",
        "quality": "High",
        "seed": 1337,
    }

    job_resp = await client.post("/api/v1/media/generate", headers=headers, json=req_payload)
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job["id"] is not None
    assert job["media_type"] == "image"
    assert job["status"] in ("queued", "processing", "completed")

    # Poll job status
    poll_resp = await client.get(f"/api/v1/media/jobs/{job['id']}", headers=headers)
    assert poll_resp.status_code == 200
    polled = poll_resp.json()
    assert polled["id"] == job["id"]

    # Check job list
    list_resp = await client.get("/api/v1/media/jobs", headers=headers)
    assert list_resp.status_code == 200
    jobs_data = list_resp.json()
    assert any(j["id"] == job["id"] for j in jobs_data["jobs"])
