"""The 13 domain concepts of the Disaster Intelligence Core.

Reuses existing typed concepts rather than duplicating them:
`Geometry`/`CoordinateReferenceSystem` (`app.ml.geospatial`), `DamageClass`
(`app.ml.schemas`), `AccessibilityStatus` (`app.roads.schemas`),
`RouteResult`/`RoutingMode` (`app.routing.schemas`). See
`app/intelligence/__init__.py` for the pipeline this domain model supports.

Two conventions apply to every model in this file:

1. **`is_simulated: bool`** — every entity that could plausibly represent
   either a real incident or the demo scenario (`demo_scenario.py`)
   carries this flag, defaulting to `False`. It is the mechanism the API
   layer and any future frontend use to guarantee demo/synthetic data is
   never presented as live information (project constraint: "Demo data
   must be explicitly marked as DEMO/SIMULATED").
2. **`Evidence`/`Uncertainty` are structural, not decorative** — a field
   typed `Evidence`/`list[Evidence]` or `Uncertainty` is never optional on
   an assessed entity: `Recommendation -> Evidence -> Observation` is a
   real, checkable chain, not `Recommendation -> unexplained output`.
3. **Every `Geometry` field is paired with an explicit `*_crs` field**
   (`CoordinateReferenceSystem`, `app.ml.geospatial.crs`), defaulting to
   `IMAGE` — the same discipline `app.ml.schemas.BuildingDamage` already
   applies. A `PointGeometry`'s coordinates look identical whether they're
   pixels or WGS84 degrees; nothing in this module infers one from the
   other, and `app.intelligence.capability_matching` refuses to compute a
   real-world distance for any geometry not explicitly tagged `WGS84`
   (project constraint: "Image-space coordinates must not be treated as
   geographic coordinates").
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import Geometry
from app.ml.schemas import DamageClass
from app.roads.schemas import AccessibilityStatus
from app.routing.schemas import RouteResult

# --------------------------------------------------------------------------
# Uncertainty — foundational; referenced by nearly every other model below.
# --------------------------------------------------------------------------


class UncertaintyLevel(StrEnum):
    """A qualitative uncertainty band — engineering categories, not a
    validated statistical scale, the same honesty already established by
    `app.roads.schemas.RiskLevel`/`app.ml.geospatial.priority.DamagePriority`.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


class Uncertainty(BaseModel):
    """Explicit representation of how much to trust a piece of information.

    `confidence` is populated **only** when a genuinely calibrated numeric
    value exists upstream (e.g. a real model's own softmax probability) —
    never invented to fill the field (project constraint: "DO NOT create
    fake numerical confidence"). Every entity in this milestone that has
    no real calibrated model behind it (which, as of F2, is all of them —
    see `hazard_prediction.py`) sets `confidence=None` and relies on
    `level`/`reason`/`missing_information` instead.
    """

    level: UncertaintyLevel
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Only set when a real, calibrated probability exists. None otherwise.",
    )
    reason: str = Field(description="Why this level/confidence was assigned.")
    missing_information: list[str] = Field(default_factory=list)
    source_limitations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class EvidenceSourceType(StrEnum):
    """A closed vocabulary of where evidence can come from — deliberately
    not free text, so a caller can filter/group evidence by kind."""

    OBSERVATION = "observation"
    DAMAGE_ANALYSIS = "damage_analysis"
    ROAD_RISK_ANALYSIS = "road_risk_analysis"
    ROUTING_RESULT = "routing_result"
    RESOURCE_REGISTRY = "resource_registry"
    DEMO_SCENARIO = "demo_scenario"


class Evidence(BaseModel):
    """Links an assessment or recommendation back to the concrete thing
    that justified it. The goal (see the F2 brief, "Evidence"):

        Recommendation -> Evidence -> Observation

    rather than "Recommendation -> unexplained AI output".
    """

    id: UUID
    source_type: EvidenceSourceType
    observation_id: UUID | None = Field(
        default=None, description="Set when this evidence traces to a specific Observation."
    )
    source: str = Field(description="Human-readable name of the originating dataset/subsystem.")
    originating_subsystem: str = Field(
        description=(
            "Dotted module path or service name that produced this evidence, "
            "e.g. 'app.risk.analyzer'."
        )
    )
    timestamp: datetime
    summary: str = Field(
        description="One-line, human-readable statement of what this evidence shows."
    )
    data_ref: str | None = Field(
        default=None,
        description=(
            "Opaque reference to the underlying record (e.g. a building_id or edge id) "
            "for traceability."
        ),
    )


