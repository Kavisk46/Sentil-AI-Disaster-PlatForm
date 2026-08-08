"""Application settings.

Settings are loaded once from environment variables (and an optional `.env`
file) and exposed through `get_settings()`, which is cached so the rest of
the application shares a single, immutable configuration object rather than
re-reading the environment on every access.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]


class Settings(BaseSettings):
    """Strongly-typed application configuration.

    Every setting has a sensible development-mode default so the API is
    runnable out of the box; production deployments are expected to override
    these via real environment variables rather than editing code.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application metadata
    APP_NAME: str = "SentinelAI API"
    APP_DESCRIPTION: str = (
        "Backend API for SentinelAI — an AI-powered disaster intelligence platform."
    )
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = False

    # Networking
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS: origins allowed to call this API from a browser.
    # Deliberately `list[str]`, not `list[AnyHttpUrl]`: pydantic's URL type
    # normalizes a bare origin by appending a trailing slash
    # ("http://localhost:3000" -> "http://localhost:3000/"), which then
    # fails to exact-match the browser's unmodified `Origin` header and
    # silently breaks CORS. `NoDecode` opts this field out of
    # pydantic-settings' default behavior of JSON-decoding complex (list)
    # values read from the environment, so a plain comma-separated string in
    # `.env` reaches our validator below instead of failing as invalid JSON.
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Image ingestion (Milestone 2). UPLOAD_DIR is a local, gitignored,
    # development-only location — see app/services/file_storage.py, which
    # keeps this behind an interface so it can be swapped for object storage
    # (S3/R2/GCS) later without an API change.
    UPLOAD_DIR: Path = Path("storage/uploads")
    MAX_UPLOAD_SIZE_MB: int = 10

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Allow BACKEND_CORS_ORIGINS to be a comma-separated string in .env."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    return Settings()
