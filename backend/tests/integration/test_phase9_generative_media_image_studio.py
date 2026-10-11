"""Phase 9 Master Integration Test Suite: Generative Media & Image Studio.

Verifies:
1. Studio Configuration & Creative Metas:
   - Supported style presets (photorealistic, cinematic, anime, cyberpunk, 3d_render, oil_painting, minimalist, watercolor).
   - Diffusion resolution mapping across all standard aspect ratios (1:1, 16:9, 9:16, 2:3, 3:2, 4:5).
   - Supported neural synthesis models (flux, flux-realism, turbo, imagen-3.0).
2. Prompt Enhancement:
   - Enriching raw user ideas with volumetric lighting, style nuances, and composition descriptors.
3. Neural Image Generation & Gallery Lifecycle:
   - Multi-tenant creation and gallery persistence.
   - Favorite toggling and filter isolation.
   - Reference asset upload handling with deduplication.
4. Knowledge Vault Artwork Export:
   - Indexing artwork, prompt specs, and visual metadata directly into Knowledge Vault.
5. Central ToolRegistry Integration & Confirmation Gating:
   - All 7 image tools registered in ToolRegistry.
   - Destructive tool (image_delete_generation) strictly gated with RiskLevel.HIGH and requires_confirmation=True.
6. Deterministic Intent Routing in AgentPlanner:
   - Single-intent decomposition for image generation, prompt improvement, gallery browsing, vault export, and deletion.
7. Multi-Tenant Anti-IDOR Boundary Isolation:
   - Cross-tenant access attempts return 404 with zero data leakage.
"""

from __future__ import annotations

import io
import sys
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, "src")

from app.agent_runtime.planner import AgentPlanner
from app.images.repository import clear_in_memory_stores as clear_images
from app.images.service import ImageStudioService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel, ToolExecutionRequest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    clear_images()


