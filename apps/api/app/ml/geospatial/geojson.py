"""Converts building predictions into standard GeoJSON (RFC 7946) —
`Feature` / `FeatureCollection` — for map visualization
(Leaflet/Mapbox/MapLibre) and eventual PostGIS ingestion. Deliberately no
custom map format: RFC 7946 is the format every mapping library in the
frontend contract already understands.

Only buildings with a real `geometry` become GeoJSON features — a building
with no location (no bounding box was ever produced for it) has nothing
spatial to serialize and is silently excluded, never given an invented
point or box. `properties.georeferenced` tells a map consumer whether
`geometry`'s coordinates are real longitude/latitude (safe to plot on a
geographic map) or pixel coordinates of the source image (**not** safe to
plot geographically — see "Image-space vs geospatial" in
apps/api/README.md). `properties` deliberately carries only what the task
requires (`building_id`, `damage_class`, `confidence`, `priority`,
`georeferenced`) — no model internals (raw logits, model name, ...) leak
into map-facing output.

This codebase's own `BoundingBoxGeometry` has no direct GeoJSON
equivalent — GeoJSON's geometry types are Point/LineString/Polygon/Multi*/
GeometryCollection, with no dedicated bounding-box shape (RFC 7946 §5 only
allows an optional `bbox` *member* on any object, not a geometry type of
its own). So a `BoundingBoxGeometry` is rendered here as a closed,
five-position rectangular `Polygon` ring — a real, correct GeoJSON
representation of the same rectangle, not an approximation.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import (
    BoundingBoxGeometry,
    Coordinate,
    Geometry,
    PointGeometry,
    PolygonGeometry,
)
from app.ml.geospatial.priority import compute_damage_priority
from app.ml.schemas import BuildingDamage


class GeoJSONPoint(BaseModel):
    """RFC 7946 §3.1.2 Point geometry."""

    type: Literal["Point"] = "Point"
    coordinates: Coordinate


class GeoJSONPolygon(BaseModel):
    """RFC 7946 §3.1.6 Polygon geometry."""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[Coordinate]]


GeoJSONGeometry = GeoJSONPoint | GeoJSONPolygon


class FeatureProperties(BaseModel):
    """The GeoJSON `Feature.properties` this platform emits — deliberately
    only these five fields (see the module docstring)."""

    building_id: str
    damage_class: str
    confidence: float
    priority: str
    georeferenced: bool


class Feature(BaseModel):
    """RFC 7946 §3.2 Feature."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONGeometry
    properties: FeatureProperties


class FeatureCollection(BaseModel):
    """RFC 7946 §3.3 FeatureCollection.

    `coordinate_reference_system` is a foreign member (RFC 7946 §6.1
    explicitly allows, and expects consumers to ignore, members outside
    the spec) — useful here because every feature in one analysis's
    collection shares the same source image and therefore the same CRS, so
    recording it once at the collection level avoids repeating it on every
    feature.
    """

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature] = Field(default_factory=list)
    coordinate_reference_system: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE


def _to_geojson_geometry(geometry: Geometry) -> GeoJSONGeometry:
    if isinstance(geometry, PointGeometry):
        return GeoJSONPoint(coordinates=geometry.coordinates)
    if isinstance(geometry, PolygonGeometry):
        return GeoJSONPolygon(coordinates=geometry.coordinates)
    if isinstance(geometry, BoundingBoxGeometry):
        x_min, y_min, x_max, y_max = geometry.coordinates
        ring = [
            (x_min, y_min),
            (x_max, y_min),
            (x_max, y_max),
            (x_min, y_max),
            (x_min, y_min),
        ]
        return GeoJSONPolygon(coordinates=[ring])
    raise TypeError(f"Unsupported geometry type: {type(geometry)!r}")  # pragma: no cover


def building_to_feature(building: BuildingDamage) -> Feature | None:
    """`None` if `building.geometry` is `None` — nothing to map."""
    if building.geometry is None:
        return None
    return Feature(
        geometry=_to_geojson_geometry(building.geometry),
        properties=FeatureProperties(
            building_id=building.building_id,
            damage_class=building.damage_class.value,
            confidence=building.confidence,
            priority=compute_damage_priority(building.damage_class).value,
            georeferenced=building.georeferenced,
        ),
    )


def to_feature_collection(buildings: Sequence[BuildingDamage]) -> FeatureCollection:
    """Converts every mappable building (`geometry is not None`) into a
    `FeatureCollection`. Buildings with no geometry are silently excluded —
    see `building_to_feature`. The collection's
    `coordinate_reference_system` is taken from the first mappable
    building (all buildings in one analysis share one source image, so one
    CRS); an empty `buildings` sequence defaults to `IMAGE`.
    """
    features: list[Feature] = []
    crs = CoordinateReferenceSystem.IMAGE
    for building in buildings:
        feature = building_to_feature(building)
        if feature is None:
            continue
        if not features:
            crs = building.coordinate_reference_system
        features.append(feature)
    return FeatureCollection(features=features, coordinate_reference_system=crs)
