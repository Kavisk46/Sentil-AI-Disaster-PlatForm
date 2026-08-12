from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ml.datasets.schemas import BuildingAnnotation, DatasetSample, DatasetSplit, ImageSample
from app.ml.schemas import DamageClass


def test_dataset_split_has_three_values() -> None:
    assert {s.value for s in DatasetSplit} == {"train", "validation", "test"}


def test_image_sample_allows_missing_pre_post_pair() -> None:
    """A dataset without pre/post pairing should still be representable."""
    sample = ImageSample(
        disaster_id="hurricane-x",
        disaster_type="wind",
        image_path=Path("images/a.png"),
        annotation_path=Path("labels/a.json"),
    )

    assert sample.pre_image_path is None
    assert sample.post_image_path is None


def test_image_sample_with_pre_post_pair() -> None:
    sample = ImageSample(
        disaster_id="hurricane-x",
        disaster_type="wind",
        image_path=Path("images/a_post_disaster.png"),
        pre_image_path=Path("images/a_pre_disaster.png"),
        post_image_path=Path("images/a_post_disaster.png"),
        annotation_path=Path("labels/a_post_disaster.json"),
    )

    assert sample.image_path == sample.post_image_path


def test_building_annotation_requires_a_known_damage_class() -> None:
    with pytest.raises(ValidationError):
        BuildingAnnotation.model_validate(
            {"building_id": "b0", "polygon_wkt": "POLYGON ((0 0))", "damage_class": "obliterated"}
        )


def test_dataset_sample_bundles_image_and_buildings() -> None:
    image = ImageSample(
        disaster_id="hurricane-x",
        disaster_type="wind",
        image_path=Path("images/a.png"),
        annotation_path=Path("labels/a.json"),
    )
    building = BuildingAnnotation(
        building_id="b0", polygon_wkt="POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
        damage_class=DamageClass.DESTROYED,
    )

    sample = DatasetSample(image=image, buildings=[building])

    assert sample.image.disaster_id == "hurricane-x"
    assert sample.buildings == [building]
