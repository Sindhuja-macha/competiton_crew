"""
Centralised application settings loaded from environment variables / .env file.
Uses pydantic-settings so every value is typed and validated at startup.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = Field(
        default="Competitive Intelligence Briefing Crew",
        alias="APP_NAME",
    )
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ------------------------------------------------------------------
    # LLM / OpenRouter
    # ------------------------------------------------------------------
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    primary_model: str = Field(
        default="meta-llama/llama-3.1-8b-instruct:free",
        alias="PRIMARY_MODEL",
    )
    fallback_model: str = Field(
        default="microsoft/phi-3-mini-128k-instruct:free",
        alias="FALLBACK_MODEL",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    database_url: str = Field(
        default="sqlite:///./data/competitive_intel.db",
        alias="DATABASE_URL",
    )

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        alias="CORS_ORIGINS",
    )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    export_dir: str = Field(default="./data/exports", alias="EXPORT_DIR")

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        """Accept JSON array string or plain list."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            # Fallback: comma-separated string
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v  # type: ignore[return-value]

    @field_validator("log_level", mode="before")
    @classmethod
    def upper_log_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def ensure_export_dir_exists(self) -> "Settings":
        os.makedirs(self.export_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.database_url.replace("sqlite:///", "")), exist_ok=True)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
