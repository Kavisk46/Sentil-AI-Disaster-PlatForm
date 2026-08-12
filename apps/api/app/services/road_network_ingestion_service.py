"""Ingestion orchestration: OSM data acquisition
(`app.roads.osm_source.RoadNetworkSource`) -> graph construction
(`app.roads.builder.build_road_network`) -> `RoadNetworkRepository`.

This is the seam a future explicit command ("load road network for
bounding box" — a CLI command or an admin-only endpoint, neither
implemented this milestone) would call. Not wired into application
startup and not invoked by any route or by the test suite: no application
code downloads OSM data automatically, and nothing here fabricates road
data when a fetch fails — `RoadNetworkSourceError` (raised by the source)
simply propagates to whatever future caller invokes this.
"""

from app.roads.builder import build_road_network
from app.roads.osm_source import RoadNetworkSource
from app.services.road_network_repository import RoadNetworkRepository


class RoadNetworkIngestionService:
    def __init__(self, source: RoadNetworkSource, repository: RoadNetworkRepository) -> None:
        self._source = source
        self._repository = repository

    def load_for_bounding_box(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float
    ) -> None:
        """Fetch OSM road data for the given bounding box and add it to
        the repository. Raises `RoadNetworkSourceError` if the fetch
        fails — never silently leaves the repository unchanged while
        claiming success."""
        data = self._source.fetch_bounding_box(min_lat, min_lon, max_lat, max_lon)
        build_road_network(data, self._repository)
