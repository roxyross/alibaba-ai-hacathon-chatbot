"""Phase 36 Integration Tests: Video Studio, Multi-Track Sequencer & Canvas Inpainting APIs."""

from __future__ import annotations

import io
import sys
import uuid
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


@pytest.mark.anyio
async def test_video_generation_dispatch_and_polling(client: httpx.AsyncClient) -> None:
    """Test video generation dispatch and truthful status polling."""
    auth = await _get_auth_headers(client, f"vid_{uuid.uuid4().hex[:6]}@roxy.ai")

    # 1. Dispatch video generation
    resp = await client.post(
        "/api/v1/media/generate",
        headers=auth,
        json={
            "prompt": "Cinematic drone shot flying over a cybernetic neon city",
            "media_type": "video",
            "model": "veo-3.1-generate-preview",
            "duration": 5.0,
            "aspect_ratio": "16:9",
            "resolution": "1080p",
        },
    )
    assert resp.status_code == 200
    job = resp.json()
    assert "id" in job
    assert job["media_type"] == "video"
    assert job["model"] == "veo-3.1-generate-preview"
    assert job["status"] in ("pending", "processing", "queued")

    # 2. Check job status polling
    poll_resp = await client.get(f"/api/v1/media/jobs/{job['id']}", headers=auth)
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["id"] == job["id"]
    assert poll_data["media_type"] == "video"


@pytest.mark.anyio
async def test_canvas_inpaint_dispatch_and_asset_library_filtering(client: httpx.AsyncClient) -> None:
    """Test Canvas inpaint job submission and media asset library filtering."""
    auth = await _get_auth_headers(client, f"canvas_{uuid.uuid4().hex[:6]}@roxy.ai")

    # 1. Dispatch an inpaint synthesis job with mask and reference image
    fake_base_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    fake_mask_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    res = await client.post(
        "/api/v1/media/generate",
        headers=auth,
        json={
            "prompt": "Add futuristic glowing glasses on subject",
            "media_type": "image",
            "model": "flux",
            "reference_images": [fake_base_img],
            "mask_image": fake_mask_img,
        },
    )
    assert res.status_code == 200
    job_data = res.json()
    assert job_data["prompt"] == "Add futuristic glowing glasses on subject"
    assert job_data["media_type"] == "image"

    # 2. Upload video asset and verify asset library filtering
    fake_video_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42..."
    files = {"file": ("intro_clip.mp4", io.BytesIO(fake_video_bytes), "video/mp4")}
    upl_res = await client.post("/api/v1/media/upload", headers=auth, files=files)
    assert upl_res.status_code == 200
    upload = upl_res.json()
    assert upload["media_type"] == "video"
    assert upload["filename"] == "intro_clip.mp4"
    asset_id = upload["id"]

    # 3. Query asset library for video only
    lib_res = await client.get("/api/v1/media/assets?media_type=video", headers=auth)
    assert lib_res.status_code == 200
    assets = lib_res.json()["assets"]
    assert any(a["id"] == asset_id for a in assets)
    assert all(a["media_type"] == "video" for a in assets)

    # 4. Query asset library for image only
    img_lib_res = await client.get("/api/v1/media/assets?media_type=image", headers=auth)
    assert img_lib_res.status_code == 200
    img_assets = img_lib_res.json()["assets"]
    assert not any(a["id"] == asset_id for a in img_assets)
