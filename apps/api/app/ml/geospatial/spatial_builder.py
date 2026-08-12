"""Turns a pixel-space `BoundingBox` (from `RawDetection`/`app.ml.postprocessing`)
into the `(Geometry, CoordinateReferenceSystem, georeferenced)` triple
`BuildingDamage` carries — the "Spatial Representation" step of the
pipeline:

    Computer Vision -> Building Prediction -> Spatial Representation -> GeoJSON / PostGIS

No georeferencing metadata source exists for ordinary JPEG/PNG/WEBP uploads
(see `app.ml.geospatial.georeferencing`), so `image_space_geometry` — the
only function `app.ml.postprocessing.build_analysis` currently calls —
always returns pixel-space geometry with `georeferenced=False`.
`georeferenced_geometry` exists so a future real metadata source has a
tested, ready function to call instead, without this module changing.
"""

from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import BoundingBoxGeometry, Geometry
from app.ml.geospatial.georeferencing import GeoreferencingTransform
from app.ml.spatial import BoundingBox


def image_space_geometry(
    bounding_box: BoundingBox | None,
) -> tuple[Geometry | None, CoordinateReferenceSystem, bool]:
    """Pixel-space geometry, honestly marked non-georeferenced.

    Returns `(None, CoordinateReferenceSystem.IMAGE, False)` when
    `bounding_box` is `None` — no location was produced for this
    detection, so no geometry is fabricated for it either.
    """
    if bounding_box is None:
        return None, CoordinateReferenceSystem.IMAGE, False
    return (
        BoundingBoxGeometry.from_pixel_bbox(bounding_box),
        CoordinateReferenceSystem.IMAGE,
        False,
    )


def georeferenced_geometry(
    bounding_box: BoundingBox | None,
    transform: GeoreferencingTransform,
) -> tuple[Geometry | None, CoordinateReferenceSystem, bool]:
    """Real geographic geometry, via an actual `GeoreferencingTransform`.

    Performs no georeferencing decision itself — `transform` must already
    come from real image metadata (see `app.ml.geospatial.georeferencing`);
    this function only applies the coordinate math. Not called by any
    route yet (see the module docstring); exercised directly by tests.
    """
    if bounding_box is None:
        return None, CoordinateReferenceSystem.IMAGE, False
    polygon = transform.transform_bounding_box(bounding_box)
    return polygon, transform.target_crs, True
