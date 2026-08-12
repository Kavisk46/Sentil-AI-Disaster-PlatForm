"""Assembles routing results: analysis-existence + risk-context lookup
(`RoadRiskService`, which itself already handles "analysis not completed"/
"no georeferenced damage"/"no road network") + nearest-node resolution
(`app.routing.nearest_node`) + shortest-path search
(`app.routing.algorithm`) — all over the **same** road graph Milestones
6A/6B already established.

    API route -> RoutingService (this file) -> app.routing (engine)
        -> RoadNetworkRepository -> RoadRiskService -> RouteResult

Kept as its own service, same reasoning as every other `*Service` split in
this codebase: DI-facing orchestration here, pure pathfinding math in
`app.routing`, testable independently of the HTTP layer or any repository.

`route()` calls `RoadRiskService.get_road_risk()` **unconditionally**, for
both modes — not just `risk_aware`. This is deliberate: whenever risk data
*is* available, `distance_only` routing still reports how risky its
(risk-blind) chosen path turned out to be (`RouteResult.accumulated_risk`),
which is exactly what the "shortest path is riskier" research scenario and
`compare_routes()` need. When risk data *isn't* available (the honest,
common state today — see `apps/api/README.md`), `distance_only` still
works, falling back to the road network's raw (non-risk-assessed) edges;
only `risk_aware` mode actually requires risk data to proceed.
"""

from uuid import UUID

from app.risk.config import RoadRiskConfig
from app.roads.schemas import GeographicCoordinate
from app.routing.algorithm import GraphView, haversine_heuristic, shortest_path
from app.routing.config import RoutingConfig
from app.routing.cost import build_edge_cost_fn
from app.routing.metrics import count_blocked_edges, count_risky_segments, high_risk_edges_avoided
from app.routing.metrics import detour_ratio as compute_detour_ratio
from app.routing.nearest_node import InMemoryNearestNodeLocator
from app.routing.result_builder import build_route_result
from app.routing.schemas import RouteComparison, RouteResult, RoutingMode
from app.schemas.routing import RoutingRequest
from app.services.road_network_repository import RoadNetworkRepository
from app.services.road_risk_service import RoadRiskService

_NO_ROAD_NETWORK_REASON = "No road network is loaded (see GET /api/v1/roads/status)."
_NO_NEARBY_NODE_REASON = (
    "No road network node was found within the configured snap distance of the "
    "requested start/destination coordinates."
)
_NO_PATH_REASON = (
    "No path exists between the start and destination nodes in the current road graph."
)


class RoutingService:
    def __init__(
        self,
        road_network_repository: RoadNetworkRepository,
        road_risk_service: RoadRiskService,
        routing_config: RoutingConfig,
        risk_config: RoadRiskConfig,
    ) -> None:
        self._road_network_repository = road_network_repository
        self._road_risk_service = road_risk_service
        self._routing_config = routing_config
        self._risk_config = risk_config

    def route(self, request: RoutingRequest) -> RouteResult:
        """Raises `AnalysisNotFoundError` (-> `404`) if `analysis_id` is
        unknown — the same contract as `RoadRiskService.get_road_risk`,
        which this calls first."""
        risk_response = self._road_risk_service.get_road_risk(request.analysis_id)

        graph = self._road_network_repository.get_graph()
        if not graph.nodes:
            return self._unavailable(request.mode, _NO_ROAD_NETWORK_REASON)

        locator = InMemoryNearestNodeLocator(
            graph.nodes, self._routing_config.max_snap_distance_meters
        )
        start_node = locator.find_nearest(request.start.latitude, request.start.longitude)
        destination_node = locator.find_nearest(
            request.destination.latitude, request.destination.longitude
        )
        if start_node is None or destination_node is None:
            return self._unavailable(request.mode, _NO_NEARBY_NODE_REASON)

        if risk_response.available:
            edges = risk_response.edges
        elif request.mode is RoutingMode.RISK_AWARE:
            return self._unavailable(
                request.mode, risk_response.reason, start_node.node_id, destination_node.node_id
            )
        else:
            edges = graph.edges

        view = GraphView(graph.nodes, edges)
        cost_fn = build_edge_cost_fn(request.mode, self._routing_config, self._risk_config)
        use_astar = self._routing_config.use_astar_heuristic
        heuristic = haversine_heuristic(destination_node) if use_astar else None
        path = shortest_path(view, start_node.node_id, destination_node.node_id, cost_fn, heuristic)

        if not path.found:
            return RouteResult(
                routing_mode=request.mode,
                found=False,
                start_node=start_node.node_id,
                destination_node=destination_node.node_id,
                reason=_NO_PATH_REASON,
            )

        nodes_by_id = {node.node_id: node for node in graph.nodes}
        return build_route_result(path, request.mode, nodes_by_id)

    def compare_routes(
        self, analysis_id: UUID, start: GeographicCoordinate, destination: GeographicCoordinate
    ) -> RouteComparison:
        """Runs both routing modes for the same start/destination/analysis
        and assembles a comparison — see `app.routing`, "Route
        comparison." Purely descriptive: nothing here feeds back into
        route selection.
        """
        distance_only = self.route(
            RoutingRequest(
                analysis_id=analysis_id,
                start=start,
                destination=destination,
                mode=RoutingMode.DISTANCE_ONLY,
            )
        )
        risk_aware = self.route(
            RoutingRequest(
                analysis_id=analysis_id,
                start=start,
                destination=destination,
                mode=RoutingMode.RISK_AWARE,
            )
        )

        distance_difference = None
        risk_difference = None
        ratio = None
        if distance_only.found and risk_aware.found:
            distance_difference = (risk_aware.total_distance or 0.0) - (
                distance_only.total_distance or 0.0
            )
            risk_difference = (risk_aware.accumulated_risk or 0.0) - (
                distance_only.accumulated_risk or 0.0
            )
            ratio = compute_detour_ratio(risk_aware.total_distance, distance_only.total_distance)

        graph = self._road_network_repository.get_graph()

        return RouteComparison(
            distance_only=distance_only,
            risk_aware=risk_aware,
            distance_difference=distance_difference,
            risk_difference=risk_difference,
            routes_differ=distance_only.node_sequence != risk_aware.node_sequence,
            detour_ratio=ratio,
            risky_segments_distance_only=count_risky_segments(distance_only),
            risky_segments_risk_aware=count_risky_segments(risk_aware),
            blocked_segments_in_graph=count_blocked_edges(graph.edges),
            high_risk_edges_avoided=high_risk_edges_avoided(distance_only, risk_aware),
        )

    @staticmethod
    def _unavailable(
        mode: RoutingMode,
        reason: str | None,
        start_node: str | None = None,
        destination_node: str | None = None,
    ) -> RouteResult:
        return RouteResult(
            routing_mode=mode,
            found=False,
            start_node=start_node,
            destination_node=destination_node,
            reason=reason,
        )
