from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.schemas import BuildingDamage, DamageClass
from app.risk.analyzer import compute_road_risk
from app.risk.config import RoadRiskConfig
from app.risk.spatial import representative_point
from app.routing.accessibility import Traversability
from app.routing.config import RoutingConfig

from research.experiments.routing.ablation import (
    ABLATION_D_DAMAGE_AND_RISK,
    DAMAGE_AWARE,
    FULL_SENTINELAI,
    NAMED_CONFIGURATIONS,
    RISK_AWARE,
    SHORTEST_PATH,
    AblationFlags,
    load_ablation_config,
)
from research.experiments.routing.cost_functions import (
    build_research_edge_cost_fn,
    naive_damage_density_by_edge,
)
from research.experiments.routing.fixtures import diamond_detour_scenario

_CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


def _risk_config() -> RoadRiskConfig:
    return RoadRiskConfig(
        severity_weights={
            DamageClass.NO_DAMAGE: 0.0,
            DamageClass.MINOR: 0.25,
            DamageClass.MAJOR: 0.6,
            DamageClass.DESTROYED: 1.0,
        },
        search_radius_meters=150.0,
        distance_decay_rate=0.02,
        aggregation_cap=1.0,
        risk_level_low_max=0.25,
        risk_level_moderate_max=0.5,
        risk_level_high_max=0.75,
        cost_penalty_scale=4.0,
    )


def _routing_config() -> RoutingConfig:
    return RoutingConfig(
        restricted_accessibility_penalty=0.5,
        unknown_accessibility_policy=Traversability.OPEN,
        max_snap_distance_meters=500.0,
        use_astar_heuristic=False,
    )


def _find_nearby_within(
    buildings: Sequence[BuildingDamage],
) -> Callable[[BoundingBoxGeometry], list[BuildingDamage]]:
    def find(bbox: BoundingBoxGeometry) -> list[BuildingDamage]:
        result = []
        for building in buildings:
            assert building.geometry is not None
            lon, lat = representative_point(building.geometry)
            min_lon, min_lat, max_lon, max_lat = bbox.coordinates
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                result.append(building)
        return result

    return find


def test_named_configurations_cover_every_baseline_and_ablation_name() -> None:
    expected = {
        "shortest_path", "damage_aware", "risk_aware", "full_sentinelai",
        "ablation_a_none", "ablation_b_damage_only", "ablation_c_road_risk_only",
        "ablation_d_damage_and_risk", "ablation_e_full_with_hazard",
    }
    assert set(NAMED_CONFIGURATIONS.keys()) == expected


def test_baselines_match_the_milestones_own_definitions() -> None:
    assert SHORTEST_PATH.use_damage is False and SHORTEST_PATH.use_road_risk is False
    assert DAMAGE_AWARE.use_damage is True and DAMAGE_AWARE.use_road_risk is False
    assert RISK_AWARE.use_damage is False and RISK_AWARE.use_road_risk is True
    assert (
        FULL_SENTINELAI.use_damage
        and FULL_SENTINELAI.use_road_risk
        and FULL_SENTINELAI.use_hazard
    )


def test_hazard_flag_is_the_only_difference_between_d_and_full_sentinelai() -> None:
    assert ABLATION_D_DAMAGE_AND_RISK.use_damage == FULL_SENTINELAI.use_damage
    assert ABLATION_D_DAMAGE_AND_RISK.use_road_risk == FULL_SENTINELAI.use_road_risk
    assert ABLATION_D_DAMAGE_AND_RISK.use_hazard != FULL_SENTINELAI.use_hazard


@pytest.mark.parametrize(
    "filename,expected_name",
    [
        ("shortest_path.json", "shortest_path"),
        ("damage_aware.json", "damage_aware"),
        ("risk_aware.json", "risk_aware"),
        ("full_sentinelai.json", "full_sentinelai"),
        ("ablation_a_none.json", "ablation_a_none"),
        ("ablation_b_damage_only.json", "ablation_b_damage_only"),
        ("ablation_c_road_risk_only.json", "ablation_c_road_risk_only"),
        ("ablation_d_damage_and_risk.json", "ablation_d_damage_and_risk"),
        ("ablation_e_full_with_hazard.json", "ablation_e_full_with_hazard"),
    ],
)
def test_every_config_file_loads_and_matches_named_configurations(
    filename: str, expected_name: str
) -> None:
    name, flags = load_ablation_config(_CONFIGS_DIR / filename)
    assert name == expected_name
    assert flags == NAMED_CONFIGURATIONS[expected_name]


def test_damage_aware_and_risk_aware_are_genuinely_different_cost_signals() -> None:
    """The core scientific-honesty claim of this ablation design: 'damage
    penalty' and 'road risk penalty' must not silently be the same
    number under a different name."""
    scenario = diamond_detour_scenario()
    risk_config = _risk_config()
    routing_config = _routing_config()
    nodes_by_id = {node.node_id: node for node in scenario.nodes}

    risk_assessed_edges = compute_road_risk(
        scenario.edges, nodes_by_id, _find_nearby_within(scenario.buildings), risk_config
    )
    damage_density = naive_damage_density_by_edge(
        scenario.edges, nodes_by_id, scenario.buildings, risk_config
    )

    risky_edge = next(
        edge for edge in risk_assessed_edges if edge.source_node == "A" and edge.target_node == "B"
    )

    damage_cost_fn = build_research_edge_cost_fn(
        DAMAGE_AWARE, routing_config, risk_config, damage_density
    )
    risk_cost_fn = build_research_edge_cost_fn(
        RISK_AWARE, routing_config, risk_config, damage_density
    )

    damage_cost = damage_cost_fn(risky_edge)
    risk_cost = risk_cost_fn(risky_edge)

    assert damage_cost is not None and risk_cost is not None
    assert damage_cost != pytest.approx(risk_cost)


def test_hazard_flag_never_changes_cost() -> None:
    """`use_hazard` must be a documented no-op today — SentinelAI has no
    hazard subsystem to feed a cost term from."""
    scenario = diamond_detour_scenario()
    risk_config = _risk_config()
    routing_config = _routing_config()
    nodes_by_id = {node.node_id: node for node in scenario.nodes}

    risk_assessed_edges = compute_road_risk(
        scenario.edges, nodes_by_id, _find_nearby_within(scenario.buildings), risk_config
    )
    damage_density = naive_damage_density_by_edge(
        scenario.edges, nodes_by_id, scenario.buildings, risk_config
    )
    edge = risk_assessed_edges[0]

    with_hazard = build_research_edge_cost_fn(
        AblationFlags(use_damage=True, use_road_risk=True, use_hazard=True),
        routing_config, risk_config, damage_density,
    )
    without_hazard = build_research_edge_cost_fn(
        AblationFlags(use_damage=True, use_road_risk=True, use_hazard=False),
        routing_config, risk_config, damage_density,
    )

    assert with_hazard(edge) == without_hazard(edge)
