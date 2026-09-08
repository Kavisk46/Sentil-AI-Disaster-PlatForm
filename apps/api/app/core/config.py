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

    # Damage-intelligence model. Milestone F4 wires a *real*, working
    # default: `MODEL_PROVIDER="open_clip"` loads a genuine pretrained CLIP
    # checkpoint (`MODEL_NAME`/`MODEL_VERSION` double as the open_clip
    # architecture name / pretrained-weights tag — e.g. "ViT-B-32"/"openai")
    # and performs real zero-shot damage-severity classification — no
    # training, no fine-tuning, CPU-only. This is a **general-purpose**
    # pretrained model, NOT trained or fine-tuned on xBD or any
    # disaster-specific dataset — see apps/api/README.md ("Milestone F4 —
    # real inference") for the full honesty disclosure and confidence
    # interpretation. `MODEL_PROVIDER="legacy_resnet"` restores Milestone
    # 3A/3C's original architecture (`TorchDamageClassifier`, requiring an
    # external fine-tuned checkpoint at `MODEL_PATH` — set `MODEL_NAME`/
    # `MODEL_VERSION` to describe that checkpoint instead, when using this
    # provider). `MODEL_ENABLED=False` disables real inference entirely
    # (every analysis ends `MODEL_UNAVAILABLE`, honestly) — the original
    # pre-F4 default, still available for offline/no-network environments.
    MODEL_ENABLED: bool = True
    MODEL_PROVIDER: Literal["open_clip", "legacy_resnet"] = "open_clip"
    MODEL_PATH: Path | None = None
    MODEL_NAME: str = "ViT-B-32"
    MODEL_VERSION: str = "openai"
    MODEL_DEVICE: str = "cpu"
    # Rejects an image whose width or height exceeds this many pixels
    # before any decode-heavy preprocessing runs — an explicit,
    # configurable decompression-bomb guard independent of (and tighter
    # than) Pillow's own built-in `Image.MAX_IMAGE_PIXELS` default. See
    # app/ml/preprocessing.py.
    MODEL_MAX_IMAGE_DIM: int = 4096
    # Stage 1 (see "Why Stage 1 has no real implementation yet" in
    # apps/api/README.md) proposes an NxN grid of deterministic image
    # tiles as candidate regions — not a building detector, since no
    # legitimate off-the-shelf pretrained model has a "building" class.
    # 2 -> 4 tiles per image, a deliberately small default given CPU-only
    # inference cost per tile (see app/ml/tile_localizer.py).
    MODEL_TILE_GRID: int = 2

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

    # Disaster Intelligence Core (Milestone F2) — a deterministic
    # "baseline heuristic" search-priority scorer and capability matcher
    # (see apps/api/README.md / docs/architecture/intelligence.md), the
    # same "not scientifically validated" honesty as ROAD_RISK_*. Every
    # tunable is centralized here so nothing in app/intelligence/
    # hardcodes a weight/threshold inline — see app/intelligence/config.py
    # for how these become SearchPriorityConfig/CapabilityMatchingConfig.
    SEARCH_PRIORITY_DAMAGE_SEVERITY_WEIGHT: float = 0.4
    SEARCH_PRIORITY_ACCESSIBILITY_WEIGHT: float = 0.25
    SEARCH_PRIORITY_POPULATION_EXPOSURE_WEIGHT: float = 0.2
    SEARCH_PRIORITY_EVIDENCE_STRENGTH_WEIGHT: float = 0.15
    SEARCH_PRIORITY_POPULATION_EXPOSURE_CAP: float = 100.0
    SEARCH_PRIORITY_CRITICAL_THRESHOLD: float = 0.75
    SEARCH_PRIORITY_HIGH_THRESHOLD: float = 0.5
    SEARCH_PRIORITY_MODERATE_THRESHOLD: float = 0.25
    CAPABILITY_MATCHING_MAX_DISTANCE_METERS: float = 20_000.0

    # Milestone F5 — production infrastructure. `DATABASE_URL` defaults to
    # a local Postgres matching `docker-compose.yml`'s `postgres` service
    # (`docker compose up` needs zero further configuration); a bare
    # `sqlite:///...` URL also works for lightweight local runs without
    # Docker — see docs/architecture/production.md, "Persistence." Every
    # repository test uses an isolated in-memory SQLite database (see
    # tests/conftest.py), never this setting, so the test suite never
    # requires a developer's personal database.
    DATABASE_URL: str = "postgresql+psycopg://sentinelai:sentinelai@localhost:5432/sentinelai"
    # `REDIS_URL` backs both the RQ job queue and the worker's published
    # model-readiness status (see app/services/job_queue.py,
    # app/services/model_status_service.py) — one dependency, two uses,
    # rather than a second piece of infrastructure for the latter.
    REDIS_URL: str = "redis://localhost:6379/0"
    OBJECT_STORAGE_BACKEND: Literal["local"] = "local"
    # Root directory for `LocalObjectStorage` — distinct from the legacy
    # `UPLOAD_DIR` only in name; kept as its own setting (rather than
    # reusing UPLOAD_DIR directly) so a deployment can point object
    # storage at a different, larger volume than the dev-only upload
    # scratch space without ambiguity. Defaults to the same path.
    OBJECT_STORAGE_ROOT: Path = Path("storage/uploads")
    WORKER_CONCURRENCY: int = 1
    JOB_MAX_RETRIES: int = 2

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if "://" not in value:
            raise ValueError("DATABASE_URL must be a valid database URL (scheme://...).")
        return value

    @field_validator("REDIS_URL")
    @classmethod
    def _validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("REDIS_URL must start with redis://, rediss://, or unix://.")
        return value

    @field_validator("WORKER_CONCURRENCY")
    @classmethod
    def _validate_worker_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("WORKER_CONCURRENCY must be >= 1.")
        return value

    @field_validator("JOB_MAX_RETRIES")
    @classmethod
    def _validate_job_max_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("JOB_MAX_RETRIES must be >= 0.")
        return value

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Allow BACKEND_CORS_ORIGINS to be a comma-separated string in .env."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("MODEL_TILE_GRID")
    @classmethod
    def _validate_tile_grid(cls, value: int) -> int:
        if value < 1:
            raise ValueError("MODEL_TILE_GRID must be >= 1.")
        return value

    @field_validator("MODEL_MAX_IMAGE_DIM")
    @classmethod
    def _validate_max_image_dim(cls, value: int) -> int:
        if value < 1:
            raise ValueError("MODEL_MAX_IMAGE_DIM must be >= 1.")
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
