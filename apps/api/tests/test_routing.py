"""Tests for risk-aware rescue routing (Milestone 6C): accessibility
resolution, edge-cost construction, Dijkstra/A* correctness, nearest-node
lookup, route-result assembly, research metrics, GeoJSON conversion,
`RoutingService`, and `POST /api/v1/routing`.

Synthetic graph used throughout (matching the milestone's own example):

    A ---- B ---- C
    |             |
    D ---- E ---- F

No internet access, no GPU, fully deterministic.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.deps import get_road_network_repository, get_spatial_repository
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import PointGeometry
from app.ml.schemas import BuildingDamage, DamageClass
from app.risk.config import RoadRiskConfig
from app.roads.geo_utils import haversine_distance_meters
from app.roads.schemas import (
    AccessibilityStatus,
    GeographicCoordinate,
    RiskLevel,
    RoadEdge,
    RoadNode,
)
from app.routing.accessibility import Traversability, resolve_accessibility
from app.routing.algorithm import GraphView, PathResult, haversine_heuristic, shortest_path
from app.routing.config import RoutingConfig
from app.routing.cost import build_edge_cost_fn
from app.routing.geojson import route_to_feature
from app.routing.metrics import (
    count_blocked_edges,
    count_risky_segments,
    detour_ratio,
    high_risk_edges_avoided,
)
from app.routing.nearest_node import InMemoryNearestNodeLocator
from app.routing.result_builder import build_route_result, summarize_accessibility
from app.routing.schemas import AccessibilitySummary, RouteResult, RoutingMode
from app.schemas.analysis import AnalysisStatus
from app.schemas.routing import RoutingRequest
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.analysis_repository import (
    AnalysisNotFoundError,
    AnalysisRecord,
    InMemoryAnalysisRepository,
)
from app.services.road_network_repository import InMemoryRoadNetworkRepository
from app.services.road_risk_service import RoadRiskService
from app.services.routing_service import RoutingService
from app.services.spatial_repository import InMemorySpatialRepository

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _node(node_id: str, lat: float, lon: float) -> RoadNode:
    return RoadNode(node_id=node_id, latitude=lat, longitude=lon)


def _edge(source: str, target: str, distance: float, **kwargs: object) -> RoadEdge:
    return RoadEdge(
        source_node=source, target_node=target, distance=distance, base_cost=distance, **kwargs
    )  # type: ignore[arg-type]


def _risk_config(**overrides: object) -> RoadRiskConfig:
    defaults: dict[str, object] = {
        "severity_weights": {
            DamageClass.NO_DAMAGE: 0.0,
            DamageClass.MINOR: 0.25,
            DamageClass.MAJOR: 0.6,
            DamageClass.DESTROYED: 1.0,
        },
        "search_radius_meters": 150.0,
        "distance_decay_rate": 0.02,
        "aggregation_cap": 1.0,
        "risk_level_low_max": 0.25,
        "risk_level_moderate_max": 0.5,
        "risk_level_high_max": 0.75,
        "cost_penalty_scale": 4.0,
    }
    defaults.update(overrides)
    return RoadRiskConfig(**defaults)  # type: ignore[arg-type]


def _routing_config(**overrides: object) -> RoutingConfig:
    defaults: dict[str, object] = {
        "restricted_accessibility_penalty": 0.5,
        "unknown_accessibility_policy": Traversability.OPEN,
        "max_snap_distance_meters": 500.0,
        "use_astar_heuristic": False,
    }
    defaults.update(overrides)
    return RoutingConfig(**defaults)  # type: ignore[arg-type]


def _rectangle_repository() -> InMemoryRoadNetworkRepository:
    """
        A ---- B ---- C
        |             |
        D ---- E ---- F

    Top path (A-B-C-F): 3 edges x 50m = 150m.
    Bottom path (A-D-E-F): 3 edges x 100m = 300m — deliberately twice as
    long, so distance_only always prefers the top path unless it's
    blocked.
    """
    repository = InMemoryRoadNetworkRepository()
    coordinates = {
        "A": (10.000, 20.000),
        "B": (10.000, 20.001),
        "C": (10.000, 20.002),
        "D": (9.990, 20.000),
        "E": (9.990, 20.001),
        "F": (9.990, 20.002),
    }
    for node_id, (lat, lon) in coordinates.items():
        repository.add_node(_node(node_id, lat, lon))

    for source, target in [("A", "B"), ("B", "C"), ("C", "F")]:
        repository.add_edge(_edge(source, target, 50.0))
        repository.add_edge(_edge(target, source, 50.0))
    for source, target in [("A", "D"), ("D", "E"), ("E", "F")]:
        repository.add_edge(_edge(source, target, 100.0))
        repository.add_edge(_edge(target, source, 100.0))

    return repository


def _set_risk(
    repository: InMemoryRoadNetworkRepository,
    pairs: list[tuple[str, str]],
    distance: float,
    risk_score: float,
    risk_level: RiskLevel,
) -> None:
    """Overwrites both directions of each (source, target) pair in `pairs`
    with the given risk fields — used only by tests exercising
    `app.routing`'s pure functions directly (`GraphView` built straight
    from a repository), which trust whatever risk fields an edge already
    carries. `RoutingService`-level tests must NOT use this: `RoadRiskService`
    always recomputes risk from real building proximity and would
    overwrite it (see `test_compare_routes_reports_differences_when_routes_differ`).
    """
    for source, target in pairs:
        forward = _edge(source, target, distance, risk_score=risk_score, risk_level=risk_level)
        backward = _edge(target, source, distance, risk_score=risk_score, risk_level=risk_level)
        repository.add_edge(forward)
        repository.add_edge(backward)


def _building(
    building_id: str,
    damage_class: DamageClass,
    lon: float,
    lat: float,
    confidence: float = 0.9,
) -> BuildingDamage:
    return BuildingDamage(
        building_id=building_id,
        damage_class=damage_class,
        confidence=confidence,
        geometry=PointGeometry(coordinates=(lon, lat)),
        coordinate_reference_system=CoordinateReferenceSystem.WGS84,
        georeferenced=True,
    )


# ---------------------------------------------------------------------------
# app.routing.accessibility
# ---------------------------------------------------------------------------


def test_open_accessibility_resolves_to_open() -> None:
    result = resolve_accessibility(AccessibilityStatus.OPEN, Traversability.BLOCKED)
    assert result is Traversability.OPEN


def test_restricted_accessibility_resolves_to_restricted() -> None:
    result = resolve_accessibility(AccessibilityStatus.RESTRICTED, Traversability.OPEN)
    assert result is Traversability.RESTRICTED


def test_blocked_accessibility_always_resolves_to_blocked() -> None:
    result = resolve_accessibility(AccessibilityStatus.BLOCKED, Traversability.OPEN)
    assert result is Traversability.BLOCKED


@pytest.mark.parametrize(
    "policy", [Traversability.OPEN, Traversability.RESTRICTED, Traversability.BLOCKED]
)
def test_unknown_accessibility_follows_configured_policy(policy: Traversability) -> None:
    assert resolve_accessibility(AccessibilityStatus.UNKNOWN, policy) is policy


def test_risk_level_never_affects_accessibility_resolution() -> None:
    """Accessibility resolution takes no risk information at all — a
    critical-risk edge resolves identically to a risk-free one."""
    edge = _edge(
        "A",
        "B",
        10.0,
        accessibility=AccessibilityStatus.OPEN,
        risk_score=1.0,
        risk_level=RiskLevel.CRITICAL,
    )
    assert resolve_accessibility(edge.accessibility, Traversability.OPEN) is Traversability.OPEN


# ---------------------------------------------------------------------------
# RoutingConfig validation
# ---------------------------------------------------------------------------


def test_routing_config_rejects_negative_restricted_penalty() -> None:
    with pytest.raises(ValueError, match="restricted_accessibility_penalty"):
        _routing_config(restricted_accessibility_penalty=-0.1)


def test_routing_config_rejects_non_positive_snap_distance() -> None:
    with pytest.raises(ValueError, match="max_snap_distance_meters"):
        _routing_config(max_snap_distance_meters=0.0)


def test_routing_config_from_settings_uses_settings_values() -> None:
    from app.core.config import Settings

    settings = Settings(
        ROUTING_MAX_SNAP_DISTANCE_METERS=42.0, ROUTING_UNKNOWN_ACCESSIBILITY_POLICY="blocked"
    )
    config = RoutingConfig.from_settings(settings)
    assert config.max_snap_distance_meters == 42.0
    assert config.unknown_accessibility_policy is Traversability.BLOCKED


# ---------------------------------------------------------------------------
# app.routing.cost — build_edge_cost_fn
# ---------------------------------------------------------------------------


def test_blocked_edge_cost_is_none() -> None:
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())
    edge = _edge("A", "B", 100.0, accessibility=AccessibilityStatus.BLOCKED)
    assert cost_fn(edge) is None


def test_distance_only_ignores_risk_score() -> None:
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())
    edge = _edge("A", "B", 100.0, risk_score=1.0)
    assert cost_fn(edge) == 100.0


def test_risk_aware_uses_compute_risk_adjusted_cost_formula() -> None:
    """Do not silently invent a different formula — cost must equal
    base_cost * (1 + cost_penalty_scale * risk_score)."""
    risk_config = _risk_config(cost_penalty_scale=4.0)
    cost_fn = build_edge_cost_fn(RoutingMode.RISK_AWARE, _routing_config(), risk_config)
    edge = _edge("A", "B", 100.0, risk_score=0.5)
    assert cost_fn(edge) == pytest.approx(100.0 * (1 + 4.0 * 0.5))


def test_restricted_edge_applies_penalty_in_both_modes() -> None:
    routing_config = _routing_config(restricted_accessibility_penalty=0.5)
    edge = _edge("A", "B", 100.0, accessibility=AccessibilityStatus.RESTRICTED)

    distance_cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, routing_config, _risk_config())
    risk_cost_fn = build_edge_cost_fn(RoutingMode.RISK_AWARE, routing_config, _risk_config())

    assert distance_cost_fn(edge) == pytest.approx(150.0)
    # risk_score is None -> no risk penalty, only the accessibility penalty applies.
    assert risk_cost_fn(edge) == pytest.approx(150.0)


def test_unassessed_risk_score_leaves_risk_aware_cost_at_base() -> None:
    cost_fn = build_edge_cost_fn(RoutingMode.RISK_AWARE, _routing_config(), _risk_config())
    edge = _edge("A", "B", 100.0, risk_score=None)
    assert cost_fn(edge) == 100.0


# ---------------------------------------------------------------------------
# 1. Dijkstra/A* correctness
# ---------------------------------------------------------------------------


def test_shortest_path_finds_the_lower_distance_route() -> None:
    repository = _rectangle_repository()
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())

    path = shortest_path(graph, "A", "F", cost_fn)

    assert path.found is True
    assert path.node_sequence == ["A", "B", "C", "F"]
    assert path.total_cost == pytest.approx(150.0)


def test_shortest_path_trivial_start_equals_destination() -> None:
    repository = _rectangle_repository()
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())

    path = shortest_path(graph, "A", "A", cost_fn)

    assert path == PathResult(found=True, node_sequence=["A"], edge_sequence=[], total_cost=0.0)


def test_shortest_path_unknown_node_is_not_found() -> None:
    repository = _rectangle_repository()
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())

    assert shortest_path(graph, "A", "ghost", cost_fn).found is False
    assert shortest_path(graph, "ghost", "A", cost_fn).found is False


def test_dijkstra_and_astar_agree_on_a_geometrically_real_graph() -> None:
    """A* (haversine heuristic, admissible for base_cost since real edge
    distance is always >= straight-line distance) must find the same
    optimal path and cost as plain Dijkstra (heuristic=None)."""
    nodes = {
        "A": _node("A", 10.0, 20.0),
        "B": _node("B", 10.0, 20.001),
        "C": _node("C", 10.0, 20.002),
        "D": _node("D", 9.999, 20.0),
        "F": _node("F", 9.999, 20.002),
    }
    edges = [
        _edge("A", "B", haversine_distance_meters(10.0, 20.0, 10.0, 20.001)),
        _edge("B", "C", haversine_distance_meters(10.0, 20.001, 10.0, 20.002)),
        _edge("C", "F", haversine_distance_meters(10.0, 20.002, 9.999, 20.002)),
        _edge("A", "D", haversine_distance_meters(10.0, 20.0, 9.999, 20.0)),
        _edge("D", "F", haversine_distance_meters(9.999, 20.0, 9.999, 20.002)),
    ]
    graph = GraphView(list(nodes.values()), edges)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())

    dijkstra_result = shortest_path(graph, "A", "F", cost_fn, heuristic=None)
    astar_heuristic = haversine_heuristic(nodes["F"])
    astar_result = shortest_path(graph, "A", "F", cost_fn, heuristic=astar_heuristic)

    assert dijkstra_result.found is True
    assert astar_result.found is True
    assert dijkstra_result.node_sequence == astar_result.node_sequence
    assert dijkstra_result.total_cost == pytest.approx(astar_result.total_cost)


# ---------------------------------------------------------------------------
# 4. Accessibility filtering / blocked road forces a detour
# ---------------------------------------------------------------------------


def test_blocked_edge_forces_a_detour() -> None:
    repository = _rectangle_repository()
    repository.add_edge(_edge("C", "F", 50.0, accessibility=AccessibilityStatus.BLOCKED))
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())

    path = shortest_path(graph, "A", "F", cost_fn)

    assert path.found is True
    assert path.node_sequence == ["A", "D", "E", "F"]  # forced onto the (longer) bottom path
    assert path.total_cost == pytest.approx(300.0)


def test_fully_blocked_graph_reports_no_route() -> None:
    repository = _rectangle_repository()
    for source, target in [("C", "F"), ("F", "C"), ("E", "F"), ("F", "E")]:
        repository.add_edge(_edge(source, target, 50.0, accessibility=AccessibilityStatus.BLOCKED))
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())

    path = shortest_path(graph, "A", "F", cost_fn)

    assert path.found is False


# ---------------------------------------------------------------------------
# 5. Restricted road remains available with penalty
# ---------------------------------------------------------------------------


def test_restricted_edge_is_traversable_but_costs_more() -> None:
    """A single-edge graph with no alternative: the restricted edge must
    still be usable (not blocked), with the penalty reflected in cost but
    NOT in the reported physical distance."""
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(_node("X", 0.0, 0.0))
    repository.add_node(_node("Y", 0.0, 0.001))
    repository.add_edge(_edge("X", "Y", 100.0, accessibility=AccessibilityStatus.RESTRICTED))
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)
    routing_config = _routing_config(restricted_accessibility_penalty=0.5)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, routing_config, _risk_config())

    path = shortest_path(graph, "X", "Y", cost_fn)

    assert path.found is True
    assert path.total_cost == pytest.approx(150.0)  # 100 * 1.5
    nodes_by_id = {"X": repository.get_node("X"), "Y": repository.get_node("Y")}
    result = build_route_result(path, RoutingMode.DISTANCE_ONLY, nodes_by_id)
    assert result.total_distance == pytest.approx(100.0)  # unpenalized, a physical fact
    assert result.total_cost == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# 2/3. distance-only vs risk-aware routing / research experiment
# ---------------------------------------------------------------------------


_TOP_PATH_PAIRS = [("A", "B"), ("B", "C"), ("C", "F")]
_BOTTOM_PATH_PAIRS = [("A", "D"), ("D", "E"), ("E", "F")]


def _risky_top_safe_bottom_repository() -> InMemoryRoadNetworkRepository:
    """The rectangle graph with the top path (shorter) marked
    maximally risky and the bottom path (longer) marked risk-free."""
    repository = _rectangle_repository()
    _set_risk(repository, _TOP_PATH_PAIRS, 50.0, risk_score=1.0, risk_level=RiskLevel.CRITICAL)
    _set_risk(repository, _BOTTOM_PATH_PAIRS, 100.0, risk_score=0.0, risk_level=RiskLevel.LOW)
    return repository


def test_distance_only_prefers_the_shorter_riskier_path() -> None:
    """Shortest path is also riskier here — distance_only must still pick
    it (it never looks at risk_score)."""
    repository = _risky_top_safe_bottom_repository()
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())

    path = shortest_path(graph, "A", "F", cost_fn)

    assert path.node_sequence == ["A", "B", "C", "F"]  # top: shorter AND riskier


def test_risk_aware_prefers_the_longer_safer_path_research_benchmark() -> None:
    """RESEARCH EXPERIMENT (controlled algorithmic demonstration, not a
    real-world emergency claim):

        Route A: shorter (150m), higher risk (risk_score=1.0 throughout)
        Route B: longer (300m), lower risk (risk_score=0.0 throughout)

    distance_only must choose Route A; risk_aware, with a strong enough
    configured risk penalty, must choose Route B instead.
    """
    repository = _risky_top_safe_bottom_repository()
    graph = GraphView(repository.get_graph().nodes, repository.get_graph().edges)

    # cost_penalty_scale=4.0 (default): Route A adjusted cost = 50*5*3 = 750 > Route B's 300.
    routing_config = _routing_config()
    risk_config = _risk_config()
    distance_cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, routing_config, risk_config)
    risk_cost_fn = build_edge_cost_fn(RoutingMode.RISK_AWARE, routing_config, risk_config)

    distance_only_path = shortest_path(graph, "A", "F", distance_cost_fn)
    risk_aware_path = shortest_path(graph, "A", "F", risk_cost_fn)

    assert distance_only_path.node_sequence == ["A", "B", "C", "F"]  # Route A: shorter, riskier
    assert risk_aware_path.node_sequence == ["A", "D", "E", "F"]  # Route B: longer, safer
    # The safer route costs more under risk_aware's own objective, by design.
    assert risk_aware_path.total_cost > distance_only_path.total_cost


# ---------------------------------------------------------------------------
# 6. Nearest-node lookup
# ---------------------------------------------------------------------------


def test_nearest_node_finds_the_closest_node() -> None:
    nodes = [_node("A", 10.0, 20.0), _node("B", 20.0, 30.0)]
    locator = InMemoryNearestNodeLocator(nodes, max_distance_meters=100_000.0)

    nearest = locator.find_nearest(10.001, 20.001)

    assert nearest is not None
    assert nearest.node_id == "A"


def test_nearest_node_respects_max_distance() -> None:
    nodes = [_node("A", 10.0, 20.0)]
    locator = InMemoryNearestNodeLocator(nodes, max_distance_meters=10.0)

    assert locator.find_nearest(30.0, 40.0) is None  # far away, exceeds max distance


def test_nearest_node_of_empty_graph_is_none() -> None:
    locator = InMemoryNearestNodeLocator([], max_distance_meters=500.0)
    assert locator.find_nearest(10.0, 20.0) is None


# ---------------------------------------------------------------------------
# 7/8. Route reconstruction / route distance
# ---------------------------------------------------------------------------


def test_build_route_result_reconstructs_the_full_route() -> None:
    repository = _rectangle_repository()
    nodes_by_id = {node.node_id: node for node in repository.get_graph().nodes}
    cost_fn = build_edge_cost_fn(RoutingMode.DISTANCE_ONLY, _routing_config(), _risk_config())
    graph = GraphView(list(nodes_by_id.values()), repository.get_graph().edges)
    path = shortest_path(graph, "A", "F", cost_fn)

    result = build_route_result(path, RoutingMode.DISTANCE_ONLY, nodes_by_id)

    assert result.found is True
    assert result.routing_mode is RoutingMode.DISTANCE_ONLY
    assert result.start_node == "A"
    assert result.destination_node == "F"
    assert result.node_sequence == ["A", "B", "C", "F"]
    assert [e.source_node for e in result.edge_sequence] == ["A", "B", "C"]
    assert result.number_of_edges == 3
    assert result.total_distance == pytest.approx(150.0)
    assert len(result.route_geometry) == 4
    assert result.route_geometry[0] == nodes_by_id["A"].geometry.coordinates


def test_build_route_result_trivial_route_has_no_edges() -> None:
    node = _node("A", 10.0, 20.0)
    path = PathResult(found=True, node_sequence=["A"], edge_sequence=[], total_cost=0.0)

    result = build_route_result(path, RoutingMode.DISTANCE_ONLY, {"A": node})

    assert result.node_sequence == ["A"]
    assert result.edge_sequence == []
    assert result.total_distance == 0.0
    assert result.accumulated_risk == 0.0
    assert result.route_geometry == [node.geometry.coordinates]


# ---------------------------------------------------------------------------
# 9. Route risk (accumulated_risk)
# ---------------------------------------------------------------------------


def test_accumulated_risk_sums_risk_assessed_edges() -> None:
    node_a, node_b, node_c = _node("A", 0, 0), _node("B", 0, 1), _node("C", 0, 2)
    edges = [_edge("A", "B", 10.0, risk_score=0.3), _edge("B", "C", 10.0, risk_score=0.4)]
    path = PathResult(
        found=True, node_sequence=["A", "B", "C"], edge_sequence=edges, total_cost=20.0
    )
    nodes_by_id = {"A": node_a, "B": node_b, "C": node_c}

    result = build_route_result(path, RoutingMode.RISK_AWARE, nodes_by_id)

    assert result.accumulated_risk == pytest.approx(0.7)


def test_accumulated_risk_is_none_when_never_assessed() -> None:
    """Distinct from 0.0: None means risk was never evaluated at all for
    this route (e.g. distance_only without an available risk analysis)."""
    node_a, node_b = _node("A", 0, 0), _node("B", 0, 1)
    edges = [_edge("A", "B", 10.0, risk_score=None)]
    path = PathResult(found=True, node_sequence=["A", "B"], edge_sequence=edges, total_cost=10.0)

    result = build_route_result(path, RoutingMode.DISTANCE_ONLY, {"A": node_a, "B": node_b})

    assert result.accumulated_risk is None


def test_summarize_accessibility_counts_each_status() -> None:
    edges = [
        _edge("A", "B", 10.0, accessibility=AccessibilityStatus.OPEN),
        _edge("B", "C", 10.0, accessibility=AccessibilityStatus.RESTRICTED),
        _edge("C", "D", 10.0, accessibility=AccessibilityStatus.UNKNOWN),
    ]
    summary = summarize_accessibility(edges)
    assert summary == AccessibilitySummary(open=1, restricted=1, blocked=0, unknown=1)


# ---------------------------------------------------------------------------
# 10. Detour ratio / research metrics
# ---------------------------------------------------------------------------


def test_detour_ratio_matches_the_specified_formula() -> None:
    assert detour_ratio(300.0, 150.0) == pytest.approx(2.0)


def test_detour_ratio_is_none_when_baseline_distance_is_zero() -> None:
    assert detour_ratio(100.0, 0.0) is None


def test_detour_ratio_is_none_when_either_distance_is_missing() -> None:
    assert detour_ratio(None, 150.0) is None
    assert detour_ratio(150.0, None) is None


def test_count_risky_segments_counts_high_and_critical_only() -> None:
    node_a, node_b, node_c, node_d = (
        _node("A", 0, 0),
        _node("B", 0, 1),
        _node("C", 0, 2),
        _node("D", 0, 3),
    )
    edges = [
        _edge("A", "B", 10.0, risk_level=RiskLevel.LOW),
        _edge("B", "C", 10.0, risk_level=RiskLevel.HIGH),
        _edge("C", "D", 10.0, risk_level=RiskLevel.CRITICAL),
    ]
    path = PathResult(
        found=True, node_sequence=["A", "B", "C", "D"], edge_sequence=edges, total_cost=30.0
    )
    nodes_by_id = {"A": node_a, "B": node_b, "C": node_c, "D": node_d}
    route = build_route_result(path, RoutingMode.RISK_AWARE, nodes_by_id)

    assert count_risky_segments(route) == 2


def test_count_blocked_edges_counts_only_blocked() -> None:
    edges = [
        _edge("A", "B", 10.0, accessibility=AccessibilityStatus.BLOCKED),
        _edge("B", "C", 10.0, accessibility=AccessibilityStatus.OPEN),
    ]
    assert count_blocked_edges(edges) == 1


def test_high_risk_edges_avoided_lists_edges_unique_to_distance_only() -> None:
    node_a, node_b, node_c = _node("A", 0, 0), _node("B", 0, 1), _node("C", 0, 2)
    distance_only_edges = [_edge("A", "B", 10.0, risk_level=RiskLevel.CRITICAL)]
    risk_aware_edges = [_edge("A", "C", 20.0, risk_level=RiskLevel.LOW)]
    distance_only_path = PathResult(
        found=True, node_sequence=["A", "B"], edge_sequence=distance_only_edges, total_cost=10.0
    )
    risk_aware_path = PathResult(
        found=True, node_sequence=["A", "C"], edge_sequence=risk_aware_edges, total_cost=20.0
    )
    distance_only = build_route_result(
        distance_only_path, RoutingMode.DISTANCE_ONLY, {"A": node_a, "B": node_b}
    )
    risk_aware = build_route_result(
        risk_aware_path, RoutingMode.RISK_AWARE, {"A": node_a, "C": node_c}
    )

    avoided = high_risk_edges_avoided(distance_only, risk_aware)

    assert avoided == ["A->B"]


def test_high_risk_edges_avoided_is_empty_if_either_route_not_found() -> None:
    not_found = RouteResult(routing_mode=RoutingMode.DISTANCE_ONLY, found=False)
    found = RouteResult(routing_mode=RoutingMode.RISK_AWARE, found=True)
    assert high_risk_edges_avoided(not_found, found) == []


# ---------------------------------------------------------------------------
# 12. GeoJSON route output
# ---------------------------------------------------------------------------


def test_route_to_feature_produces_a_linestring() -> None:
    route = RouteResult(
        routing_mode=RoutingMode.DISTANCE_ONLY,
        found=True,
        route_geometry=[(20.0, 10.0), (20.001, 10.0), (20.002, 10.0)],
        total_distance=150.0,
        total_cost=150.0,
        accumulated_risk=0.0,
    )

    feature = route_to_feature(route)

    assert feature is not None
    assert feature.geometry.type == "LineString"
    assert feature.geometry.coordinates == route.route_geometry
    assert feature.properties.routing_mode == "distance_only"
    assert feature.properties.total_distance == 150.0


def test_route_to_feature_is_none_when_not_found() -> None:
    route = RouteResult(routing_mode=RoutingMode.DISTANCE_ONLY, found=False)
    assert route_to_feature(route) is None


def test_route_to_feature_is_none_for_a_single_point_trivial_route() -> None:
    route = RouteResult(
        routing_mode=RoutingMode.DISTANCE_ONLY, found=True, route_geometry=[(20.0, 10.0)]
    )
    assert route_to_feature(route) is None


# ---------------------------------------------------------------------------
# 13. Invalid coordinates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_latitude", [90.1, -90.1])
def test_geographic_coordinate_rejects_out_of_range_latitude(bad_latitude: float) -> None:
    with pytest.raises(ValidationError):
        GeographicCoordinate(latitude=bad_latitude, longitude=0.0)


@pytest.mark.parametrize("bad_longitude", [180.1, -180.1])
def test_geographic_coordinate_rejects_out_of_range_longitude(bad_longitude: float) -> None:
    with pytest.raises(ValidationError):
        GeographicCoordinate(latitude=0.0, longitude=bad_longitude)


def test_geographic_coordinate_is_always_wgs84() -> None:
    coordinate = GeographicCoordinate(latitude=10.0, longitude=20.0)
    assert coordinate.coordinate_reference_system is CoordinateReferenceSystem.WGS84


# ---------------------------------------------------------------------------
# RoutingService (unit tests, fake AnalysisProcessingService/RoadRiskService)
# ---------------------------------------------------------------------------


def _processing_service_with(record: AnalysisRecord) -> AnalysisProcessingService:
    repository = InMemoryAnalysisRepository()
    repository.create(record)
    return AnalysisProcessingService(
        repository=repository, file_storage=None, inference_engine=None  # type: ignore[arg-type]
    )


def _record(status: AnalysisStatus, analysis_id: UUID | None = None) -> AnalysisRecord:
    now = datetime.now(UTC)
    return AnalysisRecord(
        analysis_id=analysis_id or uuid4(),
        status=status,
        original_filename="a.png",
        storage_name="a.png",
        content_type="image/png",
        size_bytes=10,
        created_at=now,
        updated_at=now,
    )


def _routing_service(
    road_network_repository: InMemoryRoadNetworkRepository,
    analysis_record: AnalysisRecord,
    spatial_repository: InMemorySpatialRepository | None = None,
) -> RoutingService:
    road_risk_service = RoadRiskService(
        processing_service=_processing_service_with(analysis_record),
        spatial_repository=spatial_repository or InMemorySpatialRepository(),
        road_network_repository=road_network_repository,
        config=_risk_config(),
    )
    return RoutingService(
        road_network_repository=road_network_repository,
        road_risk_service=road_risk_service,
        routing_config=_routing_config(),
        risk_config=_risk_config(),
    )


def test_routing_service_route_finds_a_route_without_risk_data() -> None:
    """distance_only must still work when risk data is unavailable — the
    honest, common state today."""
    repository = _rectangle_repository()
    record = _record(AnalysisStatus.COMPLETED)
    service = _routing_service(repository, record)

    result = service.route(
        RoutingRequest(
            analysis_id=record.analysis_id,
            start=GeographicCoordinate(latitude=10.0, longitude=20.0),
            destination=GeographicCoordinate(latitude=9.990, longitude=20.002),
            mode=RoutingMode.DISTANCE_ONLY,
        )
    )

    assert result.found is True
    assert result.node_sequence == ["A", "B", "C", "F"]
    assert result.accumulated_risk is None  # never assessed


def test_routing_service_risk_aware_without_risk_data_is_unavailable() -> None:
    repository = _rectangle_repository()
    record = _record(AnalysisStatus.COMPLETED)
    service = _routing_service(repository, record)

    result = service.route(
        RoutingRequest(
            analysis_id=record.analysis_id,
            start=GeographicCoordinate(latitude=10.0, longitude=20.0),
            destination=GeographicCoordinate(latitude=9.990, longitude=20.002),
            mode=RoutingMode.RISK_AWARE,
        )
    )

    assert result.found is False
    assert result.reason is not None


def test_routing_service_risk_aware_with_available_risk_data_uses_it() -> None:
    repository = _rectangle_repository()
    record = _record(AnalysisStatus.COMPLETED)
    spatial_repository = InMemorySpatialRepository()
    # A destroyed building right next to the top path -> should push
    # risk_aware onto the bottom path.
    spatial_repository.save_buildings(
        record.analysis_id,
        [_building("b1", DamageClass.DESTROYED, lon=20.001, lat=10.0, confidence=1.0)],
    )
    service = _routing_service(repository, record, spatial_repository)

    result = service.route(
        RoutingRequest(
            analysis_id=record.analysis_id,
            start=GeographicCoordinate(latitude=10.0, longitude=20.0),
            destination=GeographicCoordinate(latitude=9.990, longitude=20.002),
            mode=RoutingMode.RISK_AWARE,
        )
    )

    assert result.found is True
    assert result.accumulated_risk is not None
    assert result.accumulated_risk > 0.0


def test_routing_service_route_raises_not_found_for_unknown_analysis() -> None:
    repository = _rectangle_repository()
    service = _routing_service(repository, _record(AnalysisStatus.COMPLETED))

    with pytest.raises(AnalysisNotFoundError):
        service.route(
            RoutingRequest(
                analysis_id=uuid4(),
                start=GeographicCoordinate(latitude=10.0, longitude=20.0),
                destination=GeographicCoordinate(latitude=9.990, longitude=20.002),
                mode=RoutingMode.DISTANCE_ONLY,
            )
        )


def test_routing_service_reports_unavailable_for_empty_road_network() -> None:
    record = _record(AnalysisStatus.COMPLETED)
    service = _routing_service(InMemoryRoadNetworkRepository(), record)

    result = service.route(
        RoutingRequest(
            analysis_id=record.analysis_id,
            start=GeographicCoordinate(latitude=10.0, longitude=20.0),
            destination=GeographicCoordinate(latitude=9.990, longitude=20.002),
            mode=RoutingMode.DISTANCE_ONLY,
        )
    )

    assert result.found is False
    assert result.reason is not None


def test_routing_service_reports_unavailable_when_no_node_is_near_coordinates() -> None:
    repository = _rectangle_repository()
    record = _record(AnalysisStatus.COMPLETED)
    service = _routing_service(repository, record)

    result = service.route(
        RoutingRequest(
            analysis_id=record.analysis_id,
            start=GeographicCoordinate(latitude=50.0, longitude=50.0),  # far from every node
            destination=GeographicCoordinate(latitude=9.990, longitude=20.002),
            mode=RoutingMode.DISTANCE_ONLY,
        )
    )

    assert result.found is False
    assert result.reason is not None


# ---------------------------------------------------------------------------
# 11. Route comparison
# ---------------------------------------------------------------------------


def test_compare_routes_reports_differences_when_routes_differ() -> None:
    """`RoadRiskService.get_road_risk()` always *recomputes* risk from real
    building proximity (it never trusts pre-set `risk_score` fields on
    repository edges — see `app.risk.analyzer`), so — unlike the pure
    algorithm-level tests above, which build a `GraphView` directly and
    bypass `RoadRiskService` entirely — this test must place real,
    georeferenced buildings near the top path rather than setting
    `risk_score` by hand.
    """
    repository = _rectangle_repository()
    record = _record(AnalysisStatus.COMPLETED)
    spatial_repository = InMemorySpatialRepository()
    spatial_repository.save_buildings(
        record.analysis_id,
        [
            _building("b1", DamageClass.DESTROYED, lon=20.0005, lat=10.0, confidence=1.0),
            _building("b2", DamageClass.DESTROYED, lon=20.0015, lat=10.0, confidence=1.0),
            _building("b3", DamageClass.DESTROYED, lon=20.002, lat=9.995, confidence=1.0),
        ],
    )
    service = _routing_service(repository, record, spatial_repository)

    comparison = service.compare_routes(
        record.analysis_id,
        GeographicCoordinate(latitude=10.0, longitude=20.0),
        GeographicCoordinate(latitude=9.990, longitude=20.002),
    )

    assert comparison.distance_only.node_sequence == ["A", "B", "C", "F"]
    assert comparison.risk_aware.node_sequence == ["A", "D", "E", "F"]
    assert comparison.routes_differ is True
    assert comparison.distance_difference == pytest.approx(150.0)  # 300 - 150
    assert comparison.detour_ratio == pytest.approx(2.0)
    assert comparison.risky_segments_distance_only == 3
    assert comparison.risky_segments_risk_aware == 0
    assert "A->B" in comparison.high_risk_edges_avoided


# ---------------------------------------------------------------------------
# 15. Routing API
# ---------------------------------------------------------------------------


def test_routing_api_returns_422_for_invalid_coordinates(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/routing",
        json={
            "analysis_id": str(uuid4()),
            "start": {"latitude": 999.0, "longitude": 0.0},
            "destination": {"latitude": 0.0, "longitude": 0.0},
            "mode": "distance_only",
        },
    )
    assert response.status_code == 422


def test_routing_api_returns_422_for_missing_mode(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/routing",
        json={
            "analysis_id": str(uuid4()),
            "start": {"latitude": 0.0, "longitude": 0.0},
            "destination": {"latitude": 0.0, "longitude": 0.0},
        },
    )
    assert response.status_code == 422


def test_routing_api_returns_404_for_unknown_analysis(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/routing",
        json={
            "analysis_id": str(uuid4()),
            "start": {"latitude": 0.0, "longitude": 0.0},
            "destination": {"latitude": 0.0, "longitude": 0.001},
            "mode": "distance_only",
        },
    )
    assert response.status_code == 404


def test_routing_api_distance_only_end_to_end(analysis_app_factory) -> None:  # type: ignore[no-untyped-def]
    """No fake model needed for distance_only — it works even against the
    real (currently-always-failing) production pipeline, since it doesn't
    need risk data."""
    from fastapi.testclient import TestClient

    app: FastAPI = analysis_app_factory()
    client = TestClient(app)

    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(buffer, format="PNG")
    post_response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", buffer.getvalue(), "image/png")}
    )
    analysis_id = post_response.json()["analysis_id"]

    road_repository = _rectangle_repository()
    app.dependency_overrides[get_road_network_repository] = lambda: road_repository

    response = client.post(
        "/api/v1/routing",
        json={
            "analysis_id": analysis_id,
            "start": {"latitude": 10.0, "longitude": 20.0},
            "destination": {"latitude": 9.990, "longitude": 20.002},
            "mode": "distance_only",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["node_sequence"] == ["A", "B", "C", "F"]
    assert body["total_distance"] == pytest.approx(150.0)


class _FakeCompletingModel:
    """Test-only `DamageModel` producing one detection, so the analysis
    actually reaches `completed` — `RoadRiskService` (and therefore
    risk-aware routing) requires that, same pattern as `test_road_risk.py`.
    """

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list:  # type: ignore[type-arg]
        from app.ml.model import RawDetection
        from app.ml.spatial import BoundingBox

        return [
            RawDetection(
                damage_class=DamageClass.MINOR,
                confidence=0.5,
                bounding_box=BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10),
            )
        ]

    def health(self):  # type: ignore[no-untyped-def]
        from app.ml.schemas import ModelStatus

        return ModelStatus(model_loaded=True, model_name="fake", model_version="test", device="cpu")


def test_routing_api_risk_aware_end_to_end(analysis_app_factory) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    app: FastAPI = analysis_app_factory(model=_FakeCompletingModel())
    client = TestClient(app)

    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(buffer, format="PNG")
    post_response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", buffer.getvalue(), "image/png")}
    )
    analysis_id = post_response.json()["analysis_id"]

    road_repository = _rectangle_repository()
    for source, target in [("A", "B"), ("B", "C"), ("C", "F")]:
        road_repository.add_edge(_edge(source, target, 50.0))
        road_repository.add_edge(_edge(target, source, 50.0))
    app.dependency_overrides[get_road_network_repository] = lambda: road_repository

    spatial_repository = app.dependency_overrides[get_spatial_repository]()
    spatial_repository.save_buildings(
        UUID(analysis_id),
        [_building("b1", DamageClass.DESTROYED, lon=20.001, lat=10.0, confidence=1.0)],
    )

    response = client.post(
        "/api/v1/routing",
        json={
            "analysis_id": analysis_id,
            "start": {"latitude": 10.0, "longitude": 20.0},
            "destination": {"latitude": 9.990, "longitude": 20.002},
            "mode": "risk_aware",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["node_sequence"] == ["A", "D", "E", "F"]  # avoids the risky top path
    # The chosen (bottom) path is far from the building — a little risk
    # leaks onto its first edge (A-D) since the search radius reaches
    # slightly past A — but far less than the top path's would have been.
    assert body["accumulated_risk"] < 0.5
