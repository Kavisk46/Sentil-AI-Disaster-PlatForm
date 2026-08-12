"""Tests for the xBD dataset loader — all synthetic, tiny fixtures.

No real xBD data, no downloads, no network — every test builds its own
minimal fake dataset directory under pytest's `tmp_path`.
"""

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from app.ml.datasets.base import load_sample
from app.ml.datasets.schemas import DatasetSplit
from app.ml.datasets.validation import (
    DatasetValidationError,
    MalformedAnnotationError,
    MissingAnnotationError,
    MissingImageError,
)
from app.ml.datasets.xbd import (
    UnknownDamageLabelError,
    XbdDataset,
    XbdDatasetConfig,
    normalize_damage_label,
)
from app.ml.schemas import DamageClass


def _write_sample(
    root: Path,
    disaster_id: str,
    sample_number: str,
    subtypes: list[str],
    disaster_type: str = "wind",
    *,
    skip_pre_image: bool = False,
    skip_post_image: bool = False,
    skip_label: bool = False,
    label_payload: dict[str, object] | None = None,
    raw_label_text: str | None = None,
) -> str:
    images_dir = root / "images"
    labels_dir = root / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    sample_id = f"{disaster_id}_{sample_number}"

    def _write_png(path: Path) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buffer, format="PNG")
        path.write_bytes(buffer.getvalue())

    if not skip_pre_image:
        _write_png(images_dir / f"{sample_id}_pre_disaster.png")
    if not skip_post_image:
        _write_png(images_dir / f"{sample_id}_post_disaster.png")

    label_path = labels_dir / f"{sample_id}_post_disaster.json"
    if not skip_label:
        if raw_label_text is not None:
            label_path.write_text(raw_label_text)
        else:
            payload = label_payload if label_payload is not None else {
                "metadata": {"disaster_type": disaster_type},
                "features": {
                    "xy": [
                        {
                            "wkt": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
                            "properties": {"uid": f"{sample_id}-b{i}", "subtype": subtype},
                        }
                        for i, subtype in enumerate(subtypes)
                    ]
                },
            }
            label_path.write_text(json.dumps(payload))

    return sample_id


# ---------------------------------------------------------------------------
# Dataset configuration
# ---------------------------------------------------------------------------


def test_config_accepts_a_root_and_split_assignment(tmp_path: Path) -> None:
    config = XbdDatasetConfig(
        root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN}
    )

    assert config.root == tmp_path
    assert config.split_assignment["hurricane-x"] == DatasetSplit.TRAIN


def test_config_defaults_images_and_labels_dirnames(tmp_path: Path) -> None:
    config = XbdDatasetConfig(root=tmp_path, split_assignment={})

    assert config.images_dirname == "images"
    assert config.labels_dirname == "labels"


# ---------------------------------------------------------------------------
# Sample parsing
# ---------------------------------------------------------------------------


def test_load_image_sample_resolves_paths_and_disaster_type(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path, "hurricane-x", "00000000", ["no-damage"], disaster_type="wind"
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    sample = dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)

    assert sample.disaster_id == "hurricane-x"
    assert sample.disaster_type == "wind"
    assert sample.image_path == sample.post_image_path
    assert sample.pre_image_path is not None and sample.pre_image_path.exists()
    assert sample.post_image_path is not None and sample.post_image_path.exists()
    assert sample.annotation_path.exists()


def test_load_annotations_returns_one_building_per_feature(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path, "hurricane-x", "00000000", ["no-damage", "destroyed", "major-damage"]
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )
    image_sample = dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)

    buildings = dataset.load_annotations(image_sample)

    assert [b.damage_class for b in buildings] == [
        DamageClass.NO_DAMAGE,
        DamageClass.DESTROYED,
        DamageClass.MAJOR,
    ]
    assert all(b.polygon_wkt.startswith("POLYGON") for b in buildings)


def test_load_sample_composes_image_and_annotations(tmp_path: Path) -> None:
    sample_id = _write_sample(tmp_path, "hurricane-x", "00000000", ["minor-damage"])
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    sample = load_sample(dataset, DatasetSplit.TRAIN, sample_id)

    assert sample.image.disaster_id == "hurricane-x"
    assert len(sample.buildings) == 1
    assert sample.buildings[0].damage_class == DamageClass.MINOR


def test_disaster_id_with_hyphens_is_parsed_correctly(tmp_path: Path) -> None:
    """Disaster ids like 'santa-rosa-wildfire' contain hyphens; only the
    trailing numeric sample number should be split off."""
    sample_id = _write_sample(tmp_path, "santa-rosa-wildfire", "00000042", ["destroyed"])
    dataset = XbdDataset(
        XbdDatasetConfig(
            root=tmp_path, split_assignment={"santa-rosa-wildfire": DatasetSplit.TEST}
        )
    )

    sample = dataset.load_image_sample(DatasetSplit.TEST, sample_id)

    assert sample.disaster_id == "santa-rosa-wildfire"


# ---------------------------------------------------------------------------
# Label normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("no-damage", DamageClass.NO_DAMAGE),
        ("minor-damage", DamageClass.MINOR),
        ("major-damage", DamageClass.MAJOR),
        ("destroyed", DamageClass.DESTROYED),
    ],
)
def test_normalize_damage_label_maps_known_subtypes(raw: str, expected: DamageClass) -> None:
    assert normalize_damage_label(raw) == expected


