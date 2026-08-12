"""Application settings.

Settings are loaded once from environment variables (and an optional `.env`
file) and exposed through `get_settings()`, which is cached so the rest of
the application shares a single, immutable configuration object rather than
re-reading the environment on every access.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
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

    # Damage-intelligence model (Milestone 3A — architecture only, no
    # trained model yet). MODEL_PATH is unset by default; app/ml/model.py's
    # only implementation never claims to be loaded regardless of this
    # value, since no model-loading backend exists yet either. Deployment
    # environments will set MODEL_PATH once a real, trained model exists.
    MODEL_PATH: Path | None = None
    MODEL_NAME: str = "sentinelai-damage-classifier"
    MODEL_VERSION: str = "unconfigured"
    MODEL_DEVICE: str = "cpu"

    # Road risk model (Milestone 6B) — a deterministic "baseline heuristic
    # risk model" (see apps/api/README.md, "Road risk model"), explicitly
    # NOT scientifically validated. Every tunable constant the formula uses
    # is centralized here — nothing in app/risk/ hardcodes one inline — so
    # a deployment can retune the model via environment variables without a
    # code change. See app/risk/config.py for how these become a
    # `RoadRiskConfig`.
    ROAD_RISK_SEVERITY_WEIGHT_NO_DAMAGE: float = 0.0
    ROAD_RISK_SEVERITY_WEIGHT_MINOR: float = 0.25
    ROAD_RISK_SEVERITY_WEIGHT_MAJOR: float = 0.6
    ROAD_RISK_SEVERITY_WEIGHT_DESTROYED: float = 1.0
    ROAD_RISK_SEARCH_RADIUS_METERS: float = 150.0
    ROAD_RISK_DISTANCE_DECAY_RATE: float = 0.02
    ROAD_RISK_AGGREGATION_CAP: float = 1.0
    ROAD_RISK_LEVEL_LOW_MAX: float = 0.25
    ROAD_RISK_LEVEL_MODERATE_MAX: float = 0.5
    ROAD_RISK_LEVEL_HIGH_MAX: float = 0.75
    ROAD_RISK_COST_PENALTY_SCALE: float = 4.0

    # Routing (Milestone 6C) — see apps/api/README.md ("Risk-aware rescue
    # routing"). Centralized here for the same reason ROAD_RISK_* is:
    # nothing in app/routing/ hardcodes a coefficient inline. Reuses
    # ROAD_RISK_COST_PENALTY_SCALE (via app.risk.formula.compute_risk_adjusted_cost)
    # for the risk term itself rather than a second, parallel penalty
    # constant — see app/routing/cost.py.
    ROUTING_RESTRICTED_ACCESSIBILITY_PENALTY: float = 0.5
    ROUTING_UNKNOWN_ACCESSIBILITY_POLICY: Literal["open", "restricted", "blocked"] = "open"
    ROUTING_MAX_SNAP_DISTANCE_METERS: float = 500.0
    ROUTING_USE_ASTAR_HEURISTIC: bool = False

    # AI incident intelligence (Milestone 7) — see apps/api/README.md
    # ("AI incident intelligence"). LLM_API_KEY is read from the
    # environment only, never hardcoded and never logged (see
    # app/incident/anthropic_provider.py). LLM_PROVIDER defaults to
    # "deterministic" — no external call, no API key required — so the
    # summary endpoint works out of the box with zero configuration;
    # "mock" exists only for tests/local development, never intended for
    # production. INCIDENT_* thresholds drive the deterministic
    # severity/confidence classification (app/incident/severity.py) —
    # centralized here for the same reason ROAD_RISK_*/ROUTING_* are.
    LLM_PROVIDER: Literal["deterministic", "mock", "anthropic"] = "deterministic"
    # SecretStr so Settings' own repr/str (e.g. in a debugger, or a future
    # log statement someone adds without realizing) never prints the raw
    # key — callers must explicitly opt in via `.get_secret_value()`.
    LLM_API_KEY: SecretStr | None = None
    LLM_MODEL: str = "claude-haiku-4-5-20251001"
    LLM_TIMEOUT_SECONDS: float = 15.0
    INCIDENT_MAX_LISTED_STRUCTURE_IDS: int = 10
    INCIDENT_SEVERITY_DESTROYED_RATIO_CRITICAL: float = 0.25
    INCIDENT_SEVERITY_SEVERE_RATIO_HIGH: float = 0.5
    INCIDENT_SEVERITY_SEVERE_RATIO_MODERATE: float = 0.2
    INCIDENT_CONFIDENCE_HIGH_MIN: float = 0.8
    INCIDENT_CONFIDENCE_MODERATE_MIN: float = 0.5

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
