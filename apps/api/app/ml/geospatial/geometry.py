"""Validated coordinate geometry — the spatial shapes a building prediction
can carry, in *either* pixel space or geographic space. Which one applies to
a given `Geometry` instance is recorded separately (`CoordinateReferenceSystem`
and `georeferenced` on `app.ml.schemas.BuildingDamage`), never inferred from
the geometry itself — a `PolygonGeometry` looks identical whether its
coordinates are pixels or WGS84 degrees.

Deliberately not the pixel-only `app.ml.spatial.BoundingBox` — that type
stays exactly what it's always been (what a `BuildingLocalizer`/`DamageModel`
produces, in pixel space). `Geometry` here is the "Spatial Representation"
step of the pipeline:

    Computer Vision -> Building Prediction -> Spatial Representation -> GeoJSON / PostGIS

Every geometry constructor validates eagerly (Pydantic field validators) so
malformed geometry — NaN/Infinity coordinates, an unclosed polygon ring, an
inverted bounding box — is rejected at construction time and can never reach
a repository or a future PostGIS layer. No geometry library (shapely or
similar) is added for this — matches the same deferral already made in
`app.ml.datasets.schemas` (`polygon_wkt` kept as raw WKT) — full geometric
operations (self-intersection checks, true polygon simplification) are
deferred until something actually needs them.
"""

import math
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.ml.spatial import BoundingBox

Coordinate = tuple[float, float]


class GeometryType(StrEnum):
    """This codebase's own internal geometry discriminator — distinct from
    GeoJSON's `"Point"`/`"Polygon"` type strings (see `app.ml.geospatial.geojson`),
    which follow RFC 7946's exact casing/vocabulary instead."""

    POINT = "point"
    POLYGON = "polygon"
    BOUNDING_BOX = "bounding_box"


class InvalidGeometryError(ValueError):
    """Raised when geometry coordinates are structurally invalid: a
    non-finite (NaN/Infinity) value, a polygon ring that isn't closed or
    has fewer than 3 distinct vertices, or a bounding box with min > max.

    Subclasses `ValueError` so Pydantic's normal validation-error handling
    applies automatically wherever geometry is parsed from a request body
    (-> `422 Unprocessable Entity`); production code paths that build
    geometry from real model output should never trigger it.
    """


def _is_finite(value: float) -> bool:
    return math.isfinite(value)


def _validate_pair(pair: Coordinate) -> Coordinate:
    x, y = pair
    if not (_is_finite(x) and _is_finite(y)):
        raise InvalidGeometryError(f"Coordinate contains a non-finite value: {pair!r}")
    return (x, y)


class PointGeometry(BaseModel):
    """A single coordinate pair — `(x, y)` in pixel space, or
    `(longitude, latitude)` once georeferenced (see
    `app.ml.geospatial.crs.CoordinateReferenceSystem`)."""

    type: Literal[GeometryType.POINT] = GeometryType.POINT
    coordinates: Coordinate

    @field_validator("coordinates")
    @classmethod
    def _validate_coordinates(cls, value: Coordinate) -> Coordinate:
        return _validate_pair(value)


class PolygonGeometry(BaseModel):
    """One or more linear rings (first = exterior, any further rings =
    holes — the standard GeoJSON/WKT polygon convention). Each ring must be
    closed (first position == last) and have at least 3 distinct vertices.

    Preferred over `PointGeometry`/`BoundingBoxGeometry` whenever a model
    provides real segmentation — nothing in this codebase does yet (see
    `app.ml.localizer`), so this is exercised by tests with synthetic
    geometry today, not by any live prediction.
    """

    type: Literal[GeometryType.POLYGON] = GeometryType.POLYGON
    coordinates: list[list[Coordinate]]

    @field_validator("coordinates")
    @classmethod
    def _validate_rings(cls, rings: list[list[Coordinate]]) -> list[list[Coordinate]]:
        if not rings:
            raise InvalidGeometryError("Polygon must have at least one ring (the exterior).")
        validated: list[list[Coordinate]] = []
        for ring in rings:
            if len(ring) < 4:
                raise InvalidGeometryError(
                    "Polygon ring must have at least 4 positions (>=3 distinct "
                    f"vertices plus the closing point); got {len(ring)}."
                )
            checked = [_validate_pair(point) for point in ring]
            if checked[0] != checked[-1]:
                raise InvalidGeometryError(
                    "Polygon ring must be closed: first position must equal the "
                    f"last position; got {checked[0]!r} != {checked[-1]!r}."
                )
            if len(set(checked)) < 3:
                raise InvalidGeometryError(
                    "Polygon ring must have at least 3 distinct vertices."
                )
            validated.append(checked)
        return validated


class BoundingBoxGeometry(BaseModel):
    """An axis-aligned box: `(x_min, y_min, x_max, y_max)`. The geometric
    counterpart to `app.ml.spatial.BoundingBox` — same shape, but usable in
    either pixel or geographic space and validated the same way every other
    `Geometry` variant is.
    """

    type: Literal[GeometryType.BOUNDING_BOX] = GeometryType.BOUNDING_BOX
    coordinates: tuple[float, float, float, float]

    @field_validator("coordinates")
    @classmethod
    def _validate_bounds(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        x_min, y_min, x_max, y_max = value
        if not all(_is_finite(v) for v in value):
            raise InvalidGeometryError(f"Bounding box contains a non-finite value: {value!r}")
        if x_min > x_max or y_min > y_max:
            raise InvalidGeometryError(f"Bounding box min must not exceed max: {value!r}")
        return value

    @classmethod
    def from_pixel_bbox(cls, bbox: BoundingBox) -> "BoundingBoxGeometry":
        return cls(coordinates=(bbox.x_min, bbox.y_min, bbox.x_max, bbox.y_max))

    def intersects(self, other: "BoundingBoxGeometry") -> bool:
        """Standard axis-aligned box intersection test — the in-memory
        stand-in for a future PostGIS `ST_Intersects`."""
        ax_min, ay_min, ax_max, ay_max = self.coordinates
        bx_min, by_min, bx_max, by_max = other.coordinates
        return ax_min <= bx_max and bx_min <= ax_max and ay_min <= by_max and by_min <= ay_max


Geometry = Annotated[
    PointGeometry | PolygonGeometry | BoundingBoxGeometry,
    Field(discriminator="type"),
]
