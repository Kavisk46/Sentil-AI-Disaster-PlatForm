"""Tests for the road-network foundation (Milestone 6A): the graph
abstraction (`RoadNetworkRepository`), OSM data acquisition/parsing,
graph construction from OSM data, and `GET /api/v1/roads/status`.

No internet access, no GPU, fully deterministic. `OverpassRoadNetworkSource`
is exercised only through its query-building and error-handling paths
(via a patched `urllib.request.urlopen`) — its `fetch_bounding_box()` is
never called against the real network anywhere in this file.
"""

import math
from unittest.mock import patch
from urllib.error import URLError

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_road_network_repository
from app.main import create_app
from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.roads.builder import build_road_network
from app.roads.errors import UnknownRoadNodeError
from app.roads.geo_utils import haversine_distance_meters
from app.roads.osm_source import (
    OSMNode,
    OSMRoadData,
    OSMWay,
    OverpassRoadNetworkSource,
    RoadNetworkSourceError,
    parse_overpass_response,
)
from app.roads.schemas import AccessibilityStatus, RoadEdge, RoadNode
from app.roads.weighting import compute_base_cost
from app.services.road_network_ingestion_service import RoadNetworkIngestionService
from app.services.road_network_repository import InMemoryRoadNetworkRepository
from app.services.road_network_status_service import RoadNetworkStatusService


def _node(node_id: str, latitude: float, longitude: float) -> RoadNode:
    return RoadNode(node_id=node_id, latitude=latitude, longitude=longitude)


def _edge(
    source_node: str,
    target_node: str,
    distance: float = 100.0,
    *,
    one_way: bool = False,
    accessibility: AccessibilityStatus = AccessibilityStatus.OPEN,
    **kwargs: object,
) -> RoadEdge:
    return RoadEdge(
        source_node=source_node,
        target_node=target_node,
        distance=distance,
        base_cost=compute_base_cost(distance),
        one_way=one_way,
        accessibility=accessibility,
        **kwargs,  # type: ignore[arg-type]
    )


def _synthetic_road_network() -> InMemoryRoadNetworkRepository:
    """The fixture network from the milestone spec:

        A -- B -- C
        |         |
        D --------

    All edges two-way (added as one `RoadEdge` per direction), a small,
    deterministic square around (10, 20).
    """
    repository = InMemoryRoadNetworkRepository()
    nodes = {
        "A": _node("A", 10.000, 20.000),
        "B": _node("B", 10.000, 20.001),
        "C": _node("C", 10.000, 20.002),
        "D": _node("D", 9.999, 20.000),
    }
    for node in nodes.values():
        repository.add_node(node)

    for source_id, target_id in [("A", "B"), ("B", "C"), ("A", "D"), ("D", "C")]:
        distance = haversine_distance_meters(
            nodes[source_id].latitude,
            nodes[source_id].longitude,
            nodes[target_id].latitude,
            nodes[target_id].longitude,
        )
        repository.add_edge(_edge(source_id, target_id, distance))
        repository.add_edge(_edge(target_id, source_id, distance))

    return repository


def _sample_overpass_payload() -> dict[str, object]:
    return {
        "version": 0.6,
        "elements": [
            {"type": "node", "id": 1, "lat": 10.0, "lon": 20.0},
            {"type": "node", "id": 2, "lat": 10.0, "lon": 20.001},
            {"type": "node", "id": 3, "lat": 10.0, "lon": 20.002},
            {"type": "node", "id": 4, "lat": 10.0, "lon": 20.003},
            {
                "type": "way",
                "id": 100,
                "nodes": [1, 2, 3],
                "tags": {
                    "highway": "residential",
                    "name": "Test Street",
                    "maxspeed": "50",
                    "lanes": "2",
                    "surface": "asphalt",
                },
            },
            {
                "type": "way",
                "id": 101,
                "nodes": [3, 1],
                "tags": {"highway": "service", "oneway": "yes"},
            },
            # Deliberately a different node pair (3, 4) than any segment of
            # way 100/101 — two distinct OSM ways sharing an endpoint pair
            # would collide in `RoadNetworkRepository`'s (source, target)
            # keying (last write wins), which is a realistic edge case but
            # not what this fixture is testing.
            {"type": "way", "id": 102, "nodes": [3, 4], "tags": {}},
        ],
    }