def test_normalize_damage_label_rejects_unclassified_by_default() -> None:
    with pytest.raises(UnknownDamageLabelError):
        normalize_damage_label("un-classified")


def test_normalize_damage_label_rejects_truly_unknown_subtype() -> None:
    with pytest.raises(UnknownDamageLabelError):
        normalize_damage_label("flooded-beyond-repair")


def test_normalize_damage_label_non_strict_warns_and_returns_none() -> None:
    with pytest.warns(UserWarning):
        result = normalize_damage_label("un-classified", strict=False)

    assert result is None


def test_load_annotations_raises_on_unknown_subtype(tmp_path: Path) -> None:
    sample_id = _write_sample(tmp_path, "hurricane-x", "00000000", ["catastrophic"])
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )
    image_sample = dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)

    with pytest.raises(UnknownDamageLabelError):
        dataset.load_annotations(image_sample)


# ---------------------------------------------------------------------------
# Invalid / malformed annotation handling
# ---------------------------------------------------------------------------


def test_malformed_json_raises_clearly(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path, "hurricane-x", "00000000", [], raw_label_text="{not valid json"
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    with pytest.raises(MalformedAnnotationError):
        dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)


def test_missing_metadata_disaster_type_raises(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path, "hurricane-x", "00000000", [], label_payload={"features": {"xy": []}}
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    with pytest.raises(MalformedAnnotationError):
        dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)


def test_missing_features_key_raises(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path,
        "hurricane-x",
        "00000000",
        [],
        label_payload={"metadata": {"disaster_type": "wind"}},
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )
    image_sample = dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)

    with pytest.raises(MalformedAnnotationError):
        dataset.load_annotations(image_sample)


def test_feature_missing_wkt_raises(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path,
        "hurricane-x",
        "00000000",
        [],
        label_payload={
            "metadata": {"disaster_type": "wind"},
            "features": {"xy": [{"properties": {"uid": "b0", "subtype": "no-damage"}}]},
        },
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )
    image_sample = dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)

    with pytest.raises(MalformedAnnotationError):
        dataset.load_annotations(image_sample)


# ---------------------------------------------------------------------------
# Missing file handling
# ---------------------------------------------------------------------------


def test_missing_pre_image_raises(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path, "hurricane-x", "00000000", ["no-damage"], skip_pre_image=True
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    with pytest.raises(MissingImageError):
        dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)


def test_missing_post_image_raises(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path, "hurricane-x", "00000000", ["no-damage"], skip_post_image=True
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    with pytest.raises(MissingImageError):
        dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)


def test_missing_label_file_raises(tmp_path: Path) -> None:
    sample_id = _write_sample(
        tmp_path, "hurricane-x", "00000000", ["no-damage"], skip_label=True
    )
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    with pytest.raises(MissingAnnotationError):
        dataset.load_image_sample(DatasetSplit.TRAIN, sample_id)


# ---------------------------------------------------------------------------
# Split behavior
# ---------------------------------------------------------------------------


def test_list_samples_only_returns_the_requested_split(tmp_path: Path) -> None:
    train_id = _write_sample(tmp_path, "hurricane-x", "00000000", ["no-damage"])
    test_id = _write_sample(tmp_path, "wildfire-y", "00000000", ["destroyed"])
    dataset = XbdDataset(
        XbdDatasetConfig(
            root=tmp_path,
            split_assignment={
                "hurricane-x": DatasetSplit.TRAIN,
                "wildfire-y": DatasetSplit.TEST,
            },
        )
    )

    assert dataset.list_samples(DatasetSplit.TRAIN) == [train_id]
    assert dataset.list_samples(DatasetSplit.TEST) == [test_id]
    assert dataset.list_samples(DatasetSplit.VALIDATION) == []


def test_all_samples_from_one_disaster_land_in_the_same_split(tmp_path: Path) -> None:
    """Multiple tiles from the same disaster must never be split across
    train/validation/test — see apps/api/README.md on data leakage."""
    first = _write_sample(tmp_path, "hurricane-x", "00000000", ["no-damage"])
    second = _write_sample(tmp_path, "hurricane-x", "00000001", ["destroyed"])
    dataset = XbdDataset(
        XbdDatasetConfig(root=tmp_path, split_assignment={"hurricane-x": DatasetSplit.TRAIN})
    )

    train_samples = dataset.list_samples(DatasetSplit.TRAIN)

    assert set(train_samples) == {first, second}
    assert dataset.list_samples(DatasetSplit.VALIDATION) == []
    assert dataset.list_samples(DatasetSplit.TEST) == []


def test_unassigned_disaster_raises_rather_than_defaulting_silently(tmp_path: Path) -> None:
    _write_sample(tmp_path, "unassigned-disaster", "00000000", ["no-damage"])
    dataset = XbdDataset(XbdDatasetConfig(root=tmp_path, split_assignment={}))

    with pytest.raises(DatasetValidationError):
        dataset.list_samples(DatasetSplit.TRAIN)
