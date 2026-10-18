"""GET /models and POST /models/refresh — list providers, discovery status, and dynamic models."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_optional_current_user
from app.auth.models import User
from app.model_provider.schemas import (
    ModelInfo,
    ModelListResponse,
    ModelRefreshResponse,
    ProviderModels,
    ProviderSyncStatus,
)


router = APIRouter(prefix="/models", tags=["models"])


@router.post("/refresh", response_model=ModelRefreshResponse)
async def refresh_models(
    current_user: User | None = Depends(get_optional_current_user),
) -> ModelRefreshResponse:
    """Trigger dynamic model catalog discovery across all configured providers.

    Returns the refreshed catalog with freshness timestamps, configured/unconfigured
    statuses, promoted defaults, and voice/live preservation.
    """
    from app.ai_gateway.models.provider import get_provider_config
    from app.ai_gateway.services.catalog_discovery import ModelCatalogDiscoveryService

    service = ModelCatalogDiscoveryService.get_instance()
    sync_results = await service.refresh_all()

    now_iso = datetime.now(timezone.utc).isoformat()
    provider_models_list: list[ProviderModels] = []
    statuses: list[ProviderSyncStatus] = []
    total_discovered = 0

    display_names = {
        "gemini": "Google Gemini",
        "dashscope": "Alibaba DashScope / Qwen",
        "grok": "xAI Grok",
        "groq": "Groq",
        "deepseek": "DeepSeek",
        "openai": "OpenAI",
        "anthropic": "Anthropic Claude",
    }

    for prov_name, result in sync_results.items():
        prov_cfg = get_provider_config(prov_name)
        is_enabled = prov_cfg.is_enabled if prov_cfg else True
        has_key = prov_cfg.has_api_key if prov_cfg else False
        configured = is_enabled and has_key

        if result.success:
            total_discovered += result.discovered_count

        status_str = "synced" if (result.success and configured) else (
            "unconfigured" if not has_key else ("disabled" if not is_enabled else "degraded")
        )

        statuses.append(
            ProviderSyncStatus(
                provider=prov_name,
                configured=configured,
                is_enabled=is_enabled,
                status=status_str,
                discovered_count=result.discovered_count,
                default_model=result.promoted_default or service.get_default_model(prov_name),
                voice_live_model=service.get_voice_live_model() if prov_name == "gemini" else None,
                last_synced_at=now_iso,
                provenance=result.provenance,
                error=result.error_reason,
            )
        )

        model_infos = [
            ModelInfo(
                name=m.model_id,
                display_name=m.display_name,
                enabled=m.is_stable and not m.is_deprecated,
                task_types=m.task_types,
                max_tokens=m.max_tokens,
                cost_per_1k_input=m.cost_per_1k_input,
                cost_per_1k_output=m.cost_per_1k_output,
                is_stable=m.is_stable,
                requires_api_key=m.requires_api_key,
                provenance=m.provenance,
            )
            for m in result.models
        ]

        provider_models_list.append(
            ProviderModels(
                name=prov_name,
                display_name=display_names.get(prov_name, prov_name.capitalize()),
                enabled=is_enabled,
                models=model_infos,
                default_model=result.promoted_default or service.get_default_model(prov_name),
                voice_live_model=service.get_voice_live_model() if prov_name == "gemini" else None,
            )
        )

    return ModelRefreshResponse(
        success=True,
        last_synced_at=now_iso,
        providers_discovered=total_discovered,
        is_cached=False,
        providers=provider_models_list,
        provider_statuses=statuses,
    )


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
            name="gemini",
            display_name="Google Gemini",
            enabled=True,
            models=[
                ModelInfo(
                    name="gemini-4-argon",
                    display_name="Gemini 4 Argon (Default General Reasoning)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal"],
                    max_tokens=32768,
                ),
                ModelInfo(
                    name="gemini-3.8-flash",
                    display_name="Gemini 3.8 Flash (Multimodal Audio & Modulation)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal", "audio"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="gemini-3.6-flash",
                    display_name="Gemini 3.6 Flash (Fast & Full Reasoning)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="gemini-3.7-flash",
                    display_name="Gemini 3.7 Flash",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="gemini-3.1-flash",
                    display_name="Gemini 3.1 Flash",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="gemini-2.5-flash",
                    display_name="Gemini 2.5 Flash",
                    enabled=True,
                    task_types=["general", "coding", "reasoning", "multimodal"],
                    max_tokens=8192,
                ),
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
            name="grok",
            display_name="xAI Grok",
            enabled=True,
            models=[
                ModelInfo(
                    name="grok-4.7",
                    display_name="xAI Grok 4.7 (Flagship Reasoning & Coding)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=16384,
                ),
                ModelInfo(
                    name="grok-3",
                    display_name="xAI Grok 3 (Flagship Reasoning & Coding)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="grok-3-mini",
                    display_name="xAI Grok 3 Mini (High-Speed)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="grok-2",
                    display_name="xAI Grok 2",
                    enabled=True,
                    task_types=["general", "coding"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="grok-2-vision-1212",
                    display_name="xAI Grok 2 Vision",
                    enabled=True,
                    task_types=["general", "multimodal", "coding"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="grok-beta",
                    display_name="xAI Grok Beta",
                    enabled=True,
                    task_types=["general", "coding"],
                    max_tokens=8192,
                ),
            ],
        ),
        ProviderModels(
            name="groq",
            display_name="Groq",
            enabled=True,
            models=[
                ModelInfo(
                    name="qwen/qwen3.8-27b",
                    display_name="Groq / Qwen 27B (Fast Inference)",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=4096,
                ),
                ModelInfo(
                    name="openai/gpt-oss-120b",
                    display_name="Groq / GPT-OSS 120B",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=4096,
                ),
                ModelInfo(
                    name="qwen/qwen3.6-27b",
                    display_name="Groq / Qwen 3.6 27B",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=4096,
                ),
                ModelInfo(
                    name="llama-3.3-70b-versatile",
                    display_name="Groq / Llama 3.3 70B",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=4096,
                ),
                ModelInfo(
                    name="mixtral-8x7b-32768",
                    display_name="Groq / Mixtral 8x7B",
                    enabled=True,
                    task_types=["general", "coding"],
                    max_tokens=4096,
                ),
            ],
        ),
        ProviderModels(
            name="openai",
            display_name="OpenAI",
            enabled=False,
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
            name="anthropic",
            display_name="Anthropic Claude",
            enabled=False,
            models=[
                ModelInfo(
                    name="claude-3-5-sonnet-latest",
                    display_name="Claude 3.5 Sonnet",
                    enabled=True,
                    task_types=["general", "coding", "reasoning"],
                    max_tokens=8192,
                ),
                ModelInfo(
                    name="claude-3-5-haiku-latest",
                    display_name="Claude 3.5 Haiku",
                    enabled=True,
                    task_types=["general", "coding"],
                    max_tokens=8192,
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
