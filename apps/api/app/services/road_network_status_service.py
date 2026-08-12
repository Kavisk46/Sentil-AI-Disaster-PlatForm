"""Assembles `GET /api/v1/roads/status`'s response from
`RoadNetworkRepository` — read-only, no ingestion, no routing. Kept as its
own tiny service (rather than inline in the route) for the same reason
`DamageMapService` is separate from its route: independently testable
without the HTTP layer.
"""

from app.schemas.roads import RoadNetworkStatusResponse
from app.services.road_network_repository import RoadNetworkRepository

_UNAVAILABLE_MESSAGE = "Road network unavailable: no road data has been loaded for any region yet."


class RoadNetworkStatusService:
    def __init__(self, repository: RoadNetworkRepository) -> None:
        self._repository = repository

    def get_status(self) -> RoadNetworkStatusResponse:
        graph = self._repository.get_graph()
        loaded = len(graph.nodes) > 0
        return RoadNetworkStatusResponse(
            loaded=loaded,
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            bounds=self._repository.get_bounds() if loaded else None,
            message=None if loaded else _UNAVAILABLE_MESSAGE,
        )
