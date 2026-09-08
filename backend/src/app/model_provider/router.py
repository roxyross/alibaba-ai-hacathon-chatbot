"""GET /models — list providers and their models for the UI picker."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.model_provider.schemas import (
    ModelInfo,
    ModelListResponse,
    ProviderModels,
)


router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """Return the catalog of providers + models for the chat UI."""
    import asyncio
    from sqlalchemy import select
    from app.db import get_session_factory
    from app.models.provider import Provider as ProviderRow
    from app.models.model import Model as ModelRow

    providers: list[ProviderModels] = []

    try:
        factory = get_session_factory()
        if factory is not None:
            async with asyncio.timeout(2.0):
                async with factory() as session:
                    provider_rows = (await session.execute(select(ProviderRow))).scalars().all()
                    for prov in provider_rows:
                        model_rows = (
                            await session.execute(
                                select(ModelRow).where(ModelRow.provider_id == prov.id)
                            )
                        ).scalars().all()
                        providers.append(
                            ProviderModels(
                                name=prov.name,
                                display_name=prov.name.capitalize(),
                                enabled=prov.enabled,
                                models=[
                                    ModelInfo(
                                        name=m.name,
                                        display_name=m.display_name or m.name,
                                        enabled=m.enabled,
                                        task_types=m.task_types or [],
                                        max_tokens=m.max_tokens or 4096,
                                    )
                                    for m in model_rows
                                ],
                            )
                        )
    except Exception:
        pass
        if providers:
            return ModelListResponse(providers=providers)

    # Catalog of all supported providers and models for ROXY JARVIS
    fallback: list[ProviderModels] = [
        ProviderModels(
            name="grok",
            display_name="xAI / Groq",
            enabled=True,
            models=[
                ModelInfo(
                    name="qwen/qwen3.8-27b",
                    display_name="Grok / Qwen 27B (Fast Inference)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=800,
                ),
                ModelInfo(
                    name="openai/gpt-oss-120b",
                    display_name="Grok / GPT-OSS 120B",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=800,
                ),
                ModelInfo(
                    name="grok-2",
                    display_name="xAI Grok 2",
                    enabled=True,
                    task_types=["general", "coding"],
                    max_tokens=8192,
                ),
            ],
        ),
        ProviderModels(
            name="gemini",
            display_name="Google Gemini",
            enabled=True,
            models=[
                ModelInfo(
                    name="gemini-2.0-flash",
                    display_name="Gemini 2.0 Flash",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="gemini-1.5-pro",
                    display_name="Gemini 1.5 Pro",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="gemini-1.5-flash",
                    display_name="Gemini 1.5 Flash",
                    enabled=True,
                    task_types=["general", "coding"],
                    max_tokens=8192,
                ),
            ],
        ),
        ProviderModels(
            name="openai",
            display_name="OpenAI",
            enabled=True,
            models=[
                ModelInfo(
                    name="gpt-4o",
                    display_name="GPT-4o",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=4096,
                ),
                ModelInfo(
                    name="gpt-4o-mini",
                    display_name="GPT-4o Mini",
                    enabled=True,
                    task_types=["general", "coding"],
                    max_tokens=4096,
                ),
            ],
        ),
        ProviderModels(
            name="deepseek",
            display_name="DeepSeek",
            enabled=True,
            models=[
                ModelInfo(
                    name="deepseek-chat",
                    display_name="DeepSeek V3",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=4096,
                ),
                ModelInfo(
                    name="deepseek-reasoner",
                    display_name="DeepSeek R1",
                    enabled=True,
                    task_types=["reasoning", "coding"],
                    max_tokens=4096,
                ),
            ],
        ),
    ]
    return ModelListResponse(providers=fallback)
