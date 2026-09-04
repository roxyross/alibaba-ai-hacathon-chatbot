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
async def list_models(
    current_user: User = Depends(get_current_user),
) -> ModelListResponse:
    """Return the catalog of providers + models for the chat UI.

    The catalog is built from the existing Provider and Model tables when the
    DB is configured, and falls back to the static provider configurations
    otherwise. The model picker in the frontend reads this endpoint.
    """
    from sqlalchemy import select
    from app.db import get_session_factory
    from app.models.provider import Provider as ProviderRow
    from app.models.model import Model as ModelRow

    providers: list[ProviderModels] = []

    factory = get_session_factory()
    if factory is not None:
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
        return ModelListResponse(providers=providers)

    # In-memory fallback: surface the default model for each provider we know.
    fallback: list[ProviderModels] = [
        ProviderModels(
            name="deepseek",
            display_name="DeepSeek",
            enabled=True,
            models=[ModelInfo(name="deepseek-chat-v3", display_name="DeepSeek V3")],
        ),
        ProviderModels(
            name="grok",
            display_name="Grok",
            enabled=True,
            models=[ModelInfo(name="grok-3", display_name="Grok 3")],
        ),
        ProviderModels(
            name="openai",
            display_name="OpenAI",
            enabled=False,
            models=[ModelInfo(name="gpt-4o", display_name="GPT-4o")],
        ),
        ProviderModels(
            name="gemini",
            display_name="Gemini",
            enabled=True,
            models=[ModelInfo(name="gemini-2.0-flash", display_name="Gemini 2.0 Flash")],
        ),
    ]
    return ModelListResponse(providers=fallback)
