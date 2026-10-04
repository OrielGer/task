"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_env: str = "development"

    # Database. Defaults to a local SQLite file so the app/tests run with no
    # external services; Docker/production override DATABASE_URL to Postgres.
    database_url: str = "sqlite+pysqlite:///./wfi_dev.db"

    redis_url: str | None = None

    # Auth
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60

    # CORS (comma-separated)
    cors_origins: str = "http://localhost:3000"

    # Rate limiting (requests per window, per client+route bucket)
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Work-session engine
    session_idle_break_seconds: int = 300

    # Collector config returned to agents/extension (non-executable; data only)
    content_debounce_seconds: int = 5
    heartbeat_seconds: int = 60
    batch_max: int = 500

    # Retention
    retention_activity_events_days: int = 180
    retention_content_versions_days: int = 90
    retention_ai_summaries_days: int = 365
    retention_analytics_days: int = 730

    # AI provider: mock | openai | anthropic | gemini
    ai_provider: str = "mock"
    ai_model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    # Use the AI provider to classify work sessions (falls back to deterministic
    # rules when the provider is mock or returns unparseable output).
    ai_session_classifier: bool = False

    # Encryption key for integration tokens at rest (falls back to jwt_secret).
    integration_enc_key: str = ""
    # Marketing integration mode: live | sandbox. "sandbox" returns deterministic
    # sample data with no network calls (used for demos/tests).
    integration_mode: str = "sandbox"

    # Background scheduler (retention, nightly summaries, automation recompute).
    scheduler_enabled: bool = False
    scheduler_summary_hour_utc: int = 2  # nightly job hour

    # Default pagination page size for list endpoints.
    page_size_default: int = 50
    page_size_max: int = 200

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