# ---------------------------------------------------------------------------
# 1. Node creation
# ---------------------------------------------------------------------------


def test_road_node_can_be_constructed_with_valid_coordinates() -> None:
    node = _node("n1", 12.5, -8.25)
    assert node.node_id == "n1"
    assert node.latitude == 12.5
    assert node.longitude == -8.25


def test_road_node_exposes_a_milestone_5_point_geometry() -> None:
    node = _node("n1", 12.5, -8.25)
    assert node.geometry.coordinates == (-8.25, 12.5)  # (lon, lat) GeoJSON order


def test_repository_add_and_get_node_roundtrip() -> None:
    repository = InMemoryRoadNetworkRepository()
    node = _node("n1", 1.0, 2.0)

    repository.add_node(node)

    assert repository.get_node("n1") == node


def test_repository_get_unknown_node_returns_none() -> None:
    repository = InMemoryRoadNetworkRepository()
    assert repository.get_node("does-not-exist") is None


# ---------------------------------------------------------------------------
# 2. Edge creation
# ---------------------------------------------------------------------------


def test_road_edge_can_be_constructed_with_valid_distance() -> None:
    edge = _edge("A", "B", distance=150.0)
    assert edge.source_node == "A"
    assert edge.target_node == "B"
    assert edge.distance == 150.0


def test_repository_add_and_get_edge_roundtrip() -> None:
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(_node("A", 0.0, 0.0))
    repository.add_node(_node("B", 0.0, 0.001))
    edge = _edge("A", "B", distance=111.0)

    repository.add_edge(edge)

    assert repository.get_edge("A", "B") == edge


def test_repository_get_unknown_edge_returns_none() -> None:
    repository = InMemoryRoadNetworkRepository()
    assert repository.get_edge("A", "B") is None


def test_add_edge_with_unknown_source_node_raises() -> None:
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(_node("B", 0.0, 0.0))

    with pytest.raises(UnknownRoadNodeError):
        repository.add_edge(_edge("A", "B"))


def test_add_edge_with_unknown_target_node_raises() -> None:
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(_node("A", 0.0, 0.0))

    with pytest.raises(UnknownRoadNodeError):
        repository.add_edge(_edge("A", "B"))


# ---------------------------------------------------------------------------
# 3. Directed edges
# ---------------------------------------------------------------------------


def test_adding_one_direction_does_not_create_the_reverse() -> None:
    """A one-way road: only A->B should exist, never B->A."""
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(_node("A", 0.0, 0.0))
    repository.add_node(_node("B", 0.0, 0.001))

    repository.add_edge(_edge("A", "B", one_way=True))

    assert repository.get_edge("A", "B") is not None
    assert repository.get_edge("B", "A") is None


def test_a_two_way_road_is_represented_as_two_directed_edges() -> None:
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(_node("A", 0.0, 0.0))
    repository.add_node(_node("B", 0.0, 0.001))

    repository.add_edge(_edge("A", "B"))
    repository.add_edge(_edge("B", "A"))

    assert repository.get_edge("A", "B") is not None
    assert repository.get_edge("B", "A") is not None


# ---------------------------------------------------------------------------
# 4. Neighbor lookup
# ---------------------------------------------------------------------------


def test_neighbors_returns_directly_reachable_nodes() -> None:
    repository = _synthetic_road_network()

    neighbor_ids = {node.node_id for node in repository.neighbors("A")}

    assert neighbor_ids == {"B", "D"}


def test_neighbors_of_unknown_node_is_empty_not_an_error() -> None:
    repository = InMemoryRoadNetworkRepository()
    assert repository.neighbors("nope") == []


def test_neighbors_respects_directionality() -> None:
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(_node("A", 0.0, 0.0))
    repository.add_node(_node("B", 0.0, 0.001))
    repository.add_edge(_edge("A", "B", one_way=True))

    assert {n.node_id for n in repository.neighbors("A")} == {"B"}
    assert repository.neighbors("B") == []


# ---------------------------------------------------------------------------
# 5. Distance validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_distance", [0.0, -5.0, math.nan, math.inf])
def test_road_edge_rejects_non_positive_or_non_finite_distance(bad_distance: float) -> None:
    with pytest.raises(ValidationError):
        RoadEdge(
            source_node="A",
            target_node="B",
            distance=bad_distance,
            base_cost=1.0,
        )


