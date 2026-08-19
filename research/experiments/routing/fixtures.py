"""Small, fully deterministic synthetic road-graph fixtures for the
routing evaluation. Never real OSM data, never randomly generated (every
coordinate below is a fixed literal — no `random_seed` is needed for
these fixtures specifically). Not a real disaster site: the origin
coordinate is an arbitrary placeholder chosen only to sit at a latitude
where the degree-to-meter conversion is easy to reason about.

`diamond_detour_scenario()` layout — every distance is computed from
these coordinates via `app.roads.geo_utils.haversine_distance_meters`,
the same function production OSM ingestion uses, never a separately
hand-computed number that could silently drift from what the app itself
would compute:

               B
              / \\
             A   D      (direct route A-B-D, ~670m)
              \\ /
               C          (detour route A-C-D, ~890m, ~33% longer)

One `DESTROYED` building sits ~5m from node B — within
`RoadRiskConfig.search_radius_meters` (150m default) of edges A-B and
B-D, and, by construction, ~325m away (outside that radius) of edges A-C
and C-D. That is what gives the ablation study something real to
measure: the direct route is shorter but passes next to detected damage;
the detour avoids it at a real, computed distance cost.
"""

import dataclasses
import math

from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import PointGeometry
from app.ml.schemas import BuildingDamage, DamageClass
from app.roads.geo_utils import haversine_distance_meters
from app.roads.schemas import AccessibilityStatus, RoadEdge, RoadNode

_ORIGIN_LATITUDE = 10.0
_ORIGIN_LONGITUDE = 20.0
_METERS_PER_DEGREE_LATITUDE = 111_320.0


def _offset_node(node_id: str, east_meters: float, north_meters: float) -> RoadNode:
    latitude = _ORIGIN_LATITUDE + north_meters / _METERS_PER_DEGREE_LATITUDE
    meters_per_degree_longitude = _METERS_PER_DEGREE_LATITUDE * math.cos(
        math.radians(_ORIGIN_LATITUDE)
    )
    longitude = _ORIGIN_LONGITUDE + east_meters / meters_per_degree_longitude
    return RoadNode(node_id=node_id, latitude=latitude, longitude=longitude)


def _bidirectional_edges(node_a: RoadNode, node_b: RoadNode) -> list[RoadEdge]:
    distance = haversine_distance_meters(
        node_a.latitude, node_a.longitude, node_b.latitude, node_b.longitude
    )
    return [
        RoadEdge(
            source_node=node_a.node_id,
            target_node=node_b.node_id,
            distance=distance,
            base_cost=distance,
            accessibility=AccessibilityStatus.OPEN,
        ),
        RoadEdge(
            source_node=node_b.node_id,
            target_node=node_a.node_id,
            distance=distance,
            base_cost=distance,
            accessibility=AccessibilityStatus.OPEN,
        ),
    ]


def _damaged_building(
    building_id: str,
    damage_class: DamageClass,
    confidence: float,
    near_node: RoadNode,
    offset_north_meters: float,
) -> BuildingDamage:
    latitude = near_node.latitude + offset_north_meters / _METERS_PER_DEGREE_LATITUDE
    return BuildingDamage(
        building_id=building_id,
        damage_class=damage_class,
        confidence=confidence,
        geometry=PointGeometry(coordinates=(near_node.longitude, latitude)),
        coordinate_reference_system=CoordinateReferenceSystem.WGS84,
        georeferenced=True,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class RoutingScenario:
    scenario_id: str
    description: str
    nodes: list[RoadNode]
    edges: list[RoadEdge]
    buildings: list[BuildingDamage]
    origin_node_id: str
    destination_node_id: str


def diamond_detour_scenario() -> RoutingScenario:
    node_a = _offset_node("A", east_meters=0, north_meters=0)
    node_b = _offset_node("B", east_meters=150, north_meters=300)
    node_c = _offset_node("C", east_meters=-330, north_meters=300)
    node_d = _offset_node("D", east_meters=0, north_meters=600)

    edges = [
        *_bidirectional_edges(node_a, node_b),
        *_bidirectional_edges(node_b, node_d),
        *_bidirectional_edges(node_a, node_c),
        *_bidirectional_edges(node_c, node_d),
    ]

    building = _damaged_building(
        "bldg-1", DamageClass.DESTROYED, confidence=0.95, near_node=node_b, offset_north_meters=5.0
    )

    return RoutingScenario(
        scenario_id="diamond_detour_v1",
        description=(
            "Synthetic 4-node diamond graph: a direct route (A-B-D) passes ~5m from one "
            "destroyed building; a detour route (A-C-D) stays ~325m away (outside the "
            "default 150m road-risk search radius) at a real, computed distance cost. Not "
            "real OSM data or a real disaster site."
        ),
        nodes=[node_a, node_b, node_c, node_d],
        edges=edges,
        buildings=[building],
        origin_node_id="A",
        destination_node_id="D",
    )


def no_damage_scenario() -> RoutingScenario:
    """The same graph with zero damaged buildings — exercises the
    zero-baseline-risk path (`risk_reduction_percent` must be `None`,
    never a divide-by-zero crash or a fabricated `0%`)."""
    base = diamond_detour_scenario()
    return dataclasses.replace(
        base,
        scenario_id="diamond_no_damage_v1",
        description=(
            "Same graph as diamond_detour_v1 with no damaged buildings — a zero-baseline-risk "
            "fixture."
        ),
        buildings=[],
    )


def unreachable_destination_scenario() -> RoutingScenario:
    """An origin/destination pair with no connecting edge at all —
    exercises the "route not found" path for every configuration."""
    node_a = _offset_node("A", east_meters=0, north_meters=0)
    node_isolated = _offset_node("Z", east_meters=1000, north_meters=1000)
    return RoutingScenario(
        scenario_id="unreachable_v1",
        description="Two disconnected nodes — no route exists in any configuration.",
        nodes=[node_a, node_isolated],
        edges=[],
        buildings=[],
        origin_node_id="A",
        destination_node_id="Z",
    )
