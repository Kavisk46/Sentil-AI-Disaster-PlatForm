"""Maps an arbitrary `(latitude, longitude)` to the nearest graph node —
"do not assume the provided coordinate exactly matches a graph node."

Distance uses `app.roads.geo_utils.haversine_distance_meters` (the same
real, standard geodesic calculation the rest of this codebase already
uses) — never a raw lat/lon degree comparison. **Never fabricates a
match:** if the nearest node is farther than `max_distance_meters`, or
there are no nodes at all, `find_nearest()` returns `None` rather than
snapping to an implausibly distant node.
"""

import math
from collections.abc import Sequence
from typing import Protocol

from app.roads.geo_utils import haversine_distance_meters
from app.roads.schemas import RoadNode


class NearestNodeLocator(Protocol):
    def find_nearest(self, latitude: float, longitude: float) -> RoadNode | None: ...


class InMemoryNearestNodeLocator:
    """Linear scan over every candidate node — O(n) per lookup, acceptable
    at prototype scale (the same tradeoff `app.risk`'s bounding-box
    pre-filter already documents). A future KD-tree or PostGIS-backed
    implementation (`<->` nearest-neighbor operator) would satisfy the
    same `NearestNodeLocator` Protocol without any caller changing.
    """

    def __init__(self, nodes: Sequence[RoadNode], max_distance_meters: float) -> None:
        self._nodes = list(nodes)
        self._max_distance_meters = max_distance_meters

    def find_nearest(self, latitude: float, longitude: float) -> RoadNode | None:
        best_node: RoadNode | None = None
        best_distance = math.inf
        for node in self._nodes:
            distance = haversine_distance_meters(latitude, longitude, node.latitude, node.longitude)
            if distance < best_distance:
                best_distance = distance
                best_node = node

        if best_node is None or best_distance > self._max_distance_meters:
            return None
        return best_node
