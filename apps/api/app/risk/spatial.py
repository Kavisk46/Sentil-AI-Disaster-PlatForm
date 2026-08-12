"""Point-to-road-segment distance and the coarse spatial pre-filter for
road-risk analysis.

**Distance is never computed from raw latitude/longitude degrees.** A
degree of longitude spans a different physical distance depending on
latitude (shrinking to zero at the poles), so subtracting raw
lat/lon coordinates and treating the result as "distance" would silently
distort every measurement away from the equator. Instead,
`point_to_segment_distance_meters()` projects both the point and the road
segment into a local tangent-plane (equirectangular) approximation
centered on the query point, converting angular offsets into meters using
the same spherical-Earth model `app.roads.geo_utils`'s haversine distance
already uses (Milestone 6A) — consistent with that choice rather than
introducing a second, different Earth model. This is an appropriate,
standard simplification at the scale this analysis runs at (individual
road segments up to a few hundred meters, informed by
`RoadRiskConfig.search_radius_meters`); it is not a survey-grade geodesic
calculation and is not claimed to be one. Reprojecting into a real
projected CRS (e.g. UTM, via `pyproj`) is the natural upgrade path once
this needs to be accurate at larger scales or near the poles — deliberately
not added now, matching this codebase's established pattern of deferring
geodesy libraries (Milestone 5's `pyproj` deferral) until something
actually needs them.

`padded_bounding_box()` is the spatial-indexing seam: a coarse candidate
filter (a bounding box, reusing `app.ml.geospatial.geometry.BoundingBoxGeometry`
directly) that a caller uses to fetch only plausibly-nearby buildings
before running the exact (and more expensive) point-to-segment check —
see `app.risk.analyzer` for how this composes with
`SpatialRepository`-shaped lookups today, and how a future PostGIS-backed
implementation (`ST_DWithin` with a spatial index) would replace it
without `analyzer.py` changing.
"""

import math

from app.ml.geospatial.geometry import (
    BoundingBoxGeometry,
    Geometry,
    PointGeometry,
    PolygonGeometry,
)
from app.roads.schemas import RoadNode

_EARTH_RADIUS_METERS = 6_371_000.0
_METERS_PER_DEGREE_LATITUDE = 111_320.0
_MIN_LONGITUDE_SCALE = 1e-6  # guards the cos(latitude) divisor near the poles


def point_to_segment_distance_meters(
    point_lon: float,
    point_lat: float,
    segment_start_lon: float,
    segment_start_lat: float,
    segment_end_lon: float,
    segment_end_lat: float,
) -> float:
    """Distance in meters from `(point_lon, point_lat)` to the line
    segment `(segment_start -> segment_end)`, all WGS84 degrees.

    Projects everything into a local plane centered on the point itself
    (so the point is the origin, simplifying the projection), then does
    standard 2D point-to-segment distance in that plane.
    """
    start_x, start_y = _to_local_meters(point_lat, point_lon, segment_start_lat, segment_start_lon)
    end_x, end_y = _to_local_meters(point_lat, point_lon, segment_end_lat, segment_end_lon)

    segment_dx, segment_dy = end_x - start_x, end_y - start_y
    length_sq = segment_dx * segment_dx + segment_dy * segment_dy
    if length_sq == 0.0:
        # Degenerate segment (source and target coincide) — distance to
        # that single point.
        return math.hypot(start_x, start_y)

    # Project the origin (the point, at (0, 0)) onto the segment,
    # clamped to the segment itself (not the infinite line through it).
    t = (-start_x * segment_dx - start_y * segment_dy) / length_sq
    t = max(0.0, min(1.0, t))
    closest_x = start_x + t * segment_dx
    closest_y = start_y + t * segment_dy
    return math.hypot(closest_x, closest_y)


def _to_local_meters(
    lat_ref: float, lon_ref: float, lat: float, lon: float
) -> tuple[float, float]:
    """Local tangent-plane `(east, north)` meters of `(lat, lon)` relative
    to `(lat_ref, lon_ref)`."""
    x = math.radians(lon - lon_ref) * math.cos(math.radians(lat_ref)) * _EARTH_RADIUS_METERS
    y = math.radians(lat - lat_ref) * _EARTH_RADIUS_METERS
    return x, y


def padded_bounding_box(
    source: RoadNode, target: RoadNode, radius_meters: float
) -> BoundingBoxGeometry:
    """A `BoundingBoxGeometry` covering `source`/`target` padded by
    `radius_meters` in every direction — the coarse candidate filter
    `app.risk.analyzer.compute_road_risk` uses before the exact
    point-to-segment check. Padding converts meters to degrees using the
    same approximation as everywhere else in this module (not a second,
    inconsistent one)."""
    latitudes = (source.latitude, target.latitude)
    longitudes = (source.longitude, target.longitude)
    mid_latitude = sum(latitudes) / 2

    latitude_pad = radius_meters / _METERS_PER_DEGREE_LATITUDE
    longitude_scale = max(math.cos(math.radians(mid_latitude)), _MIN_LONGITUDE_SCALE)
    longitude_pad = radius_meters / (_METERS_PER_DEGREE_LATITUDE * longitude_scale)

    return BoundingBoxGeometry(
        coordinates=(
            min(longitudes) - longitude_pad,
            min(latitudes) - latitude_pad,
            max(longitudes) + longitude_pad,
            max(latitudes) + latitude_pad,
        )
    )


def representative_point(geometry: Geometry) -> tuple[float, float]:
    """A single `(x, y)` point standing in for `geometry`, for distance
    purposes:

    - `PointGeometry` — its own coordinates.
    - `BoundingBoxGeometry` — the box's center.
    - `PolygonGeometry` — the exterior ring's vertex-average centroid (a
      simple, documented approximation, not an area-weighted centroid;
      adequate for the small building footprints this platform produces,
      not claimed to be accurate for large or highly irregular polygons).
    """
    if isinstance(geometry, PointGeometry):
        return geometry.coordinates
    if isinstance(geometry, BoundingBoxGeometry):
        x_min, y_min, x_max, y_max = geometry.coordinates
        return ((x_min + x_max) / 2, (y_min + y_max) / 2)
    if isinstance(geometry, PolygonGeometry):
        ring = geometry.coordinates[0][:-1]  # exclude the closing duplicate point
        xs = [x for x, _ in ring]
        ys = [y for _, y in ring]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    raise TypeError(f"Unsupported geometry type: {type(geometry)!r}")  # pragma: no cover