# --------------------------------------------------------------------------
# Disaster
# --------------------------------------------------------------------------


class DisasterType(StrEnum):
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    HURRICANE = "hurricane"
    WILDFIRE = "wildfire"
    LANDSLIDE = "landslide"
    TSUNAMI = "tsunami"
    STRUCTURAL_COLLAPSE = "structural_collapse"
    OTHER = "other"


class DisasterStatus(StrEnum):
    REPORTED = "reported"
    ACTIVE = "active"
    RESPONSE_IN_PROGRESS = "response_in_progress"
    CONTAINED = "contained"
    CLOSED = "closed"


class Disaster(BaseModel):
    """The top-level incident every other entity in this module is scoped
    to. `location`/`start_time` are optional because the current system
    (a single-image upload pipeline, no live feed ingestion) cannot
    always provide them — never fabricated when absent."""

    id: UUID
    type: DisasterType
    label: str = Field(
        description="Short human-readable name, e.g. 'Demo Coastal Flooding Scenario'."
    )
    status: DisasterStatus
    location: Geometry | None = None
    location_crs: CoordinateReferenceSystem = Field(
        default=CoordinateReferenceSystem.IMAGE,
        description=(
            "CRS of `location`. Defaults to IMAGE (non-geographic) — only ever WGS84 "
            "when `location` genuinely is. See the module docstring on CRS tagging."
        ),
    )
    start_time: datetime | None = None
    source: str = Field(
        description="Where this record came from, e.g. 'demo_scenario' or 'manual_entry'."
    )
    is_simulated: bool = Field(
        description=(
            "True for demo/synthetic scenarios. Must never be True for a real disaster record."
        )
    )
    provenance: str = Field(description="How/why this Disaster record was created.")


# --------------------------------------------------------------------------
# Observation
# --------------------------------------------------------------------------


class ObservationType(StrEnum):
    SATELLITE_IMAGE = "satellite_image"
    DRONE_IMAGE = "drone_image"
    ROAD_OBSTRUCTION_REPORT = "road_obstruction_report"
    INFRASTRUCTURE_DAMAGE_REPORT = "infrastructure_damage_report"
    EMERGENCY_REPORT = "emergency_report"
    DAMAGE_DETECTION = "damage_detection"


class Observation(BaseModel):
    """A single piece of *observed* information. An Observation is **not**
    a prediction — see `HazardPrediction` for the (currently unimplemented)
    predictive counterpart."""

    id: UUID
    type: ObservationType
    source: str
    timestamp: datetime
    geometry: Geometry | None = None
    geometry_crs: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE
    value_ref: str = Field(
        description=(
            "Opaque reference to the underlying data (e.g. a building_id, image path, "
            "or edge id) — never the raw payload itself."
        )
    )
    evidence: Evidence
    uncertainty: Uncertainty
    is_simulated: bool = False


# --------------------------------------------------------------------------
# AffectedArea
# --------------------------------------------------------------------------


class AffectedArea(BaseModel):
    """An area determined from one or more observations."""

    id: UUID
    geometry: Geometry
    geometry_crs: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE
    damage_level: DamageClass
    affected_population: int | None = Field(
        default=None,
        ge=0,
        description="Only set when a real population source exists. Never estimated.",
    )
    accessibility: AccessibilityStatus | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    uncertainty: Uncertainty
    is_simulated: bool = False


# --------------------------------------------------------------------------
# SearchZone
# --------------------------------------------------------------------------


