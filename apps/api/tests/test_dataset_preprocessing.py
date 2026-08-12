from pathlib import Path

from app.ml.datasets.preprocessing import NoOpAugmentation
from app.ml.datasets.schemas import BuildingAnnotation, DatasetSample, ImageSample
from app.ml.schemas import DamageClass


def _sample() -> DatasetSample:
    image = ImageSample(
        disaster_id="hurricane-x",
        disaster_type="wind",
        image_path=Path("images/a.png"),
        annotation_path=Path("labels/a.json"),
    )
    building = BuildingAnnotation(
        building_id="b0",
        polygon_wkt="POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
        damage_class=DamageClass.MINOR,
    )
    return DatasetSample(image=image, buildings=[building])


def test_noop_augmentation_returns_the_same_sample_unchanged() -> None:
    sample = _sample()

    result = NoOpAugmentation()(sample)

    assert result == sample
