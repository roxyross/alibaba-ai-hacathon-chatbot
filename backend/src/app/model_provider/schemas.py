"""Model-provider Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelInfo(BaseModel):
    """A single model under a provider."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    display_name: str
    enabled: bool = True
    task_types: list[str] = []
    max_tokens: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    is_stable: bool = True
    requires_api_key: bool = False
    provenance: str = "official_api"


class ProviderModels(BaseModel):
    """All models for a single provider."""

    name: str
    display_name: str
    enabled: bool
    models: list[ModelInfo]
    default_model: str | None = None
    voice_live_model: str | None = None


class ModelListResponse(BaseModel):
    """Top-level response: list of providers with their models."""

    providers: list[ProviderModels]


class ProviderSyncStatus(BaseModel):
    """Status details for a single provider sync."""

    provider: str
    configured: bool
    is_enabled: bool
    status: str
    discovered_count: int
    default_model: str | None = None
    voice_live_model: str | None = None
    last_synced_at: str | None = None
    provenance: str = "official_api"
    error: str | None = None


class ModelRefreshResponse(BaseModel):
    """Response returned by POST /models/refresh."""

    success: bool
    last_synced_at: str
    providers_discovered: int
    is_cached: bool = False
    providers: list[ProviderModels]
    provider_statuses: list[ProviderSyncStatus]

