"""Pydantic settings for the runtime coordinator."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime coordinator settings — all from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_decode_policy="replace",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------
    runtime_host: str = "0.0.0.0"
    runtime_port: int = 8001
    debug: bool = False

    # Aliases used by main.py
    @property
    def host(self) -> str:
        return self.runtime_host

    @property
    def port(self) -> int:
        return self.runtime_port

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    repo_root: Path = Path(__file__).resolve().parents[3]
    agents_dir: Path = Path(__file__).resolve().parents[3] / ".claude" / "agents"
    skills_dir: Path = Path(__file__).resolve().parents[3] / ".claude" / "skills"

    # ------------------------------------------------------------------
    # Backend gateway (AI providers)
    # ------------------------------------------------------------------
    backend_base_url: str = "http://localhost:8000"
    backend_api_key: str = ""  # forwarded JWT bearer to backend

    # ------------------------------------------------------------------
    # Gateway timeouts
    # ------------------------------------------------------------------
    gateway_timeout_seconds: float = 60.0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_audience: str = "roxy-runtime"

    # ------------------------------------------------------------------
    # Classifier
    # ------------------------------------------------------------------
    classifier_uncertain_threshold: float = 0.15
    classifier_margin: float = 1.1  # top/second must exceed this to not be uncertain
    classifier_v1_keyword_weight: float = 0.6
    classifier_v1_similarity_weight: float = 0.4

    # ------------------------------------------------------------------
    # Specialist timeout
    # ------------------------------------------------------------------
    specialist_timeout_seconds: int = 30

    # ------------------------------------------------------------------
    # Database (future: Neon Postgres)
    # ------------------------------------------------------------------
    database_url: str | None = None  # asyncpg://...

    # ------------------------------------------------------------------
    # Google Cloud (voice + embeddings)
    # ------------------------------------------------------------------
    google_application_credentials: str | None = None
    google_cloud_project: str | None = None
    google_api_key: str | None = None
    google_embedding_url: str = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"

    # ------------------------------------------------------------------
    # TTS voice defaults
    # ------------------------------------------------------------------
    tts_voice: str = "en-US-Neural2-F"
    tts_language_code: str = "en-US"
    tts_pitch: float = 0.0

    # ------------------------------------------------------------------
    # Gmail API (email_send)
    # ------------------------------------------------------------------
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_refresh_token: str | None = None

    # ------------------------------------------------------------------
    # Plaid API (bank_connect)
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_environment: str = "sandbox"

    # Logging
    # ------------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------
    rate_limit_per_minute: int = 60

    @property
    def agents_path(self) -> Path:
        return self.agents_dir

    @property
    def skills_path(self) -> Path:
        return self.skills_dir

    def resolve_agents_dir(self) -> Path:
        """Resolved agents directory path."""
        return Path(self.agents_dir).resolve()

    def resolve_skills_dir(self) -> Path:
        """Resolved skills directory path."""
        return Path(self.skills_dir).resolve()

    @property
    def backend_ai_chat_url(self) -> str:
        """Full URL for the backend AI chat endpoint."""
        return f"{self.backend_base_url.rstrip('/')}/api/v1/ai/chat"


# Singleton
settings = Settings()
