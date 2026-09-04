"""Provider configuration read from environment variables.

All API keys are read from env at runtime — never hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


# -----------------------------------------------------------------------------
# Provider feature flags
# -----------------------------------------------------------------------------

PROVIDER_FEATURE_FLAGS: dict[str, str] = {
    "deepseek": "PROVIDER_DEEPSEEK_ENABLED",
    "grok": "PROVIDER_GROK_ENABLED",
    "openai": "PROVIDER_OPENAI_ENABLED",
    "gemini": "PROVIDER_GEMINI_ENABLED",
}

PROVIDER_API_KEY_VARS: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "grok": "GROK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

PROVIDER_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "grok": "https://api.x.ai/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}

# Routing priority: lower number = higher priority.
# Active providers: Gemini (primary) → Grok (fallback).
# DeepSeek and OpenAI remain registered but are disabled via feature flags.
DEFAULT_ROUTING_PRIORITY: dict[str, int] = {
    "gemini": 1,
    "grok": 2,
    "deepseek": 3,
    "openai": 4,
}


# -----------------------------------------------------------------------------
# Circuit breaker defaults
# -----------------------------------------------------------------------------

CB_FAILURES = int(os.environ.get("CIRCUIT_BREAKER_FAILURES", "5"))
CB_RESET_SECONDS = int(os.environ.get("CIRCUIT_BREAKER_RESET_SECONDS", "30"))


# -----------------------------------------------------------------------------
# Dataclasses (not Pydantic — used internally by adapters)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a single model within a provider."""

    name: str  # Provider-native model name, e.g. "deepseek-chat-v3"
    display_name: str  # Human-readable, e.g. "DeepSeek V3"
    task_types: tuple[str, ...] = ("general",)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_tokens: int = 4096
    enabled: bool = True


@dataclass
class ProviderConfig:
    """Runtime configuration for a single AI provider."""

    name: str
    api_key_env_var: str
    base_url: str
    routing_priority: int
    timeout_seconds: float = 10.0
    supports_streaming: bool = True
    models: tuple[ModelConfig, ...] = field(default_factory=tuple)

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env_var)

    @property
    def is_enabled(self) -> bool:
        flag_env = PROVIDER_FEATURE_FLAGS.get(self.name)
        if flag_env is None:
            return True
        return os.environ.get(flag_env, "true").lower() in ("true", "1", "yes")

    @property
    def has_api_key(self) -> bool:
        key = self.api_key
        return key is not None and key != ""


# -----------------------------------------------------------------------------
# Provider registry
# -----------------------------------------------------------------------------

def _default_models(provider: str) -> tuple[ModelConfig, ...]:
    defaults: dict[str, tuple[ModelConfig, ...]] = {
        "deepseek": (
            ModelConfig(name="deepseek-chat-v3", display_name="DeepSeek V3", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.001, cost_per_1k_output=0.002, max_tokens=64000),
            ModelConfig(name="deepseek-reasoner", display_name="DeepSeek R1", task_types=("reasoning",), cost_per_1k_input=0.001, cost_per_1k_output=0.006, max_tokens=64000),
        ),
        "grok": (
            ModelConfig(name="grok-3", display_name="Grok 3", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.005, cost_per_1k_output=0.015, max_tokens=131072),
            ModelConfig(name="grok-2", display_name="Grok 2", task_types=("general",), cost_per_1k_input=0.002, cost_per_1k_output=0.01, max_tokens=131072),
        ),
        "openai": (
            ModelConfig(name="gpt-4o", display_name="GPT-4o", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0025, cost_per_1k_output=0.01, max_tokens=128000),
            ModelConfig(name="gpt-4o-mini", display_name="GPT-4o Mini", task_types=("general", "coding"), cost_per_1k_input=0.00015, cost_per_1k_output=0.0006, max_tokens=128000),
        ),
        "gemini": (
            ModelConfig(name="gemini-2.0-flash", display_name="Gemini 2.0 Flash", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-1.5-pro", display_name="Gemini 1.5 Pro", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.00125, cost_per_1k_output=0.005, max_tokens=2000000),
        ),
    }
    return defaults.get(provider, ())


def get_provider_config(name: str) -> ProviderConfig | None:
    """Build ProviderConfig for a named provider, reading from env."""
    api_key_var = PROVIDER_API_KEY_VARS.get(name)
    base_url = PROVIDER_BASE_URLS.get(name)
    if api_key_var is None or base_url is None:
        return None

    return ProviderConfig(
        name=name,
        api_key_env_var=api_key_var,
        base_url=base_url,
        routing_priority=DEFAULT_ROUTING_PRIORITY.get(name, 99),
        timeout_seconds=10.0,
        supports_streaming=True,
        models=_default_models(name),
    )


def get_all_provider_configs() -> list[ProviderConfig]:
    """Return configured provider configs for all known providers."""
    configs = []
    for name in PROVIDER_API_KEY_VARS:
        cfg = get_provider_config(name)
        if cfg is not None:
            configs.append(cfg)
    return configs
