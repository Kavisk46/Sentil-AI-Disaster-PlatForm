"""A deterministic, clearly-labeled **DEMO** disaster scenario.

Every entity this module builds has `is_simulated=True` — see
`app.intelligence.schemas`' module docstring for why that flag exists and
how it's meant to be used (never presented as live information; the API
layer must surface it, not strip it — see `app/schemas/intelligence.py`).

Coordinates are centered on `_ORIGIN = (1.5, 1.5)` — the same
deliberately fictional point in open ocean the frontend's own demo
fixtures already use (`apps/web/src/lib/demo/demo-data.ts`), so this
scenario can never be mistaken for a real place or a real event.

Every id in this module is generated with `uuid5(NAMESPACE_URL, ...)`
from a fixed name string, not `uuid4()` — so `build_demo_scenario()`
returns byte-for-byte identical ids on every call, in every process,
forever. This is what "deterministic so tests are reproducible" means in
practice: a test can assert on an exact id, not just "some id".

This scenario is deliberately built to demonstrate that **having
equipment is not enough**:

- `_EXCAVATOR` exists (a real `Resource` with `HEAVY_LIFTING`) but is
  `UNAVAILABLE` (a blocking maintenance constraint) — capable, but not
  deployable right now.
- `_MISMATCHED_TEAM` is `AVAILABLE` and reachable, but lacks
  `GROUND_SEARCH` — available, but not capable of the task.
- `_GROUND_TEAM` is capable, available, *and* reachable — the only
  resource `app.intelligence.capability_matching` should ever rank as
  eligible for the critical search zone, proving the matcher actually
  discriminates rather than just returning the nearest or first resource.
- `_BRIDGE` is `NON_OPERATIONAL` near the critical zone, so
  `app.intelligence.recommendation` should recommend inspecting it —
  "can it reach the target" and "is the route operational" are genuinely
  separate questions in this scenario, not merely available/unavailable
  and capable/incapable in isolation.
"""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.intelligence.schemas import (
    AffectedArea,
    Disaster,
    DisasterStatus,
    DisasterType,
    Evidence,
    EvidenceSourceType,
    Hazard,
    HazardSeverity,
    HazardType,
    Infrastructure,
    InfrastructureStatus,
    InfrastructureType,
    Observation,
    ObservationType,
    OperationalConstraint,
    RescueTeam,
    Resource,
    ResourceAvailability,
    ResourceCapability,
    ResourceType,
    Route,
    TerrainCapability,
    Uncertainty,
    UncertaintyLevel,
)
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import PointGeometry
from app.ml.schemas import DamageClass
from app.roads.schemas import AccessibilityStatus, RiskLevel, RoadEdge
from app.routing.schemas import AccessibilitySummary, RouteResult, RoutingMode
from app.services.intelligence_repository import DisasterScenario

_ORIGIN_LON, _ORIGIN_LAT = 1.5, 1.5
_DEMO_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _id(name: str) -> UUID:
    """Deterministic id for a demo entity — see module docstring."""
    return uuid5(NAMESPACE_URL, f"https://sentinelai.demo/f2/{name}")


def _point(lon_offset: float, lat_offset: float) -> PointGeometry:
    return PointGeometry(coordinates=(_ORIGIN_LON + lon_offset, _ORIGIN_LAT + lat_offset))


def _evidence(
    name: str, source_type: EvidenceSourceType, summary: str, data_ref: str | None = None
) -> Evidence:
    return Evidence(
        id=_id(f"evidence-{name}"),
        source_type=source_type,
        source="demo_scenario",
        originating_subsystem="app.intelligence.demo_scenario",
        timestamp=_DEMO_TIME,
        summary=summary,
        data_ref=data_ref,
    )


