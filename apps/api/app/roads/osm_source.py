"""OSM data **acquisition** — fetching raw OpenStreetMap road data for a
bounding box, via the Overpass API: the official, appropriate mechanism for
extracting a bounded subset of OSM data (not scraping — see
https://wiki.openstreetmap.org/wiki/Overpass_API). Deliberately separate
from graph construction (`app.roads.builder`) and from routing (not
implemented this milestone, see `app.roads`): this module only fetches and
parses raw OSM JSON into typed `OSMNode`/`OSMWay` structures — it has no
notion of a directed graph, edges, or cost.

`parse_overpass_response()` is a pure function with no network access —
this is what the test suite exercises directly, against a small static
fixture shaped exactly like a real Overpass API response, so the entire
test suite never depends on live internet access.
`OverpassRoadNetworkSource.fetch_bounding_box()` is the only thing that
actually makes a network call, and nothing in this milestone calls it
automatically (no application startup, no test) — see
`app.services.road_network_ingestion_service` for the seam a future
explicit command ("load road network for bounding box") would use.
"""

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from app.roads.errors import RoadNetworkSourceError

_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"


@dataclass(frozen=True, slots=True)
class OSMNode:
    """One raw OSM node, before it becomes a `RoadNode` (see
    `app.roads.builder`)."""

    osm_id: int
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class OSMWay:
    """One raw OSM way — an ordered sequence of node ids plus its raw
    tags. `tags` is passed through completely unmodified; interpreting
    which tags mean what is `app.roads.builder`'s job, not this module's.
    """

    osm_id: int
    node_ids: list[int]
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OSMRoadData:
    """Raw OSM road data for one bounding-box fetch — nodes keyed by OSM
    id (a way's `node_ids` reference into this), plus every `highway` way
    found."""

    nodes: dict[int, OSMNode]
    ways: list[OSMWay]


class RoadNetworkSource(Protocol):
    def fetch_bounding_box(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float
    ) -> OSMRoadData:
        """Fetch raw OSM road data for a geographic bounding box.

        Raises `RoadNetworkSourceError` on failure — never returns
        fabricated data.
        """
        ...


def _build_overpass_query(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> str:
    """An Overpass QL query for every `highway` way (plus the nodes it
    references) inside the bounding box. `(._;>;)` is Overpass QL's
    standard idiom for "also fetch every node referenced by the ways just
    matched" — without it, way geometry would be unresolvable.
    """
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f"[out:json];way[highway]({bbox});(._;>;);out body;"


def parse_overpass_response(payload: dict[str, object]) -> OSMRoadData:
    """Parses a raw Overpass API JSON response — the same shape whether it
    came from a live call or a static test fixture — into `OSMRoadData`.
    Pure function, no network access.

    Unrecognized element types are ignored rather than raising: an
    Overpass response can legitimately contain element types this module
    doesn't need (e.g. `relation`); only `node`/`way` elements are used.
    """
    nodes: dict[int, OSMNode] = {}
    ways: list[OSMWay] = []

    elements = payload.get("elements", [])
    if not isinstance(elements, list):
        raise RoadNetworkSourceError("Malformed Overpass response: 'elements' is not a list.")

    for element in elements:
        element_type = element.get("type")
        if element_type == "node":
            nodes[element["id"]] = OSMNode(
                osm_id=element["id"], latitude=element["lat"], longitude=element["lon"]
            )
        elif element_type == "way":
            ways.append(
                OSMWay(
                    osm_id=element["id"],
                    node_ids=list(element.get("nodes", [])),
                    tags=dict(element.get("tags", {})),
                )
            )

    return OSMRoadData(nodes=nodes, ways=ways)


class OverpassRoadNetworkSource:
    """The only real `RoadNetworkSource` implementation: queries the
    public Overpass API for `highway` ways within a bounding box.

    Never invoked by the application at startup, by any route, or by the
    test suite — only via an explicit future ingestion command (see
    `app.services.road_network_ingestion_service.RoadNetworkIngestionService`).
    Uses `urllib.request` (standard library) rather than adding a new HTTP
    client dependency for one call site.
    """

    def __init__(self, endpoint: str = _OVERPASS_ENDPOINT, timeout_seconds: float = 30.0) -> None:
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def fetch_bounding_box(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float
    ) -> OSMRoadData:
        query = _build_overpass_query(min_lat, min_lon, max_lat, max_lon)
        request = urllib.request.Request(
            self._endpoint,
            data=f"data={query}".encode(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read())
        except (OSError, ValueError) as exc:
            raise RoadNetworkSourceError(
                f"Failed to fetch OSM data from Overpass API at {self._endpoint!r}: {exc}"
            ) from exc
        return parse_overpass_response(payload)
