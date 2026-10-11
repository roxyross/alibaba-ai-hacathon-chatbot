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
import json
import sys
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

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


@pytest.mark.anyio
async def test_chat_streaming_image_generation_persistence(client: httpx.AsyncClient) -> None:
    """Verify that asking Roxy in streaming chat to create an image automatically persists to Image Studio."""
    auth, user_id = await _get_auth(client, f"chat_img_str_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Ask streaming chat to create an image
    stream_resp = await client.post(
        "/api/v1/runtime/chat/stream",
        headers=auth,
        json={"message": "create an image of a futuristic floating metropolis at dusk"},
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")

    # Parse SSE stream chunks
    full_text = ""
    for raw_line in stream_resp.text.splitlines():
        line = raw_line.strip()
        if line.startswith("data:"):
            payload_str = line[len("data:"):].strip()
            if payload_str:
                chunk = json.loads(payload_str)
                full_text += chunk.get("delta", "")

    assert "https://image.pollinations.ai" in full_text
    assert "futuristic floating metropolis" in full_text.lower()

    # Verify image was automatically recorded into User's Image Studio gallery
    gallery_resp = await client.get("/api/v1/images/generations", headers=auth)
    assert gallery_resp.status_code == 200
    gallery_items = gallery_resp.json()["generations"]
    assert len(gallery_items) >= 1
    assert any("futuristic floating metropolis" in g["prompt"].lower() for g in gallery_items)


@pytest.mark.anyio
async def test_image_gallery_chat_grounding(client: httpx.AsyncClient) -> None:
    """Verify that asking Roxy about saved images/gallery grounds against authentic Image Studio generations."""
    auth, user_id = await _get_auth(client, f"gallery_chat_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generate an artwork via Studio API first
    gen_payload = {
        "prompt": "bioluminescent crystal caverns with waterfalls",
        "style_preset": "fantasy",
        "aspect_ratio": "16:9",
    }
    gen_resp = await client.post("/api/v1/images/generate", headers=auth, json=gen_payload)
    assert gen_resp.status_code == 200

    mock_response = AsyncMock()
    mock_response.content = "Here is your saved artwork: bioluminescent crystal caverns with waterfalls."
    mock_response.provider = "mock_provider"
    mock_response.model = "mock_model"

    with patch("app.api.v1.runtime.AIRouter.route", return_value=mock_response) as mock_route:
        chat_resp = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "What artwork in my studio have I created?"},
        )
        assert chat_resp.status_code == 200
        assert mock_route.called
        call_request = mock_route.call_args[0][0]
        system_msgs = [m.content for m in call_request.messages if m.role.value == "system"]
        gallery_grounded = any("IMAGE STUDIO CONTEXT" in sm for sm in system_msgs)
        assert gallery_grounded is True
        assert any("bioluminescent crystal caverns" in sm for sm in system_msgs)


@pytest.mark.anyio
async def test_image_gallery_chat_offline_fallback(client: httpx.AsyncClient) -> None:
    """When router fails, runtime chat returns authentic offline fallback with saved artwork."""
    auth, user_id = await _get_auth(client, f"gallery_off_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generate an artwork via Studio API first
    gen_payload = {
        "prompt": "hyperrealistic crystal palace under auroras",
        "style_preset": "photorealistic",
        "aspect_ratio": "16:9",
    }
    await client.post("/api/v1/images/generate", headers=auth, json=gen_payload)

    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Model stream unreachable")):
        chat_resp = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "Show my image gallery"},
        )
        assert chat_resp.status_code == 200
        data = chat_resp.json()
        assert data["agent_slug"] == "image-studio"
        assert "hyperrealistic crystal palace" in data["response"].lower()
        assert "saved image generation" in data["response"].lower()


