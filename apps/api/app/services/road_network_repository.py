"""The road-network graph abstraction.

Behind a small repository interface (`RoadNetworkRepository`), same
pattern as `AnalysisRepository`/`SpatialRepository`: nothing outside this
module ever sees a raw graph-library object or a bare dict — every caller
depends on `RoadNode`/`RoadEdge`/`RoadGraph`
(`app.roads.schemas`), so a future implementation backed by a real graph
library (networkx) or a real database (PostGIS + pgRouting) can replace
`InMemoryRoadNetworkRepository` without changing any caller
(`app.roads.builder`, `RoadNetworkStatusService`, a future routing
service).

Directed by construction: `add_edge()` stores exactly the direction given
— a two-way road is represented by *two* `RoadEdge`s (one per direction),
added explicitly by the caller (see `app.roads.builder`), never inferred
here. This repository does not silently add a reverse edge for a
`one_way=False` edge.

Bounding-box queries reuse `app.ml.geospatial.geometry.BoundingBoxGeometry`
directly (Milestone 5) rather than a parallel bbox type — `coordinates` is
`(min_lon, min_lat, max_lon, max_lat)`, the same `(x_min, y_min, x_max,
y_max)` convention `BoundingBoxGeometry` already uses, with `x = longitude`
and `y = latitude` (the GeoJSON coordinate-order convention `RoadNode`
itself already follows).
"""

import threading
from typing import Protocol

from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.roads.errors import UnknownRoadNodeError
from app.roads.schemas import RoadEdge, RoadGraph, RoadNode


class RoadNetworkRepository(Protocol):
    def add_node(self, node: RoadNode) -> None:
        """Add or replace a node by `node_id`."""
        ...

    def add_edge(self, edge: RoadEdge) -> None:
        """Add or replace a directed edge, keyed by
        `(source_node, target_node)`.

        Raises `UnknownRoadNodeError` if either endpoint hasn't been added
        via `add_node()` yet — a road segment can't reference a location
        the graph doesn't know about.
        """
        ...

    def get_node(self, node_id: str) -> RoadNode | None: ...

    def get_edge(self, source_node: str, target_node: str) -> RoadEdge | None: ...

    def neighbors(self, node_id: str) -> list[RoadNode]:
        """Nodes directly reachable from `node_id` via one directed edge.
        Empty (not an error) if `node_id` is unknown or has no outgoing
        edges."""
        ...

    def get_graph(self) -> RoadGraph:
        """A snapshot of every node and edge currently stored."""
        ...

    def get_bounds(self) -> BoundingBoxGeometry | None:
        """The geographic bounding box covering every stored node, or
        `None` if no nodes have been added yet — never a fabricated
        bounds for an empty graph."""
        ...

    def query_bounding_box(self, bbox: BoundingBoxGeometry) -> list[RoadNode]:
        """Every stored node whose coordinates fall within `bbox`
        (`(min_lon, min_lat, max_lon, max_lat)`)."""
        ...


class InMemoryRoadNetworkRepository:
    """Process-local, non-persistent — same tradeoffs as
    `InMemoryAnalysisRepository`/`InMemorySpatialRepository`. A single
    instance must be shared across requests (see `app/api/deps.py`) to
    remember anything between calls. Never auto-populated: starts empty,
    and stays empty unless something explicitly calls `add_node`/`add_edge`
    (see `app.services.road_network_ingestion_service`) — no application
    startup or route triggers an OSM fetch.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, RoadNode] = {}
        self._edges: dict[tuple[str, str], RoadEdge] = {}
        self._adjacency: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def add_node(self, node: RoadNode) -> None:
        with self._lock:
            self._nodes[node.node_id] = node
            self._adjacency.setdefault(node.node_id, set())

    def add_edge(self, edge: RoadEdge) -> None:
        with self._lock:
            if edge.source_node not in self._nodes:
                raise UnknownRoadNodeError(edge.source_node)
            if edge.target_node not in self._nodes:
                raise UnknownRoadNodeError(edge.target_node)
            self._edges[(edge.source_node, edge.target_node)] = edge
            self._adjacency[edge.source_node].add(edge.target_node)

    def get_node(self, node_id: str) -> RoadNode | None:
        with self._lock:
            return self._nodes.get(node_id)

    def get_edge(self, source_node: str, target_node: str) -> RoadEdge | None:
        with self._lock:
            return self._edges.get((source_node, target_node))

    def neighbors(self, node_id: str) -> list[RoadNode]:
        with self._lock:
            target_ids = self._adjacency.get(node_id, set())
            return [self._nodes[target_id] for target_id in target_ids]

    def get_graph(self) -> RoadGraph:
        with self._lock:
            return RoadGraph(nodes=list(self._nodes.values()), edges=list(self._edges.values()))

    def get_bounds(self) -> BoundingBoxGeometry | None:
        with self._lock:
            if not self._nodes:
                return None
            latitudes = [node.latitude for node in self._nodes.values()]
            longitudes = [node.longitude for node in self._nodes.values()]
            return BoundingBoxGeometry(
                coordinates=(min(longitudes), min(latitudes), max(longitudes), max(latitudes))
            )

    def query_bounding_box(self, bbox: BoundingBoxGeometry) -> list[RoadNode]:
        min_lon, min_lat, max_lon, max_lat = bbox.coordinates
        with self._lock:
            return [
                node
                for node in self._nodes.values()
                if min_lon <= node.longitude <= max_lon and min_lat <= node.latitude <= max_lat
            ]
