"""End-to-end pipeline test: Image -> Preprocessor -> Model -> Postprocessor.

With today's only model (`UnavailableDamageModel`), the pipeline must raise
rather than return a result — confirming the whole chain never fabricates
an analysis, not just the model in isolation.
"""

import io
from uuid import uuid4

import pytest
from PIL import Image

from app.core.config import Settings
from app.ml.inference import DamageInferenceEngine
from app.ml.model import ModelNotAvailableError, ModelStatus, RawDetection, UnavailableDamageModel
from app.ml.postprocessing import PostprocessingError
from app.ml.preprocessing import ImageDimensionsExceededError, InvalidImageError
from app.ml.schemas import DamageClass


def _image_bytes(size: tuple[int, int] = (16, 16)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size).save(buffer, format="PNG")
    return buffer.getvalue()


class _InvalidDetectionModel:
    """Returns a detection with a confidence outside [0, 1] — an
    obviously-invalid model output that must surface as
    `PostprocessingError`, not silently pass through or crash
    unpredictably."""

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        return [RawDetection(damage_class=DamageClass.MINOR, confidence=1.5)]

    def health(self) -> ModelStatus:
        return ModelStatus(model_loaded=True, model_name="broken", model_version="1", device="cpu")


def test_analyze_raises_when_no_model_is_available() -> None:
    engine = DamageInferenceEngine(model=UnavailableDamageModel(Settings()))

    with pytest.raises(ModelNotAvailableError):
        engine.analyze(uuid4(), _image_bytes())


def test_analyze_rejects_invalid_image_before_reaching_the_model() -> None:
    engine = DamageInferenceEngine(model=UnavailableDamageModel(Settings()))

    with pytest.raises(InvalidImageError):
        engine.analyze(uuid4(), b"not an image")


def test_analyze_with_no_max_dimension_accepts_any_size() -> None:
    """Default (no `max_image_dimension` passed) preserves prior
    behavior — most existing callers/tests never pass one."""
    engine = DamageInferenceEngine(model=UnavailableDamageModel(Settings()))

    with pytest.raises(ModelNotAvailableError):  # reaches the model, not a dimension error
        engine.analyze(uuid4(), _image_bytes((500, 500)))


def test_analyze_rejects_an_oversized_image_before_reaching_the_model() -> None:
    engine = DamageInferenceEngine(
        model=UnavailableDamageModel(Settings()), max_image_dimension=100
    )

    with pytest.raises(ImageDimensionsExceededError):
        engine.analyze(uuid4(), _image_bytes((500, 500)))


def test_analyze_wraps_a_postprocessing_failure() -> None:
    engine = DamageInferenceEngine(model=_InvalidDetectionModel())

    with pytest.raises(PostprocessingError):
        engine.analyze(uuid4(), _image_bytes())