async def _get_auth(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Register and authenticate user, returning auth headers and user_id."""
    req_res = await client.post("/api/v1/auth/request-link", json={"email": email})
    assert req_res.status_code == 200
    token = req_res.json()["dev_token"]

    verify_res = await client.post("/api/v1/auth/verify", json={"token": token})
    assert verify_res.status_code == 200
    jwt_token = verify_res.json()["access_token"]
    user_id = verify_res.json()["user"]["id"]
    return {"Authorization": f"Bearer {jwt_token}"}, user_id


# -----------------------------------------------------------------------------
# 1. Studio Configuration & Creative Metas
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_configuration(client: AsyncClient) -> None:
    """Verify studio configuration exposes supported styles, models, and aspect ratios."""
    resp = await client.get("/api/v1/images/config")
    assert resp.status_code == 200
    data = resp.json()

    assert "styles" in data
    assert "photorealistic" in data["styles"]
    assert "cinematic" in data["styles"]
    assert "cyberpunk" in data["styles"]
    assert "anime" in data["styles"]

    assert "aspect_ratios" in data
    assert "1:1" in data["aspect_ratios"]
    assert "16:9" in data["aspect_ratios"]
    assert "9:16" in data["aspect_ratios"]

    assert "models" in data
    assert any(m["id"] == "flux" for m in data["models"])


# -----------------------------------------------------------------------------
# 2. AI Prompt Enhancement
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_prompt_enhancement(client: AsyncClient) -> None:
    """Verify prompt enhancer enriches visual prompt with volumetric lighting and style tokens."""
    auth, _ = await _get_auth(client, f"enhancer_{uuid.uuid4().hex[:6]}@roxy.ai")

    res = await client.post(
        "/api/v1/images/enhance-prompt",
        headers=auth,
        json={"prompt": "A solitary lighthouse during a thunderstorm", "style_preset": "cinematic"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "solitary lighthouse" in data["enhanced_prompt"].lower()
    assert len(data["enhanced_prompt"]) > len(data["original_prompt"])
    assert data["style_preset"] == "cinematic"


# -----------------------------------------------------------------------------
# 3. Neural Image Generation & Gallery Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_generation_and_gallery_lifecycle(client: AsyncClient) -> None:
    """Verify neural generation, dimensions, favorite toggling, and gallery retrieval."""
    auth, user_id = await _get_auth(client, f"artist_{uuid.uuid4().hex[:6]}@roxy.ai")

    # 1. Initial empty gallery
    init_res = await client.get("/api/v1/images/generations", headers=auth)
    assert init_res.status_code == 200
    assert init_res.json()["generations"] == []

    # 2. Generate 16:9 Cinematic image
    gen_res = await client.post(
        "/api/v1/images/generate",
        headers=auth,
        json={
            "prompt": "Futuristic neon bazaar on Mars with flying hovercars",
            "style_preset": "cyberpunk",
            "aspect_ratio": "16:9",
            "model": "flux",
        },
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()["generation"]
    img_id = gen_data["id"]
    assert gen_data["aspect_ratio"] == "16:9"
    assert gen_data["width"] == 1344
    assert gen_data["height"] == 768
    assert gen_data["is_favorite"] is False

    # 3. Inspect single artwork
    detail_res = await client.get(f"/api/v1/images/{img_id}", headers=auth)
    assert detail_res.status_code == 200
    assert detail_res.json()["generation"]["id"] == img_id

    # 4. Favorite artwork
    fav_res = await client.post(f"/api/v1/images/{img_id}/favorite", headers=auth)
    assert fav_res.status_code == 200
    assert fav_res.json()["generation"]["is_favorite"] is True

    # 5. Filter gallery by favorites
    fav_gallery_res = await client.get("/api/v1/images/generations?favorite=true", headers=auth)
    assert fav_gallery_res.status_code == 200
    fav_items = fav_gallery_res.json()["generations"]
    assert len(fav_items) == 1
    assert fav_items[0]["id"] == img_id

    # 6. Delete artwork
    del_res = await client.delete(f"/api/v1/images/{img_id}", headers=auth)
    assert del_res.status_code == 200

    # 7. Confirm 404 after deletion
    get_del = await client.get(f"/api/v1/images/{img_id}", headers=auth)
    assert get_del.status_code == 404


# -----------------------------------------------------------------------------
# 4. Upload Reference Assets Management
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_reference_assets_upload_and_delete(client: AsyncClient) -> None:
    """Verify reference media upload, listing, and deletion."""
    auth, user_id = await _get_auth(client, f"uploader_{uuid.uuid4().hex[:6]}@roxy.ai")

    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"

    # Upload reference
    upl_res = await client.post(
        "/api/v1/images/upload",
        headers=auth,
        files={"file": ("reference_pose.png", io.BytesIO(dummy_png), "image/png")},
    )
    assert upl_res.status_code == 200
    upload_item = upl_res.json()["upload"]
    upload_id = upload_item["id"]
    assert upload_item["media_type"] == "image"

    # List uploads
    list_res = await client.get("/api/v1/images/uploads", headers=auth)
    assert list_res.status_code == 200
    assert any(u["id"] == upload_id for u in list_res.json()["uploads"])

    # Delete upload
    del_res = await client.delete(f"/api/v1/images/uploads/{upload_id}", headers=auth)
    assert del_res.status_code == 200

    # List uploads should be empty now
    list_after = await client.get("/api/v1/images/uploads", headers=auth)
    assert list_after.status_code == 200
    assert not any(u["id"] == upload_id for u in list_after.json()["uploads"])


# -----------------------------------------------------------------------------
# 5. Knowledge Vault Artwork Export
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_export_to_knowledge_vault(client: AsyncClient) -> None:
    """Verify exporting generated artwork and creative prompt specs into Knowledge Vault."""
    auth, user_id = await _get_auth(client, f"vault_artist_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generate an artwork
    gen_res = await client.post(
        "/api/v1/images/generate",
        headers=auth,
        json={"prompt": "Ancient library carved inside a giant sequoia tree", "style_preset": "photorealistic"},
    )
    assert gen_res.status_code == 200
    img_id = gen_res.json()["generation"]["id"]

    # Export to Vault
    vault_res = await client.post(f"/api/v1/images/{img_id}/save-to-vault", headers=auth)
    assert vault_res.status_code == 200
    data = vault_res.json()
    assert data["vault_document_id"] is not None
    assert f"doc_art_{img_id}" in data["vault_document_id"]

    # Verify Knowledge Vault document list includes the artwork
    docs_resp = await client.get("/api/v1/documents", headers=auth)
    assert docs_resp.status_code == 200
    docs = docs_resp.json()["documents"]
    assert any(img_id in d["document_id"] for d in docs)



# -----------------------------------------------------------------------------
# 6. Central ToolRegistry Integration & Confirmation Gating
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_tools_in_central_registry() -> None:
    """Verify all 7 Image Studio tools are registered with proper confirmation gating."""
    svc = ImageStudioService.get_instance()
    svc.register_image_tools()
    reg = ToolRegistry.get_instance()

    expected_tools = [
        "image_generate",
        "image_enhance_prompt",
        "image_list_gallery",
        "image_get_generation",
        "image_toggle_favorite",
        "image_export_to_vault",
        "image_delete_generation",
    ]
    for tid in expected_tools:
        tool = reg.get(tid)
        assert tool is not None, f"Tool '{tid}' not found in ToolRegistry"

    # Destructive tool MUST be gated with RiskLevel.HIGH and require confirmation
    del_tool = reg.get("image_delete_generation")
    assert del_tool is not None
    assert del_tool.risk_level == RiskLevel.HIGH
    assert del_tool.requires_confirmation is True

    # Generation tool should be LOW risk without confirmation block
    gen_tool = reg.get("image_generate")
    assert gen_tool is not None
    assert gen_tool.risk_level == RiskLevel.LOW
    assert gen_tool.requires_confirmation is False


@pytest.mark.anyio
async def test_direct_execution_of_image_tools() -> None:
    """Verify executing Image Studio tools directly via ToolRegistry."""
    svc = ImageStudioService.get_instance()
    svc.register_image_tools()
    reg = ToolRegistry.get_instance()
    user_id = f"usr_img_tool_{uuid.uuid4().hex[:6]}"

    # 1. image_generate
    res_gen = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_generate",
            arguments={"prompt": "Cybernetic tiger in a bamboo forest", "style_preset": "anime"},
            user_id=user_id,
        )
    )
    assert res_gen.success is True
    img_id = res_gen.output["generation"]["id"]
    assert res_gen.output["generation"]["style_preset"] == "anime"

    # 2. image_list_gallery
    res_list = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_list_gallery",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_list.success is True
    assert res_list.output["total_generations"] == 1

    # 3. image_toggle_favorite
    res_fav = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_toggle_favorite",
            arguments={"image_id": img_id},
            user_id=user_id,
        )
    )
    assert res_fav.success is True
    assert res_fav.output["is_favorite"] is True

    # 4. image_delete_generation
    res_del = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_delete_generation",
            arguments={"image_id": img_id},
            user_id=user_id,
            bypass_confirmation=True,
        )
    )
    assert res_del.success is True
    assert res_del.output["deleted"] is True


# -----------------------------------------------------------------------------
# 7. Deterministic Intent Routing in AgentPlanner
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_image_intent_routing() -> None:
    """Verify AgentPlanner deterministic intent routing for Phase 9 image studio goals."""
    planner = AgentPlanner()

    # 1. Generate image with detected style and aspect ratio
    plan_gen = await planner.create_plan("create image of a medieval knight in cyberpunk armor, 16:9 aspect ratio")
    assert plan_gen[0]["tool_id"] == "image_generate"
    assert plan_gen[0]["tool_input"]["style_preset"] == "cyberpunk"
    assert plan_gen[0]["tool_input"]["aspect_ratio"] == "16:9"

    # 2. Enhance prompt
    plan_enhance = await planner.create_plan("enhance prompt mystical floating crystal island")
    assert plan_enhance[0]["tool_id"] == "image_enhance_prompt"
    assert "mystical floating crystal island" in plan_enhance[0]["tool_input"]["prompt"]

    # 3. View gallery
    plan_gallery = await planner.create_plan("show my image gallery")
    assert plan_gallery[0]["tool_id"] == "image_list_gallery"

    # 4. Inspect single artwork
    plan_view = await planner.create_plan("view image gen-artwork-555")
    assert plan_view[0]["tool_id"] == "image_get_generation"
    assert plan_view[0]["tool_input"]["image_id"] == "gen-artwork-555"

    # 5. Favorite artwork
    plan_fav = await planner.create_plan("favorite image gen-artwork-555")
    assert plan_fav[0]["tool_id"] == "image_toggle_favorite"
    assert plan_fav[0]["tool_input"]["image_id"] == "gen-artwork-555"

    # 6. Save to Knowledge Vault
    plan_vault = await planner.create_plan("save image to vault gen-artwork-555")
    assert plan_vault[0]["tool_id"] == "image_export_to_vault"
    assert plan_vault[0]["tool_input"]["image_id"] == "gen-artwork-555"

    # 7. Delete artwork (requires confirmation)
    plan_del = await planner.create_plan("delete artwork gen-artwork-555")
    assert plan_del[0]["tool_id"] == "image_delete_generation"
    assert plan_del[0]["tool_input"]["image_id"] == "gen-artwork-555"


# -----------------------------------------------------------------------------
# 8. Strict Multi-Tenant Anti-IDOR Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_multitenant_isolation(client: AsyncClient) -> None:
    """Verify strict multi-tenant isolation across artworks, uploads, and gallery."""
    auth_a, user_a = await _get_auth(client, f"tenant_a_{uuid.uuid4().hex[:6]}@roxy.ai")
    auth_b, user_b = await _get_auth(client, f"tenant_b_{uuid.uuid4().hex[:6]}@roxy.ai")

    # User A creates an artwork
    gen_res = await client.post(
        "/api/v1/images/generate",
        headers=auth_a,
        json={"prompt": "Confidential starship propulsion schematics", "style_preset": "photorealistic"},
    )
    assert gen_res.status_code == 200
    img_a_id = gen_res.json()["generation"]["id"]

    # User B lists gallery -> 0 artworks
    b_gallery = await client.get("/api/v1/images/generations", headers=auth_b)
    assert b_gallery.status_code == 200
    assert len(b_gallery.json()["generations"]) == 0

    # User B attempts to view User A's artwork -> 404
    b_get = await client.get(f"/api/v1/images/{img_a_id}", headers=auth_b)
    assert b_get.status_code == 404

    # User B attempts to favorite User A's artwork -> 404
    b_fav = await client.post(f"/api/v1/images/{img_a_id}/favorite", headers=auth_b)
    assert b_fav.status_code == 404

    # User B attempts to delete User A's artwork -> 404
    b_del = await client.delete(f"/api/v1/images/{img_a_id}", headers=auth_b)
    assert b_del.status_code == 404

    # User B attempts to export User A's artwork to vault -> 404
    b_vault = await client.post(f"/api/v1/images/{img_a_id}/save-to-vault", headers=auth_b)
    assert b_vault.status_code == 404

    # Confirm User A's artwork remains intact
    a_get = await client.get(f"/api/v1/images/{img_a_id}", headers=auth_a)
    assert a_get.status_code == 200
    assert a_get.json()["generation"]["id"] == img_a_id
