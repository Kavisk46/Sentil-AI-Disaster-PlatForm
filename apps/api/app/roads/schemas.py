"""Typed contracts for the road-network graph.

    Node = location/intersection
    Edge = traversable road segment
    Weight (base_cost) = travel cost — today, exactly `distance`

Coordinate validity reuses `app.ml.geospatial.geometry` directly (the
Milestone 5 utility this milestone was told to reuse rather than
duplicate): `RoadNode.geometry` is a real `PointGeometry`, and out-of-range
or non-finite coordinates raise the same `InvalidGeometryError` Milestone 5
already established — this package doesn't invent a parallel coordinate
validation error.

Milestone 6B: `RoadEdge` gains `risk_level`/`risk_sources` alongside the
`risk_score`/`accessibility` fields Milestone 6A already reserved for this
— see `app.risk` for the analysis that populates them. Defining
`RiskLevel`/`RiskSource` here (rather than in `app.risk`) keeps `RoadEdge`
a single, self-contained edge representation — "Do NOT create a second
road graph" — at the cost of `app.roads` importing `DamageClass` from
`app.ml.schemas` for `RiskSource`'s field. This mirrors the existing
precedent `app.services.analysis_repository` already set (importing
`app.ml.schemas` rather than duplicating its taxonomy), just one package
further out.

Milestone 6C: `GeographicCoordinate` is `RoadNode`'s validated
`(latitude, longitude)` pair, factored out so `app.routing`'s API request
schema (a raw start/destination coordinate, not yet a graph node) can
reuse the exact same validation rather than a parallel copy of it — "Do
not duplicate validation logic unnecessarily" applied one more time.
"""

import math
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import InvalidGeometryError, PointGeometry
from app.ml.schemas import DamageClass
from app.roads.errors import InvalidRoadGraphError

_MIN_LATITUDE, _MAX_LATITUDE = -90.0, 90.0
_MIN_LONGITUDE, _MAX_LONGITUDE = -180.0, 180.0


class AccessibilityStatus(StrEnum):
    """A road edge's accessibility. OSM ingestion (`app.roads.builder`)
    always sets `UNKNOWN` — OpenStreetMap has no concept of an ongoing
    disaster; `RESTRICTED`/`BLOCKED` are for a future milestone to derive
    from SentinelAI's own damage/hazard intelligence. See the package
    docstring ("Accessibility") for the full rationale.
    """

    OPEN = "open"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class GeographicCoordinate(BaseModel):
    """A validated WGS84 `(latitude, longitude)` pair — the base every
    real-world geographic point type in this codebase shares. Always
    WGS84 by construction (`coordinate_reference_system` below), so there
    is no separate CRS field to mis-set: this type has exactly one
    supported interpretation of its two numbers.
    """

    latitude: float
    longitude: float

    @field_validator("latitude")
    @classmethod
    def _validate_latitude(cls, value: float) -> float:
        if not math.isfinite(value) or not (_MIN_LATITUDE <= value <= _MAX_LATITUDE):
            raise InvalidGeometryError(
                f"latitude must be a finite number in [{_MIN_LATITUDE}, {_MAX_LATITUDE}]; "
                f"got {value!r}."
            )
        return value

    @field_validator("longitude")
    @classmethod
    def _validate_longitude(cls, value: float) -> float:
        if not math.isfinite(value) or not (_MIN_LONGITUDE <= value <= _MAX_LONGITUDE):
            raise InvalidGeometryError(
                f"longitude must be a finite number in [{_MIN_LONGITUDE}, {_MAX_LONGITUDE}]; "
                f"got {value!r}."
            )
        return value

    @property
    def geometry(self) -> PointGeometry:
        """This coordinate as a Milestone 5 `PointGeometry`, GeoJSON
        coordinate order (`longitude, latitude`)."""
        return PointGeometry(coordinates=(self.longitude, self.latitude))

    @property
    def coordinate_reference_system(self) -> CoordinateReferenceSystem:
        return CoordinateReferenceSystem.WGS84


class RoadNode(GeographicCoordinate):
    """A location/intersection — a point where a route can start, end, or
    change direction."""

    node_id: str