class SearchPriorityLevel(StrEnum):
    """Engineering categories, not a validated triage scale — see
    `app.intelligence.search_priority` for the thresholds."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class SearchZoneFactor(BaseModel):
    """One named, weighted contributor to a search zone's priority score.
    Present **only** when its underlying data was actually available — a
    missing factor is omitted from `SearchZone.factors` entirely (see
    `SearchZone.missing_factors`), never filled with a fabricated value."""

    name: str
    value: float = Field(ge=0.0, le=1.0, description="Normalized [0,1] value for this factor.")
    weight: float = Field(ge=0.0, le=1.0, description="This factor's share of the total score.")
    contribution: float = Field(ge=0.0, description="value * weight, before renormalization.")
    description: str = Field(description="Human-readable explanation of this factor's value.")


class SearchZone(BaseModel):
    """A candidate area for search/rescue investigation, ranked by
    transparent, documented evidence.

    A `SearchZone` is **never** a claim that a person is located here —
    every consumer of this schema (API responses, future UI) must present
    it as "high-priority search zone based on available evidence," never
    "person located here." See `app.intelligence.search_priority`.
    """

    id: UUID
    geometry: Geometry
    geometry_crs: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE
    priority_score: float = Field(ge=0.0, le=1.0)
    priority_level: SearchPriorityLevel
    factors: list[SearchZoneFactor]
    missing_factors: list[str] = Field(
        default_factory=list,
        description="Names of factors that could not be scored due to missing data.",
    )
    reasons: list[str] = Field(
        description="Human-readable explanation of why this score was assigned."
    )
    supporting_observations: list[UUID] = Field(default_factory=list)
    supporting_evidence: list[Evidence] = Field(default_factory=list)
    uncertainty: Uncertainty
    is_simulated: bool = False


# --------------------------------------------------------------------------
# Hazard
# --------------------------------------------------------------------------


class HazardType(StrEnum):
    FLOOD = "flood"
    LANDSLIDE = "landslide"
    STRUCTURAL_COLLAPSE = "structural_collapse"
    BLOCKED_ROAD = "blocked_road"
    DAMAGED_BRIDGE = "damaged_bridge"
    WILDFIRE = "wildfire"
    TSUNAMI = "tsunami"
    EARTHQUAKE_AFTERSHOCK = "earthquake_aftershock"
    OTHER = "other"


class HazardSeverity(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Hazard(BaseModel):
    """A current or observed hazard — distinct from `HazardPrediction`
    (a forecast of a *future* hazard), which this milestone does not
    fabricate results for."""

    id: UUID
    type: HazardType
    severity: HazardSeverity
    geometry: Geometry
    geometry_crs: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE
    source: str
    timestamp: datetime
    evidence: list[Evidence] = Field(default_factory=list)
    uncertainty: Uncertainty
    is_simulated: bool = False


# --------------------------------------------------------------------------
# Resource / RescueTeam
# --------------------------------------------------------------------------


class ResourceType(StrEnum):
    RESCUE_TEAM = "rescue_team"
    DRONE = "drone"
    HELICOPTER = "helicopter"
    AMBULANCE = "ambulance"
    EXCAVATOR = "excavator"
    MEDICAL_TEAM = "medical_team"
    COMMUNICATION_UNIT = "communication_unit"
    OTHER = "other"


class ResourceCapability(StrEnum):
    """A discrete, matchable capability — a closed, coarse vocabulary
    (not free text) so `app.intelligence.capability_matching` can do exact
    set comparison rather than fuzzy string matching."""

    AERIAL_RECON = "aerial_recon"
    GROUND_SEARCH = "ground_search"
    WATER_RESCUE = "water_rescue"
    MEDICAL_TRIAGE = "medical_triage"
    HEAVY_LIFTING = "heavy_lifting"
    STRUCTURAL_ASSESSMENT = "structural_assessment"
    TRANSPORT = "transport"
    COMMUNICATIONS_RELAY = "communications_relay"


class ResourceAvailability(StrEnum):
    AVAILABLE = "available"
    DEPLOYED = "deployed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class OperationalConstraint(BaseModel):
    description: str
    blocking: bool = Field(description="True if this constraint currently prevents deployment.")


class Resource(BaseModel):
    """A response capability — a drone, ambulance, excavator, or team.
    Deliberately generic enough to cover both equipment and people;
    `RescueTeam` below composes a `Resource` with the additional
    attributes only a human team has."""

    id: UUID
    type: ResourceType
    capabilities: list[ResourceCapability]
    location: Geometry | None = None
    location_crs: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE
    availability: ResourceAvailability
    capacity: int | None = Field(
        default=None, ge=0, description="e.g. seats, personnel, or payload count."
    )
    operational_constraints: list[OperationalConstraint] = Field(default_factory=list)
    is_simulated: bool = False


class TerrainCapability(StrEnum):
    URBAN = "urban"
    MOUNTAINOUS = "mountainous"
    FLOODED = "flooded"
    COLLAPSED_STRUCTURE = "collapsed_structure"
    WATER = "water"


class RescueTeam(BaseModel):
    """A human response team.

    Modeled as **composition**, not inheritance or a duplicate of
    `Resource`: `resource` carries every field a drone or excavator also
    needs (id, location, availability, operational_constraints), while
    this model adds only what's true of a human team and nothing else
    (personnel, skills, equipment, medical capability, terrain
    capability). This keeps `Resource` usable for non-human assets
    without a parallel, near-identical schema.
    """

    resource: Resource
    personnel_count: int = Field(ge=0)
    skills: list[ResourceCapability]
    equipment: list[str] = Field(default_factory=list)
    medical_capability: bool = False
    terrain_capabilities: list[TerrainCapability] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Infrastructure
# --------------------------------------------------------------------------


class InfrastructureType(StrEnum):
    ROAD = "road"
    BRIDGE = "bridge"
    HOSPITAL = "hospital"
    HELIPAD = "helipad"
    SHELTER = "shelter"
    TUNNEL = "tunnel"
    COMMUNICATION_STATION = "communication_station"
    OTHER = "other"


class InfrastructureStatus(StrEnum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    NON_OPERATIONAL = "non_operational"
    UNKNOWN = "unknown"


class Infrastructure(BaseModel):
    id: UUID
    type: InfrastructureType
    geometry: Geometry
    geometry_crs: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE
    status: InfrastructureStatus
    accessibility: AccessibilityStatus | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    uncertainty: Uncertainty
    is_simulated: bool = False


# --------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------


class Route(BaseModel):
    """A candidate path between two points.

    Reuses the existing routing engine's own `RouteResult`
    (`app.routing.schemas`) for the actual path/cost/risk computation
    rather than reinventing pathfinding — this model adds the
    domain-level framing (typed origin/destination geometry, hazard
    intersection, provenance) around it, never a second routing result.

    `estimated_time_seconds` is always `None`: the routing engine has no
    speed/traversal-time model (see `apps/api/README.md`) — only distance
    and a unitless risk-adjusted cost. It is never derived from
    `distance / assumed_speed`, since an assumed speed would itself be a
    fabricated input.
    """

    id: UUID
    origin: Geometry
    destination: Geometry
    result: RouteResult
    estimated_time_seconds: float | None = Field(
        default=None,
        description=(
            "Always None until a real travel-time model exists — never derived from "
            "an assumed speed."
        ),
    )
    blocking_hazards: list[UUID] = Field(
        default_factory=list, description="Hazard ids that intersect this route and may block it."
    )
    provenance: str


# --------------------------------------------------------------------------
# HazardPrediction — interface only; see hazard_prediction.py
# --------------------------------------------------------------------------


class HazardPredictionStatus(StrEnum):
    """`UNAVAILABLE` is the only status F2 can ever produce — no
    predictive hazard model exists in this milestone. `AVAILABLE` is
    reserved for a future real model."""

    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"


class HazardPrediction(BaseModel):
    """Interface for a future predictive-hazard model.

    This milestone implements **no** predictive model — every
    `HazardPrediction` this codebase can currently produce has
    `status=UNAVAILABLE` and `probability=None` (see
    `hazard_prediction.unavailable_prediction()`, the only constructor
    currently used). The schema exists so a real model can be plugged in
    later without an API-contract change.
    """

    prediction_id: UUID
    hazard_type: HazardType
    target_area: Geometry
    forecast_window_start: datetime
    forecast_window_end: datetime
    status: HazardPredictionStatus
    probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Only ever set by a real, calibrated model. None when status=UNAVAILABLE.",
    )
    severity: HazardSeverity | None = None
    model_source: str | None = Field(
        default=None, description="Name/version of the model that produced this prediction, if any."
    )
    evidence: list[Evidence] = Field(default_factory=list)
    uncertainty: Uncertainty


# --------------------------------------------------------------------------
# Recommendation
# --------------------------------------------------------------------------


class RecommendationAction(StrEnum):
    """A closed, deterministic vocabulary of actions the rule-based engine
    (`app.intelligence.recommendation`) can recommend — deliberately not
    free text, so every recommendation is traceable to the exact rule
    that produced it."""

    DEPLOY_DRONE_RECON = "deploy_drone_recon"
    DEPLOY_GROUND_SEARCH_TEAM = "deploy_ground_search_team"
    DEPLOY_MEDICAL_TEAM = "deploy_medical_team"
    INSPECT_INFRASTRUCTURE_BEFORE_DISPATCH = "inspect_infrastructure_before_dispatch"
    AVOID_ROUTE_DUE_TO_HAZARD = "avoid_route_due_to_hazard"
    ESCALATE_FOR_ADDITIONAL_RESOURCES = "escalate_for_additional_resources"
    HOLD_PENDING_MORE_INFORMATION = "hold_pending_more_information"


class RecommendationPriority(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class Recommendation(BaseModel):
    """The engine's ranked output. Every recommendation must be
    traceable: `supporting_evidence` is required (not optional/empty by
    default) and `rationale` must state the concrete reason, never an
    unexplained AI opinion."""

    id: UUID
    action: RecommendationAction
    target_id: UUID = Field(
        description=(
            "Id of the SearchZone, Resource, Route, or Infrastructure this "
            "recommendation concerns."
        )
    )
    target_description: str
    priority: RecommendationPriority
    rationale: str
    required_capabilities: list[ResourceCapability] = Field(default_factory=list)
    supporting_evidence: list[Evidence]
    uncertainty: Uncertainty
    limitations: list[str] = Field(default_factory=list)
    is_simulated: bool = False


# --------------------------------------------------------------------------
# CapabilityMatchResult — NOT one of the 13 core domain entities; the
# computed, explainable output of app.intelligence.capability_matching.
# --------------------------------------------------------------------------


class ReachabilityStatus(StrEnum):
    """Distinct from `AccessibilityStatus` (a property of a road/area):
    this is whether *this specific resource* can plausibly reach *this
    specific target*, given known locations. `UNKNOWN` — not `False` —
    when either location is missing or not in a real geographic CRS
    (project constraint: never treat image-space coordinates as
    geographic)."""

    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


class CapabilityMatchResult(BaseModel):
    """One resource's assessment against one target, from
    `app.intelligence.capability_matching.rank_candidates()`. Keeps the
    four questions the F2 brief requires distinguished as separate
    fields, never collapsed into one opaque score:

    1. `can_perform_task` — capability compatibility.
    2. `is_available` — current availability.
    3. `reachability` — can it reach the target (distance-based, only
       when both locations are real, tagged WGS84 coordinates).
    4. `route_operational` — `None` when not assessed; `False` when a
       blocking operational constraint is known.
    """

    resource_id: UUID
    can_perform_task: bool
    missing_capabilities: list[ResourceCapability] = Field(default_factory=list)
    is_available: bool
    distance_meters: float | None = None
    reachability: ReachabilityStatus
    route_operational: bool | None = Field(
        default=None, description="None = not assessed. False = a known blocking constraint exists."
    )
    eligible: bool = Field(
        description=(
            "True only if can_perform_task, is_available, reachability != UNREACHABLE, "
            "and route_operational != False."
        )
    )
    match_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Ranking tie-breaker among eligible candidates — see module docstring.",
    )
    rationale: list[str]
    is_simulated: bool = False
