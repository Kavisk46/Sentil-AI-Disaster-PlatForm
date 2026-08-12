"""The base-travel-cost extension seam.

    weight (future) = distance + damage_risk + hazard_risk + blockage_penalty

Milestone 6A only implements the first term. `compute_base_cost()` is
deliberately a single, tiny, tested function — every edge-construction
call site (`app.roads.builder`, test fixtures) calls it explicitly rather
than a model validator computing it implicitly, so it's obvious exactly
where "distance becomes cost" happens and easy to extend in a later
milestone (risk-aware routing) without touching `RoadEdge` itself.
"""


def compute_base_cost(distance: float) -> float:
    """Today: exactly `distance`. No damage risk, hazard risk, or
    blockage penalty is applied — see `app.roads` (package docstring) for
    the future formula this is the seam for."""
    return distance
