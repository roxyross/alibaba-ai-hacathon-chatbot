"""Provider configuration read from environment variables.

All API keys are read from env at runtime — never hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from enum import Enum


class ProviderState(str, Enum):
    """Explicit operational and authentication state for an AI provider."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    DISABLED = "DISABLED"
    CONFIGURED = "CONFIGURED"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


# -----------------------------------------------------------------------------
# Provider feature flags
# -----------------------------------------------------------------------------

PROVIDER_FEATURE_FLAGS: dict[str, str] = {
    "deepseek": "PROVIDER_DEEPSEEK_ENABLED",
    "grok": "PROVIDER_GROK_ENABLED",
    "groq": "PROVIDER_GROQ_ENABLED",
    "openai": "PROVIDER_OPENAI_ENABLED",
    "anthropic": "PROVIDER_ANTHROPIC_ENABLED",
    "gemini": "PROVIDER_GEMINI_ENABLED",
    "dashscope": "PROVIDER_DASHSCOPE_ENABLED",
}

PROVIDER_API_KEY_VARS: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "grok": "GROK_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
}

PROVIDER_BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "grok": "https://api.x.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

# Routing priority: lower number = higher priority.
# Gemini (primary product default) → DashScope (Qwen) → Groq (fast LPU) → Grok (xAI) → DeepSeek → OpenAI → Anthropic.
DEFAULT_ROUTING_PRIORITY: dict[str, int] = {
    "gemini": 1,
    "dashscope": 2,
    "groq": 3,
    "grok": 4,
    "deepseek": 5,
    "openai": 6,
    "anthropic": 7,
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
        key = os.environ.get(self.api_key_env_var) or None
        if not key:
            if self.name in ("dashscope", "qwen", "alibaba"):
                return (
                    os.environ.get("DASHSCOPE_API_KEY")
                    or os.environ.get("QWEN_API_KEY")
                    or os.environ.get("ALIBABA_API_KEY")
                    or None
                )
            if self.name == "groq" and os.environ.get("GROK_API_KEY", "").startswith("gsk_"):
                return os.environ.get("GROK_API_KEY") or None
            if self.name == "grok" and os.environ.get("XAI_API_KEY"):
                return os.environ.get("XAI_API_KEY") or None
        return key or None

    @property
    def is_enabled(self) -> bool:
        flag_env = PROVIDER_FEATURE_FLAGS.get(self.name)
        # OpenAI and Anthropic are strictly disabled by default unless explicitly turned on
        default_val = "false" if self.name in ("openai", "anthropic") else "true"
        if flag_env is None:
            return self.name not in ("openai", "anthropic")
        return os.environ.get(flag_env, default_val).lower() in ("true", "1", "yes")

    @property
    def has_api_key(self) -> bool:
        key = self.api_key
        return key is not None and key != ""

    @property
    def state(self) -> ProviderState:
        if not self.is_enabled:
            return ProviderState.DISABLED
        if not self.has_api_key:
            return ProviderState.NOT_CONFIGURED
        return ProviderState.CONFIGURED


# -----------------------------------------------------------------------------
# Provider registry
# -----------------------------------------------------------------------------

def _default_models(provider: str) -> tuple[ModelConfig, ...]:
    defaults: dict[str, tuple[ModelConfig, ...]] = {
        "dashscope": (
            ModelConfig(name="qwen-max", display_name="Qwen Max (Flagship)", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0028, cost_per_1k_output=0.0084, max_tokens=32768),
            ModelConfig(name="qwen-plus", display_name="Qwen Plus (Balanced)", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0004, cost_per_1k_output=0.0012, max_tokens=32768),
            ModelConfig(name="qwen-turbo", display_name="Qwen Turbo (Fast)", task_types=("general", "coding"), cost_per_1k_input=0.0001, cost_per_1k_output=0.0003, max_tokens=16384),
            ModelConfig(name="qwen-2.5-coder-32b", display_name="Qwen 2.5 Coder 32B", task_types=("coding", "reasoning"), cost_per_1k_input=0.001, cost_per_1k_output=0.002, max_tokens=32768),
            ModelConfig(name="qwen-2.5-72b-instruct", display_name="Qwen 2.5 72B Instruct", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.002, cost_per_1k_output=0.006, max_tokens=32768),
        ),
        "deepseek": (
            ModelConfig(name="deepseek-chat-v3", display_name="DeepSeek V3", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.001, cost_per_1k_output=0.002, max_tokens=64000),
            ModelConfig(name="deepseek-reasoner", display_name="DeepSeek R1", task_types=("reasoning",), cost_per_1k_input=0.001, cost_per_1k_output=0.006, max_tokens=64000),
        ),
        "groq": (
            ModelConfig(name="qwen/qwen3.8-27b", display_name="Groq / Qwen 27B", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=32768),
            ModelConfig(name="openai/gpt-oss-120b", display_name="Groq / GPT-OSS 120B", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=32768),
            ModelConfig(name="qwen/qwen3.6-27b", display_name="Groq / Qwen 3.6 27B", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=32768),
            ModelConfig(name="llama-3.3-70b-versatile", display_name="Groq / Llama 3.3 70B", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=32768),
            ModelConfig(name="mixtral-8x7b-32768", display_name="Groq / Mixtral 8x7B", task_types=("general", "coding"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=32768),
        ),
        "grok": (
            ModelConfig(name="grok-4.7", display_name="Grok 4.7 (Default General Reasoning)", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.005, cost_per_1k_output=0.015, max_tokens=131072),
            ModelConfig(name="grok-3", display_name="Grok 3", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.005, cost_per_1k_output=0.015, max_tokens=131072),
            ModelConfig(name="grok-3-mini", display_name="Grok 3 Mini", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.001, cost_per_1k_output=0.003, max_tokens=131072),
            ModelConfig(name="grok-2", display_name="Grok 2", task_types=("general", "coding"), cost_per_1k_input=0.002, cost_per_1k_output=0.01, max_tokens=131072),
            ModelConfig(name="grok-2-vision-1212", display_name="Grok 2 Vision", task_types=("general", "multimodal"), cost_per_1k_input=0.002, cost_per_1k_output=0.01, max_tokens=131072),
            ModelConfig(name="grok-beta", display_name="Grok Beta", task_types=("general", "coding"), cost_per_1k_input=0.005, cost_per_1k_output=0.015, max_tokens=131072),
        ),
        "openai": (
            ModelConfig(name="gpt-4o", display_name="GPT-4o", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.0025, cost_per_1k_output=0.01, max_tokens=128000),
            ModelConfig(name="gpt-4o-mini", display_name="GPT-4o Mini", task_types=("general", "coding"), cost_per_1k_input=0.00015, cost_per_1k_output=0.0006, max_tokens=128000),
        ),
        "anthropic": (
            ModelConfig(name="claude-3-5-sonnet-latest", display_name="Claude 3.5 Sonnet", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.003, cost_per_1k_output=0.015, max_tokens=8192),
            ModelConfig(name="claude-3-5-haiku-latest", display_name="Claude 3.5 Haiku", task_types=("general", "coding"), cost_per_1k_input=0.0008, cost_per_1k_output=0.004, max_tokens=8192),
        ),
        "gemini": (
            ModelConfig(name="gemini-4-argon", display_name="Gemini 4 Argon (Default General Reasoning)", task_types=("general", "coding", "reasoning", "multimodal"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=2000000),
            ModelConfig(name="gemini-3.8-flash", display_name="Gemini 3.8 Flash (Multimodal Audio & Modulation)", task_types=("general", "coding", "reasoning", "multimodal", "audio"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-3.8-plus", display_name="Gemini 3.8 Plus (Dedicated TTS, STT & Live Audio)", task_types=("audio", "tts", "stt", "live", "general", "multimodal"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-3.6-flash", display_name="Gemini 3.6 Flash (Fast & Full Reasoning)", task_types=("general", "coding", "reasoning", "multimodal"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-3.7-flash", display_name="Gemini 3.7 Flash", task_types=("general", "coding", "reasoning", "multimodal"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-3.1-flash", display_name="Gemini 3.1 Flash", task_types=("general", "coding", "reasoning", "multimodal"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-2.5-flash", display_name="Gemini 2.5 Flash", task_types=("general", "coding", "reasoning", "multimodal"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-2.0-flash", display_name="Gemini 2.0 Flash", task_types=("general", "coding", "reasoning", "multimodal"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
            ModelConfig(name="gemini-1.5-pro", display_name="Gemini 1.5 Pro", task_types=("general", "coding", "reasoning"), cost_per_1k_input=0.00125, cost_per_1k_output=0.005, max_tokens=2000000),
            ModelConfig(name="gemini-1.5-flash", display_name="Gemini 1.5 Flash", task_types=("general", "coding"), cost_per_1k_input=0.0, cost_per_1k_output=0.0, max_tokens=1000000),
        ),
    }

    return defaults.get(provider, ())


def get_provider_config(name: str) -> ProviderConfig | None:
    """Build ProviderConfig for a named provider, reading from env."""
    canonical_name = "dashscope" if name in ("qwen", "alibaba") else name
    api_key_var = PROVIDER_API_KEY_VARS.get(canonical_name)
    base_url = PROVIDER_BASE_URLS.get(canonical_name)
    if api_key_var is None or base_url is None:
        return None

    return ProviderConfig(
        name=canonical_name,
        api_key_env_var=api_key_var,
        base_url=base_url,
        routing_priority=DEFAULT_ROUTING_PRIORITY.get(canonical_name, 99),
        timeout_seconds=10.0,
        supports_streaming=True,
        models=_default_models(canonical_name),
    )


def get_all_provider_configs() -> list[ProviderConfig]:
    """Return configured provider configs for all known providers."""
    configs = []
    for name in PROVIDER_API_KEY_VARS:
        cfg = get_provider_config(name)
        if cfg is not None:
            configs.append(cfg)
    return configs