def test_road_edge_rejects_non_positive_base_cost() -> None:
    with pytest.raises(ValidationError):
        RoadEdge(source_node="A", target_node="B", distance=10.0, base_cost=0.0)


def test_road_edge_rejects_non_positive_lanes() -> None:
    with pytest.raises(ValidationError):
        RoadEdge(source_node="A", target_node="B", distance=10.0, base_cost=10.0, lanes=0)


# ---------------------------------------------------------------------------
# 6. Coordinate validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_latitude", [90.1, -90.1, math.nan, math.inf])
def test_road_node_rejects_out_of_range_or_non_finite_latitude(bad_latitude: float) -> None:
    with pytest.raises(ValidationError):
        RoadNode(node_id="n1", latitude=bad_latitude, longitude=0.0)


@pytest.mark.parametrize("bad_longitude", [180.1, -180.1, math.nan, math.inf])
def test_road_node_rejects_out_of_range_or_non_finite_longitude(bad_longitude: float) -> None:
    with pytest.raises(ValidationError):
        RoadNode(node_id="n1", latitude=0.0, longitude=bad_longitude)


def test_road_node_accepts_boundary_coordinates() -> None:
    node = RoadNode(node_id="n1", latitude=90.0, longitude=-180.0)
    assert node.latitude == 90.0
    assert node.longitude == -180.0


# ---------------------------------------------------------------------------
# 7. Bounding-box query
# ---------------------------------------------------------------------------


def test_bounding_box_query_returns_only_nodes_inside_the_box() -> None:
    repository = _synthetic_road_network()
    bbox = BoundingBoxGeometry(coordinates=(19.9995, 9.9995, 20.0025, 10.0005))

    result = {node.node_id for node in repository.query_bounding_box(bbox)}

    assert result == {"A", "B", "C"}  # D's latitude (9.999) falls outside


def test_bounding_box_query_on_empty_repository_returns_empty() -> None:
    repository = InMemoryRoadNetworkRepository()
    bbox = BoundingBoxGeometry(coordinates=(-1, -1, 1, 1))
    assert repository.query_bounding_box(bbox) == []


def test_get_bounds_covers_every_node() -> None:
    repository = _synthetic_road_network()

    bounds = repository.get_bounds()

    assert bounds is not None
    min_lon, min_lat, max_lon, max_lat = bounds.coordinates
    assert min_lat == pytest.approx(9.999)
    assert max_lat == pytest.approx(10.000)
    assert min_lon == pytest.approx(20.000)
    assert max_lon == pytest.approx(20.002)


def test_get_bounds_on_empty_repository_is_none() -> None:
    repository = InMemoryRoadNetworkRepository()
    assert repository.get_bounds() is None


# ---------------------------------------------------------------------------
# 8. Accessibility states
# ---------------------------------------------------------------------------


def test_accessibility_defaults_to_unknown() -> None:
    edge = RoadEdge(source_node="A", target_node="B", distance=10.0, base_cost=10.0)
    assert edge.accessibility == AccessibilityStatus.UNKNOWN


@pytest.mark.parametrize(
    "value", [AccessibilityStatus.OPEN, AccessibilityStatus.RESTRICTED, AccessibilityStatus.BLOCKED]
)
def test_accessibility_accepts_every_defined_state(value: AccessibilityStatus) -> None:
    edge = RoadEdge(
        source_node="A", target_node="B", distance=10.0, base_cost=10.0, accessibility=value
    )
    assert edge.accessibility == value


def test_osm_ingestion_never_marks_an_edge_blocked_or_restricted() -> None:
    """OSM alone must never determine disaster blockage — every edge
    built from OSM data starts `unknown`."""
    data = OSMRoadData(
        nodes={
            1: OSMNode(osm_id=1, latitude=10.0, longitude=20.0),
            2: OSMNode(osm_id=2, latitude=10.0, longitude=20.001),
        },
        ways=[OSMWay(osm_id=10, node_ids=[1, 2], tags={"highway": "residential"})],
    )
    repository = InMemoryRoadNetworkRepository()

    build_road_network(data, repository)

    graph = repository.get_graph()
    assert all(edge.accessibility == AccessibilityStatus.UNKNOWN for edge in graph.edges)


