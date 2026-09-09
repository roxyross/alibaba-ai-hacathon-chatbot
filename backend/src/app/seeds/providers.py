"""Seed provider configuration into the database.

Run: python -m app.seeds.providers

Upserts Provider + Model records for:
  Gemini (primary), Grok (fallback), DeepSeek (disabled), OpenAI (disabled)

T027: Uses SQLAlchemy async ORM. Falls back to a descriptive dry-run
when DATABASE_URL is not configured (no DB available).
"""

from __future__ import annotations

import os
import sys

# Ensure src is on path when run directly
sys.path.insert(0, "src")

from app.db import get_engine, Base
from app.ai_gateway.models.provider import DEFAULT_ROUTING_PRIORITY
from app.models.provider import Provider
from app.models.model import Model


def _seed_data() -> list[dict]:
    """Return provider seed records matching routing priority order.

    Priority values come from app.ai_gateway.models.provider.DEFAULT_ROUTING_PRIORITY
    so the seed stays in sync with the runtime router. To change priority, edit that map.
    """
    return [
        {
            "name": "deepseek",
            "enabled": os.environ.get("PROVIDER_DEEPSEEK_ENABLED", "true").lower() in ("true", "1"),
            "api_key_env_var": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com",
            "timeout_seconds": 10.0,
            "routing_priority": DEFAULT_ROUTING_PRIORITY.get("deepseek", 3),
            "supports_streaming": True,
            "models": [
                {
                    "name": "deepseek-chat-v3",
                    "display_name": "DeepSeek V3",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.001,
                    "cost_per_1k_output_tokens": 0.002,
                    "max_tokens": 64000,
                },
                {
                    "name": "deepseek-reasoner",
                    "display_name": "DeepSeek R1",
                    "task_types": ["reasoning"],
                    "cost_per_1k_input_tokens": 0.001,
                    "cost_per_1k_output_tokens": 0.006,
                    "max_tokens": 64000,
                },
            ],
        },
        {
            "name": "grok",
            "enabled": os.environ.get("PROVIDER_GROK_ENABLED", "true").lower() in ("true", "1"),
            "api_key_env_var": "GROK_API_KEY",
            "base_url": "https://api.x.ai/v1",
            "timeout_seconds": 10.0,
            "routing_priority": DEFAULT_ROUTING_PRIORITY.get("grok", 2),
            "supports_streaming": True,
            "models": [
                {
                    "name": "grok-3",
                    "display_name": "Grok 3",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.005,
                    "cost_per_1k_output_tokens": 0.015,
                    "max_tokens": 131072,
                },
                {
                    "name": "grok-3-mini",
                    "display_name": "Grok 3 Mini",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.001,
                    "cost_per_1k_output_tokens": 0.003,
                    "max_tokens": 131072,
                },
                {
                    "name": "grok-2",
                    "display_name": "Grok 2",
                    "task_types": ["general", "coding"],
                    "cost_per_1k_input_tokens": 0.002,
                    "cost_per_1k_output_tokens": 0.01,
                    "max_tokens": 131072,
                },
                {
                    "name": "grok-2-vision-1212",
                    "display_name": "Grok 2 Vision",
                    "task_types": ["general", "multimodal"],
                    "cost_per_1k_input_tokens": 0.002,
                    "cost_per_1k_output_tokens": 0.01,
                    "max_tokens": 131072,
                },
                {
                    "name": "grok-beta",
                    "display_name": "Grok Beta",
                    "task_types": ["general", "coding"],
                    "cost_per_1k_input_tokens": 0.005,
                    "cost_per_1k_output_tokens": 0.015,
                    "max_tokens": 131072,
                },
                {
                    "name": "qwen/qwen3.8-27b",
                    "display_name": "Grok / Qwen 27B",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.0,
                    "cost_per_1k_output_tokens": 0.0,
                    "max_tokens": 32768,
                },
                {
                    "name": "llama-3.3-70b-versatile",
                    "display_name": "Groq / Llama 3.3 70B",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.0,
                    "cost_per_1k_output_tokens": 0.0,
                    "max_tokens": 32768,
                },
            ],
        },
        {
            "name": "openai",
            "enabled": os.environ.get("PROVIDER_OPENAI_ENABLED", "true").lower() in ("true", "1"),
            "api_key_env_var": "OPENAI_API_KEY",
            "base_url": "https://api.openai.com/v1",
            "timeout_seconds": 10.0,
            "routing_priority": DEFAULT_ROUTING_PRIORITY.get("openai", 4),
            "supports_streaming": True,
            "models": [
                {
                    "name": "gpt-4o",
                    "display_name": "GPT-4o",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.0025,
                    "cost_per_1k_output_tokens": 0.01,
                    "max_tokens": 128000,
                },
                {
                    "name": "gpt-4o-mini",
                    "display_name": "GPT-4o Mini",
                    "task_types": ["general", "coding"],
                    "cost_per_1k_input_tokens": 0.00015,
                    "cost_per_1k_output_tokens": 0.0006,
                    "max_tokens": 128000,
                },
            ],
        },
        {
            "name": "gemini",
            "enabled": os.environ.get("PROVIDER_GEMINI_ENABLED", "true").lower() in ("true", "1"),
            "api_key_env_var": "GEMINI_API_KEY",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "timeout_seconds": 10.0,
            "routing_priority": DEFAULT_ROUTING_PRIORITY.get("gemini", 1),
            "supports_streaming": True,
            "models": [
                {
                    "name": "gemini-3.8-flash",
                    "display_name": "Gemini 3.8 Flash",
                    "task_types": ["general", "coding", "reasoning", "multimodal", "audio"],
                    "cost_per_1k_input_tokens": 0.0,
                    "cost_per_1k_output_tokens": 0.0,
                    "max_tokens": 1000000,
                },
                {
                    "name": "gemini-3.7-flash",
                    "display_name": "Gemini 3.7 Flash",
                    "task_types": ["general", "coding", "reasoning", "multimodal"],
                    "cost_per_1k_input_tokens": 0.0,
                    "cost_per_1k_output_tokens": 0.0,
                    "max_tokens": 1000000,
                },
                {
                    "name": "gemini-3.1-flash",
                    "display_name": "Gemini 3.1 Flash",
                    "task_types": ["general", "coding", "reasoning", "multimodal"],
                    "cost_per_1k_input_tokens": 0.0,
                    "cost_per_1k_output_tokens": 0.0,
                    "max_tokens": 1000000,
                },
                {
                    "name": "gemini-2.5-flash",
                    "display_name": "Gemini 2.5 Flash",
                    "task_types": ["general", "coding", "reasoning", "multimodal"],
                    "cost_per_1k_input_tokens": 0.0,
                    "cost_per_1k_output_tokens": 0.0,
                    "max_tokens": 1000000,
                },
                {
                    "name": "gemini-2.0-flash",
                    "display_name": "Gemini 2.0 Flash",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.0,
                    "cost_per_1k_output_tokens": 0.0,
                    "max_tokens": 1000000,
                },
                {
                    "name": "gemini-1.5-pro",
                    "display_name": "Gemini 1.5 Pro",
                    "task_types": ["general", "coding", "reasoning"],
                    "cost_per_1k_input_tokens": 0.00125,
                    "cost_per_1k_output_tokens": 0.005,
                    "max_tokens": 2000000,
                },
            ],
        },
    ]



