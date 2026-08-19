import pytest
from app.ml.schemas import DamageClass
from app.risk.config import RoadRiskConfig
from app.routing.accessibility import Traversability
from app.routing.config import RoutingConfig

from research.experiments.routing.ablation import NAMED_CONFIGURATIONS
from research.experiments.routing.fixtures import (
    RoutingScenario,
    diamond_detour_scenario,
    no_damage_scenario,
    unreachable_destination_scenario,
)
from research.experiments.routing.run_experiment import (
    RawRouteMeasurement,
    measure_configuration,
    run_scenario,
)


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


def _measure(
    scenario: RoutingScenario,
    name: str,
    routing_config: RoutingConfig,
    risk_config: RoadRiskConfig,
) -> RawRouteMeasurement:
    return measure_configuration(scenario, NAMED_CONFIGURATIONS[name], routing_config, risk_config)


def test_shortest_path_takes_the_shorter_direct_route_past_the_damage() -> None:
    scenario = diamond_detour_scenario()
    routing_config, risk_config = _routing_config(), _risk_config()

    shortest = _measure(scenario, "shortest_path", routing_config, risk_config)
    risk_aware = _measure(scenario, "risk_aware", routing_config, risk_config)

    assert shortest.found
    # The direct route (A-B-D, past the damage) is shorter than the detour
    # (A-C-D) by construction — shortest_path must pick it despite the risk.
    assert shortest.distance_km < risk_aware.distance_km
    assert shortest.route_risk > 0.0  # it really does pass next to detected damage


def test_risk_aware_reroutes_around_the_damage_at_a_real_distance_cost() -> None:
    scenario = diamond_detour_scenario()
    routing_config, risk_config = _routing_config(), _risk_config()

    shortest = _measure(scenario, "shortest_path", routing_config, risk_config)
    risk_aware = _measure(scenario, "risk_aware", routing_config, risk_config)

    assert shortest.found and risk_aware.found
    assert risk_aware.route_risk < shortest.route_risk  # avoided the damage
    assert risk_aware.distance_km > shortest.distance_km  # at a real distance cost


def test_run_scenario_computes_risk_reduction_and_overhead_from_real_measurements() -> None:
    scenario = diamond_detour_scenario()
    names = ("shortest_path", "risk_aware", "full_sentinelai")
    configurations = {name: NAMED_CONFIGURATIONS[name] for name in names}

    results = run_scenario(scenario, configurations, _routing_config(), _risk_config())
    by_configuration = {result.configuration: result for result in results}

    shortest = by_configuration["shortest_path"]
    risk_aware = by_configuration["risk_aware"]

    assert shortest.risk_reduction_percent == 0.0  # baseline vs. itself
    assert shortest.distance_overhead_percent == 0.0
    assert risk_aware.risk_reduction_percent is not None
    assert risk_aware.risk_reduction_percent > 0
    assert risk_aware.distance_overhead_percent is not None
    assert risk_aware.distance_overhead_percent > 0

    for result in results:
        assert result.reproducibility.scenario_id == scenario.scenario_id


def test_zero_baseline_risk_scenario_reports_none_not_a_crash_or_fabricated_percent() -> None:
    scenario = no_damage_scenario()
    configurations = {name: NAMED_CONFIGURATIONS[name] for name in ("shortest_path", "risk_aware")}

    results = run_scenario(scenario, configurations, _routing_config(), _risk_config())

    for result in results:
        assert result.route_risk == 0.0
        assert result.risk_reduction_percent is None


def test_unreachable_destination_reports_not_found_for_every_configuration() -> None:
    scenario = unreachable_destination_scenario()
    configurations = {name: NAMED_CONFIGURATIONS[name] for name in ("shortest_path", "risk_aware")}

    results = run_scenario(scenario, configurations, _routing_config(), _risk_config())

    for result in results:
        assert result.found is False
        assert result.risk_reduction_percent is None
        assert result.distance_overhead_percent is None


def test_run_scenario_rejects_an_unknown_baseline_name() -> None:
    scenario = diamond_detour_scenario()
    with pytest.raises(ValueError, match="baseline_name"):
        run_scenario(
            scenario,
            {"shortest_path": NAMED_CONFIGURATIONS["shortest_path"]},
            _routing_config(),
            _risk_config(),
            baseline_name="does_not_exist",
        )
