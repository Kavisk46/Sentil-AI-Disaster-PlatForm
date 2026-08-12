"""Coordinate reference system (CRS) handling.

Why CRS matters: a bare pair of numbers `(x, y)` is meaningless without
knowing which coordinate system they're expressed in. Pixel coordinates of
an uploaded image and WGS84 longitude/latitude are both just pairs of
floats in roughly overlapping numeric ranges for small images — silently
treating one as the other is exactly how fabricated GPS coordinates would
happen by accident. Every `Geometry` this codebase produces is always
paired with an explicit `CoordinateReferenceSystem` (see
`app.ml.schemas.BuildingDamage`) so a consumer never has to guess.

The intended future pipeline:

    source CRS -> coordinate transformation -> WGS84 -> GeoJSON / mapping

`WGS84` (EPSG:4326) is the only real geographic CRS supported today — it's
what RFC 7946 (the GeoJSON spec) mandates and what Leaflet/Mapbox/MapLibre
expect. A future `source CRS` (a UTM zone, State Plane, whatever a real
GeoTIFF declares) would need reprojection into WGS84 before reaching
GeoJSON — that reprojection step needs a real geodesy library (e.g.
pyproj), deliberately not added in this milestone (see
`app.ml.geospatial.georeferencing`).
"""

from enum import StrEnum


class CoordinateReferenceSystem(StrEnum):
    """The CRS a `Geometry`'s coordinates are expressed in.

    `IMAGE` is not a real-world CRS — it's this codebase's explicit marker
    for "pixel coordinates of the uploaded image, no geographic meaning
    whatsoever" so `georeferenced=False` geometry can never be confused
    with a real (if unusual) projected CRS. `WGS84` (EPSG:4326, longitude/
    latitude) is the only real geographic CRS currently supported.
    """

    IMAGE = "IMAGE"
    WGS84 = "EPSG:4326"


class UnsupportedCRSError(ValueError):
    """Raised when a CRS identifier isn't one this codebase currently
    understands. Deliberately conservative: silently accepting an unknown
    CRS string risks treating incompatible coordinates as compatible,
    which is indistinguishable from fabricating a location.
    """


_SUPPORTED = frozenset(member.value for member in CoordinateReferenceSystem)


def validate_crs(value: str) -> CoordinateReferenceSystem:
    """Parse and validate a raw CRS string. Raises `UnsupportedCRSError`
    rather than returning something that looks valid but isn't."""
    if value not in _SUPPORTED:
        raise UnsupportedCRSError(
            f"Unsupported coordinate reference system: {value!r}. Supported: "
            f"{sorted(_SUPPORTED)}."
        )
    return CoordinateReferenceSystem(value)
