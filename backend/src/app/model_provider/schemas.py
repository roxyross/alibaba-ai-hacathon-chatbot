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


class ProviderModels(BaseModel):
    """All models for a single provider."""

    name: str
    display_name: str
    enabled: bool
    models: list[ModelInfo]


class ModelListResponse(BaseModel):
    """Top-level response: list of providers with their models."""

    providers: list[ProviderModels]