# ---------------------------------------------------------------------------
# 9. Graph construction (end-to-end from OSM data)
# ---------------------------------------------------------------------------


def test_build_road_network_populates_nodes_and_edges() -> None:
    data = parse_overpass_response(_sample_overpass_payload())
    repository = InMemoryRoadNetworkRepository()

    build_road_network(data, repository)

    graph = repository.get_graph()
    assert {node.node_id for node in graph.nodes} == {"1", "2", "3", "4"}
    # way 100 (two-way, 2 segments) -> 4 directed edges
    # way 101 (one-way, 1 segment) -> 1 directed edge
    # way 102 (two-way, 1 segment, no tags) -> 2 directed edges
    assert len(graph.edges) == 4 + 1 + 2


def test_build_road_network_one_way_tag_produces_a_single_direction() -> None:
    data = parse_overpass_response(_sample_overpass_payload())
    repository = InMemoryRoadNetworkRepository()

    build_road_network(data, repository)

    assert repository.get_edge("3", "1") is not None
    assert repository.get_edge("1", "3") is None


def test_build_road_network_computes_base_cost_as_distance() -> None:
    data = parse_overpass_response(_sample_overpass_payload())
    repository = InMemoryRoadNetworkRepository()

    build_road_network(data, repository)

    edge = repository.get_edge("1", "2")
    assert edge is not None
    assert edge.base_cost == edge.distance


def test_build_road_network_skips_way_segments_referencing_unfetched_nodes() -> None:
    """A way referencing a node id outside the fetched bounding box must
    be skipped, never fabricated a position."""
    data = OSMRoadData(
        nodes={1: OSMNode(osm_id=1, latitude=10.0, longitude=20.0)},
        ways=[OSMWay(osm_id=10, node_ids=[1, 999], tags={"highway": "residential"})],
    )
    repository = InMemoryRoadNetworkRepository()

    build_road_network(data, repository)

    assert repository.get_graph().edges == []


# ---------------------------------------------------------------------------
# 10. Synthetic OSM fixture (parser correctness)
# ---------------------------------------------------------------------------


def test_parse_overpass_response_extracts_nodes() -> None:
    data = parse_overpass_response(_sample_overpass_payload())

    assert set(data.nodes) == {1, 2, 3, 4}
    assert data.nodes[1].latitude == 10.0
    assert data.nodes[1].longitude == 20.0


def test_parse_overpass_response_extracts_ways_with_tags() -> None:
    data = parse_overpass_response(_sample_overpass_payload())

    way_100 = next(way for way in data.ways if way.osm_id == 100)
    assert way_100.node_ids == [1, 2, 3]
    assert way_100.tags["highway"] == "residential"
    assert way_100.tags["name"] == "Test Street"


def test_parse_overpass_response_ignores_non_node_way_elements() -> None:
    payload: dict[str, object] = {
        "elements": [
            {"type": "node", "id": 1, "lat": 0.0, "lon": 0.0},
            {"type": "relation", "id": 5, "members": []},
        ]
    }
    data = parse_overpass_response(payload)
    assert list(data.nodes) == [1]
    assert data.ways == []


def test_parse_overpass_response_rejects_malformed_payload() -> None:
    with pytest.raises(RoadNetworkSourceError):
        parse_overpass_response({"elements": "not-a-list"})


def test_build_overpass_query_embeds_the_bounding_box() -> None:
    from app.roads.osm_source import _build_overpass_query

    query = _build_overpass_query(1.0, 2.0, 3.0, 4.0)
    assert "1.0,2.0,3.0,4.0" in query
    assert "way[highway]" in query


def test_overpass_source_wraps_network_failures() -> None:
    """No real network call — `urlopen` is patched to fail immediately,
    proving the error path without touching the internet."""
    source = OverpassRoadNetworkSource()

    with (
        patch("app.roads.osm_source.urllib.request.urlopen", side_effect=URLError("no network")),
        pytest.raises(RoadNetworkSourceError),
    ):
        source.fetch_bounding_box(1.0, 2.0, 3.0, 4.0)


# ---------------------------------------------------------------------------
# 11. Missing road attributes
# ---------------------------------------------------------------------------


