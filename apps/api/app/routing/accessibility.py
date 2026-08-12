"""Turns `AccessibilityStatus` into a routing decision — deliberately a
tiny, standalone module, since accessibility is explicitly a *different
concept* from risk (see `app.routing`, "Accessibility is not risk"):
`open`/`restricted`/`blocked` map directly and unconditionally; only
`unknown` (the state OSM ingestion always leaves every edge in) follows a
configurable policy. Nothing here ever looks at `RoadEdge.risk_score` or
`risk_level` — a `critical`-risk edge is resolved exactly the same way
regardless of how risky it is.
"""

from enum import StrEnum

from app.roads.schemas import AccessibilityStatus


class Traversability(StrEnum):
    """What routing should actually do with an edge, once `unknown` has
    been resolved by policy. Distinct from `AccessibilityStatus` itself:
    that's the edge's *recorded* state; this is the *routing decision*
    derived from it."""

    OPEN = "open"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


def resolve_accessibility(
    status: AccessibilityStatus, unknown_policy: Traversability
) -> Traversability:
    """`OPEN`/`RESTRICTED`/`BLOCKED` map directly; `UNKNOWN` resolves via
    `unknown_policy` (see `RoutingConfig.unknown_accessibility_policy`)."""
    if status is AccessibilityStatus.OPEN:
        return Traversability.OPEN
    if status is AccessibilityStatus.RESTRICTED:
        return Traversability.RESTRICTED
    if status is AccessibilityStatus.BLOCKED:
        return Traversability.BLOCKED
    return unknown_policy