@pytest.mark.anyio
async def test_image_gallery_chat_stream_fallback(client: httpx.AsyncClient) -> None:
    """Verify that streaming chat retrieves authentic Image Studio generations in offline fallback mode."""
    auth, user_id = await _get_auth(client, f"gallery_str_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Generate an artwork first
    gen_payload = {
        "prompt": "cybernetic samurai on a rainy rooftop",
        "style_preset": "cyberpunk",
        "aspect_ratio": "1:1",
    }
    gen_resp = await client.post("/api/v1/images/generate", headers=auth, json=gen_payload)
    assert gen_resp.status_code == 200

    # Ask streaming chat about saved images
    stream_resp = await client.post(
        "/api/v1/runtime/chat/stream",
        headers=auth,
        json={"message": "Show my image gallery"},
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")

    full_text = ""
    for raw_line in stream_resp.text.splitlines():
        line = raw_line.strip()
        if line.startswith("data:"):
            payload_str = line[len("data:"):].strip()
            if payload_str:
                chunk = json.loads(payload_str)
                full_text += chunk.get("delta", "")

    assert "cybernetic samurai" in full_text.lower()
    assert "saved image generation" in full_text.lower()


# -----------------------------------------------------------------------------
# 11. ImageStudioService Singleton & ToolRegistry Verification
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_service_singleton_and_tool_registration() -> None:
    """Verify ImageStudioService singleton identity and 7 native tools in ToolRegistry."""
    from app.images.service import ImageStudioService
    from app.tools.registry import ToolRegistry
    from app.tools.schemas import RiskLevel

    svc1 = ImageStudioService.get_instance()
    svc2 = ImageStudioService.get_instance()
    assert svc1 is svc2

    svc1.register_image_tools()
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
        assert tool is not None, f"Expected tool {tid} to be registered"
        assert "image" in tool.capabilities

    # High-risk confirmation gating
    del_tool = reg.get("image_delete_generation")
    assert del_tool is not None
    assert del_tool.risk_level == RiskLevel.HIGH
    assert del_tool.requires_confirmation is True


# -----------------------------------------------------------------------------
# 12. Image Studio Native Tools Direct Execution
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_tools_direct_execution() -> None:
    """Verify end-to-end execution of all 7 image tools via Central ToolRegistry."""
    from app.images.service import ImageStudioService
    from app.tools.registry import ToolRegistry
    from app.tools.schemas import ToolExecutionRequest

    svc = ImageStudioService.get_instance()
    svc.register_image_tools()
    reg = ToolRegistry.get_instance()

    user_id = f"tool_exec_img_{uuid.uuid4().hex[:6]}"

    # 1. image_list_gallery (empty)
    res_list_empty = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_list_gallery",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_list_empty.success is True
    assert res_list_empty.output["total_generations"] == 0

    # 2. image_enhance_prompt
    res_enhance = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_enhance_prompt",
            arguments={"prompt": "sunset over cyber city", "style_preset": "cyberpunk"},
            user_id=user_id,
        )
    )
    assert res_enhance.success is True
    assert "sunset over cyber city" in res_enhance.output["enhanced_prompt"]
    assert "cyberpunk" in res_enhance.output["style_preset"]

    # 3. image_generate
    res_generate = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_generate",
            arguments={
                "prompt": "hyperrealistic neon koi fish in digital pond",
                "style_preset": "cyberpunk",
                "aspect_ratio": "16:9",
            },
            user_id=user_id,
        )
    )
    assert res_generate.success is True
    assert res_generate.output["status"] == "success"
    gen = res_generate.output["generation"]
    image_id = gen["id"]
    assert "pollinations.ai" in res_generate.output["media_url"]
    assert gen["width"] == 1344
    assert gen["height"] == 768

    # 4. image_get_generation
    res_get = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_get_generation",
            arguments={"image_id": image_id},
            user_id=user_id,
        )
    )
    assert res_get.success is True
    assert res_get.output["generation"]["id"] == image_id

    # 5. image_toggle_favorite
    res_fav = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_toggle_favorite",
            arguments={"image_id": image_id},
            user_id=user_id,
        )
    )
    assert res_fav.success is True
    assert res_fav.output["favorite"] is True

    # 6. image_export_to_vault
    res_export = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_export_to_vault",
            arguments={"image_id": image_id},
            user_id=user_id,
        )
    )
    assert res_export.success is True
    assert res_export.output["vault_document_id"] is not None

    # 7. image_list_gallery with favorite_only=True
    res_gallery_fav = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_list_gallery",
            arguments={"favorite_only": True},
            user_id=user_id,
        )
    )
    assert res_gallery_fav.success is True
    assert res_gallery_fav.output["total_generations"] == 1
    assert res_gallery_fav.output["generations"][0]["id"] == image_id

    # 8. image_delete_generation (requires confirmation)
    res_del = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_delete_generation",
            arguments={"image_id": image_id},
            user_id=user_id,
            bypass_confirmation=True,
        )
    )
    assert res_del.success is True
    assert res_del.output["deleted"] is True

    # 9. Verify artwork is gone
    res_verify_gone = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_get_generation",
            arguments={"image_id": image_id},
            user_id=user_id,
        )
    )
    assert res_verify_gone.output["status"] == "not_found"


