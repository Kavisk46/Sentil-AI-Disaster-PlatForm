"""Pixel-space spatial primitives shared across the ML pipeline.

Deliberately pixel-space only, in the coordinate frame of whatever image
was passed to `predict()`. Converting to geographic coordinates
(latitude/longitude) needs georeferencing metadata this pipeline doesn't
read yet — see `apps/api/README.md` ("Geospatial future support") for the
planned path to PostGIS/routing integration, and
`app/ml/datasets/xbd.py` for xBD's own available (but currently unread)
`features.lng_lat` geometries.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """An axis-aligned box in pixel coordinates of a specific image.

    The minimal spatial representation a building-localization stage can
    produce — chosen over a polygon or mask because it's what a detector
    naturally outputs, and it degrades cleanly (a polygon-based localizer
    could still report its bounding box; the reverse isn't true).
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def area(self) -> float:
        return self.width * self.height

    def intersection_area(self, other: "BoundingBox") -> float:
        overlap_width = max(0.0, min(self.x_max, other.x_max) - max(self.x_min, other.x_min))
        overlap_height = max(0.0, min(self.y_max, other.y_max) - max(self.y_min, other.y_min))
        return overlap_width * overlap_height

    def iou(self, other: "BoundingBox") -> float:
        """Intersection-over-union with `other`. Used by
        `app.ml.evaluation` for detection-quality metrics, once real
        spatial predictions exist to evaluate."""
        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0
