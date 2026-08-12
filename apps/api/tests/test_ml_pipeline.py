"""Tests for TwoStageDamageModel — the Stage 1 + Stage 2 orchestrator.

Uses hand-written stub stages (not the real localizer/classifier) so the
*composition* logic (locate -> crop -> classify -> assemble) is verified
in isolation, deterministically, without needing a real checkpoint or an
actually-available localizer.
"""


import pytest
from PIL import Image

from app.ml.localizer import (
    LocalizedBuilding,
    LocalizerNotAvailableError,
    UnavailableBuildingLocalizer,
)
from app.ml.model import ModelNotAvailableError, RawDetection
from app.ml.pipeline import TwoStageDamageModel
from app.ml.schemas import DamageClass, ModelStatus
from app.ml.spatial import BoundingBox


class _StubLocalizer:
    def __init__(self, boxes: list[BoundingBox]) -> None:
        self._boxes = boxes
        self.load_called = False

    def load(self) -> None:
        self.load_called = True

    def locate(self, image: Image.Image) -> list[LocalizedBuilding]:
        return [LocalizedBuilding(bounding_box=box) for box in self._boxes]

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=True, model_name="stub-localizer", model_version="1", device="cpu"
        )


class _StubClassifier:
    def __init__(self) -> None:
        self.classified_crops: list[Image.Image] = []
        self.load_called = False

    def load(self) -> None:
        self.load_called = True

    def classify(self, crop: Image.Image) -> RawDetection:
        self.classified_crops.append(crop)
        return RawDetection(damage_class=DamageClass.MINOR, confidence=0.42)

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=True, model_name="stub-classifier", model_version="1", device="cpu"
        )


def test_predict_raises_model_not_available_when_localizer_unavailable() -> None:
    model = TwoStageDamageModel(
        localizer=UnavailableBuildingLocalizer(), classifier=_StubClassifier()
    )

    with pytest.raises(ModelNotAvailableError):
        model.predict(Image.new("RGB", (100, 100)))


def test_localizer_not_available_error_is_normalized() -> None:
    """LocalizerNotAvailableError must not leak past predict() unchanged —
    callers relying on DamageModel's documented contract only need to
    catch ModelNotAvailableError, regardless of which internal stage
    failed, and the message should still say which stage did."""
    model = TwoStageDamageModel(
        localizer=UnavailableBuildingLocalizer(), classifier=_StubClassifier()
    )

    with pytest.raises(ModelNotAvailableError) as exc_info:
        model.predict(Image.new("RGB", (100, 100)))

    assert not isinstance(exc_info.value, LocalizerNotAvailableError)
    assert "Stage 1" in str(exc_info.value)


def test_predict_crops_and_classifies_each_located_building() -> None:
    boxes = [
        BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10),
        BoundingBox(x_min=20, y_min=20, x_max=40, y_max=40),
    ]
    localizer = _StubLocalizer(boxes)
    classifier = _StubClassifier()
    model = TwoStageDamageModel(localizer=localizer, classifier=classifier)
    image = Image.new("RGB", (100, 100))

    detections = model.predict(image)

    assert len(detections) == 2
    assert len(classifier.classified_crops) == 2
    # The classifier only ever sees crops, not the whole image.
    assert classifier.classified_crops[0].size == (10, 10)
    assert classifier.classified_crops[1].size == (20, 20)


def test_predict_attaches_the_located_bounding_box_to_each_detection() -> None:
    box = BoundingBox(x_min=5, y_min=5, x_max=15, y_max=25)
    model = TwoStageDamageModel(localizer=_StubLocalizer([box]), classifier=_StubClassifier())

    detections = model.predict(Image.new("RGB", (100, 100)))

    assert detections[0].bounding_box == box
    assert detections[0].damage_class == DamageClass.MINOR
    assert detections[0].confidence == 0.42


def test_predict_with_no_located_buildings_returns_empty_list() -> None:
    model = TwoStageDamageModel(localizer=_StubLocalizer([]), classifier=_StubClassifier())

    detections = model.predict(Image.new("RGB", (100, 100)))

    assert detections == []


def test_load_loads_both_stages() -> None:
    localizer = _StubLocalizer([])
    classifier = _StubClassifier()
    model = TwoStageDamageModel(localizer=localizer, classifier=classifier)

    model.load()

    assert localizer.load_called is True
    assert classifier.load_called is True


def test_health_is_loaded_only_when_both_stages_are() -> None:
    model = TwoStageDamageModel(localizer=_StubLocalizer([]), classifier=_StubClassifier())

    assert model.health().model_loaded is True


def test_health_is_not_loaded_when_localizer_is_unavailable() -> None:
    model = TwoStageDamageModel(
        localizer=UnavailableBuildingLocalizer(), classifier=_StubClassifier()
    )

    assert model.health().model_loaded is False
