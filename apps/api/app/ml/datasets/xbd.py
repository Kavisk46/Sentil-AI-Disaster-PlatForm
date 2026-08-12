"""xBD/xView2 dataset support.

xBD (Gupta et al., 2019, https://arxiv.org/abs/1911.09296 — the dataset
behind the xView2 challenge) pairs pre-disaster and post-disaster
satellite imagery with per-building polygon annotations, each labeled
with one of four damage subtypes plus an "un-classified" catch-all. It
covers multiple disaster types (hurricanes, wildfires, floods, earthquakes,
volcanic eruptions, tsunamis) across many distinct events. See
`apps/api/README.md` ("Dataset pipeline") for why it's the right fit for
SentinelAI.

This module parses the dataset's public release layout:

    <root>/images/<disaster_id>_<sample_number>_pre_disaster.png
    <root>/images/<disaster_id>_<sample_number>_post_disaster.png
    <root>/labels/<disaster_id>_<sample_number>_pre_disaster.json
    <root>/labels/<disaster_id>_<sample_number>_post_disaster.json

and each post-disaster label file's structure:

    {
      "metadata": {"disaster_type": "...", ...},
      "features": {"xy": [{"wkt": "POLYGON ((...))",
                            "properties": {"uid": "...", "subtype": "..."}},
                           ...]}
    }

IMPORTANT: this targets xBD's documented public-release format from
memory of the published dataset description — it has **not** been
validated against a real, downloaded copy of xBD in this environment (no
internet access here; see README). Validate `_SAMPLE_FILENAME_RE` and
`_parse_building_feature` against real sample files before relying on
this for actual training data loading, and expect to adjust them if the
real files differ.
"""

import json
import re
import warnings
from pathlib import Path

from pydantic import BaseModel

from app.ml.datasets.schemas import BuildingAnnotation, DatasetSplit, ImageSample
from app.ml.datasets.validation import (
    DatasetValidationError,
    MalformedAnnotationError,
    validate_annotation_exists,
    validate_image_exists,
)
from app.ml.schemas import DamageClass

# Matches "<disaster_id>_<sample_number>" (e.g. "guatemala-volcano_00000000")
# once the "_pre_disaster"/"_post_disaster" suffix has been stripped.
# Disaster ids in xBD use hyphens, not underscores, so splitting on the
# last underscore reliably separates id from sample number.
_SAMPLE_ID_RE = re.compile(r"^(?P<disaster_id>.+)_(?P<sample_number>\d+)$")

_RAW_SUBTYPE_TO_DAMAGE_CLASS: dict[str, DamageClass] = {
    "no-damage": DamageClass.NO_DAMAGE,
    "minor-damage": DamageClass.MINOR,
    "major-damage": DamageClass.MAJOR,
    "destroyed": DamageClass.DESTROYED,
}
# Present in real xBD labels for buildings the original annotators couldn't
# confidently assess — a real category, but not one with a reliable damage
# assessment, so it is deliberately excluded from `DamageClass` rather than
# guessed into one of the four real classes.
_DELIBERATELY_UNMAPPED_SUBTYPES = frozenset({"un-classified"})


class UnknownDamageLabelError(DatasetValidationError):
    """Raised when a label file contains a damage subtype this codebase
    doesn't know how to normalize. Never silently dropped or guessed at —
    see `normalize_damage_label`."""


def normalize_damage_label(raw_subtype: str, *, strict: bool = True) -> DamageClass | None:
    """Map an xBD raw damage `subtype` string to a normalized `DamageClass`.

    `strict=True` (the default, and what dataset loading uses) raises
    `UnknownDamageLabelError` on anything unrecognized. `strict=False`
    instead emits a `UserWarning` and returns `None`, for callers doing
    exploratory analysis who'd rather see a summary of unknown labels
    than stop at the first one.
    """
    if raw_subtype in _RAW_SUBTYPE_TO_DAMAGE_CLASS:
        return _RAW_SUBTYPE_TO_DAMAGE_CLASS[raw_subtype]

    if raw_subtype in _DELIBERATELY_UNMAPPED_SUBTYPES:
        message = (
            f"xBD subtype {raw_subtype!r} has no reliable damage assessment and "
            "is intentionally not normalized into a DamageClass."
        )
    else:
        message = (
            f"Unrecognized xBD damage subtype: {raw_subtype!r}. This may mean "
            "the format assumptions in app/ml/datasets/xbd.py need updating. "
            f"Known subtypes: {sorted(_RAW_SUBTYPE_TO_DAMAGE_CLASS)} "
            "(+ 'un-classified', deliberately excluded)."
        )

    if strict:
        raise UnknownDamageLabelError(message)
    warnings.warn(message, stacklevel=2)
    return None


