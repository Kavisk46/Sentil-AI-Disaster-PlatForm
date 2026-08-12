"""Image-coordinate -> geographic-coordinate transformation abstraction.

`GeoreferencingProvider` is the seam a real metadata source (a GeoTIFF's
geotransform + declared CRS, a raster catalog entry, ...) plugs into,
mirroring the same load/predict-style Protocol pattern already used for
`DamageModel` (`app.ml.model`) and `BuildingLocalizer` (`app.ml.localizer`).

Ordinary JPEG/PNG/WEBP uploads — the only image types `POST /api/v1/analysis`
accepts (see `apps/api/README.md`) — never carry a geotransform or a
declared CRS. Even a photo with EXIF GPS tags (rare, and not currently read
by this codebase) only gives a single camera location, not a per-pixel
mapping from image coordinates to geographic coordinates — that is not the
same thing as georeferencing metadata. So `NoGeoreferencingAvailable` is the
only `GeoreferencingProvider` implementation wired into production DI, and
it always raises `GeoreferencingUnavailableError` rather than guessing.

`AffineGeoTransform` is nonetheless a real, correct implementation of the
standard math (GDAL's six-parameter geotransform convention) — ready for
the moment this pipeline can ingest imagery that actually carries one (a
future GeoTIFF ingestion milestone). Nothing in this milestone constructs
one with real data; it exists as tested, honest infrastructure, not a
default that fabricates coordinates.
"""

from dataclasses import dataclass
from typing import Protocol

from app.ml.geospatial.crs import CoordinateReferenceSystem, UnsupportedCRSError
from app.ml.geospatial.geometry import PointGeometry, PolygonGeometry
from app.ml.spatial import BoundingBox


class GeoreferencingUnavailableError(RuntimeError):
    """Raised when no georeferencing metadata (a geotransform + a declared
    CRS) is available for an image. Never caught and papered over with a
    guessed transform — see `apps/api/README.md` ("Georeferenced mode")."""


class GeoreferencingTransform(Protocol):
    """Maps pixel coordinates of one specific image into geographic
    coordinates. Only ever constructed from real metadata belonging to
    that image — never a default or identity guess."""

    @property
    def target_crs(self) -> CoordinateReferenceSystem:
        """The CRS `transform_point`/`transform_bounding_box` produce
        coordinates in — always `WGS84` for every implementation this
        codebase has today (see the module docstring on reprojection)."""
        ...

    def transform_point(self, x: float, y: float) -> PointGeometry:
        """Transform one pixel coordinate into a geographic `PointGeometry`."""
        ...

    def transform_bounding_box(self, bbox: BoundingBox) -> PolygonGeometry:
        """Transform a pixel-space `BoundingBox` into a geographic
        `PolygonGeometry`. A polygon, not another bounding box: an
        arbitrary affine transform (rotation, shear) does not generally
        map a rectangle to another axis-aligned rectangle, so returning a
        `PolygonGeometry` of the four transformed corners is the only
        honest representation."""
        ...


@dataclass(frozen=True, slots=True)
class AffineGeoTransform:
    """A real, standard six-parameter affine transform — GDAL's
    geotransform convention:

        geo_x = a + col * b + row * c
        geo_y = d + col * e + row * f

    This is exactly the tuple a GeoTIFF's geotransform provides. Only
    `source_crs=WGS84` is accepted today: reprojecting a transform's output
    from another CRS into WGS84 needs a real geodesy library (pyproj or
    similar), deliberately not added in this milestone (see
    `app.ml.geospatial.crs`). Constructing this with any other `source_crs`
    fails immediately rather than silently skipping reprojection.
    """

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float
    source_crs: CoordinateReferenceSystem = CoordinateReferenceSystem.WGS84

    def __post_init__(self) -> None:
        if self.source_crs is not CoordinateReferenceSystem.WGS84:
            raise UnsupportedCRSError(
                f"AffineGeoTransform only supports source_crs=WGS84 today (got "
                f"{self.source_crs!r}) — reprojection is not implemented. See "
                "apps/api/README.md ('Geospatial damage intelligence')."
            )

    @property
    def target_crs(self) -> CoordinateReferenceSystem:
        return CoordinateReferenceSystem.WGS84

    def transform_point(self, x: float, y: float) -> PointGeometry:
        geo_x = self.a + x * self.b + y * self.c
        geo_y = self.d + x * self.e + y * self.f
        return PointGeometry(coordinates=(geo_x, geo_y))

    def transform_bounding_box(self, bbox: BoundingBox) -> PolygonGeometry:
        corners = [
            (bbox.x_min, bbox.y_min),
            (bbox.x_max, bbox.y_min),
            (bbox.x_max, bbox.y_max),
            (bbox.x_min, bbox.y_max),
        ]
        ring = [self.transform_point(x, y).coordinates for x, y in corners]
        ring.append(ring[0])
        return PolygonGeometry(coordinates=[ring])


class GeoreferencingProvider(Protocol):
    def get_transform(self, storage_name: str) -> GeoreferencingTransform:
        """Return the georeferencing transform for a stored image.

        Raises `GeoreferencingUnavailableError` if none exists — never
        fabricates one.
        """
        ...


class NoGeoreferencingAvailable:
    """The only `GeoreferencingProvider` implementation today. Always
    raises — see the module docstring for why no ordinary upload can ever
    supply real georeferencing metadata. Kept as a real, DI-wired object
    (mirrors `UnavailableBuildingLocalizer`/`UnavailableDamageModel`)
    rather than `None`, so callers depend on one honest interface
    regardless of whether georeferencing is ever actually possible for a
    given upload.
    """

    def get_transform(self, storage_name: str) -> GeoreferencingTransform:
        raise GeoreferencingUnavailableError(
            f"No georeferencing metadata is available for {storage_name!r}. "
            "Ordinary JPEG/PNG/WEBP uploads do not carry a geotransform or a "
            "declared CRS — see apps/api/README.md ('Georeferenced mode')."
        )