def test_road_edge_optional_attributes_default_to_none_not_fabricated() -> None:
    edge = RoadEdge(source_node="A", target_node="B", distance=10.0, base_cost=10.0)

    assert edge.road_type is None
    assert edge.name is None
    assert edge.maxspeed is None
    assert edge.lanes is None
    assert edge.surface is None
    assert edge.risk_score is None
    assert edge.one_way is False


def test_build_road_network_untagged_way_produces_edges_with_no_attributes() -> None:
    data = parse_overpass_response(_sample_overpass_payload())
    repository = InMemoryRoadNetworkRepository()

    build_road_network(data, repository)

    edge = repository.get_edge("3", "4")  # way 102 has no tags at all
    assert edge is not None
    assert edge.road_type is None
    assert edge.name is None
    assert edge.maxspeed is None
    assert edge.lanes is None


def test_build_road_network_non_numeric_lanes_tag_is_not_fabricated() -> None:
    data = OSMRoadData(
        nodes={
            1: OSMNode(osm_id=1, latitude=10.0, longitude=20.0),
            2: OSMNode(osm_id=2, latitude=10.0, longitude=20.001),
        },
        ways=[OSMWay(osm_id=10, node_ids=[1, 2], tags={"highway": "residential", "lanes": "2;3"})],
    )
    repository = InMemoryRoadNetworkRepository()

    build_road_network(data, repository)

    edge = repository.get_edge("1", "2")
    assert edge is not None
    assert edge.lanes is None


# ---------------------------------------------------------------------------
# Ingestion service (acquisition -> construction -> repository)
# ---------------------------------------------------------------------------


class _FakeRoadNetworkSource:
    """Test-only `RoadNetworkSource` — returns canned data, no network."""

    def __init__(self, data: OSMRoadData) -> None:
        self._data = data
        self.requested_bbox: tuple[float, float, float, float] | None = None

    def fetch_bounding_box(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float
    ) -> OSMRoadData:
        self.requested_bbox = (min_lat, min_lon, max_lat, max_lon)
        return self._data


def test_ingestion_service_loads_fetched_data_into_the_repository() -> None:
    data = parse_overpass_response(_sample_overpass_payload())
    source = _FakeRoadNetworkSource(data)
    repository = InMemoryRoadNetworkRepository()
    service = RoadNetworkIngestionService(source=source, repository=repository)

    service.load_for_bounding_box(1.0, 2.0, 3.0, 4.0)

    assert source.requested_bbox == (1.0, 2.0, 3.0, 4.0)
    assert len(repository.get_graph().nodes) == 4


# ---------------------------------------------------------------------------
# 12. Road network unavailable state
# ---------------------------------------------------------------------------


def test_status_service_reports_unavailable_for_an_empty_repository() -> None:
    service = RoadNetworkStatusService(repository=InMemoryRoadNetworkRepository())

    result = service.get_status()

    assert result.loaded is False
    assert result.node_count == 0
    assert result.edge_count == 0
    assert result.bounds is None
    assert result.message is not None
    assert "unavailable" in result.message.lower()


def test_status_service_reports_available_once_populated() -> None:
    repository = _synthetic_road_network()
    service = RoadNetworkStatusService(repository=repository)

    result = service.get_status()

    assert result.loaded is True
    assert result.node_count == 4
    assert result.edge_count == 8  # 4 two-way roads = 8 directed edges
    assert result.bounds is not None
    assert result.message is None


# ---------------------------------------------------------------------------
# 13. API status endpoint
# ---------------------------------------------------------------------------


def test_status_endpoint_reports_unavailable_by_default(client: TestClient) -> None:
    response = client.get("/api/v1/roads/status")

    assert response.status_code == 200
    body = response.json()
    assert body["loaded"] is False
    assert body["node_count"] == 0
    assert body["edge_count"] == 0
    assert body["bounds"] is None
    assert body["message"] is not None


def test_status_endpoint_reports_available_for_a_populated_network() -> None:
    app: FastAPI = create_app()
    app.dependency_overrides[get_road_network_repository] = _synthetic_road_network
    client = TestClient(app)

    response = client.get("/api/v1/roads/status")

    assert response.status_code == 200
    body = response.json()
    assert body["loaded"] is True
    assert body["node_count"] == 4
    assert body["edge_count"] == 8
    assert body["bounds"] is not None
    assert body["message"] is None


def test_status_endpoint_does_not_break_other_existing_routes(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
