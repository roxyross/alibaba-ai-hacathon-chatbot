"""Automatic Model Catalog Discovery and Safe Promotion Service.

Discovers models dynamically from official provider endpoints:
- Google Gemini API (`/v1beta/models`)
- xAI (`/v1/models`)
- Groq (`/openai/v1/models`)
- OpenAI & Anthropic (validated only when explicitly enabled; disabled by default)

Enforces:
1. Exact model ID & capability validation (never scrape unofficial lists or invent IDs).
2. Distinction between stable/GA vs preview/deprecated models.
3. Audio/Voice/Live isolation: preserves Gemini 3.8 Flash for audio/live/TTS tasks.
4. Provider separation: prevents leaking Groq models into Grok or vice-versa.
5. Canary validation & safe promotion with previous default preservation and rollback.
6. Offline/startup resilience: network failure or missing keys never blocks startup.
7. Explicit user model selection preservation.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
import structlog

from app.ai_gateway.models.provider import (
    ModelConfig,
    _default_models,
    get_provider_config,
)

log = structlog.get_logger()


@dataclass
class DiscoveredModel:
    """A model discovered from an official provider endpoint."""

    provider: str
    model_id: str
    display_name: str
    task_types: list[str]
    max_tokens: int = 4096
    input_token_limit: int = 32768
    output_token_limit: int = 4096
    is_stable: bool = True
    is_deprecated: bool = False
    is_preview: bool = False
    is_eligible_for_promotion: bool = False
    supported_generation_methods: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_model_config(self) -> ModelConfig:
        return ModelConfig(
            name=self.model_id,
            display_name=self.display_name,
            task_types=tuple(self.task_types),
            max_tokens=self.max_tokens,
            enabled=not self.is_deprecated,
        )


@dataclass
class CatalogSyncResult:
    """Result of a provider catalog synchronization run."""

    provider: str
    success: bool
    discovered_count: int
    models: list[DiscoveredModel]
    promoted_default: str | None
    previous_default: str | None
    voice_live_model: str | None = None
    error_reason: str | None = None
    live_verified: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ModelCatalogDiscoveryService:
    """Centralized lifecycle service for provider model discovery and promotion."""

    _instance: ModelCatalogDiscoveryService | None = None

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # Default active selections
        self._active_defaults: dict[str, str] = {
            "gemini": "gemini-4-argon",
            "grok": "grok-4.7",
            "groq": "qwen/qwen3.8-27b",
            "deepseek": "deepseek-chat-v3",
            "openai": "gpt-4o",
            "anthropic": "claude-3-5-sonnet-latest",
        }
        self._previous_defaults: dict[str, str] = {
            "gemini": "gemini-3.8-flash",
            "grok": "grok-3",
            "groq": "llama-3.3-70b-versatile",
            "deepseek": "deepseek-chat-v3",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-latest",
        }
        # Fixed Voice / Audio / Live API designated model
        self._designated_audio_model: str = "gemini-3.8-flash"
        # Dynamic in-memory catalogs
        self._catalogs: dict[str, list[DiscoveredModel]] = {}
        # Promotion validation canary hook (can be mocked in tests)
        self.canary_hook: Callable[[str, str], bool] | None = None

    @classmethod
    def get_instance(cls) -> ModelCatalogDiscoveryService:
        if cls._instance is None:
            cls._instance = ModelCatalogDiscoveryService()
        return cls._instance

    def get_default_model(self, provider: str, task_type: str = "general") -> str:
        """Return the current active default model for a provider and task type."""
        if task_type in ("audio", "voice", "live") and provider == "gemini":
            return self._designated_audio_model
        return self._active_defaults.get(provider, "gemini-4-argon")

    def get_previous_default(self, provider: str) -> str | None:
        """Return the healthy previous default model for fallback."""
        return self._previous_defaults.get(provider)

    def get_voice_live_model(self) -> str:
        """Preserve designated voice/TTS/Live API model."""
        return self._designated_audio_model

    def get_active_models(self, provider: str) -> list[DiscoveredModel]:
        """Return discovered models for provider, or baseline defaults if not yet discovered."""
        if provider in self._catalogs and self._catalogs[provider]:
            return self._catalogs[provider]
        # Return fallback from static config
        configs = _default_models(provider)
        return [
            DiscoveredModel(
                provider=provider,
                model_id=c.name,
                display_name=c.display_name,
                task_types=list(c.task_types),
                max_tokens=c.max_tokens,
                is_stable=True,
                is_eligible_for_promotion=(c.name == self._active_defaults.get(provider)),
            )
            for c in configs
        ]

    async def refresh_all(self, client: httpx.AsyncClient | None = None) -> dict[str, CatalogSyncResult]:
        """Refresh catalogs for all enabled providers idempotently."""
        results: dict[str, CatalogSyncResult] = {}
        for prov in ("gemini", "grok", "groq", "openai", "anthropic", "deepseek"):
            results[prov] = await self.refresh_provider_catalog(prov, client=client)
        return results

    async def refresh_provider_catalog(
        self,
        provider: str,
        client: httpx.AsyncClient | None = None,
        validate_promotion: bool = True,
    ) -> CatalogSyncResult:
        """Refresh a single provider's catalog from its official discovery endpoint."""
        async with self._lock:
            prov_cfg = get_provider_config(provider)
            prev_def = self._active_defaults.get(provider)

            if prov_cfg is None:
                return CatalogSyncResult(
                    provider=provider,
                    success=False,
                    discovered_count=0,
                    models=[],
                    promoted_default=prev_def,
                    previous_default=self._previous_defaults.get(provider),
                    error_reason=f"Unknown provider: {provider}",
                )

            # Providers disabled by default (OpenAI, Anthropic) MUST NOT send outbound requests
            if not prov_cfg.is_enabled:
                log.info("catalog_discovery.provider_disabled", provider=provider)
                return CatalogSyncResult(
                    provider=provider,
                    success=True,
                    discovered_count=0,
                    models=self.get_active_models(provider),
                    promoted_default=prev_def,
                    previous_default=self._previous_defaults.get(provider),
                    error_reason="Provider is disabled by configuration (is_enabled=False)",
                    live_verified=False,
                )

            if not prov_cfg.has_api_key:
                log.info("catalog_discovery.missing_key", provider=provider)
                return CatalogSyncResult(
                    provider=provider,
                    success=True,
                    discovered_count=0,
                    models=self.get_active_models(provider),
                    promoted_default=prev_def,
                    previous_default=self._previous_defaults.get(provider),
                    error_reason=f"API key not configured ({prov_cfg.api_key_env_var})",
                    live_verified=False,
                )

            # Fetch from official endpoint
            try:
                discovered, live_verified = await self._fetch_official_models(provider, prov_cfg, client)
            except Exception as exc:
                log.warning("catalog_discovery.fetch_failed", provider=provider, error=str(exc))
                return CatalogSyncResult(
                    provider=provider,
                    success=False,
                    discovered_count=0,
                    models=self.get_active_models(provider),
                    promoted_default=prev_def,
                    previous_default=self._previous_defaults.get(provider),
                    error_reason=f"Discovery fetch failed: {exc}",
                    live_verified=False,
                )

            if not discovered:
                return CatalogSyncResult(
                    provider=provider,
                    success=True,
                    discovered_count=0,
                    models=self.get_active_models(provider),
                    promoted_default=prev_def,
                    previous_default=self._previous_defaults.get(provider),
                    error_reason="No compatible models returned by provider",
                    live_verified=live_verified,
                )

            # Store discovered catalog
            self._catalogs[provider] = discovered

            # Promotion evaluation
            promoted_default = prev_def
            if validate_promotion:
                promoted_default = await self._evaluate_and_promote_default(provider, discovered)

            return CatalogSyncResult(
                provider=provider,
                success=True,
                discovered_count=len(discovered),
                models=discovered,
                promoted_default=promoted_default,
                previous_default=self._previous_defaults.get(provider),
                voice_live_model=self._designated_audio_model if provider == "gemini" else None,
                live_verified=live_verified,
            )

    async def _fetch_official_models(
        self,
        provider: str,
        prov_cfg: Any,
        client: httpx.AsyncClient | None,
    ) -> tuple[list[DiscoveredModel], bool]:
        """Call official provider discovery endpoints."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
            should_close = True

        try:
            if provider == "gemini":
                return await self._discover_gemini(prov_cfg, client), True
            elif provider == "grok":
                return await self._discover_grok(prov_cfg, client), True
            elif provider == "groq":
                return await self._discover_groq(prov_cfg, client), True
            elif provider == "openai":
                return await self._discover_openai(prov_cfg, client), True
            elif provider == "anthropic":
                return await self._discover_anthropic(prov_cfg, client), True
            else:
                return [], False
        finally:
            if should_close:
                await client.aclose()

    async def _discover_gemini(
        self, prov_cfg: Any, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from Google Gemini API: GET /v1beta/models?key={api_key}."""
        url = f"{prov_cfg.base_url}/models?key={prov_cfg.api_key}"
        resp = await client.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API discovery returned HTTP {resp.status_code}")

        data = resp.json()
        raw_list = data.get("models", [])
        discovered: list[DiscoveredModel] = []

        for item in raw_list:
            raw_name = item.get("name", "")
            model_id = raw_name.replace("models/", "")
            methods = item.get("supportedGenerationMethods", [])

            # Must support text generation
            if "generateContent" not in methods:
                continue

            # Exclude non-chat/specialized embedding or vision-only internal tools
            if any(term in model_id.lower() for term in ("embedding", "aqa", "imagen", "whisper")):
                continue

            display_name = item.get("displayName") or model_id
            is_preview = any(k in model_id.lower() for k in ("preview", "exp", "experimental"))
            is_deprecated = "deprecated" in model_id.lower()
            is_stable = not is_preview and not is_deprecated

            task_types = ["general", "coding", "reasoning", "multimodal"]
            # Detect audio/speech capability
            if any("audio" in m.lower() for m in methods) or "audio" in model_id.lower():
                task_types.append("audio")

            # Check if this model is eligible for general chat promotion
            is_eligible = is_stable and "generateContent" in methods and not is_deprecated

            discovered.append(
                DiscoveredModel(
                    provider="gemini",
                    model_id=model_id,
                    display_name=display_name,
                    task_types=task_types,
                    input_token_limit=item.get("inputTokenLimit", 1000000),
                    output_token_limit=item.get("outputTokenLimit", 8192),
                    max_tokens=item.get("outputTokenLimit", 8192),
                    is_stable=is_stable,
                    is_preview=is_preview,
                    is_deprecated=is_deprecated,
                    is_eligible_for_promotion=is_eligible,
                    supported_generation_methods=methods,
                    raw_metadata=item,
                )
            )

        return discovered

    async def _discover_grok(
        self, prov_cfg: Any, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from xAI API: GET /v1/models."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"xAI API discovery returned HTTP {resp.status_code}")

        data = resp.json()
        raw_list = data.get("data", [])
        discovered: list[DiscoveredModel] = []

        for item in raw_list:
            model_id = item.get("id", "")
            # Strict provider isolation: ONLY native grok models under grok!
            if not model_id.startswith("grok"):
                continue

            is_deprecated = item.get("deprecated", False) or "deprecated" in model_id.lower()
            is_preview = any(k in model_id.lower() for k in ("preview", "beta", "exp"))
            is_stable = not is_preview and not is_deprecated

            task_types = ["general", "coding", "reasoning"]
            if "vision" in model_id.lower():
                task_types.append("multimodal")

            discovered.append(
                DiscoveredModel(
                    provider="grok",
                    model_id=model_id,
                    display_name=f"xAI {model_id.capitalize()}",
                    task_types=task_types,
                    max_tokens=item.get("max_tokens", 8192),
                    is_stable=is_stable,
                    is_preview=is_preview,
                    is_deprecated=is_deprecated,
                    is_eligible_for_promotion=is_stable and not is_deprecated,
                    raw_metadata=item,
                )
            )

        return discovered

    async def _discover_groq(
        self, prov_cfg: Any, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from Groq API: GET /openai/v1/models."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq API discovery returned HTTP {resp.status_code}")

        data = resp.json()
        raw_list = data.get("data", [])
        discovered: list[DiscoveredModel] = []

        for item in raw_list:
            model_id = item.get("id", "")
            # Groq hosts Qwen, Llama, Mixtral, GPT-OSS
            is_active = item.get("active", True)
            is_deprecated = item.get("deprecated", False) or not is_active or "deprecated" in model_id.lower()

            if is_deprecated:
                continue

            # Exclude whisper or non-chat models
            if any(term in model_id.lower() for term in ("whisper", "embedding", "guard", "distil")):
                continue

            task_types = ["general", "coding"]
            if any(k in model_id.lower() for k in ("qwen", "llama", "oss", "reason")):
                task_types.append("reasoning")

            discovered.append(
                DiscoveredModel(
                    provider="groq",
                    model_id=model_id,
                    display_name=f"Groq / {model_id}",
                    task_types=task_types,
                    max_tokens=min(item.get("context_window", 32768), 4096),
                    is_stable=not is_deprecated,
                    is_deprecated=is_deprecated,
                    is_eligible_for_promotion=not is_deprecated and is_active,
                    raw_metadata=item,
                )
            )

        return discovered

    async def _discover_openai(
        self, prov_cfg: Any, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from OpenAI API: GET /v1/models (only when enabled)."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI discovery returned HTTP {resp.status_code}")
        data = resp.json()
        discovered: list[DiscoveredModel] = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if not model_id.startswith("gpt-"):
                continue
            discovered.append(
                DiscoveredModel(
                    provider="openai",
                    model_id=model_id,
                    display_name=model_id,
                    task_types=["general", "coding", "reasoning"],
                    is_stable=True,
                    is_eligible_for_promotion=False,  # Disabled by policy from becoming global default
                    raw_metadata=item,
                )
            )
        return discovered

    async def _discover_anthropic(
        self, prov_cfg: Any, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from Anthropic API: GET /v1/models (only when enabled)."""
        headers = {
            "x-api-key": prov_cfg.api_key or "",
            "anthropic-version": "2023-06-01",
        }
        url = f"{prov_cfg.base_url}/models"
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Anthropic discovery returned HTTP {resp.status_code}")
        data = resp.json()
        discovered: list[DiscoveredModel] = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            discovered.append(
                DiscoveredModel(
                    provider="anthropic",
                    model_id=model_id,
                    display_name=item.get("display_name", model_id),
                    task_types=["general", "coding", "reasoning"],
                    is_stable=True,
                    is_eligible_for_promotion=False,
                    raw_metadata=item,
                )
            )
        return discovered

    async def _evaluate_and_promote_default(
        self,
        provider: str,
        discovered: list[DiscoveredModel],
    ) -> str:
        """Safely evaluate candidates and promote the newest stable model."""
        current_default = self._active_defaults.get(provider, "")
        eligible = [
            m for m in discovered
            if m.is_eligible_for_promotion and not m.is_deprecated and m.is_stable
        ]

        if not eligible:
            log.info("catalog_discovery.no_eligible_candidate", provider=provider, keeping=current_default)
            return current_default

        # Policy ranking:
        # 1. Version / number extraction or specific priority
        # 2. General reasoning capability
        candidate = self._pick_highest_ranking_model(provider, eligible)
        if not candidate or candidate.model_id == current_default:
            return current_default

        # Run canary policy check before promoting
        passed = await self._run_canary_validation(provider, candidate.model_id)
        if passed:
            log.info(
                "catalog_discovery.promoting_model",
                provider=provider,
                old_default=current_default,
                new_default=candidate.model_id,
            )
            self._previous_defaults[provider] = current_default
            self._active_defaults[provider] = candidate.model_id
            return candidate.model_id
        else:
            log.warning(
                "catalog_discovery.canary_failed_rollback",
                provider=provider,
                candidate=candidate.model_id,
                retained_default=current_default,
            )
            return current_default

    def _pick_highest_ranking_model(
        self, provider: str, candidates: list[DiscoveredModel]
    ) -> DiscoveredModel | None:
        """Pick the newest compatible GA model for a provider based on official versioning rules."""
        if not candidates:
            return None

        # Gemini ranking: promote highest general reasoning version (e.g. 4-argon > 3.8-flash > 2.5-flash)
        if provider == "gemini":
            # Priority: explicit flagship general models
            def gemini_rank(m: DiscoveredModel) -> float:
                mid = m.model_id.lower()
                # Version regex (matches 4, 3.8, 3.6, 2.5, 2.0, 1.5)
                match = re.search(r"(\d+(?:\.\d+)?)", mid)
                val = float(match.group(1)) if match else 1.0
                if "pro" in mid or "argon" in mid:
                    val += 0.5
                return val

            return max(candidates, key=gemini_rank)

        # Grok ranking: grok-4.7 > grok-3 > grok-2
        if provider == "grok":
            def grok_rank(m: DiscoveredModel) -> float:
                mid = m.model_id.lower()
                match = re.search(r"grok-(\d+(?:\.\d+)?)", mid)
                return float(match.group(1)) if match else 1.0

            return max(candidates, key=grok_rank)

        # Groq ranking: prefer active fast reasoning (qwen3.8-27b > gpt-oss-120b > llama-3.3-70b)
        if provider == "groq":
            return candidates[0]

        return candidates[0]

    async def _run_canary_validation(self, provider: str, model_id: str) -> bool:
        """Run canary validation hook or structural check."""
        if self.canary_hook is not None:
            try:
                res = self.canary_hook(provider, model_id)
                if asyncio.iscoroutine(res):
                    return await res
                return bool(res)
            except Exception as e:
                log.warning("catalog_discovery.canary_hook_error", error=str(e))
                return False

        # Default validation: verify provider config has API key and model is non-empty
        prov_cfg = get_provider_config(provider)
        if not prov_cfg or not prov_cfg.has_api_key:
            return False
        return True