class XbdDatasetConfig(BaseModel):
    """Configuration for `XbdDataset`.

    `split_assignment` maps disaster id -> split explicitly, rather than
    this module inventing a default train/val/test ratio: which disasters
    belong in which split is a research decision the caller makes, not
    something to guess at. Every disaster discovered under `root` must
    have an entry, or `list_samples` raises — see
    `apps/api/README.md` ("Data splits and leakage") for why silently
    defaulting an unassigned disaster to a split would be actively unsafe.
    """

    root: Path
    split_assignment: dict[str, DatasetSplit]
    images_dirname: str = "images"
    labels_dirname: str = "labels"


class XbdDataset:
    """`DisasterDamageDataset` implementation for local, xBD-formatted data."""

    def __init__(self, config: XbdDatasetConfig) -> None:
        self._config = config

    @property
    def root(self) -> Path:
        return self._config.root

    @property
    def _images_dir(self) -> Path:
        return self._config.root / self._config.images_dirname

    @property
    def _labels_dir(self) -> Path:
        return self._config.root / self._config.labels_dirname

    def list_samples(self, split: DatasetSplit) -> list[str]:
        sample_ids = []
        for path in sorted(self._images_dir.glob("*_post_disaster.png")):
            sample_id = path.stem.removesuffix("_post_disaster")
            disaster_id = self._parse_disaster_id(sample_id)

            assigned_split = self._config.split_assignment.get(disaster_id)
            if assigned_split is None:
                raise DatasetValidationError(
                    f"Disaster {disaster_id!r} (from {path.name}) has no split "
                    "assignment in XbdDatasetConfig.split_assignment. Every "
                    "discovered disaster must be explicitly assigned exactly "
                    "one split — see apps/api/README.md."
                )
            if assigned_split == split:
                sample_ids.append(sample_id)
        return sample_ids

    def load_image_sample(self, split: DatasetSplit, sample_id: str) -> ImageSample:
        self._parse_disaster_id(sample_id)  # validates the id shape early

        pre_image_path = self._images_dir / f"{sample_id}_pre_disaster.png"
        post_image_path = self._images_dir / f"{sample_id}_post_disaster.png"
        annotation_path = self._labels_dir / f"{sample_id}_post_disaster.json"

        validate_image_exists(pre_image_path)
        validate_image_exists(post_image_path)
        validate_annotation_exists(annotation_path)

        payload = _load_json(annotation_path)
        disaster_type = _read_disaster_type(payload, annotation_path)

        return ImageSample(
            disaster_id=self._parse_disaster_id(sample_id),
            disaster_type=disaster_type,
            image_path=post_image_path,
            pre_image_path=pre_image_path,
            post_image_path=post_image_path,
            annotation_path=annotation_path,
        )

    def load_annotations(self, sample: ImageSample) -> list[BuildingAnnotation]:
        payload = _load_json(sample.annotation_path)
        features = payload.get("features")
        if not isinstance(features, dict) or "xy" not in features:
            raise MalformedAnnotationError(f"{sample.annotation_path}: missing 'features.xy'.")

        xy_features = features["xy"]
        if not isinstance(xy_features, list):
            raise MalformedAnnotationError(
                f"{sample.annotation_path}: 'features.xy' must be a list."
            )

        return [
            _parse_building_feature(feature, sample.annotation_path, index)
            for index, feature in enumerate(xy_features)
        ]

    def _parse_disaster_id(self, sample_id: str) -> str:
        match = _SAMPLE_ID_RE.match(sample_id)
        if not match:
            raise DatasetValidationError(
                f"Malformed sample id {sample_id!r}: expected "
                "'<disaster_id>_<sample_number>'."
            )
        return match.group("disaster_id")


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MalformedAnnotationError(f"{path}: not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise MalformedAnnotationError(f"{path}: expected a JSON object at the top level.")
    return payload


def _read_disaster_type(payload: dict[str, object], annotation_path: Path) -> str:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or "disaster_type" not in metadata:
        raise MalformedAnnotationError(f"{annotation_path}: missing 'metadata.disaster_type'.")
    return str(metadata["disaster_type"])


def _parse_building_feature(
    feature: object, annotation_path: Path, index: int
) -> BuildingAnnotation:
    if not isinstance(feature, dict):
        raise MalformedAnnotationError(f"{annotation_path}: feature #{index} is not an object.")

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise MalformedAnnotationError(
            f"{annotation_path}: feature #{index} missing 'properties'."
        )

    wkt = feature.get("wkt")
    uid = properties.get("uid")
    subtype = properties.get("subtype")
    if not isinstance(wkt, str) or not isinstance(uid, str) or not isinstance(subtype, str):
        raise MalformedAnnotationError(
            f"{annotation_path}: feature #{index} missing 'wkt' / "
            "'properties.uid' / 'properties.subtype'."
        )

    damage_class = normalize_damage_label(subtype)  # strict=True: never None here
    if damage_class is None:  # pragma: no cover - unreachable with strict=True
        raise UnknownDamageLabelError(f"{annotation_path}: feature #{index} subtype {subtype!r}")

    return BuildingAnnotation(building_id=uid, polygon_wkt=wkt, damage_class=damage_class)
