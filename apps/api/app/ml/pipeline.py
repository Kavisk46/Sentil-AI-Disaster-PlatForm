"""Composes Stage 1 (localization) + Stage 2 (classification) into the
existing, unmodified `DamageModel` Protocol.

    Image -> BuildingLocalizer.locate() -> crop each box
          -> TorchDamageClassifier.classify() each crop -> list[RawDetection]

This is the only file that knows both stages exist — `app/ml/inference.py`
and the API layer consume `TwoStageDamageModel` exactly like any other
`DamageModel`, unaware it's two components internally. That's the point:
Stage 1 and Stage 2 can each be replaced independently (see
`apps/api/README.md`) without this file's callers noticing.
"""

from typing import Protocol

from PIL import Image

from app.ml.localizer import BuildingLocalizer, LocalizerNotAvailableError
from app.ml.model import ModelNotAvailableError, RawDetection
from app.ml.schemas import ModelStatus


class _DamageClassifier(Protocol):
    """Structural type for Stage 2 — matches `TorchDamageClassifier`
    without importing it directly, keeping this module free of any
    PyTorch dependency of its own."""

    def load(self) -> None: ...
    def classify(self, crop: Image.Image) -> RawDetection: ...
    def health(self) -> ModelStatus: ...


class TwoStageDamageModel:
    """`DamageModel` implementation composing a `BuildingLocalizer` and a
    per-crop damage classifier.

    Both stage failures are normalized to `ModelNotAvailableError` —
    `DamageModel.predict()`'s documented exception contract doesn't
    distinguish *which* internal stage was unavailable, only that no
    genuine result could be produced.
    """

    def __init__(self, localizer: BuildingLocalizer, classifier: _DamageClassifier) -> None:
        self._localizer = localizer
        self._classifier = classifier

    def load(self) -> None:
        self._localizer.load()
        self._classifier.load()

    def predict(self, image: Image.Image) -> list[RawDetection]:
        try:
            located_buildings = self._localizer.locate(image)
        except LocalizerNotAvailableError as exc:
            raise ModelNotAvailableError(
                "Stage 1 (building localization) is unavailable: "
                f"{exc}"
            ) from exc

        detections: list[RawDetection] = []
        for building in located_buildings:
            box = building.bounding_box
            crop = image.crop((box.x_min, box.y_min, box.x_max, box.y_max))
            detection = self._classifier.classify(crop)
            detections.append(
                RawDetection(
                    damage_class=detection.damage_class,
                    confidence=detection.confidence,
                    bounding_box=box,
                )
            )
        return detections

    def health(self) -> ModelStatus:
        """Reports the pipeline as loaded only if *both* stages are —
        an end-to-end result requires both, so claiming readiness with
        either one missing would misrepresent what this model can
        actually do."""
        localizer_status = self._localizer.health()
        classifier_status = self._classifier.health()
        return ModelStatus(
            model_loaded=localizer_status.model_loaded and classifier_status.model_loaded,
            model_name=f"{localizer_status.model_name}+{classifier_status.model_name}",
            model_version=classifier_status.model_version,
            device=classifier_status.device,
        )
