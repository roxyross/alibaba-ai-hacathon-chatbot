"""Phase 10 Master Integration Test Suite: Image Studio & Multimodal Creative Engine.

Verifies:
1. Fresh user empty state (zero generations, zero uploads).
2. Studio configuration endpoint (styles, aspect ratios, models).
3. Neural image generation with style presets, aspect ratios, and dimensions.
4. AI-assisted prompt enhancement endpoint.
5. Favoriting and gallery filtering.
6. Single generation retrieval and deletion.
7. Knowledge Vault artwork export and document indexing.
8. Uploaded reference assets management.
9. Strict multi-tenant isolation across generations, uploads, and vault exports.
10. Multi-agent chat image generation automatically recording to Image Studio gallery.
"""

from __future__ import annotations

import io
import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

sys.path.insert(0, "src")

from app.images.repository import clear_in_memory_stores as clear_images
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


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    clear_images()


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Return (auth_headers, user_id)."""
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    verify_data = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()
    token = verify_data["access_token"]
    user_id = verify_data["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, user_id


# -----------------------------------------------------------------------------
# 1. Fresh User Empty State
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_empty_state(client: httpx.AsyncClient) -> None:
    """Verify fresh user starts with empty generations and uploads, and non-existent image returns 404."""
    auth, _ = await _get_auth(client, f"img_fresh_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generations empty
    gens_resp = await client.get("/api/v1/images/generations", headers=auth)
    assert gens_resp.status_code == 200
    assert gens_resp.json()["generations"] == []

    # Uploads empty
    upl_resp = await client.get("/api/v1/images/uploads", headers=auth)
    assert upl_resp.status_code == 200
    assert upl_resp.json()["uploads"] == []

    # Accessing non-existent image returns 404
    fake_id = f"gen-{uuid.uuid4().hex[:12]}"
    res_404 = await client.get(f"/api/v1/images/{fake_id}", headers=auth)
    assert res_404.status_code == 404


# -----------------------------------------------------------------------------
# 2. Studio Configuration
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_config(client: httpx.AsyncClient) -> None:
    """Verify studio configuration exposes supported styles, models, and aspect ratios."""
    resp = await client.get("/api/v1/images/config")
    assert resp.status_code == 200
    data = resp.json()

    assert "styles" in data
    assert "photorealistic" in data["styles"]
    assert "cinematic" in data["styles"]
    assert "anime" in data["styles"]
    assert "cyberpunk" in data["styles"]

    assert "aspect_ratios" in data
    assert "1:1" in data["aspect_ratios"]
    assert "16:9" in data["aspect_ratios"]

    assert "models" in data
    assert any(m["id"] == "flux" for m in data["models"])


# -----------------------------------------------------------------------------
# 3. Neural Image Generation & Dimensions
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_generation_and_dimensions(client: httpx.AsyncClient) -> None:
    """Verify neural image generation maps aspect ratio to dimensions and returns media URL."""
    auth, user_id = await _get_auth(client, f"img_gen_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generate 16:9 landscape cyberpunk image
    req_body = {
        "prompt": "Futuristic neon high-speed train cutting through foggy mountains",
        "style_preset": "cyberpunk",
        "aspect_ratio": "16:9",
        "model": "flux",
        "seed": 424242,
    }
    resp = await client.post("/api/v1/images/generate", headers=auth, json=req_body)
    assert resp.status_code == 200
    gen = resp.json()["generation"]

    assert gen["user_id"] == user_id
    assert gen["prompt"] == req_body["prompt"]
    assert gen["style_preset"] == "cyberpunk"
    assert gen["aspect_ratio"] == "16:9"
    assert gen["width"] == 1344
    assert gen["height"] == 768
    assert gen["seed"] == 424242
    assert "pollinations.ai" in gen["media_url"]
    assert "width=1344" in gen["media_url"]
    assert "height=768" in gen["media_url"]

    # Verify generation is in user's list
    list_resp = await client.get("/api/v1/images/generations", headers=auth)
    assert list_resp.status_code == 200
    items = list_resp.json()["generations"]
    assert len(items) == 1
    assert items[0]["id"] == gen["id"]


# -----------------------------------------------------------------------------
# 4. Prompt Enhancer
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_prompt_enhancer(client: httpx.AsyncClient) -> None:
    """Verify prompt enhancer augments basic prompts with stylistic nuances."""
    auth, _ = await _get_auth(client, f"img_enh_{uuid.uuid4().hex[:6]}@roxy.ai")

    resp = await client.post(
        "/api/v1/images/enhance-prompt",
        headers=auth,
        json={"prompt": "ancient marble temple on a cliff", "style_preset": "cinematic"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "enhanced_prompt" in data
    assert "ancient marble temple" in data["enhanced_prompt"]
    assert "cinematic" in data["enhanced_prompt"].lower() or "lighting" in data["enhanced_prompt"].lower()


# -----------------------------------------------------------------------------
# 5. Favorites & Gallery Filtering
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_favorites_and_filtering(client: httpx.AsyncClient) -> None:
    """Verify favoriting and filtering gallery by favorites."""
    auth, _ = await _get_auth(client, f"img_fav_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generate Image 1
    g1 = (await client.post(
        "/api/v1/images/generate",
        headers=auth,
        json={"prompt": "Artwork One", "style_preset": "anime"},
    )).json()["generation"]

    # Generate Image 2
    g2 = (await client.post(
        "/api/v1/images/generate",
        headers=auth,
        json={"prompt": "Artwork Two", "style_preset": "oil_painting"},
    )).json()["generation"]

    # Toggle favorite on Image 1
    fav_resp = await client.post(f"/api/v1/images/{g1['id']}/favorite", headers=auth)
    assert fav_resp.status_code == 200
    assert fav_resp.json()["generation"]["is_favorite"] is True

    # Filter favorite_only=true -> only g1
    fav_list = await client.get("/api/v1/images/generations?favorite=true", headers=auth)
    assert fav_list.status_code == 200
    fav_items = fav_list.json()["generations"]
    assert len(fav_items) == 1
    assert fav_items[0]["id"] == g1["id"]

    # Full list -> both g1 and g2
    all_list = await client.get("/api/v1/images/generations", headers=auth)
    assert len(all_list.json()["generations"]) == 2

    # Delete Image 2
    del_resp = await client.delete(f"/api/v1/images/{g2['id']}", headers=auth)
    assert del_resp.status_code == 200

    # Verify Image 2 is gone
    get_g2 = await client.get(f"/api/v1/images/{g2['id']}", headers=auth)
    assert get_g2.status_code == 404
    rem_list = await client.get("/api/v1/images/generations", headers=auth)
    assert len(rem_list.json()["generations"]) == 1


# -----------------------------------------------------------------------------
# 6. Knowledge Vault Export
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_save_to_knowledge_vault(client: httpx.AsyncClient) -> None:
    """Verify exporting generated artwork to Knowledge Vault indexes it as a document."""
    auth, user_id = await _get_auth(client, f"img_vault_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generate Image
    gen = (await client.post(
        "/api/v1/images/generate",
        headers=auth,
        json={"prompt": "Deep sea bioluminescent coral reef", "style_preset": "photorealistic"},
    )).json()["generation"]

    # Save to Vault
    vault_resp = await client.post(f"/api/v1/images/{gen['id']}/save-to-vault", headers=auth)
    assert vault_resp.status_code == 200
    v_data = vault_resp.json()
    assert v_data["vault_document_id"] is not None
    assert f"doc_art_{gen['id']}" in v_data["vault_document_id"]

    # Verify Knowledge Vault document list includes the artwork
    docs_resp = await client.get("/api/v1/documents", headers=auth)
    assert docs_resp.status_code == 200
    docs = docs_resp.json()["documents"]
    assert any(gen["id"] in d["document_id"] for d in docs)


# -----------------------------------------------------------------------------
# 7. Upload Reference Assets
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_upload_reference_assets(client: httpx.AsyncClient) -> None:
    """Verify uploading reference assets and deleting them."""
    auth, _ = await _get_auth(client, f"img_upl_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Upload mock reference image
    file_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
    files = {"file": ("reference_moodboard.png", io.BytesIO(file_bytes), "image/png")}

    upl_resp = await client.post("/api/v1/images/upload", headers=auth, files=files)
    assert upl_resp.status_code == 200
    upload = upl_resp.json()["upload"]
    assert upload["filename"] == "reference_moodboard.png"
    upload_id = upload["id"]

    # List uploads
    list_upl = await client.get("/api/v1/images/uploads", headers=auth)
    assert list_upl.status_code == 200
    assert len(list_upl.json()["uploads"]) == 1

    # Delete upload
    del_upl = await client.delete(f"/api/v1/images/uploads/{upload_id}", headers=auth)
    assert del_upl.status_code == 200

    # Verify empty
    list_upl2 = await client.get("/api/v1/images/uploads", headers=auth)
    assert len(list_upl2.json()["uploads"]) == 0


# -----------------------------------------------------------------------------
# 8. Strict Multi-Tenant Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """Verify User B cannot view, favorite, delete, or export User A's generated images."""
    auth_a, user_a_id = await _get_auth(client, f"user_a_studio_{uuid.uuid4().hex[:6]}@roxy.ai")
    auth_b, user_b_id = await _get_auth(client, f"user_b_studio_{uuid.uuid4().hex[:6]}@roxy.ai")
    assert user_a_id != user_b_id

    # User A creates image
    gen_a = (await client.post(
        "/api/v1/images/generate",
        headers=auth_a,
        json={"prompt": "User A Private Concept Art", "style_preset": "3d_render"},
    )).json()["generation"]
    a_id = gen_a["id"]

    # User B list -> does NOT see User A's image
    b_list = await client.get("/api/v1/images/generations", headers=auth_b)
    assert b_list.status_code == 200
    assert all(img["id"] != a_id for img in b_list.json()["generations"])

    # User B get -> 404
    b_get = await client.get(f"/api/v1/images/{a_id}", headers=auth_b)
    assert b_get.status_code == 404

    # User B favorite -> 404
    b_fav = await client.post(f"/api/v1/images/{a_id}/favorite", headers=auth_b)
    assert b_fav.status_code == 404

    # User B save to vault -> 404
    b_vault = await client.post(f"/api/v1/images/{a_id}/save-to-vault", headers=auth_b)
    assert b_vault.status_code == 404

    # User B delete -> 404
    b_del = await client.delete(f"/api/v1/images/{a_id}", headers=auth_b)
    assert b_del.status_code == 404

    # User A image remains unaffected
    a_verify = await client.get(f"/api/v1/images/{a_id}", headers=auth_a)
    assert a_verify.status_code == 200
    assert a_verify.json()["generation"]["prompt"] == "User A Private Concept Art"


# -----------------------------------------------------------------------------
# 9. Multi-Agent Chat Synchronization
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_chat_image_generation_persistence(client: httpx.AsyncClient) -> None:
    """Verify that asking Roxy in chat to create an image automatically persists to Image Studio."""
    auth, user_id = await _get_auth(client, f"chat_img_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Ask chat to create an image
    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        headers=auth,
        json={"message": "create an image of a cybernetic tiger in a bamboo forest"},
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert "response" in chat_data
    assert "https://image.pollinations.ai" in chat_data["response"]

    # Verify image was automatically recorded into User's Image Studio gallery
    gallery_resp = await client.get("/api/v1/images/generations", headers=auth)
    assert gallery_resp.status_code == 200
    gallery_items = gallery_resp.json()["generations"]
    assert len(gallery_items) >= 1
    assert "cybernetic tiger" in gallery_items[0]["prompt"].lower()
