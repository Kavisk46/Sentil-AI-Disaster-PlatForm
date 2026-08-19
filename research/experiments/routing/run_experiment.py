"""Orchestrates one scenario across a set of named ablation/baseline
configurations: builds a risk-assessed graph (reusing
`app.risk.analyzer.compute_road_risk` exactly as production does),
computes the naive damage-density map, runs
`app.routing.algorithm.shortest_path` with each configuration's cost
function, times it with `time.perf_counter()`, and returns one
`ExperimentResult` per configuration. Relative metrics
(`risk_reduction_percent`/`distance_overhead_percent`) are always
computed against the same scenario's designated baseline result — never
a different graph or scenario.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.schemas import BuildingDamage
from app.risk.analyzer import compute_road_risk
from app.risk.config import RoadRiskConfig
from app.risk.spatial import representative_point
from app.routing.algorithm import GraphView, shortest_path
from app.routing.config import RoutingConfig

from research.core.metrics import distance_overhead_percent, risk_reduction_percent
from research.core.reproducibility import build_reproducibility_metadata
from research.core.schemas import ExperimentResult
from research.experiments.routing.ablation import AblationFlags
from research.experiments.routing.cost_functions import (
    build_research_edge_cost_fn,
    naive_damage_density_by_edge,
)
from research.experiments.routing.fixtures import RoutingScenario

FindNearby = Callable[[BoundingBoxGeometry], list[BuildingDamage]]


def _find_nearby_within(buildings: Sequence[BuildingDamage]) -> FindNearby:
    def find(bbox: BoundingBoxGeometry) -> list[BuildingDamage]:
        min_lon, min_lat, max_lon, max_lat = bbox.coordinates
        found = []
        for building in buildings:
            if building.geometry is None:
                continue
            lon, lat = representative_point(building.geometry)
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                found.append(building)
        return found

    return find


@dataclass(frozen=True, slots=True)
class RawRouteMeasurement:
    distance_km: float
    route_risk: float
    runtime_ms: float
    found: bool


def measure_configuration(
    scenario: RoutingScenario,
    flags: AblationFlags,
    routing_config: RoutingConfig,
    risk_config: RoadRiskConfig,
) -> RawRouteMeasurement:
    nodes_by_id = {node.node_id: node for node in scenario.nodes}
    risk_assessed_edges = compute_road_risk(
        scenario.edges, nodes_by_id, _find_nearby_within(scenario.buildings), risk_config
    )
    damage_density = naive_damage_density_by_edge(
        scenario.edges, nodes_by_id, scenario.buildings, risk_config
    )
    cost_fn = build_research_edge_cost_fn(flags, routing_config, risk_config, damage_density)

    view = GraphView(scenario.nodes, risk_assessed_edges)
    start = time.perf_counter()
    path = shortest_path(view, scenario.origin_node_id, scenario.destination_node_id, cost_fn)
    runtime_ms = (time.perf_counter() - start) * 1000.0

    if not path.found:
        return RawRouteMeasurement(
            distance_km=0.0, route_risk=0.0, runtime_ms=runtime_ms, found=False
        )

    distance_m = sum(edge.distance for edge in path.edge_sequence)
    route_risk = sum(edge.risk_score or 0.0 for edge in path.edge_sequence)
    return RawRouteMeasurement(
        distance_km=distance_m / 1000.0, route_risk=route_risk, runtime_ms=runtime_ms, found=True
    )


def run_scenario(
    scenario: RoutingScenario,
    configurations: Mapping[str, AblationFlags],
    routing_config: RoutingConfig,
    risk_config: RoadRiskConfig,
    *,
    baseline_name: str = "shortest_path",
    dataset_version: str = "research-fixture-v1",
    model_version: str = "n/a (synthetic fixture — no ML model involved)",
    random_seed: int | None = None,
) -> list[ExperimentResult]:
    """Runs every configuration in `configurations` against `scenario`,
    computing risk-reduction/distance-overhead relative to
    `configurations[baseline_name]`'s own measured result for this same
    scenario/graph."""
    if baseline_name not in configurations:
        raise ValueError(f"baseline_name {baseline_name!r} must be a key of configurations.")

    measurements = {
        name: measure_configuration(scenario, flags, routing_config, risk_config)
        for name, flags in configurations.items()
    }
    baseline = measurements[baseline_name]

    routing_configuration_dict = {
        "restricted_accessibility_penalty": routing_config.restricted_accessibility_penalty,
        "unknown_accessibility_policy": routing_config.unknown_accessibility_policy.value,
        "max_snap_distance_meters": routing_config.max_snap_distance_meters,
        "use_astar_heuristic": routing_config.use_astar_heuristic,
    }
    risk_configuration_dict = {
        "search_radius_meters": risk_config.search_radius_meters,
        "distance_decay_rate": risk_config.distance_decay_rate,
        "aggregation_cap": risk_config.aggregation_cap,
        "cost_penalty_scale": risk_config.cost_penalty_scale,
    }

    results: list[ExperimentResult] = []
    for name, measurement in measurements.items():
        reduction = None
        overhead = None
        if measurement.found and baseline.found:
            reduction = risk_reduction_percent(baseline.route_risk, measurement.route_risk)
            if baseline.distance_km > 0:
                overhead = distance_overhead_percent(baseline.distance_km, measurement.distance_km)

        reproducibility = build_reproducibility_metadata(
            scenario_id=scenario.scenario_id,
            dataset_version=dataset_version,
            model_version=model_version,
            routing_configuration=routing_configuration_dict,
            risk_configuration=risk_configuration_dict,
            random_seed=random_seed,
        )
        results.append(
            ExperimentResult(
                experiment_id=reproducibility.experiment_id,
                scenario_id=scenario.scenario_id,
                configuration=name,
                distance_km=measurement.distance_km,
                route_risk=measurement.route_risk,
                risk_reduction_percent=reduction,
                distance_overhead_percent=overhead,
                runtime_ms=measurement.runtime_ms,
                found=measurement.found,
                reproducibility=reproducibility,
            )
        )
    return results
