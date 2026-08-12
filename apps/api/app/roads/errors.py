"""Road-network domain errors.

Deliberately plain Python exceptions with no FastAPI/HTTP import (same
convention as `app.services.exceptions`) so the graph abstraction stays
testable without the HTTP layer. Coordinate/geometry validity itself
reuses `app.ml.geospatial.geometry.InvalidGeometryError` directly (see
`schemas.py`) rather than duplicating that validation logic — the errors
here cover what Milestone 5's geometry validation doesn't: road-specific
scalar attributes and graph referential integrity.
"""


class RoadNetworkError(Exception):
    """Base class for road-network domain errors."""


class InvalidRoadGraphError(RoadNetworkError, ValueError):
    """Raised for a road-specific attribute that fails validation (a
    non-positive edge distance, a non-positive lane count, ...).

    Subclasses `ValueError` so Pydantic's normal validation-error handling
    applies automatically wherever a `RoadNode`/`RoadEdge` is constructed
    from untrusted input.
    """


class UnknownRoadNodeError(RoadNetworkError):
    """Raised when an edge references a `node_id` the repository has never
    seen via `add_node()` — a graph referential-integrity check that can
    only happen at the repository (a `RoadEdge` alone has no way to know
    which node ids exist)."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f"Unknown road node id: {node_id!r}. Call add_node() first.")


class RoadNetworkSourceError(RuntimeError):
    """Raised when raw OSM road data cannot be fetched or parsed. Never
    caught and papered over with fabricated road data — see
    `app.roads.osm_source`."""
