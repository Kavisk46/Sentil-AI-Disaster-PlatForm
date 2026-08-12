"""Geospatial damage-intelligence pipeline (Milestone 5).

    Building Prediction -> Spatial Representation -> GeoJSON / PostGIS -> Map

Converts building-level damage predictions (`app.ml.schemas.BuildingDamage`)
into a spatial representation that can be serialized to GeoJSON and, later,
persisted to PostGIS. Deliberately separate from `app.ml.spatial`, which
stays pixel-space-only (what a `BuildingLocalizer`/`DamageModel` actually
produces) — this package is where pixel-space geometry either stays
pixel-space (`georeferenced=False`, the only real case today — no ordinary
JPEG/PNG/WEBP upload carries georeferencing metadata) or, once a real
transform exists, becomes real geographic geometry. No route or model
fabricates a latitude/longitude — see `apps/api/README.md`
("Geospatial damage intelligence") for the full picture.

- `geometry.py` — `PointGeometry`/`PolygonGeometry`/`BoundingBoxGeometry`:
  validated coordinate geometry, agnostic of pixel vs. geographic.
- `crs.py` — `CoordinateReferenceSystem`: explicit CRS, never assumed.
- `georeferencing.py` — `GeoreferencingTransform`/`GeoreferencingProvider`:
  the pixel -> geographic transformation seam. `NoGeoreferencingAvailable`
  is the only implementation wired into production DI today.
- `spatial_builder.py` — turns a pixel `BoundingBox` into
  `(Geometry, CoordinateReferenceSystem, georeferenced)`: image-space by
  default, geographic once a real transform is supplied.
- `priority.py` — `DamagePriority`: deterministic, damage-severity-only
  priority.
- `geojson.py` — `Feature`/`FeatureCollection`: standard GeoJSON
  (RFC 7946) conversion.

See `apps/api/README.md` ("Geospatial damage intelligence") for the full
picture: image coordinates vs. geographic coordinates, why GPS coordinates
are never invented, GeoJSON representation, CRS handling, damage-based
priority, and the planned PostGIS/OpenStreetMap integration.
"""
