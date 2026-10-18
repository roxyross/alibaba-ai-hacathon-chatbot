"""Contract tests for POST /api/v1/models/refresh and GET /api/v1/models endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_get_models_endpoint() -> None:
    """GET /api/v1/models returns catalog of providers and models."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert len(data["providers"]) > 0

        prov_names = [p["name"] for p in data["providers"]]
        assert "gemini" in prov_names
        assert "groq" in prov_names
        assert "deepseek" in prov_names


@pytest.mark.asyncio
async def test_post_models_refresh_endpoint() -> None:
    """POST /api/v1/models/refresh invokes discovery and returns metadata & status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/models/refresh")
        assert resp.status_code == 200
        data = resp.json()

        assert data["success"] is True
        assert "last_synced_at" in data
        assert "providers" in data
        assert "provider_statuses" in data
        assert len(data["providers"]) > 0
        assert len(data["provider_statuses"]) > 0

        # Check Gemini provider
        gemini_prov = next((p for p in data["providers"] if p["name"] == "gemini"), None)
        assert gemini_prov is not None
        assert gemini_prov["voice_live_model"] == "gemini-3.8-flash"
        assert gemini_prov["default_model"] in ("gemini-4-argon", "gemini-3.8-flash")

        # Check provider statuses list
        status_map = {s["provider"]: s for s in data["provider_statuses"]}
        assert "gemini" in status_map
        assert "openai" in status_map
        assert "anthropic" in status_map

        # OpenAI and Anthropic should be marked unconfigured or disabled by default
        assert status_map["openai"]["status"] in ("unconfigured", "disabled", "synced")
        assert status_map["anthropic"]["status"] in ("unconfigured", "disabled", "synced")
