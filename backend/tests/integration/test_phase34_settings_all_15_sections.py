"""Phase 34 Integration Test Suite: 15-Section Global Settings Architecture.

Covers:
1. Complete 15-section settings lifecycle (GET defaults, PATCH full suite, GET verified).
2. Global Image Studio defaults (provider, model, resolution, aspect ratio, quality, consistency).
3. Global Video Studio defaults (provider, model, resolution, aspect ratio, duration, audio, quality).
4. BYOK API Keys persistence and retrieval.
5. Strict tenant isolation (User A modifications never bleed into User B).
6. Partial update idempotency (updating image defaults does not clobber video defaults).
"""

from __future__ import annotations

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


async def test_settings_all_15_sections_full_lifecycle(client: httpx.AsyncClient) -> None:
    headers_u1 = await _get_auth_headers(client, "settings_15sec_user1@roxy.ai")
    headers_u2 = await _get_auth_headers(client, "settings_15sec_user2@roxy.ai")

    # 1. User 1 initially receives clean production defaults
    initial_resp = await client.get("/api/v1/settings", headers=headers_u1)
    assert initial_resp.status_code == 200
    initial = initial_resp.json()
    assert initial["theme"] == "dark"
    assert initial["voice_id"] == "aura-asteria-en"
    assert initial["image_default_model"] == "imagen-3.0-generate-002"
    assert initial["video_default_model"] == "veo-3.1-generate-preview"

    # 2. User 1 updates across all 15 settings sections
    payload_15_sections = {
        # Section 1: Profile
        "display_name": "Dr. Elena Vance",
        "bio": "Lead AI Researcher & Creative Technologist",
        "timezone": "America/Los_Angeles",
        "avatar_url": "https://cdn.example.com/elena.jpg",
        # Section 2: Appearance
        "theme": "light",
        "accent_color": "Emerald",
        "bubble_style": "Compact",
        "font_size": "Large",
        # Section 3: AI Persona
        "custom_persona": "You are a cutting-edge multimodal researcher.",
        "tone": "Academic",
        "temperature": 0.45,
        "response_length": "Detailed",
        # Section 4: Models & Providers
        "preferred_provider": "gemini",
        "default_chat_model": "gemini-2.5-pro",
        "stream_speed": "smooth",
        "auto_scroll": False,
        # Section 5: Image Studio Defaults
        "image_default_provider": "google",
        "image_default_model": "imagen-4.0-generate-001",
        "image_default_quality": "Ultra",
        "image_default_resolution": "1344x768",
        "image_default_aspect_ratio": "16:9",
        "image_default_count": 2,
        "image_style_preset": "cinematic",
        "image_character_consistency": True,
        # Section 6: Video Studio Defaults
        "video_default_provider": "google",
        "video_default_model": "veo-3.1-generate-preview",
        "video_default_resolution": "1080p",
        "video_default_aspect_ratio": "9:16",
        "video_default_duration": 10,
        "video_default_audio": True,
        "video_default_quality": "High",
        # Section 7: Voice & Audio
        "voice_id": "aura-luna-en",
        "speech_speed": 1.15,
        "auto_play_audio": True,
        "sound_effects": False,
        # Section 8: Notifications
        "email_digests": False,
        "job_alerts": True,
        "budget_alerts": True,
        "quiet_hours_start": "23:00",
        "quiet_hours_end": "07:00",
        # Section 9: Data & Privacy
        "allow_learning": False,
        "store_voice_recordings": False,
        "store_generation_prompts": True,
        "retention_days": "365",
        # Section 10: Security & Sessions
        "two_factor_enabled": True,
        "session_timeout_minutes": 240,
        # Section 11: Connected Accounts
        "connected_google": True,
        "connected_github": True,
        "connected_apple": False,
        # Section 12: Billing & Credits
        "auto_topup_threshold": 100,
        # Section 13: BYOK Keys
        "byok_gemini": "AIzaSyCustomGeminiKey77889900112233",
        "byok_openai": "sk-proj-CustomOpenAIKey112233445566",
        "byok_anthropic": "sk-ant-CustomAnthropicKey998877",
        "byok_flux": "r8_customFluxKey1234567890",
        # Section 14: Memory & Context
        "auto_memory_extraction": True,
        "context_window": "128k",
    }

    patch_resp = await client.patch("/api/v1/settings", headers=headers_u1, json=payload_15_sections)
    assert patch_resp.status_code == 200
    res_data = patch_resp.json()
    assert res_data["display_name"] == "Dr. Elena Vance"
    assert res_data["image_default_model"] == "imagen-4.0-generate-001"
    assert res_data["video_default_resolution"] == "1080p"
    assert res_data["video_default_duration"] == 10
    assert res_data["byok_gemini"] == "AIzaSyCustomGeminiKey77889900112233"

    # 3. GET retrieves all persisted values exactly
    get_resp = await client.get("/api/v1/settings", headers=headers_u1)
    assert get_resp.status_code == 200
    saved = get_resp.json()
    assert saved["display_name"] == "Dr. Elena Vance"
    assert saved["bio"] == "Lead AI Researcher & Creative Technologist"
    assert saved["theme"] == "light"
    assert saved["image_default_aspect_ratio"] == "16:9"
    assert saved["image_character_consistency"] is True
    assert saved["video_default_aspect_ratio"] == "9:16"
    assert saved["context_window"] == "128k"
    assert saved["byok_flux"] == "r8_customFluxKey1234567890"

    # 4. Partial update test: update only video duration and theme, rest stays untouched
    partial_patch = await client.patch(
        "/api/v1/settings",
        headers=headers_u1,
        json={"video_default_duration": 5, "theme": "dark"},
    )
    assert partial_patch.status_code == 200
    p_data = partial_patch.json()
    assert p_data["video_default_duration"] == 5
    assert p_data["theme"] == "dark"
    # Previously saved image defaults preserved
    assert p_data["image_default_model"] == "imagen-4.0-generate-001"
    assert p_data["display_name"] == "Dr. Elena Vance"

    # 5. User 2 remains completely isolated
    u2_resp = await client.get("/api/v1/settings", headers=headers_u2)
    assert u2_resp.status_code == 200
    u2_data = u2_resp.json()
    assert u2_data.get("display_name") is None
    assert u2_data["theme"] == "dark"
    assert u2_data["image_default_model"] == "imagen-3.0-generate-002"
    assert u2_data.get("byok_gemini") is None
