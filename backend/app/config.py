"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_port: int = 8000
    app_version: str = "0.1.0"

    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/omniquant.db"

    ai_enabled: bool = False
    # Primary provider is a local OmniRoute gateway.
    ai_base_url: str = "http://127.0.0.1:20128/v1"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_timeout_seconds: int = 45
    # Direct OpenRouter call, used only when OmniRoute fails or times out.
    ai_fallback_base_url: str = "https://openrouter.ai/api/v1"
    ai_fallback_api_key: str = ""
    ai_fallback_model: str = ""

    market_data_timeout_seconds: float = 30.0
    market_data_max_retries: int = 2
    max_history_days: int = 3650  # ~10 years

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def ai_primary_configured(self) -> bool:
        return bool(self.ai_enabled and self.ai_base_url and self.ai_api_key and self.ai_model)

    @property
    def ai_fallback_configured(self) -> bool:
        return bool(
            self.ai_enabled
            and self.ai_fallback_base_url
            and self.ai_fallback_api_key
            and self.ai_fallback_model
        )

    @property
    def ai_configured(self) -> bool:
        return self.ai_primary_configured or self.ai_fallback_configured


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return settings
