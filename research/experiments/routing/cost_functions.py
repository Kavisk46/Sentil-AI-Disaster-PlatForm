"""Research-only edge-cost functions for the ablation study.

Reuses `app.risk`/`app.routing` primitives directly wherever production
code already computes the thing this evaluation needs — the calibrated
risk-adjusted cost (`app.risk.formula.compute_risk_adjusted_cost`) and
accessibility resolution (`app.routing.accessibility.resolve_accessibility`)
are used **unmodified**, not re-implemented.

The one new primitive this module adds, `naive_damage_density_by_edge()`,
exists because SentinelAI's real `RoadEdge.risk_score` is *already*
computed entirely from proximity to detected damage (severity-weighted,
distance-decayed, confidence-scaled — see `app.risk.formula`) — there is
no second, independent "damage" signal at the road-edge level to reuse
for a genuinely distinct "damage-aware" baseline. This function is a
deliberately **naive** (unweighted, undecayed) damage-proximity count,
so "damage-aware" (B) and "road-risk-aware" (C) measure two different
things in this evaluation: a crude "is there any damage nearby" signal
versus SentinelAI's actual calibrated model. It is research-only code —
never imported by `apps/api/app`, and it changes no product behavior.
"""

from collections.abc import Mapping, Sequence

from app.ml.schemas import BuildingDamage, DamageClass
from app.risk.config import RoadRiskConfig
from app.risk.formula import compute_risk_adjusted_cost
from app.risk.spatial import (
    padded_bounding_box,
    point_to_segment_distance_meters,
    representative_point,
)
from app.roads.schemas import RoadEdge, RoadNode
from app.routing.accessibility import Traversability, resolve_accessibility
from app.routing.config import RoutingConfig
from app.routing.cost import EdgeCostFn

from research.experiments.routing.ablation import AblationFlags

EdgeKey = tuple[str, str]

_DAMAGE_DENSITY_NORMALIZER = 3.0
"""Number of nearby damaged buildings treated as "maximal" naive damage
density (capped at `1.0` beyond this) — an unconstrained modeling choice
for this evaluation only, in the same spirit as the constants in
`app.risk.formula`; not calibrated against real data."""


def naive_damage_density_by_edge(
    edges: Sequence[RoadEdge],
    nodes_by_id: Mapping[str, RoadNode],
    buildings: Sequence[BuildingDamage],
    config: RoadRiskConfig,
) -> dict[EdgeKey, float]:
    """An unweighted count of *any* damaged building
    (`damage_class != NO_DAMAGE`) within `config.search_radius_meters` of
    each edge, normalized to `[0, 1]`. Deliberately not severity-weighted,
    distance-decayed, or confidence-scaled — see the module docstring for
    why that's the point."""
    damaged = [
        building
        for building in buildings
        if building.damage_class is not DamageClass.NO_DAMAGE and building.geometry is not None
    ]

    density: dict[EdgeKey, float] = {}
    for edge in edges:
        source = nodes_by_id.get(edge.source_node)
        target = nodes_by_id.get(edge.target_node)
        key = (edge.source_node, edge.target_node)
        if source is None or target is None:
            density[key] = 0.0
            continue

        bbox = padded_bounding_box(source, target, config.search_radius_meters)
        min_lon, min_lat, max_lon, max_lat = bbox.coordinates

        count = 0
        for building in damaged:
            assert building.geometry is not None  # narrowed above
            point_lon, point_lat = representative_point(building.geometry)
            if not (min_lon <= point_lon <= max_lon and min_lat <= point_lat <= max_lat):
                continue
            distance = point_to_segment_distance_meters(
                point_lon,
                point_lat,
                source.longitude,
                source.latitude,
                target.longitude,
                target.latitude,
            )
            if distance <= config.search_radius_meters:
                count += 1

        density[key] = min(1.0, count / _DAMAGE_DENSITY_NORMALIZER)

    return density


def build_research_edge_cost_fn(
    flags: AblationFlags,
    routing_config: RoutingConfig,
    risk_config: RoadRiskConfig,
    damage_density_by_edge: Mapping[EdgeKey, float] | None = None,
    damage_penalty_scale: float = 1.0,
) -> EdgeCostFn:
    """Builds an edge-cost function reflecting exactly `flags`:

    - Always: `edge.base_cost` (real road distance, untouched).
    - `use_damage`: multiplied by
      `(1 + damage_penalty_scale * naive_damage_density)` — see
      `naive_damage_density_by_edge()`.
    - `use_road_risk`: run through
      `app.risk.formula.compute_risk_adjusted_cost` **unmodified** — the
      exact function `app.routing.cost.build_edge_cost_fn` already uses
      for `RoutingMode.RISK_AWARE`.
    - `use_hazard`: has **no effect**. SentinelAI has no hazard subsystem
      (see `research.experiments.hazards`); this flag exists so all five
      ablation configurations are representable today without inventing
      a hazard signal that doesn't exist.

    Accessibility is layered on top exactly as
    `app.routing.cost.build_edge_cost_fn` does, reusing
    `app.routing.accessibility.resolve_accessibility` directly.
    """
    density = damage_density_by_edge or {}

    def cost(edge: RoadEdge) -> float | None:
        traversability = resolve_accessibility(
            edge.accessibility, routing_config.unknown_accessibility_policy
        )
        if traversability is Traversability.BLOCKED:
            return None

        effective_cost = edge.base_cost

        if flags.use_damage:
            edge_density = density.get((edge.source_node, edge.target_node), 0.0)
            effective_cost *= 1 + damage_penalty_scale * edge_density

        if flags.use_road_risk:
            effective_cost = compute_risk_adjusted_cost(
                effective_cost, edge.risk_score, risk_config
            )

        # flags.use_hazard: intentionally inert — see the docstring above.

        if traversability is Traversability.RESTRICTED:
            effective_cost *= 1 + routing_config.restricted_accessibility_penalty

        return effective_cost

    return cost