class RiskLevel(StrEnum):
    """Engineering categories for `RoadEdge.risk_score`, not validated
    emergency-management standards — see `app.risk.formula.classify_risk_level`
    for the (centrally configured) thresholds and `app.risk` for the full
    rationale."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class RiskSource(BaseModel):
    """One damaged building's contribution to a `RoadEdge`'s `risk_score`
    — kept so a responder can eventually see *why* a road is considered
    risky, not just a bare number. Never fabricated: only ever produced by
    `app.risk.analyzer.compute_road_risk` from a real, georeferenced
    `BuildingDamage` actually found within the configured search radius of
    the edge.
    """

    building_id: str
    damage_class: DamageClass
    confidence: float = Field(ge=0.0, le=1.0)
    distance_meters: float
    contribution: float = Field(ge=0.0, le=1.0)

    @field_validator("distance_meters")
    @classmethod
    def _validate_distance_meters(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise InvalidRoadGraphError(
                f"distance_meters must be non-negative and finite; got {value!r}."
            )
        return value


class RoadEdge(BaseModel):
    """A directed, traversable road segment from `source_node` to
    `target_node`. Two-way OSM roads become *two* `RoadEdge`s (one per
    direction, both `one_way=False`) — this type itself is always
    directed; there is no separate undirected representation.

    Every OSM-derived attribute is `None` when OSM didn't tag it —
    `road_type`/`name`/`maxspeed`/`surface`/`lanes` are never given a
    fabricated default. `risk_score`/`risk_level`/`risk_sources` are always
    `None`/`None`/`[]` from OSM ingestion: OpenStreetMap has no concept of
    disaster risk. `app.risk.analyzer.compute_road_risk` (Milestone 6B) is
    the only thing that ever populates them — always on a **copy** of an
    edge (`model_copy`), never by mutating an edge already stored in
    `RoadNetworkRepository`, since risk is specific to one analysis's
    damage predictions, not a property of the physical road network
    itself. `accessibility` is deliberately untouched by that process too
    — see `AccessibilityStatus` and `app.risk` ("Why risk is not
    blockage").
    """

    source_node: str
    target_node: str
    distance: float = Field(description="Meters. Must be positive and finite.")
    base_cost: float = Field(
        description=(
            "Today: exactly `distance` (app.roads.weighting.compute_base_cost). "
            "The seam a future risk-aware weighting stage extends — see also "
            "app.risk.formula.compute_risk_adjusted_cost, which derives a "
            "risk-adjusted cost from this without storing it as a field."
        )
    )
    road_type: str | None = Field(
        default=None, description="Raw OSM `highway` tag value, passed through unmodified."
    )
    name: str | None = None
    maxspeed: str | None = Field(
        default=None,
        description=(
            "Raw OSM `maxspeed` tag value (units vary by country/tag) — not parsed or "
            "unit-converted."
        ),
    )
    lanes: int | None = None
    one_way: bool = False
    surface: str | None = None
    accessibility: AccessibilityStatus = AccessibilityStatus.UNKNOWN
    risk_score: float | None = None
    risk_level: RiskLevel | None = Field(
        default=None,
        description="`None` until app.risk.analyzer.compute_road_risk assesses this edge.",
    )
    risk_sources: list[RiskSource] = Field(
        default_factory=list,
        description="Every damaged building that contributed to `risk_score`, for explainability.",
    )

    @field_validator("distance")
    @classmethod
    def _validate_distance(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise InvalidRoadGraphError(
                f"distance must be a positive, finite number of meters; got {value!r}."
            )
        return value

    @field_validator("base_cost")
    @classmethod
    def _validate_base_cost(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise InvalidRoadGraphError(
                f"base_cost must be a positive, finite number; got {value!r}."
            )
        return value

    @field_validator("lanes")
    @classmethod
    def _validate_lanes(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise InvalidRoadGraphError(
                f"lanes must be a positive integer if given; got {value!r}."
            )
        return value

    @field_validator("risk_score")
    @classmethod
    def _validate_risk_score(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise InvalidRoadGraphError(f"risk_score must be finite if given; got {value!r}.")
        return value


class RoadGraph(BaseModel):
    """A snapshot of the full road network — every node and edge as of the
    call. Not a live view: mutating the repository afterward doesn't
    change an already-returned `RoadGraph`."""

    nodes: list[RoadNode] = Field(default_factory=list)
    edges: list[RoadEdge] = Field(default_factory=list)
