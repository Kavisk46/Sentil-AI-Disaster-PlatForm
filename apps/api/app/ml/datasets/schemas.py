"""Typed structures for dataset samples and annotations.

These describe what's on disk in a training dataset — distinct from
`app.ml.schemas`, which describes API-facing inference *results*.
`DamageClass` is the one thing shared between them: the same normalized
taxonomy a dataset's labels are mapped into is exactly what a trained
model will eventually predict.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from app.ml.schemas import DamageClass

__all__ = [
    "BuildingAnnotation",
    "DatasetSample",
    "DatasetSplit",
    "ImageSample",
]


class DatasetSplit(StrEnum):
    """Which partition of the dataset a sample belongs to.

    Assignment is disaster-level, not sample-level or random — see
    `apps/api/README.md` ("Data splits and leakage") for why.
    """

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class ImageSample(BaseModel):
    """One imagery sample within a dataset — paths only, nothing decoded.

    `image_path` always points at the image damage should be assessed
    from (the post-disaster image, when a pre/post pair exists) so a
    consumer that doesn't care about pre/post pairing can ignore
    `pre_image_path`/`post_image_path` entirely. Datasets without paired
    imagery leave those two unset.
    """

    disaster_id: str
    disaster_type: str
    image_path: Path
    pre_image_path: Path | None = None
    post_image_path: Path | None = None
    annotation_path: Path


class BuildingAnnotation(BaseModel):
    """One building's ground-truth damage annotation.

    `polygon_wkt` is the raw Well-Known-Text polygon string as stored in
    the dataset, intentionally unparsed into a geometry object — adding a
    geometry library (shapely or similar) is deferred until something
    actually needs to do geometric operations on it (e.g. mask
    rasterization during training), not assumed now. A future dataset
    that annotates with raster masks instead of polygons would add a
    separate field here rather than overloading this one.
    """

    building_id: str
    polygon_wkt: str
    damage_class: DamageClass


class DatasetSample(BaseModel):
    """One fully-loaded training example: an image sample and every
    building annotated within it."""

    image: ImageSample
    buildings: list[BuildingAnnotation]
