"""Repository for Disaster Intelligence Core scenario data — the raw
inputs (`Disaster`, `Observation`s, `AffectedArea`s, `Hazard`s,
`Resource`s, `RescueTeam`s, `Infrastructure`, `Route`s) a scenario
provides. Mirrors `app.services.spatial_repository`'s exact shape
(Protocol + `InMemoryX` + `threading.Lock`), the same in-memory
placeholder tradeoff, and the same PostGIS/database-migration story: a
future persistent implementation replaces `InMemoryIntelligenceRepository`
without any caller (`IntelligenceService`) changing.

**Search zones and recommendations are deliberately NOT stored here.**
Both are pure, deterministic functions of a scenario's raw inputs plus a
config (`app.intelligence.search_priority`/`recommendation`) — computing
them on every request is cheap, always reflects the latest config, and
avoids a second source of truth that could drift from the inputs it was
derived from. See `app.services.intelligence_service`.

Scoped by `disaster_id: UUID`, mirroring `SpatialRepository`'s
`analysis_id`-scoped queries — no cross-disaster query exists yet (a
natural extension once there's a real use case, not implemented
speculatively here).
"""

import threading
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.intelligence.schemas import (
    AffectedArea,
    Disaster,
    Hazard,
    Infrastructure,
    Observation,
    RescueTeam,
    Resource,
    Route,
)


class DisasterNotFoundError(Exception):
    """Raised when `disaster_id` doesn't correspond to any known scenario.
    `GET /api/v1/intelligence/{disaster_id}...` maps this to `404` — see
    `app/api/exception_handlers.py`."""


@dataclass(frozen=True, slots=True)
class DisasterScenario:
    """One disaster's complete set of raw intelligence inputs — a demo
    scenario (`app.intelligence.demo_scenario`) or, in the future, a real
    ingested incident. Immutable: `IntelligenceRepository.save_scenario`
    replaces the whole bundle rather than mutating it in place."""

    disaster: Disaster
    observations: tuple[Observation, ...] = field(default_factory=tuple)
    affected_areas: tuple[AffectedArea, ...] = field(default_factory=tuple)
    hazards: tuple[Hazard, ...] = field(default_factory=tuple)
    resources: tuple[Resource, ...] = field(default_factory=tuple)
    rescue_teams: tuple[RescueTeam, ...] = field(default_factory=tuple)
    infrastructure: tuple[Infrastructure, ...] = field(default_factory=tuple)
    routes: tuple[Route, ...] = field(default_factory=tuple)


class IntelligenceRepository(Protocol):
    def save_scenario(self, scenario: DisasterScenario) -> None:
        """Store (or replace) the full scenario for `scenario.disaster.id`."""
        ...

    def get_scenario(self, disaster_id: UUID) -> DisasterScenario | None:
        """The scenario for `disaster_id`, or `None` if nothing has been
        saved for it yet — never a fabricated empty scenario."""
        ...

    def list_disaster_ids(self) -> list[UUID]:
        """Every known `disaster_id` — used by the API layer to validate
        a request without needing the full scenario."""
        ...


class InMemoryIntelligenceRepository:
    """Process-local, non-persistent — same tradeoffs as
    `InMemorySpatialRepository`. A single instance must be shared across
    requests (see `app/api/deps.py`) to remember anything between calls."""

    def __init__(self) -> None:
        self._scenarios: dict[UUID, DisasterScenario] = {}
        self._lock = threading.Lock()

    def save_scenario(self, scenario: DisasterScenario) -> None:
        with self._lock:
            self._scenarios[scenario.disaster.id] = scenario

    def get_scenario(self, disaster_id: UUID) -> DisasterScenario | None:
        with self._lock:
            return self._scenarios.get(disaster_id)

    def list_disaster_ids(self) -> list[UUID]:
        with self._lock:
            return list(self._scenarios.keys())
