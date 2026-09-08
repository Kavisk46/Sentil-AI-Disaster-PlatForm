"""The **deterministic capability matcher**.

Given a target (a `SearchZone`, or any geometry + required-capability set)
and a list of candidate `Resource`s, ranks them by four independently
answered questions — deliberately kept separate rather than blended into
one opaque score, per the F2 brief:

1. **Can this resource perform the task?** — exact `ResourceCapability`
   set comparison (`app.intelligence.schemas.ResourceCapability` is a
   closed vocabulary specifically so this is exact, not fuzzy).
2. **Can it reach the target?** — great-circle distance
   (`app.roads.geo_utils.haversine_distance_meters`, reused directly, no
   second distance formula), computed **only** when both the resource's
   location and the target's geometry are explicitly tagged
   `CoordinateReferenceSystem.WGS84`. If either is untagged/image-space,
   reachability is `UNKNOWN` — never guessed from raw numbers that might
   be pixels (project constraint: never treat image-space coordinates as
   geographic).
3. **Is the route operational?** — F2 does not integrate full
   route/road-risk computation per candidate (that would require a real
   `Route` for every resource-target pair, out of scope for this
   milestone's deterministic-baseline goal). Instead this is assessed
   from the resource's own `operational_constraints`: any
   `blocking=True` constraint marks the route as known-not-operational.
   This is a documented simplification, not a claim of full route
   verification — a real implementation would additionally query
   `app.routing`/`app.risk` for hazard-aware path feasibility.
4. **Is the resource currently available?** — `Resource.availability ==
   AVAILABLE`, nothing else.

**Nearest resource != necessarily best resource**: `rank_candidates()`
sorts *eligible* candidates (all four gates passed) ahead of ineligible
ones, and only uses distance as a final tiebreak among otherwise-equal
candidates — a capability mismatch or unavailability always outranks
proximity, by construction.
"""

from uuid import UUID

from app.intelligence.config import CapabilityMatchingConfig
from app.intelligence.schemas import (
    CapabilityMatchResult,
    ReachabilityStatus,
    Resource,
    ResourceAvailability,
    ResourceCapability,
)
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import Geometry
from app.risk.spatial import representative_point
from app.roads.geo_utils import haversine_distance_meters

# Fixed, documented tie-break weights for `match_score` — not sourced from
# `CapabilityMatchingConfig` because they only ever rank candidates that
# have *already* passed the four hard gates above; unlike
# `SearchPriorityConfig`'s weights, mistuning them cannot cause an
# inappropriate assignment (capability/availability/reachability/route
# gates already prevent that), only a different tie-break order among
# otherwise-equivalent candidates.
_CAN_PERFORM_SCORE = 0.4
_AVAILABLE_SCORE = 0.3
_REACHABLE_SCORE = 0.2
_REACHABILITY_UNKNOWN_SCORE = 0.1
_ROUTE_OPERATIONAL_SCORE = 0.1
_ROUTE_UNKNOWN_SCORE = 0.05


def _reachability(
    resource: Resource,
    target_geometry: Geometry,
    target_geometry_crs: CoordinateReferenceSystem,
    config: CapabilityMatchingConfig,
) -> tuple[ReachabilityStatus, float | None]:
    if resource.location is None or resource.location_crs != CoordinateReferenceSystem.WGS84:
        return ReachabilityStatus.UNKNOWN, None
    if target_geometry_crs != CoordinateReferenceSystem.WGS84:
        return ReachabilityStatus.UNKNOWN, None

    resource_lon, resource_lat = representative_point(resource.location)
    target_lon, target_lat = representative_point(target_geometry)
    distance = haversine_distance_meters(resource_lat, resource_lon, target_lat, target_lon)

    if distance <= config.max_reachable_distance_meters:
        return ReachabilityStatus.REACHABLE, distance
    return ReachabilityStatus.UNREACHABLE, distance


def _route_operational(resource: Resource) -> bool | None:
    """`False` if any known constraint blocks deployment; `None` (not
    `True`) otherwise — the absence of a *known* blocker is not the same
    as a *verified* operational route (see module docstring, point 3)."""
    if any(constraint.blocking for constraint in resource.operational_constraints):
        return False
    return None


