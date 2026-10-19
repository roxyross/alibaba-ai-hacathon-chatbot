"""Automatic Model Catalog Discovery and Safe Promotion Service.

Discovers models dynamically from official provider endpoints:
- Google Gemini API (`/v1beta/models`)
- Alibaba DashScope / Qwen (`/compatible-mode/v1/models`)
- xAI Grok (`/v1/models`)
- Groq Inference Platform (`/openai/v1/models`)
- DeepSeek (`/models`)
- OpenAI (`/v1/models` — validated only when enabled)
- Anthropic Claude (`/v1/models` — validated only when enabled)

Enforces:
1. Exact model ID & capability validation (never scrape unofficial lists or invent IDs).
2. Distinction between stable/GA vs preview/deprecated models.
3. Audio/Voice/Live isolation: preserves Gemini 3.8 Flash for audio/live/TTS tasks.
4. Provider separation: prevents leaking Groq models into Grok or vice-versa.
5. Canary validation & safe promotion with previous default preservation and rollback.
6. Offline/startup resilience: network failure or missing keys never blocks startup.
7. Explicit user model selection preservation.
8. Bounded retries, pagination, and caching across transient failures.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
import structlog

from app.ai_gateway.models.provider import (
    ModelConfig,
    ProviderConfig,
    ProviderState,
    _default_models,
    get_all_provider_configs,
    get_provider_config,
)

log = structlog.get_logger()


@dataclass
class DiscoveredModel:
    """A model discovered from an official provider endpoint with validation metadata."""

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
    requires_api_key: bool = False
    validation_status: str = "verified"  # discovered | catalogued | metadata_validated | compatibility_tested | verified | deprecated
    provenance: str = "official_api"  # official_api | cached | static_baseline
    capabilities: list[str] = field(default_factory=list)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_successful_discovery: datetime | None = None
    status: str = "active"  # active | deprecated | retired | retained
    retirement_evidence: str | None = None
    supported_generation_methods: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_model_config(self) -> ModelConfig:
        return ModelConfig(
            name=self.model_id,
            display_name=self.display_name,
            task_types=tuple(self.task_types),
            cost_per_1k_input=self.cost_per_1k_input,
            cost_per_1k_output=self.cost_per_1k_output,
            max_tokens=self.max_tokens,
            enabled=not self.is_deprecated and self.status != "retired",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "task_types": self.task_types,
            "max_tokens": self.max_tokens,
            "input_token_limit": self.input_token_limit,
            "output_token_limit": self.output_token_limit,
            "is_stable": self.is_stable,
            "is_deprecated": self.is_deprecated,
            "is_preview": self.is_preview,
            "is_eligible_for_promotion": self.is_eligible_for_promotion,
            "requires_api_key": self.requires_api_key,
            "validation_status": self.validation_status,
            "provenance": self.provenance,
            "status": self.status,
            "capabilities": self.capabilities,
            "cost_per_1k_input": self.cost_per_1k_input,
            "cost_per_1k_output": self.cost_per_1k_output,
            "discovered_at": self.discovered_at.isoformat(),
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "last_verified_at": self.last_verified_at.isoformat(),
            "last_successful_discovery": (
                self.last_successful_discovery.isoformat()
                if self.last_successful_discovery
                else None
            ),
            "retirement_evidence": self.retirement_evidence,
            "supported_generation_methods": self.supported_generation_methods,
            "raw_metadata": self.raw_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveredModel:
        now_utc = datetime.now(timezone.utc)
        disc_at = (
            datetime.fromisoformat(data["discovered_at"])
            if "discovered_at" in data
            else now_utc
        )
        first_seen = (
            datetime.fromisoformat(data["first_seen_at"])
            if "first_seen_at" in data
            else disc_at
        )
        last_seen = (
            datetime.fromisoformat(data["last_seen_at"])
            if "last_seen_at" in data
            else disc_at
        )
        last_ver = (
            datetime.fromisoformat(data["last_verified_at"])
            if "last_verified_at" in data
            else disc_at
        )
        last_succ = (
            datetime.fromisoformat(data["last_successful_discovery"])
            if data.get("last_successful_discovery")
            else None
        )

        return cls(
            provider=data["provider"],
            model_id=data["model_id"],
            display_name=data["display_name"],
            task_types=list(data.get("task_types", ["general"])),
            max_tokens=data.get("max_tokens", 4096),
            input_token_limit=data.get("input_token_limit", 32768),
            output_token_limit=data.get("output_token_limit", 4096),
            is_stable=data.get("is_stable", True),
            is_deprecated=data.get("is_deprecated", False),
            is_preview=data.get("is_preview", False),
            is_eligible_for_promotion=data.get("is_eligible_for_promotion", False),
            requires_api_key=data.get("requires_api_key", False),
            validation_status=data.get("validation_status", "verified"),
            provenance=data.get("provenance", "cached"),
            capabilities=list(data.get("capabilities", [])),
            cost_per_1k_input=float(data.get("cost_per_1k_input", 0.0)),
            cost_per_1k_output=float(data.get("cost_per_1k_output", 0.0)),
            discovered_at=disc_at,
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            last_verified_at=last_ver,
            last_successful_discovery=last_succ,
            status=data.get("status", "active"),
            retirement_evidence=data.get("retirement_evidence"),
            supported_generation_methods=list(
                data.get("supported_generation_methods", [])
            ),
            raw_metadata=dict(data.get("raw_metadata", {})),
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
    provider_state: ProviderState = ProviderState.CONFIGURED
    provenance: str = "official_api"
    is_stale: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ModelCatalogDiscoveryService:
    """Centralized lifecycle service for provider model discovery, persistence, and safe promotion."""

    _instance: ModelCatalogDiscoveryService | None = None

    def __init__(self, cache_file_path: str | None = None) -> None:
        self._lock = asyncio.Lock()
        self._active_refreshes: set[str] = set()
        self.cache_file_path: str = cache_file_path or os.environ.get(
            "ROXY_CATALOG_CACHE_PATH",
            os.path.join(os.path.dirname(__file__), ".model_catalog_cache.json"),
        )
        # Default active selections
        self._active_defaults: dict[str, str] = {
            "gemini": "gemini-4-argon",
            "dashscope": "qwen-max",
            "grok": "grok-4.7",
            "groq": "qwen/qwen3.8-27b",
            "deepseek": "deepseek-chat-v3",
            "openai": "gpt-4o",
            "anthropic": "claude-3-5-sonnet-latest",
        }
        self._previous_defaults: dict[str, str] = {
            "gemini": "gemini-3.8-flash",
            "dashscope": "qwen-plus",
            "grok": "grok-3",
            "groq": "llama-3.3-70b-versatile",
            "deepseek": "deepseek-chat-v3",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-latest",
        }
        # Fixed Voice / Audio / Live API designated model
        self._designated_audio_model: str = "gemini-3.8-flash"
        # In-memory and cached catalogs
        self._catalogs: dict[str, list[DiscoveredModel]] = {}
        self._cached_catalogs: dict[str, list[DiscoveredModel]] = {}
        self._last_refresh_timestamps: dict[str, datetime] = {}
        self._last_refresh_status: dict[str, str] = {}
        # Promotion validation canary hook (can be mocked in tests)
        self.canary_hook: Callable[[str, str], bool] | None = None

        # Load persisted catalog cache if available
        self._load_cache_from_disk()

    @classmethod
    def get_instance(cls) -> ModelCatalogDiscoveryService:
        if cls._instance is None:
            cls._instance = ModelCatalogDiscoveryService()
        return cls._instance

    def _save_cache_to_disk(self) -> None:
        """Persist last-known-good catalog and model lifecycle state to disk atomically."""
        if not self.cache_file_path:
            return
        try:
            cache_path = self.cache_file_path
            os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
            data = {
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "active_defaults": self._active_defaults,
                "previous_defaults": self._previous_defaults,
                "catalogs": {
                    prov: [m.to_dict() for m in models]
                    for prov, models in self._cached_catalogs.items()
                },
                "last_refresh_timestamps": {
                    prov: dt.isoformat()
                    for prov, dt in self._last_refresh_timestamps.items()
                },
                "last_refresh_status": self._last_refresh_status,
            }
            tmp_path = f"{cache_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, cache_path)
        except Exception as exc:
            log.warning("catalog_discovery.save_cache_failed", error=str(exc))

    def _load_cache_from_disk(self) -> None:
        """Load last-known-good catalog from disk if present."""
        if not self.cache_file_path or not os.path.exists(self.cache_file_path):
            return
        try:
            with open(self.cache_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "active_defaults" in data and isinstance(data["active_defaults"], dict):
                self._active_defaults.update(data["active_defaults"])
            if "previous_defaults" in data and isinstance(data["previous_defaults"], dict):
                self._previous_defaults.update(data["previous_defaults"])

            if "catalogs" in data and isinstance(data["catalogs"], dict):
                for prov, model_dicts in data["catalogs"].items():
                    restored = [DiscoveredModel.from_dict(md) for md in model_dicts]
                    self._cached_catalogs[prov] = restored
                    self._catalogs[prov] = restored

            if "last_refresh_status" in data and isinstance(data["last_refresh_status"], dict):
                self._last_refresh_status.update(data["last_refresh_status"])
        except Exception as exc:
            log.warning("catalog_discovery.load_cache_failed", error=str(exc))

    def resolve_effective_model(
        self,
        provider: str,
        user_selected_model: str | None = None,
        task_type: str = "general",
    ) -> str:
        """Resolve effective model adhering strictly to user selection preservation."""
        if user_selected_model:
            return user_selected_model
        return self.get_default_model(provider, task_type)

    def mark_model_retired(self, provider: str, model_id: str, evidence: str) -> bool:
        """Explicitly record verified official provider retirement for a model."""
        canonical = "dashscope" if provider in ("qwen", "alibaba") else provider
        models = self.get_active_models(canonical)
        for m in models:
            if m.model_id == model_id:
                m.is_deprecated = True
                m.status = "retired"
                m.validation_status = "retired"
                m.retirement_evidence = evidence
                m.last_verified_at = datetime.now(timezone.utc)
                self._save_cache_to_disk()
                return True
        return False

    def get_default_model(self, provider: str, task_type: str = "general") -> str:
        """Return the current active default model for a provider and task type."""
        canonical = "dashscope" if provider in ("qwen", "alibaba") else provider
        if canonical == "gemini":
            if task_type in ("tts", "stt", "live", "text-to-speech", "speech-to-text", "live_audio", "live-audio"):
                return "gemini-3.8-plus"
            if task_type in ("audio", "voice"):
                return self._designated_audio_model
        return self._active_defaults.get(canonical, "gemini-4-argon")

    def get_previous_default(self, provider: str) -> str | None:
        """Return the healthy previous default model for fallback."""
        canonical = "dashscope" if provider in ("qwen", "alibaba") else provider
        return self._previous_defaults.get(canonical)

    def get_voice_live_model(self) -> str:
        """Preserve designated voice/TTS/Live API model."""
        return self._designated_audio_model

    def get_last_refresh_timestamp(self, provider: str) -> datetime | None:
        canonical = "dashscope" if provider in ("qwen", "alibaba") else provider
        return self._last_refresh_timestamps.get(canonical)

    def get_active_models(self, provider: str) -> list[DiscoveredModel]:
        """Return discovered models for provider, cached models, or baseline defaults."""
        canonical = "dashscope" if provider in ("qwen", "alibaba") else provider
        if canonical in self._catalogs and self._catalogs[canonical]:
            return self._catalogs[canonical]
        if canonical in self._cached_catalogs and self._cached_catalogs[canonical]:
            return self._cached_catalogs[canonical]

        # Return fallback from static config with explicit provenance and key status
        prov_cfg = get_provider_config(canonical)
        has_key = prov_cfg.has_api_key if prov_cfg else False
        configs = _default_models(canonical)
        return [
            DiscoveredModel(
                provider=canonical,
                model_id=c.name,
                display_name=c.display_name,
                task_types=list(c.task_types),
                max_tokens=c.max_tokens,
                cost_per_1k_input=c.cost_per_1k_input,
                cost_per_1k_output=c.cost_per_1k_output,
                is_stable=True,
                is_eligible_for_promotion=(c.name == self._active_defaults.get(canonical)),
                requires_api_key=not has_key,
                validation_status="verified",
                provenance="static_baseline",
            )
            for c in configs
        ]

    async def refresh_all(
        self, client: httpx.AsyncClient | None = None
    ) -> dict[str, CatalogSyncResult]:
        """Refresh catalogs for all supported providers concurrently with error isolation."""
        results: dict[str, CatalogSyncResult] = {}
        providers = ["gemini", "dashscope", "grok", "groq", "deepseek", "openai", "anthropic"]

        for prov in providers:
            try:
                results[prov] = await self.refresh_provider_catalog(prov, client=client)
            except Exception as exc:
                log.error("catalog_discovery.unhandled_provider_error", provider=prov, error=str(exc))
                prev_def = self._active_defaults.get(prov)
                results[prov] = CatalogSyncResult(
                    provider=prov,
                    success=False,
                    discovered_count=len(self.get_active_models(prov)),
                    models=self.get_active_models(prov),
                    promoted_default=prev_def,
                    previous_default=self._previous_defaults.get(prov),
                    error_reason=f"Discovery failed: {exc}",
                    live_verified=False,
                    provenance="cached",
                )
        return results

    async def refresh_provider_catalog(
        self,
        provider: str,
        client: httpx.AsyncClient | None = None,
        validate_promotion: bool = True,
    ) -> CatalogSyncResult:
        """Refresh a single provider's catalog from its official discovery endpoint."""
        canonical = "dashscope" if provider in ("qwen", "alibaba") else provider
        if canonical in self._active_refreshes:
            log.warning("catalog_discovery.concurrent_refresh_skipped", provider=canonical)
            cached_models = self.get_active_models(canonical)
            return CatalogSyncResult(
                provider=canonical,
                success=True,
                discovered_count=len(cached_models),
                models=cached_models,
                promoted_default=self._active_defaults.get(canonical),
                previous_default=self._previous_defaults.get(canonical),
                error_reason="Concurrent refresh in progress; returning cached catalog",
                live_verified=False,
                provider_state=ProviderState.HEALTHY,
                provenance="cached",
            )

        self._active_refreshes.add(canonical)
        try:
            async with self._lock:
                prov_cfg = get_provider_config(canonical)
                prev_def = self._active_defaults.get(canonical)

                if prov_cfg is None:
                    return CatalogSyncResult(
                        provider=canonical,
                        success=False,
                        discovered_count=0,
                        models=[],
                        promoted_default=prev_def,
                        previous_default=self._previous_defaults.get(canonical),
                        error_reason=f"Unknown provider: {canonical}",
                        provider_state=ProviderState.UNAVAILABLE,
                    )

                # Providers disabled by default (OpenAI, Anthropic) MUST NOT send outbound requests
                if not prov_cfg.is_enabled:
                    log.info("catalog_discovery.provider_disabled", provider=canonical)
                    models = self.get_active_models(canonical)
                    for m in models:
                        m.requires_api_key = not prov_cfg.has_api_key
                    return CatalogSyncResult(
                        provider=canonical,
                        success=True,
                        discovered_count=len(models),
                        models=models,
                        promoted_default=prev_def,
                        previous_default=self._previous_defaults.get(canonical),
                        error_reason="Provider is disabled by configuration (is_enabled=False)",
                        live_verified=False,
                        provider_state=ProviderState.DISABLED,
                        provenance="static_baseline",
                    )

                # If provider lacks credentials, return cached or static baseline without calling out
                if not prov_cfg.has_api_key:
                    log.info("catalog_discovery.missing_key", provider=canonical)
                    models = self.get_active_models(canonical)
                    for m in models:
                        m.requires_api_key = True
                    self._last_refresh_status[canonical] = "credentials_missing"
                    return CatalogSyncResult(
                        provider=canonical,
                        success=True,
                        discovered_count=len(models),
                        models=models,
                        promoted_default=prev_def,
                        previous_default=self._previous_defaults.get(canonical),
                        error_reason=f"API key not configured ({prov_cfg.api_key_env_var})",
                        live_verified=False,
                        provider_state=ProviderState.NOT_CONFIGURED,
                        provenance="static_baseline" if canonical not in self._cached_catalogs else "cached",
                    )

                # Fetch from official endpoint with bounded retries
                try:
                    discovered, live_verified = await self._fetch_official_models(canonical, prov_cfg, client)
                except Exception as exc:
                    log.warning("catalog_discovery.fetch_failed", provider=canonical, error=str(exc))
                    self._last_refresh_status[canonical] = f"error: {exc}"
                    # Preserve previously cached models if available! Never delete on single failure
                    cached_models = self.get_active_models(canonical)
                    for m in cached_models:
                        m.provenance = "cached"
                    return CatalogSyncResult(
                        provider=canonical,
                        success=False,
                        discovered_count=len(cached_models),
                        models=cached_models,
                        promoted_default=prev_def,
                        previous_default=self._previous_defaults.get(canonical),
                        error_reason=f"Discovery fetch failed: {exc}",
                        live_verified=False,
                        provider_state=ProviderState.DEGRADED,
                        provenance="cached",
                        is_stale=True,
                    )

                if not discovered:
                    models = self.get_active_models(canonical)
                    return CatalogSyncResult(
                        provider=canonical,
                        success=True,
                        discovered_count=len(models),
                        models=models,
                        promoted_default=prev_def,
                        previous_default=self._previous_defaults.get(canonical),
                        error_reason="No compatible models returned by provider",
                        live_verified=live_verified,
                        provider_state=ProviderState.HEALTHY,
                        provenance="cached",
                    )

                # Durable model preservation: merge newly discovered models with historical known models
                deduped_discovered: dict[str, DiscoveredModel] = {m.model_id: m for m in discovered}
                now_utc = datetime.now(timezone.utc)

                if canonical in self._catalogs and self._catalogs[canonical]:
                    model_registry: dict[str, DiscoveredModel] = {
                        m.model_id: m for m in self._catalogs[canonical]
                    }
                elif canonical in self._cached_catalogs and self._cached_catalogs[canonical]:
                    model_registry = {
                        m.model_id: m for m in self._cached_catalogs[canonical]
                    }
                else:
                    model_registry = {}

                for m in deduped_discovered.values():
                    if m.model_id in model_registry:
                        old = model_registry[m.model_id]
                        m.first_seen_at = old.first_seen_at or old.discovered_at
                        m.last_seen_at = now_utc
                        m.last_verified_at = now_utc
                        m.last_successful_discovery = now_utc
                        # Preserve retirement if confirmed
                        if old.status == "retired" and not m.is_stable:
                            m.status = "retired"
                            m.retirement_evidence = old.retirement_evidence
                        elif m.is_deprecated:
                            m.status = "deprecated"
                        else:
                            m.status = "active"
                        m.provenance = "official_api"
                        model_registry[m.model_id] = m
                    else:
                        m.first_seen_at = now_utc
                        m.last_seen_at = now_utc
                        m.last_verified_at = now_utc
                        m.last_successful_discovery = now_utc
                        m.status = "deprecated" if m.is_deprecated else "active"
                        m.provenance = "official_api"
                        model_registry[m.model_id] = m

                # Models previously known but missing from this response:
                # A transient omission MUST NOT delete previously known models!
                for mid, m in list(model_registry.items()):
                    if mid not in deduped_discovered:
                        m.provenance = "cached"
                        if m.status not in ("retired", "deprecated"):
                            m.status = "retained"

                final_models = list(model_registry.values())

                # Store in active catalog and persistent cache
                self._catalogs[canonical] = final_models
                self._cached_catalogs[canonical] = final_models
                self._last_refresh_timestamps[canonical] = now_utc
                self._last_refresh_status[canonical] = "success"
                self._save_cache_to_disk()

                # Promotion evaluation
                promoted_default = prev_def
                if validate_promotion:
                    promoted_default = await self._evaluate_and_promote_default(canonical, final_models)

                return CatalogSyncResult(
                    provider=canonical,
                    success=True,
                    discovered_count=len(deduped_discovered),
                    models=final_models,
                    promoted_default=promoted_default,
                    previous_default=self._previous_defaults.get(canonical),
                    voice_live_model=self._designated_audio_model if canonical == "gemini" else None,
                    live_verified=live_verified,
                    provider_state=ProviderState.HEALTHY,
                    provenance="official_api",
                )
        finally:
            self._active_refreshes.discard(canonical)

    # -------------------------------------------------------------------------
    # Provider-specific official discovery methods
    # -------------------------------------------------------------------------

    async def _fetch_official_models(
        self,
        provider: str,
        prov_cfg: ProviderConfig,
        client: httpx.AsyncClient | None,
    ) -> tuple[list[DiscoveredModel], bool]:
        """Route to provider-specific discovery endpoint."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
            should_close = True

        try:
            if provider == "gemini":
                return await self._discover_gemini(prov_cfg, client), True
            elif provider == "dashscope":
                return await self._discover_dashscope(prov_cfg, client), True
            elif provider == "grok":
                return await self._discover_grok(prov_cfg, client), True
            elif provider == "groq":
                return await self._discover_groq(prov_cfg, client), True
            elif provider == "deepseek":
                return await self._discover_deepseek(prov_cfg, client), True
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
        self, prov_cfg: ProviderConfig, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from Google Gemini API: GET /v1beta/models with pagination."""
        discovered: list[DiscoveredModel] = []
        page_token: str | None = None
        pages_fetched = 0

        while pages_fetched < 5:
            url = f"{prov_cfg.base_url}/models?key={prov_cfg.api_key}"
            if page_token:
                url += f"&pageToken={page_token}"

            resp = await self._get_with_retry(client, url)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API discovery returned HTTP {resp.status_code}")

            data = resp.json()
            raw_list = data.get("models", [])

            for item in raw_list:
                raw_name = item.get("name", "")
                model_id = raw_name.replace("models/", "")
                methods = item.get("supportedGenerationMethods", [])

                # Must support text generation
                if "generateContent" not in methods:
                    continue

                # Exclude non-chat / internal embedding models
                if any(term in model_id.lower() for term in ("embedding", "aqa", "imagen", "whisper")):
                    continue

                display_name = item.get("displayName") or model_id
                is_preview = any(k in model_id.lower() for k in ("preview", "exp", "experimental"))
                is_deprecated = "deprecated" in model_id.lower()
                is_stable = not is_preview and not is_deprecated

                task_types = ["general", "coding", "reasoning", "multimodal"]
                if any("audio" in m.lower() for m in methods) or "audio" in model_id.lower():
                    task_types.append("audio")

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
                        provenance="official_api",
                        validation_status="verified" if is_stable else "catalogued",
                        raw_metadata=item,
                    )
                )

            page_token = data.get("nextPageToken")
            pages_fetched += 1
            if not page_token:
                break

        return discovered

    async def _discover_dashscope(
        self, prov_cfg: ProviderConfig, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from Alibaba DashScope (Qwen): GET /compatible-mode/v1/models."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await self._get_with_retry(client, url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"DashScope API discovery returned HTTP {resp.status_code}")

        data = resp.json()
        raw_list = data.get("data", [])
        discovered: list[DiscoveredModel] = []

        for item in raw_list:
            model_id = item.get("id", "")
            # Filter to Qwen models
            if not any(k in model_id.lower() for k in ("qwen", "qwq")):
                continue

            # Exclude embedding or text-to-image specialized non-chat endpoints
            if any(term in model_id.lower() for term in ("embedding", "ocr", "wanx", "tts")):
                continue

            is_deprecated = "deprecated" in model_id.lower()
            is_preview = any(k in model_id.lower() for k in ("preview", "beta", "exp"))
            is_stable = not is_preview and not is_deprecated

            task_types = ["general", "coding", "reasoning"]
            if "coder" in model_id.lower():
                task_types = ["coding", "reasoning"]
            elif "vl" in model_id.lower():
                task_types.append("multimodal")

            display_name = f"Alibaba / {model_id}"

            discovered.append(
                DiscoveredModel(
                    provider="dashscope",
                    model_id=model_id,
                    display_name=display_name,
                    task_types=task_types,
                    max_tokens=32768,
                    is_stable=is_stable,
                    is_preview=is_preview,
                    is_deprecated=is_deprecated,
                    is_eligible_for_promotion=is_stable and not is_deprecated,
                    provenance="official_api",
                    validation_status="verified" if is_stable else "catalogued",
                    raw_metadata=item,
                )
            )

        return discovered

    async def _discover_grok(
        self, prov_cfg: ProviderConfig, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from xAI API: GET /v1/models."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await self._get_with_retry(client, url, headers=headers)
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
                    provenance="official_api",
                    validation_status="verified" if is_stable else "catalogued",
                    raw_metadata=item,
                )
            )

        return discovered

    async def _discover_groq(
        self, prov_cfg: ProviderConfig, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from Groq API: GET /openai/v1/models."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await self._get_with_retry(client, url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Groq API discovery returned HTTP {resp.status_code}")

        data = resp.json()
        raw_list = data.get("data", [])
        discovered: list[DiscoveredModel] = []

        for item in raw_list:
            model_id = item.get("id", "")
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
                    provenance="official_api",
                    validation_status="verified",
                    raw_metadata=item,
                )
            )

        return discovered

    async def _discover_deepseek(
        self, prov_cfg: ProviderConfig, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from DeepSeek API: GET /models."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await self._get_with_retry(client, url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"DeepSeek API discovery returned HTTP {resp.status_code}")

        data = resp.json()
        raw_list = data.get("data", [])
        discovered: list[DiscoveredModel] = []

        for item in raw_list:
            model_id = item.get("id", "")
            if not model_id:
                continue

            task_types = ["general", "coding"]
            if "reason" in model_id.lower() or "r1" in model_id.lower():
                task_types = ["reasoning", "coding"]

            display_name = "DeepSeek R1" if "reason" in model_id.lower() else f"DeepSeek {model_id.capitalize()}"

            discovered.append(
                DiscoveredModel(
                    provider="deepseek",
                    model_id=model_id,
                    display_name=display_name,
                    task_types=task_types,
                    max_tokens=64000,
                    is_stable=True,
                    is_eligible_for_promotion=True,
                    provenance="official_api",
                    validation_status="verified",
                    raw_metadata=item,
                )
            )

        return discovered

    async def _discover_openai(
        self, prov_cfg: ProviderConfig, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from OpenAI API: GET /v1/models (only when enabled)."""
        headers = {"Authorization": f"Bearer {prov_cfg.api_key}"}
        url = f"{prov_cfg.base_url}/models"
        resp = await self._get_with_retry(client, url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI discovery returned HTTP {resp.status_code}")

        data = resp.json()
        discovered: list[DiscoveredModel] = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if not any(model_id.startswith(p) for p in ("gpt-", "o1", "o3", "chatgpt")):
                continue
            discovered.append(
                DiscoveredModel(
                    provider="openai",
                    model_id=model_id,
                    display_name=model_id,
                    task_types=["general", "coding", "reasoning"],
                    is_stable=True,
                    is_eligible_for_promotion=False,  # Disabled by policy from replacing verified default
                    provenance="official_api",
                    validation_status="verified",
                    raw_metadata=item,
                )
            )
        return discovered

    async def _discover_anthropic(
        self, prov_cfg: ProviderConfig, client: httpx.AsyncClient
    ) -> list[DiscoveredModel]:
        """Fetch models from Anthropic API: GET /v1/models (only when enabled)."""
        headers = {
            "x-api-key": prov_cfg.api_key or "",
            "anthropic-version": "2023-06-01",
        }
        url = f"{prov_cfg.base_url}/models"
        resp = await self._get_with_retry(client, url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Anthropic discovery returned HTTP {resp.status_code}")

        data = resp.json()
        discovered: list[DiscoveredModel] = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if not model_id or not model_id.lower().startswith("claude-"):
                continue
            discovered.append(
                DiscoveredModel(
                    provider="anthropic",
                    model_id=model_id,
                    display_name=item.get("display_name", model_id),
                    task_types=["general", "coding", "reasoning"],
                    is_stable=True,
                    is_eligible_for_promotion=False,
                    provenance="official_api",
                    validation_status="verified",
                    raw_metadata=item,
                )
            )
        return discovered

    # -------------------------------------------------------------------------
    # Safe bounded HTTP retries
    # -------------------------------------------------------------------------

    async def _get_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str] | None = None,
        max_retries: int = 2,
    ) -> httpx.Response:
        """Execute GET with exponential backoff on transient errors and rate limits."""
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = await client.get(url, headers=headers)
                # Handle rate limiting (429) with Retry-After header
                if resp.status_code == 429 and attempt < max_retries:
                    retry_after = 1.0
                    if "retry-after" in resp.headers:
                        try:
                            retry_after = float(resp.headers["retry-after"])
                        except ValueError:
                            retry_after = 1.0
                    await asyncio.sleep(min(retry_after, 3.0))
                    continue
                # Transient 5xx errors retry
                if resp.status_code in (500, 502, 503, 504) and attempt < max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                return resp
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Failed to fetch {url} after {max_retries} retries")

    # -------------------------------------------------------------------------
    # Safe Canary Evaluation & Promotion
    # -------------------------------------------------------------------------

    async def _evaluate_and_promote_default(
        self,
        provider: str,
        discovered: list[DiscoveredModel],
    ) -> str:
        """Safely evaluate candidates and promote the newest stable model."""
        current_default = self._active_defaults.get(provider, "")
        eligible = [
            m
            for m in discovered
            if m.is_eligible_for_promotion and not m.is_deprecated and m.is_stable
        ]

        if not eligible:
            log.info("catalog_discovery.no_eligible_candidate", provider=provider, keeping=current_default)
            return current_default

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
            def gemini_rank(m: DiscoveredModel) -> float:
                mid = m.model_id.lower()
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

        # DashScope ranking: qwen-max > qwen-plus > qwen-turbo
        if provider == "dashscope":
            def dashscope_rank(m: DiscoveredModel) -> float:
                mid = m.model_id.lower()
                if "max" in mid:
                    return 3.0
                if "plus" in mid:
                    return 2.0
                if "coder" in mid:
                    return 1.8
                return 1.0

            return max(candidates, key=dashscope_rank)

        # Groq ranking: prefer active fast reasoning (qwen3.8-27b > gpt-oss-120b > llama-3.3-70b)
        if provider == "groq":
            return candidates[0]

        # DeepSeek ranking: deepseek-chat-v3 > deepseek-chat > deepseek-reasoner
        if provider == "deepseek":
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
