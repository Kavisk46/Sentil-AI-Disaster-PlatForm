"""Graph **construction** — turns raw `OSMRoadData` (`app.roads.osm_source`)
into `RoadNode`/`RoadEdge` records and populates a `RoadNetworkRepository`.

    OpenStreetMap -> Road Network (OSMRoadData) -> Graph (RoadNetworkRepository)

Deliberately separate from OSM data acquisition (doesn't know or care
whether `OSMRoadData` came from a live Overpass call or a static test
fixture) and from routing (doesn't compute a path, only builds the graph
those algorithms would later run on).

Every OSM way's tags are read defensively — real-world OSM extracts have
inconsistent, sometimes-missing tagging. A missing tag becomes `None` on
the resulting `RoadEdge`, never a fabricated default (see "Road
attributes" in `apps/api/README.md`).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.roads.geo_utils import haversine_distance_meters
from app.roads.osm_source import OSMRoadData, OSMWay
from app.roads.schemas import AccessibilityStatus, RoadEdge, RoadNode
from app.roads.weighting import compute_base_cost

if TYPE_CHECKING:
    from app.services.road_network_repository import RoadNetworkRepository

_ONE_WAY_VALUES = frozenset({"yes", "true", "1"})


@dataclass(frozen=True, slots=True)
class _WayAttributes:
    """The subset of an OSM way's tags `RoadEdge` cares about, parsed once
    per way rather than threaded through as five separate parameters."""

    road_type: str | None
    name: str | None
    maxspeed: str | None
    lanes: int | None
    one_way: bool
    surface: str | None

    @classmethod
    def from_tags(cls, tags: dict[str, str]) -> "_WayAttributes":
        return cls(
            road_type=tags.get("highway"),
            name=tags.get("name"),
            maxspeed=tags.get("maxspeed"),
            lanes=_parse_lanes(tags.get("lanes")),
            one_way=tags.get("oneway") in _ONE_WAY_VALUES,
            surface=tags.get("surface"),
        )


def build_road_network(data: OSMRoadData, repository: "RoadNetworkRepository") -> None:
    """Populates `repository` with `data`'s nodes and directed edges.

    `RoadNetworkRepository` is imported only for the type hint (guarded by
    `TYPE_CHECKING` above) — this module has no runtime dependency on
    `app.services`, keeping `app.roads` free of any `app.services`/FastAPI
    coupling, matching `app.ml`'s own layering.
    """
    for osm_node in data.nodes.values():
        repository.add_node(
            RoadNode(
                node_id=str(osm_node.osm_id),
                latitude=osm_node.latitude,
                longitude=osm_node.longitude,
            )
        )

    for way in data.ways:
        for edge in _edges_for_way(way, data):
            repository.add_edge(edge)


def _edges_for_way(way: OSMWay, data: OSMRoadData) -> list[RoadEdge]:
    attributes = _WayAttributes.from_tags(way.tags)

    edges: list[RoadEdge] = []
    for source_id, target_id in zip(way.node_ids, way.node_ids[1:], strict=False):
        source_node = data.nodes.get(source_id)
        target_node = data.nodes.get(target_id)
        if source_node is None or target_node is None:
            # A way referencing a node outside the fetched bounding box
            # (Overpass's own `>` recurse-down only resolves nodes for
            # ways matched by the query, not neighbors outside it) — skip
            # rather than fabricate a position for a node we never fetched.
            continue

        distance = haversine_distance_meters(
            source_node.latitude, source_node.longitude, target_node.latitude, target_node.longitude
        )
        edges.append(_make_edge(str(source_id), str(target_id), distance, attributes))
        if not attributes.one_way:
            edges.append(_make_edge(str(target_id), str(source_id), distance, attributes))
    return edges


def _make_edge(
    source_node: str, target_node: str, distance: float, attributes: _WayAttributes
) -> RoadEdge:
    return RoadEdge(
        source_node=source_node,
        target_node=target_node,
        distance=distance,
        base_cost=compute_base_cost(distance),
        road_type=attributes.road_type,
        name=attributes.name,
        maxspeed=attributes.maxspeed,
        lanes=attributes.lanes,
        one_way=attributes.one_way,
        surface=attributes.surface,
        accessibility=AccessibilityStatus.UNKNOWN,
        risk_score=None,
    )


def _parse_lanes(raw: str | None) -> int | None:
    """OSM's `lanes` tag is a free-text string — sometimes non-numeric
    (e.g. `"2;3"` for a lane count that changes along the way). Returns
    `None` rather than fabricating a number for anything that doesn't
    parse cleanly."""
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None