def build_demo_scenario() -> DisasterScenario:
    """Build the full DEMO scenario. Pure, deterministic, no I/O — safe
    to call as often as needed (e.g. once at repository-seed time — see
    `app/api/deps.py`)."""

    disaster = Disaster(
        id=_id("disaster"),
        type=DisasterType.FLOOD,
        label="DEMO: Coastal Flooding Scenario",
        status=DisasterStatus.ACTIVE,
        location=_point(0, 0),
        location_crs=CoordinateReferenceSystem.WGS84,
        start_time=_DEMO_TIME,
        source="demo_scenario",
        is_simulated=True,
        provenance=(
            "Deterministic F2 demo scenario, hand-authored to exercise the intelligence pipeline "
            "end-to-end. Not a real event, not derived from any real disaster."
        ),
    )

    obs_satellite = Observation(
        id=_id("obs-satellite"),
        type=ObservationType.SATELLITE_IMAGE,
        source="demo_scenario",
        timestamp=_DEMO_TIME,
        geometry=_point(-0.001, -0.001),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        value_ref="demo-satellite-frame-001",
        evidence=_evidence(
            "obs-satellite",
            EvidenceSourceType.OBSERVATION,
            "Satellite pass shows a destroyed structure and standing water.",
            "demo-satellite-frame-001",
        ),
        uncertainty=Uncertainty(
            level=UncertaintyLevel.LOW,
            confidence=None,
            reason="Clear imagery, unobstructed view of the structure.",
        ),
        is_simulated=True,
    )
    obs_drone = Observation(
        id=_id("obs-drone"),
        type=ObservationType.DRONE_IMAGE,
        source="demo_scenario",
        timestamp=_DEMO_TIME,
        geometry=_point(0.004, 0.002),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        value_ref="demo-drone-frame-014",
        evidence=_evidence(
            "obs-drone",
            EvidenceSourceType.OBSERVATION,
            "Drone flyover shows major structural damage; population count not confirmed.",
            "demo-drone-frame-014",
        ),
        uncertainty=Uncertainty(
            level=UncertaintyLevel.MODERATE,
            confidence=None,
            reason="Partial occlusion from smoke/haze in this frame.",
            missing_information=["confirmed occupancy count"],
        ),
        is_simulated=True,
    )
    obs_road = Observation(
        id=_id("obs-road"),
        type=ObservationType.ROAD_OBSTRUCTION_REPORT,
        source="demo_scenario",
        timestamp=_DEMO_TIME,
        geometry=_point(0.006, -0.002),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        value_ref="demo-road-report-002",
        evidence=_evidence(
            "obs-road",
            EvidenceSourceType.OBSERVATION,
            "Field report: bridge deck impassable.",
            "demo-road-report-002",
        ),
        uncertainty=Uncertainty(
            level=UncertaintyLevel.MODERATE,
            confidence=None,
            reason="Single unverified field report.",
            missing_information=["independent confirmation"],
        ),
        is_simulated=True,
    )
    obs_infra = Observation(
        id=_id("obs-infra"),
        type=ObservationType.INFRASTRUCTURE_DAMAGE_REPORT,
        source="demo_scenario",
        timestamp=_DEMO_TIME,
        geometry=_point(0.006, -0.002),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        value_ref="demo-infra-report-001",
        evidence=_evidence(
            "obs-infra",
            EvidenceSourceType.OBSERVATION,
            "Structural spotter confirms bridge deck failure.",
            "demo-infra-report-001",
        ),
        uncertainty=Uncertainty(
            level=UncertaintyLevel.LOW,
            confidence=None,
            reason="Confirmed by a qualified structural spotter.",
        ),
        is_simulated=True,
    )
    observations = (obs_satellite, obs_drone, obs_road, obs_infra)

    area_critical = AffectedArea(
        id=_id("area-critical"),
        geometry=_point(-0.001, -0.001),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        damage_level=DamageClass.DESTROYED,
        affected_population=42,
        accessibility=AccessibilityStatus.BLOCKED,
        evidence=[obs_satellite.evidence],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.LOW,
            confidence=None,
            reason="Single clear satellite observation, well corroborated.",
        ),
        is_simulated=True,
    )
    area_uncertain = AffectedArea(
        id=_id("area-uncertain"),
        geometry=_point(0.004, 0.002),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        damage_level=DamageClass.MAJOR,
        # deliberately unknown — see search_priority's missing-factor handling
        affected_population=None,
        accessibility=AccessibilityStatus.RESTRICTED,
        evidence=[obs_drone.evidence],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.MODERATE,
            confidence=None,
            reason="Partial occlusion in the only available observation.",
            missing_information=["confirmed occupancy count", "second corroborating observation"],
        ),
        is_simulated=True,
    )
    area_minor = AffectedArea(
        id=_id("area-minor"),
        geometry=_point(-0.003, 0.003),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        damage_level=DamageClass.MINOR,
        affected_population=8,
        accessibility=AccessibilityStatus.OPEN,
        evidence=[],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.HIGH,
            confidence=None,
            reason=(
                "No direct observation on file for this area; inferred from adjacent "
                "imagery only."
            ),
            missing_information=["direct observation"],
        ),
        is_simulated=True,
    )
    affected_areas = (area_critical, area_uncertain, area_minor)

    hazard_flood = Hazard(
        id=_id("hazard-flood"),
        type=HazardType.FLOOD,
        severity=HazardSeverity.HIGH,
        geometry=_point(-0.001, -0.001),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        source="demo_scenario",
        timestamp=_DEMO_TIME,
        evidence=[obs_satellite.evidence],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.LOW, confidence=None, reason="Standing water clearly visible."
        ),
        is_simulated=True,
    )
    hazard_bridge = Hazard(
        id=_id("hazard-bridge"),
        type=HazardType.DAMAGED_BRIDGE,
        severity=HazardSeverity.CRITICAL,
        geometry=_point(0.006, -0.002),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        source="demo_scenario",
        timestamp=_DEMO_TIME,
        evidence=[obs_road.evidence, obs_infra.evidence],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.LOW,
            confidence=None,
            reason="Confirmed by both a field report and a structural spotter.",
        ),
        is_simulated=True,
    )
    hazards = (hazard_flood, hazard_bridge)

    drone_resource = Resource(
        id=_id("resource-drone"),
        type=ResourceType.DRONE,
        capabilities=[ResourceCapability.AERIAL_RECON],
        location=_point(0.0005, 0.0005),
        location_crs=CoordinateReferenceSystem.WGS84,
        availability=ResourceAvailability.AVAILABLE,
        capacity=1,
        is_simulated=True,
    )
    ground_team_resource = Resource(
        id=_id("resource-ground-team"),
        type=ResourceType.RESCUE_TEAM,
        capabilities=[ResourceCapability.GROUND_SEARCH, ResourceCapability.MEDICAL_TRIAGE],
        location=_point(-0.0015, -0.0012),  # close to area_critical
        location_crs=CoordinateReferenceSystem.WGS84,
        availability=ResourceAvailability.AVAILABLE,
        capacity=6,
        is_simulated=True,
    )
    ground_team = RescueTeam(
        resource=ground_team_resource,
        personnel_count=6,
        skills=[ResourceCapability.GROUND_SEARCH, ResourceCapability.MEDICAL_TRIAGE],
        equipment=["rope rescue kit", "stretcher"],
        medical_capability=True,
        terrain_capabilities=[TerrainCapability.URBAN, TerrainCapability.FLOODED],
    )
    ambulance = Resource(
        id=_id("resource-ambulance"),
        type=ResourceType.AMBULANCE,
        capabilities=[ResourceCapability.MEDICAL_TRIAGE, ResourceCapability.TRANSPORT],
        location=_point(0.002, -0.004),
        location_crs=CoordinateReferenceSystem.WGS84,
        availability=ResourceAvailability.AVAILABLE,
        capacity=2,
        is_simulated=True,
    )
    excavator = Resource(
        id=_id("resource-excavator"),
        type=ResourceType.EXCAVATOR,
        capabilities=[ResourceCapability.HEAVY_LIFTING],
        location=_point(-0.0008, -0.0009),
        location_crs=CoordinateReferenceSystem.WGS84,
        availability=ResourceAvailability.UNAVAILABLE,
        capacity=1,
        operational_constraints=[
            OperationalConstraint(description="Under scheduled maintenance", blocking=True)
        ],
        is_simulated=True,
    )
    mismatched_team = Resource(
        id=_id("resource-mismatched-team"),
        type=ResourceType.RESCUE_TEAM,
        # no GROUND_SEARCH — capability mismatch by design
        capabilities=[ResourceCapability.MEDICAL_TRIAGE],
        location=_point(0.5, 0.5),  # far away — also fails the reachability gate
        location_crs=CoordinateReferenceSystem.WGS84,
        availability=ResourceAvailability.AVAILABLE,
        capacity=4,
        is_simulated=True,
    )
    resources = (drone_resource, ground_team_resource, ambulance, excavator, mismatched_team)
    rescue_teams = (ground_team,)

    bridge = Infrastructure(
        id=_id("infra-bridge"),
        type=InfrastructureType.BRIDGE,
        geometry=_point(0.006, -0.002),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        status=InfrastructureStatus.NON_OPERATIONAL,
        accessibility=AccessibilityStatus.BLOCKED,
        evidence=[obs_road.evidence, obs_infra.evidence],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.LOW,
            confidence=None,
            reason="Confirmed non-operational by two independent reports.",
        ),
        is_simulated=True,
    )
    hospital = Infrastructure(
        id=_id("infra-hospital"),
        type=InfrastructureType.HOSPITAL,
        geometry=_point(0.01, 0.01),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        status=InfrastructureStatus.OPERATIONAL,
        accessibility=AccessibilityStatus.OPEN,
        evidence=[],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.LOW,
            confidence=None,
            reason="No damage reported near this facility.",
        ),
        is_simulated=True,
    )
    road = Infrastructure(
        id=_id("infra-road"),
        type=InfrastructureType.ROAD,
        geometry=_point(0.003, -0.003),
        geometry_crs=CoordinateReferenceSystem.WGS84,
        status=InfrastructureStatus.DEGRADED,
        accessibility=AccessibilityStatus.RESTRICTED,
        evidence=[],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.MODERATE,
            confidence=None,
            reason="Inferred from proximity to observed flooding, not directly observed.",
            missing_information=["direct observation"],
        ),
        is_simulated=True,
    )
    infrastructure = (bridge, hospital, road)

    demo_edge = RoadEdge(
        source_node="demo-n1",
        target_node="demo-n2",
        distance=850.0,
        base_cost=850.0,
        road_type="secondary",
        name="Demo Ridge Route",
        accessibility=AccessibilityStatus.OPEN,
        risk_score=0.12,
        risk_level=RiskLevel.LOW,
        risk_sources=[],
    )
    route_result = RouteResult(
        routing_mode=RoutingMode.RISK_AWARE,
        found=True,
        start_node="demo-n1",
        destination_node="demo-n2",
        node_sequence=["demo-n1", "demo-n2"],
        edge_sequence=[demo_edge],
        route_geometry=[
            (_ORIGIN_LON - 0.0015, _ORIGIN_LAT - 0.0012),
            (_ORIGIN_LON - 0.001, _ORIGIN_LAT - 0.001),
        ],
        total_distance=850.0,
        total_cost=850.0,
        accumulated_risk=0.12,
        number_of_edges=1,
        accessibility_summary=AccessibilitySummary(open=1, restricted=0, blocked=0, unknown=0),
        reason=None,
    )
    route = Route(
        id=_id("route-ground-team-to-critical-zone"),
        origin=_point(-0.0015, -0.0012),
        destination=_point(-0.001, -0.001),
        result=route_result,
        estimated_time_seconds=None,
        blocking_hazards=[],
        provenance=(
            "Hand-authored demo route — no real road network is loaded in this deployment "
            "(see apps/api/README.md, 'Road risk model'). Never computed by the live routing "
            "engine."
        ),
    )
    routes = (route,)

    return DisasterScenario(
        disaster=disaster,
        observations=observations,
        affected_areas=affected_areas,
        hazards=hazards,
        resources=resources,
        rescue_teams=rescue_teams,
        infrastructure=infrastructure,
        routes=routes,
    )