def _match_score(
    can_perform: bool,
    is_available: bool,
    reachability: ReachabilityStatus,
    route_operational: bool | None,
) -> float:
    score = 0.0
    if can_perform:
        score += _CAN_PERFORM_SCORE
    if is_available:
        score += _AVAILABLE_SCORE
    if reachability == ReachabilityStatus.REACHABLE:
        score += _REACHABLE_SCORE
    elif reachability == ReachabilityStatus.UNKNOWN:
        score += _REACHABILITY_UNKNOWN_SCORE
    if route_operational is True:
        score += _ROUTE_OPERATIONAL_SCORE
    elif route_operational is None:
        score += _ROUTE_UNKNOWN_SCORE
    return round(score, 4)


def assess_resource(
    resource: Resource,
    required_capabilities: list[ResourceCapability],
    target_geometry: Geometry,
    target_geometry_crs: CoordinateReferenceSystem,
    config: CapabilityMatchingConfig,
) -> CapabilityMatchResult:
    """Assess one resource against one target. Pure function — no I/O,
    fully deterministic."""
    missing_capabilities = [c for c in required_capabilities if c not in resource.capabilities]
    can_perform = not missing_capabilities
    is_available = resource.availability == ResourceAvailability.AVAILABLE

    reachability, distance = _reachability(resource, target_geometry, target_geometry_crs, config)
    route_operational = _route_operational(resource)

    eligible = (
        can_perform
        and is_available
        and reachability != ReachabilityStatus.UNREACHABLE
        and route_operational is not False
    )

    missing_note = ""
    if missing_capabilities:
        missing_note = f" (missing: {', '.join(c.value for c in missing_capabilities)})"
    rationale = []
    rationale.append(f"Capability match: {'yes' if can_perform else 'no'}{missing_note}.")
    rationale.append(f"Availability: {resource.availability.value}.")
    if reachability == ReachabilityStatus.UNKNOWN:
        rationale.append(
            "Reachability unknown: resource or target location is not a tagged "
            "geographic coordinate."
        )
    elif distance is not None:
        rationale.append(f"Distance to target: {distance:.0f}m ({reachability.value}).")
    if route_operational is False:
        rationale.append("Route not operational: a known blocking constraint exists.")

    return CapabilityMatchResult(
        resource_id=resource.id,
        can_perform_task=can_perform,
        missing_capabilities=missing_capabilities,
        is_available=is_available,
        distance_meters=distance,
        reachability=reachability,
        route_operational=route_operational,
        eligible=eligible,
        match_score=_match_score(can_perform, is_available, reachability, route_operational),
        rationale=rationale,
        is_simulated=resource.is_simulated,
    )


def rank_candidates(
    required_capabilities: list[ResourceCapability],
    target_geometry: Geometry,
    target_geometry_crs: CoordinateReferenceSystem,
    resources: list[Resource],
    config: CapabilityMatchingConfig,
) -> list[CapabilityMatchResult]:
    """Rank every candidate resource against one target. Eligible
    candidates (all four gates passed) always sort ahead of ineligible
    ones; within each group, higher `match_score` first, then lower
    `distance_meters` (unknown-distance candidates last) as the final
    tiebreak — proximity only ever breaks ties among otherwise-equivalent
    candidates, never overrides a capability/availability/route gate."""
    results = [
        assess_resource(
            resource, required_capabilities, target_geometry, target_geometry_crs, config
        )
        for resource in resources
    ]

    def sort_key(result: CapabilityMatchResult) -> tuple[bool, float, float, str]:
        distance_key = (
            result.distance_meters if result.distance_meters is not None else float("inf")
        )
        return (not result.eligible, -result.match_score, distance_key, str(result.resource_id))

    return sorted(results, key=sort_key)


def resource_id_map(resources: list[Resource]) -> dict[UUID, Resource]:
    """Small helper: id -> Resource, for callers that need to look up the
    full record behind a `CapabilityMatchResult.resource_id`."""
    return {resource.id: resource for resource in resources}
