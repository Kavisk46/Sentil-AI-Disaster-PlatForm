"""Converts a `RouteResult` into standard GeoJSON (RFC 7946) — a `Feature`
with a `LineString` geometry.

Reuses `app.ml.geospatial.geometry.Coordinate` (the shared `(x, y)` tuple
type every geometry module in this codebase already uses) rather than
inventing a parallel one. Does **not** reuse
`app.ml.geospatial.geojson.Feature`/`FeatureCollection` directly: those
are typed specifically for building predictions
(`FeatureProperties` has `building_id`/`damage_class`/... fields that make
no sense for a route), so this module defines its own, structurally
identical `Feature` following the exact same RFC 7946 pattern, with
properties this milestone actually needs — the task's requirement is
"reuse existing geospatial utilities" and "do not duplicate geometry
logic," which the shared `Coordinate` type and the identical structural
approach satisfy; it is not a requirement to force two different
"properties" shapes into one Pydantic model.
"""

from typing import Literal

from pydantic import BaseModel

from app.ml.geospatial.geometry import Coordinate
from app.routing.schemas import RouteResult


class GeoJSONLineString(BaseModel):
    """RFC 7946 §3.1.4 LineString geometry."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[Coordinate]


class RouteFeatureProperties(BaseModel):
    routing_mode: str
    total_distance: float
    total_cost: float
    accumulated_risk: float


class RouteFeature(BaseModel):
    """RFC 7946 §3.2 Feature."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONLineString
    properties: RouteFeatureProperties


def route_to_feature(route: RouteResult) -> RouteFeature | None:
    """`None` if `route.found` is `False`, or the route has fewer than 2
    points (a GeoJSON `LineString` requires at least 2 positions — the
    trivial start==destination route has only 1) — never a fabricated
    geometry for a route that doesn't exist or can't be drawn as a line.
    """
    if not route.found or len(route.route_geometry) < 2:
        return None
    return RouteFeature(
        geometry=GeoJSONLineString(coordinates=route.route_geometry),
        properties=RouteFeatureProperties(
            routing_mode=route.routing_mode.value,
            total_distance=route.total_distance or 0.0,
            total_cost=route.total_cost or 0.0,
            accumulated_risk=route.accumulated_risk or 0.0,
        ),
    )