# -----------------------------------------------------------------------------
# 13. AgentPlanner Image Studio Intent Routing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_image_intent_routing() -> None:
    """Verify AgentPlanner deterministic decomposition and routing to image studio tools."""
    from app.agent_runtime.planner import AgentPlanner
    from app.images.service import ImageStudioService

    ImageStudioService.get_instance().register_image_tools()
    planner = AgentPlanner()

    # A. Generate image
    plan_gen = await planner.create_plan("generate image of futuristic Tokyo in cyberpunk style")
    assert len(plan_gen) == 1
    assert plan_gen[0]["tool_id"] == "image_generate"
    assert "futuristic Tokyo" in plan_gen[0]["tool_input"]["prompt"]
    assert plan_gen[0]["tool_input"]["style_preset"] == "cyberpunk"

    # B. Enhance prompt
    plan_enh = await planner.create_plan("enhance image prompt a majestic eagle soaring above clouds")
    assert len(plan_enh) == 1
    assert plan_enh[0]["tool_id"] == "image_enhance_prompt"
    assert "majestic eagle" in plan_enh[0]["tool_input"]["prompt"]

    # C. Show gallery
    plan_gal = await planner.create_plan("show my image gallery")
    assert len(plan_gal) == 1
    assert plan_gal[0]["tool_id"] == "image_list_gallery"

    # D. View artwork
    plan_view = await planner.create_plan("view image gen-artwork-777")
    assert len(plan_view) == 1
    assert plan_view[0]["tool_id"] == "image_get_generation"
    assert plan_view[0]["tool_input"]["image_id"] == "gen-artwork-777"

    # E. Favorite artwork
    plan_fav = await planner.create_plan("favorite image gen-artwork-777")
    assert len(plan_fav) == 1
    assert plan_fav[0]["tool_id"] == "image_toggle_favorite"
    assert plan_fav[0]["tool_input"]["image_id"] == "gen-artwork-777"

    # F. Export artwork to vault
    plan_export = await planner.create_plan("save image to vault gen-artwork-777")
    assert len(plan_export) == 1
    assert plan_export[0]["tool_id"] == "image_export_to_vault"
    assert plan_export[0]["tool_input"]["image_id"] == "gen-artwork-777"

    # G. Delete artwork (requires confirmation)
    plan_del = await planner.create_plan("delete artwork gen-artwork-777")
    assert len(plan_del) == 1
    assert plan_del[0]["tool_id"] == "image_delete_generation"
    assert plan_del[0]["tool_input"]["image_id"] == "gen-artwork-777"


# -----------------------------------------------------------------------------
# 14. Multi-Tenant Isolation via Tool Registry Execution
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_image_studio_tool_multitenant_isolation() -> None:
    """Verify strict multi-tenant isolation across image generations via ToolRegistry."""
    from app.images.service import ImageStudioService
    from app.tools.registry import ToolRegistry
    from app.tools.schemas import ToolExecutionRequest

    svc = ImageStudioService.get_instance()
    svc.register_image_tools()
    reg = ToolRegistry.get_instance()

    user_a = f"img_tenant_a_{uuid.uuid4().hex[:6]}"
    user_b = f"img_tenant_b_{uuid.uuid4().hex[:6]}"

    # User A generates an artwork
    res_a = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_generate",
            arguments={"prompt": "Confidential blueprint of starship engine"},
            user_id=user_a,
        )
    )
    assert res_a.success is True
    img_a_id = res_a.output["generation"]["id"]

    # User B lists gallery -> 0 artworks, zero cross-tenant leak
    res_b_list = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_list_gallery",
            arguments={},
            user_id=user_b,
        )
    )
    assert res_b_list.success is True
    assert res_b_list.output["total_generations"] == 0

    # User B tries to view User A's artwork -> not_found
    res_b_get = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_get_generation",
            arguments={"image_id": img_a_id},
            user_id=user_b,
        )
    )
    assert res_b_get.output["status"] == "not_found"

    # User B tries to favorite User A's artwork -> not_found
    res_b_fav = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_toggle_favorite",
            arguments={"image_id": img_a_id},
            user_id=user_b,
        )
    )
    assert res_b_fav.output["status"] == "not_found"

    # User B tries to delete User A's artwork -> triggers confirmation gate
    res_b_del_unconfirmed = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_delete_generation",
            arguments={"image_id": img_a_id},
            user_id=user_b,
        )
    )
    assert res_b_del_unconfirmed.success is False
    assert res_b_del_unconfirmed.output.get("challenge") is not None
    del_challenge = res_b_del_unconfirmed.output["challenge"]
    del_token = del_challenge["challenge_token"]

    from app.trust.confirmation_gate import ConfirmationGate
    ConfirmationGate.resolve_challenge(
        challenge_id=del_challenge["challenge_id"],
        user_id=user_b,
        decision="approve",
        challenge_token=del_token,
    )

    res_b_del = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_delete_generation",
            arguments={"image_id": img_a_id},
            user_id=user_b,
            confirmation_token=del_token,
        )
    )
    assert res_b_del.output["deleted"] is False

    # Confirm User A's artwork is untouched
    res_a_verify = await reg.execute(
        ToolExecutionRequest(
            tool_id="image_get_generation",
            arguments={"image_id": img_a_id},
            user_id=user_a,
        )
    )
    assert res_a_verify.output["status"] == "success"
    assert res_a_verify.output["generation"]["id"] == img_a_id