async def _run_migration() -> None:
    """Create all tables (idempotent — uses CREATE TABLE IF NOT EXISTS)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  ✓ Database tables created/verified")


async def _seed_with_sqlalchemy(records: list[dict]) -> None:
    """Upsert records via SQLAlchemy async session."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db import get_engine

    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for provider_data in records:
            models_data = provider_data.pop("models")

            # Upsert Provider
            stmt = select(Provider).where(Provider.name == provider_data["name"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                for key, val in provider_data.items():
                    setattr(existing, key, val)
                provider = existing
            else:
                provider = Provider(**provider_data)
                session.add(provider)
                await session.flush()

            # Upsert Models
            for model_data in models_data:
                model_stmt = select(Model).where(
                    Model.provider_id == provider.id,
                    Model.name == model_data["name"],
                )
                model_result = await session.execute(model_stmt)
                existing_model = model_result.scalar_one_or_none()

                if existing_model:
                    for key, val in model_data.items():
                        setattr(existing_model, key, val)
                else:
                    m = Model(**model_data, provider_id=provider.id)
                    session.add(m)

            print(f"  ✓ {provider_data['name']} ({len(models_data)} models)")

        await session.commit()
    await engine.dispose()


def _seed_dry_run(records: list[dict]) -> None:
    """Print what would be seeded — used when DATABASE_URL is not configured."""
    print("  ⚠ DATABASE_URL not configured — dry-run (no DB changes)")
    for provider in records:
        print(f"  [dry-run] Provider: {provider['name']} (priority={provider['routing_priority']})")
        for model in provider["models"]:
            print(
                f"         Model: {model['name']} "
                f"(${model['cost_per_1k_input_tokens']}/1k in, "
                f"${model['cost_per_1k_output_tokens']}/1k out)"
            )


def main() -> None:
    import os
    from app.db import get_engine

    print("Seeding AI provider configuration...")
    records = _seed_data()

    # Check if DATABASE_URL is set
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url or db_url == "postgresql+asyncpg://user:pass@localhost:5432/roxy":
        _seed_dry_run(records)
        return

    import asyncio

    async def _inner() -> None:
        await _run_migration()
        await _seed_with_sqlalchemy(records)

    asyncio.run(_inner())


if __name__ == "__main__":
    main()
